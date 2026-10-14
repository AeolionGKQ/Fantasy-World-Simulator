import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { api, asApiError } from "../../api";
import type { ShellActions } from "../../app/shellActions";
import { playerProblemMessage } from "../../playerCopy";
import type { AppSettings, ImageModelTestResult, ModelTestResult } from "../../types";
import {
  canStartSettingRequest,
  defaultImageModel,
  IMAGE_MODEL_NAME,
  invalidateModelCapabilities,
  isCurrentModelTestResponse,
  isStructuredOutputError,
  mergeModelTestCapability,
  mergeSavedModelSettings,
  mergeSavedNarrationSettings,
  modelCapabilityKey,
  resetStructuredOutputCapability,
  structuredOutputProbePayload,
  type ImageModelState,
  type ModelState,
  type ModelTestState,
  type NarrationState,
} from "./settingsLogic";

export type StructuredProbeFeedback = { kind: "success" | "error"; message: string };

/** All state and requests of the settings page; the three form sections only render it. */
export function useSettingsPage(actions: ShellActions) {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [imageApiKey, setImageApiKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [modelState, setModelState] = useState<ModelState>("idle");
  const [narrationState, setNarrationState] = useState<NarrationState>("idle");
  const [imageModelState, setImageModelState] = useState<ImageModelState>("idle");
  const [imageModelTestResult, setImageModelTestResult] = useState<ImageModelTestResult | null>(null);
  const [testState, setTestState] = useState<ModelTestState>("idle");
  const [testResult, setTestResult] = useState<{ key: string; result: ModelTestResult } | null>(null);
  const [structuredProbeFeedback, setStructuredProbeFeedback] = useState<StructuredProbeFeedback | null>(null);
  const [actionError, setActionError] = useState("");
  const testRequestToken = useRef(0);
  const settingRequestInFlight = useRef(false);

  const beginSettingRequest = () => {
    if (settingRequestInFlight.current) return false;
    settingRequestInFlight.current = true;
    return true;
  };

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setSettings(await api.getSettings()); }
    catch (reason) { setError(reason); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const modelPayload = () => {
    if (!settings) throw new Error("设置尚未载入");
    const model = {
      protocol: settings.model.protocol ?? "openai",
      base_url: settings.model.base_url,
      model: settings.model.model,
      timeout_seconds: settings.model.timeout_seconds,
      structured_output: settings.model.structured_output && settings.model.structured_output_capability === "supported",
      thinking_enabled: settings.model.thinking_enabled,
      max_concurrency: settings.model.max_concurrency,
      ...(apiKey ? { api_key: apiKey } : {}),
    };
    return model;
  };

  const saveModel = async (event: FormEvent) => {
    event.preventDefault();
    if (!settings || !canStartSettingRequest(modelState, narrationState, testState) || !beginSettingRequest()) return;
    const requestedKey = modelCapabilityKey(settings.model.protocol, settings.model.base_url, settings.model.model);
    setModelState("saving"); setActionError(""); setTestResult(null); setStructuredProbeFeedback(null);
    try {
      const updated = await api.updateModel({ ...modelPayload(),
        ...(settings.model.structured_output_probe_token ? {
          structured_output_probe_token: settings.model.structured_output_probe_token,
        } : {}) }, settings.revision, crypto.randomUUID());
      setSettings((current) => {
        if (!current || modelCapabilityKey(current.model.protocol, current.model.base_url, current.model.model) !== requestedKey) return current;
        return mergeSavedModelSettings(current, updated);
      });
      setApiKey(""); setModelState("saved");
      window.setTimeout(() => setModelState("idle"), 2200);
    } catch (reason) {
      const apiError = asApiError(reason);
      setActionError(playerProblemMessage(apiError.problem));
      if (isStructuredOutputError(apiError)) {
        setSettings((current) => resetStructuredOutputCapability(current, apiError.message));
      }
      setModelState("idle");
    } finally {
      settingRequestInFlight.current = false;
    }
  };

  const testModel = async (forceThinkingProbe = false) => {
    if (!settings || !canStartSettingRequest(modelState, narrationState, testState) || !beginSettingRequest()) return;
    const requestedKey = modelCapabilityKey(settings.model.protocol, settings.model.base_url, settings.model.model);
    const requestToken = ++testRequestToken.current;
    setTestState(forceThinkingProbe ? "thinking" : "testing"); setActionError(""); setTestResult(null); setStructuredProbeFeedback(null);
    try {
      const result = await api.testModel({ ...modelPayload(), force_thinking_probe: forceThinkingProbe });
      if (!isCurrentModelTestResponse(settings, requestedKey, requestToken, testRequestToken.current)) return;
      setTestResult({ key: requestedKey, result });
      setSettings((current) => {
        if (!isCurrentModelTestResponse(current, requestedKey, requestToken, testRequestToken.current)) return current;
        return mergeModelTestCapability(current, requestedKey, result);
      });
    } catch (reason) {
      if (requestToken === testRequestToken.current) setActionError(playerProblemMessage(asApiError(reason).problem));
    }
    finally {
      settingRequestInFlight.current = false;
      if (requestToken === testRequestToken.current) setTestState("idle");
    }
  };

  const probeStructuredOutput = async () => {
    if (!settings || !canStartSettingRequest(modelState, narrationState, testState) || !beginSettingRequest()) return;
    const requestedKey = modelCapabilityKey(settings.model.protocol, settings.model.base_url, settings.model.model);
    const requestToken = ++testRequestToken.current;
    setTestState("probing"); setActionError(""); setTestResult(null); setStructuredProbeFeedback(null);
    setSettings((current) => resetStructuredOutputCapability(current, "正在测试是否支持规范回复格式…"));
    try {
      const result = await api.testModel(structuredOutputProbePayload(modelPayload()));
      if (!isCurrentModelTestResponse(settings, requestedKey, requestToken, testRequestToken.current)) return;
      setTestResult({ key: requestedKey, result });
      setSettings((current) => {
        if (!isCurrentModelTestResponse(current, requestedKey, requestToken, testRequestToken.current)) return current;
        return mergeModelTestCapability(current, requestedKey, result, true);
      });
      if (result.structured_output_capability === "supported") {
        setStructuredProbeFeedback({ kind: "success", message: "当前服务支持规范回复格式。点击“保存模型设置”后生效。" });
      } else {
        setStructuredProbeFeedback({ kind: "error", message: "当前服务未通过格式测试，此选项保持关闭。你仍可使用普通回复继续游戏。" });
      }
    } catch (reason) {
      if (requestToken !== testRequestToken.current) return;
      const apiError = asApiError(reason);
      setSettings((current) => resetStructuredOutputCapability(current, apiError.message));
      setActionError(playerProblemMessage(apiError.problem));
    } finally {
      settingRequestInFlight.current = false;
      if (requestToken === testRequestToken.current) setTestState("idle");
    }
  };

  /** Turning the structured-output switch off needs no probe: drop pending results and reset the capability. */
  const disableStructuredOutput = () => {
    testRequestToken.current += 1;
    setSettings((current) => resetStructuredOutputCapability(current, "已关闭规范回复格式。"));
    setTestResult(null); setStructuredProbeFeedback(null); setTestState("idle");
  };

  const invalidateModelTest = (update: (model: AppSettings["model"]) => AppSettings["model"]) => {
    testRequestToken.current += 1;
    setSettings((current) => current ? { ...current, model: invalidateModelCapabilities(update(current.model)) } : current);
    setTestResult(null); setStructuredProbeFeedback(null); setTestState("idle");
  };

  const saveNarration = async (event: FormEvent) => {
    event.preventDefault();
    if (!settings || !canStartSettingRequest(modelState, narrationState, testState) || !beginSettingRequest()) return;
    setNarrationState("saving"); setActionError("");
    try {
      const updated = await api.updateNarration(settings.narration, settings.revision, crypto.randomUUID());
      setSettings((current) => current ? mergeSavedNarrationSettings(current, updated) : current);
      await actions.refreshSaves();
      setNarrationState("saved");
      window.setTimeout(() => setNarrationState("idle"), 2200);
    } catch (reason) {
      setActionError(playerProblemMessage(asApiError(reason).problem)); setNarrationState("idle");
    } finally {
      settingRequestInFlight.current = false;
    }
  };

  const saveImageModel = async (event: FormEvent) => {
    event.preventDefault();
    if (!settings || imageModelState !== "idle") return;
    setImageModelState("saving"); setActionError(""); setImageModelTestResult(null);
    try {
      const imageModel = settings.image_model ?? defaultImageModel;
      const updated = await api.updateImageModel({ base_url: imageModel.base_url,
        model: IMAGE_MODEL_NAME, timeout_seconds: imageModel.timeout_seconds,
        ...(imageApiKey ? { api_key: imageApiKey } : {}) }, settings.revision, crypto.randomUUID());
      setSettings(updated); setImageApiKey(""); setImageModelState("saved");
      window.setTimeout(() => setImageModelState("idle"), 1800);
    } catch (reason) { setActionError(playerProblemMessage(asApiError(reason).problem)); setImageModelState("idle"); }
  };

  const testImageModel = async () => {
    if (!settings || imageModelState !== "idle") return;
    setImageModelState("testing"); setActionError(""); setImageModelTestResult(null);
    try {
      const imageModel = settings.image_model ?? defaultImageModel;
      const result = await api.testImageModel({ base_url: imageModel.base_url,
        model: IMAGE_MODEL_NAME, timeout_seconds: imageModel.timeout_seconds,
        ...(imageApiKey ? { api_key: imageApiKey } : {}) });
      setImageModelTestResult(result);
    } catch (reason) { setActionError(playerProblemMessage(asApiError(reason).problem)); }
    finally { setImageModelState("idle"); }
  };

  return {
    settings, setSettings, loading, error, load, actionError,
    apiKey, setApiKey, imageApiKey, setImageApiKey,
    modelState, narrationState, imageModelState, testState,
    testResult, imageModelTestResult, structuredProbeFeedback,
    saveModel, testModel, probeStructuredOutput, disableStructuredOutput, invalidateModelTest,
    saveNarration, saveImageModel, testImageModel,
  };
}

export type SettingsController = ReturnType<typeof useSettingsPage>;
