import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { api, asApiError } from "../../api";
import { useNotify } from "../../app/notice";
import type { ShellActions } from "../../app/shellActions";
import { playerProblemMessage } from "../../playerCopy";
import type { ApiProblem, AppSettings, EmbeddingModelTestResult, ImageModelTestResult, ModelTestResult } from "../../types";
import {
  canStartSettingRequest,
  defaultEmbeddingModel,
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
  const [embeddingApiKey, setEmbeddingApiKey] = useState("");
  const [embeddingModelState, setEmbeddingModelState] = useState<ImageModelState>("idle");
  const [embeddingModelTestResult, setEmbeddingModelTestResult] = useState<EmbeddingModelTestResult | null>(null);
  const [testState, setTestState] = useState<ModelTestState>("idle");
  const [testResult, setTestResult] = useState<{ key: string; result: ModelTestResult } | null>(null);
  // Failed connection tests are shown next to each section's test button, like a passing result.
  const [testError, setTestError] = useState<{ key: string; problem: ApiProblem } | null>(null);
  const [imageTestError, setImageTestError] = useState<ApiProblem | null>(null);
  const [embeddingTestError, setEmbeddingTestError] = useState<ApiProblem | null>(null);
  const [structuredProbeFeedback, setStructuredProbeFeedback] = useState<StructuredProbeFeedback | null>(null);
  const notify = useNotify();
  /** A failed save goes to the notice bar, named by its section since the bar is shared. */
  const saveFailed = (section: string, reason: unknown) => {
    const problem = asApiError(reason).problem;
    notify({ tone: "error", text: `${section}未能保存：${playerProblemMessage(problem)}`, traceId: problem.trace_id });
  };
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
    setModelState("saving"); setTestResult(null); setStructuredProbeFeedback(null);
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
      saveFailed("剧情模型配置", reason);
      if (isStructuredOutputError(apiError)) {
        setSettings((current) => resetStructuredOutputCapability(current, apiError.message));
      }
      setModelState("idle");
    } finally {
      settingRequestInFlight.current = false;
      void actions.refreshServiceStatus();
    }
  };

  const testModel = async (forceThinkingProbe = false) => {
    if (!settings || !canStartSettingRequest(modelState, narrationState, testState) || !beginSettingRequest()) return;
    const requestedKey = modelCapabilityKey(settings.model.protocol, settings.model.base_url, settings.model.model);
    const requestToken = ++testRequestToken.current;
    setTestState(forceThinkingProbe ? "thinking" : "testing"); setTestResult(null); setTestError(null); setStructuredProbeFeedback(null);
    try {
      const result = await api.testModel({ ...modelPayload(), force_thinking_probe: forceThinkingProbe });
      if (!isCurrentModelTestResponse(settings, requestedKey, requestToken, testRequestToken.current)) return;
      setTestResult({ key: requestedKey, result });
      setSettings((current) => {
        if (!isCurrentModelTestResponse(current, requestedKey, requestToken, testRequestToken.current)) return current;
        return mergeModelTestCapability(current, requestedKey, result);
      });
    } catch (reason) {
      if (requestToken === testRequestToken.current) setTestError({ key: requestedKey, problem: asApiError(reason).problem });
    }
    finally {
      settingRequestInFlight.current = false;
      if (requestToken === testRequestToken.current) setTestState("idle");
      void actions.refreshServiceStatus();
    }
  };

  const probeStructuredOutput = async () => {
    if (!settings || !canStartSettingRequest(modelState, narrationState, testState) || !beginSettingRequest()) return;
    const requestedKey = modelCapabilityKey(settings.model.protocol, settings.model.base_url, settings.model.model);
    const requestToken = ++testRequestToken.current;
    setTestState("probing"); setTestResult(null); setTestError(null); setStructuredProbeFeedback(null);
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
      setStructuredProbeFeedback({ kind: "error", message: `${playerProblemMessage(apiError.problem)} 此选项保持关闭，你仍可使用普通回复继续游戏。` });
    } finally {
      settingRequestInFlight.current = false;
      if (requestToken === testRequestToken.current) setTestState("idle");
      void actions.refreshServiceStatus();
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
    setNarrationState("saving"); 
    try {
      const updated = await api.updateNarration(settings.narration, settings.revision, crypto.randomUUID());
      setSettings((current) => current ? mergeSavedNarrationSettings(current, updated) : current);
      await actions.refreshSaves();
      setNarrationState("saved");
      window.setTimeout(() => setNarrationState("idle"), 2200);
    } catch (reason) {
      saveFailed("叙事设置", reason); setNarrationState("idle");
    } finally {
      settingRequestInFlight.current = false;
    }
  };

  const saveImageModel = async (event: FormEvent) => {
    event.preventDefault();
    if (!settings || imageModelState !== "idle") return;
    setImageModelState("saving"); setImageModelTestResult(null);
    try {
      const imageModel = settings.image_model ?? defaultImageModel;
      const updated = await api.updateImageModel({ base_url: imageModel.base_url,
        model: IMAGE_MODEL_NAME, timeout_seconds: imageModel.timeout_seconds,
        ...(imageApiKey ? { api_key: imageApiKey } : {}) }, settings.revision, crypto.randomUUID());
      setSettings(updated); setImageApiKey(""); setImageModelState("saved");
      window.setTimeout(() => setImageModelState("idle"), 1800);
    } catch (reason) { saveFailed("生图模型配置", reason); setImageModelState("idle"); }
    void actions.refreshServiceStatus();
  };

  const testImageModel = async () => {
    if (!settings || imageModelState !== "idle") return;
    setImageModelState("testing"); setImageModelTestResult(null); setImageTestError(null);
    try {
      const imageModel = settings.image_model ?? defaultImageModel;
      const result = await api.testImageModel({ base_url: imageModel.base_url,
        model: IMAGE_MODEL_NAME, timeout_seconds: imageModel.timeout_seconds,
        ...(imageApiKey ? { api_key: imageApiKey } : {}) });
      setImageModelTestResult(result);
    } catch (reason) { setImageTestError(asApiError(reason).problem); }
    finally { setImageModelState("idle"); void actions.refreshServiceStatus(); }
  };

  const embeddingPayload = () => {
    const embeddingModel = settings?.embedding_model ?? defaultEmbeddingModel;
    return { base_url: embeddingModel.base_url.trim(), model: embeddingModel.model.trim(),
      ...(embeddingApiKey ? { api_key: embeddingApiKey } : {}) };
  };

  const saveEmbeddingModel = async (event: FormEvent) => {
    event.preventDefault();
    if (!settings || embeddingModelState !== "idle") return;
    setEmbeddingModelState("saving"); 
    try {
      const enabled = (settings.embedding_model ?? defaultEmbeddingModel).enabled;
      const updated = await api.updateEmbeddingModel({ ...embeddingPayload(), enabled }, settings.revision, crypto.randomUUID());
      setSettings(updated); setEmbeddingApiKey(""); setEmbeddingModelState("saved");
      window.setTimeout(() => setEmbeddingModelState("idle"), 1800);
    } catch (reason) { saveFailed("嵌入模型配置", reason); setEmbeddingModelState("idle"); }
    void actions.refreshServiceStatus();
  };

  const testEmbeddingModel = async () => {
    if (!settings || embeddingModelState !== "idle") return;
    setEmbeddingModelState("testing"); setEmbeddingModelTestResult(null); setEmbeddingTestError(null);
    try {
      setEmbeddingModelTestResult(await api.testEmbeddingModel(embeddingPayload()));
    } catch (reason) {
      setEmbeddingTestError(asApiError(reason).problem);
    } finally { setEmbeddingModelState("idle"); void actions.refreshServiceStatus(); }
  };

  return {
    settings, setSettings, loading, error, load,
    apiKey, setApiKey, imageApiKey, setImageApiKey,
    modelState, narrationState, imageModelState, testState,
    testResult, imageModelTestResult, structuredProbeFeedback,
    testError, imageTestError, embeddingTestError, setEmbeddingTestError,
    saveModel, testModel, probeStructuredOutput, disableStructuredOutput, invalidateModelTest,
    saveNarration, saveImageModel, testImageModel,
    embeddingApiKey, setEmbeddingApiKey, embeddingModelState, embeddingModelTestResult,
    setEmbeddingModelTestResult, saveEmbeddingModel, testEmbeddingModel,
  };
}

export type SettingsController = ReturnType<typeof useSettingsPage>;
