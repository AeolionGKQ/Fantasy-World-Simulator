import { api, type ApiError } from "../../api";
import type { AppSettings, EmbeddingModelSettings, ImageModelSettings, ModelTestResult } from "../../types";

export type ModelState = "idle" | "saving" | "saved";
export type ModelTestState = "idle" | "testing" | "thinking" | "probing";
export type NarrationState = "idle" | "saving" | "saved";
export type ImageModelState = "idle" | "saving" | "testing" | "saved";

export const IMAGE_MODEL_NAME = "gpt-image-2.5-sunburst" as const;

/** The embedding service is optional and starts empty. */
export const defaultEmbeddingModel: EmbeddingModelSettings = {
  base_url: "",
  model: "",
  enabled: true,
  timeout_seconds: 10,
  configured: false,
  api_key_configured: false,
};

/** Values shown and submitted before the image service has ever been configured. */
export const defaultImageModel: ImageModelSettings = {
  base_url: "https://api.openai.com/v1",
  model: IMAGE_MODEL_NAME,
  timeout_seconds: 300,
  configured: false,
  api_key_configured: false,
};

export const playerAddressOptions = [
  { value: "full_name", label: "全名" },
  { value: "given_name", label: "名字" },
  { value: "second_person", label: "你" },
] as const;

export type PlayerAddress = (typeof playerAddressOptions)[number]["value"];

export function capabilityLabel(value?: "supported" | "unsupported" | "unknown") {
  return value === "supported" ? "支持" : value === "unsupported" ? "不支持" : "未测试";
}

export function thinkingCapabilityLabel(value: "controlled" | "unsupported" | "unknown") {
  return value === "controlled" ? "可设置" : value === "unsupported" ? "由服务商决定" : "未测试";
}

export function thinkingStrategyLabel(value: ModelTestResult["thinking_strategy"]) {
  const labels = { bundle: "七种兼容参数组合", enable_thinking: "enable_thinking", thinking: "thinking.type", reasoning_effort: "reasoning_effort", chat_template_kwargs: "chat_template_kwargs.enable_thinking", reasoning_enabled: "reasoning.enabled", reasoning_effort_nested: "reasoning.effort", thinking_budget: "thinking_config.thinking_budget", anthropic_adaptive: "Anthropic adaptive / disabled", anthropic_adaptive_between_tools: "Anthropic adaptive / between_tools", anthropic_enabled: "Anthropic enabled / disabled", anthropic_enabled_between_tools: "Anthropic enabled / between_tools" };
  return value ? labels[value] : "未识别";
}

export function thinkingCapabilityMessage(capability: "controlled" | "unsupported" | "unknown", confidence: "verified" | "accepted_bundle" | "unsupported" | "unknown", _strategy?: ModelTestResult["thinking_strategy"]) {
  if (capability === "unsupported") return "当前服务不支持关闭思考，将使用服务商的默认设置。";
  if (capability === "unknown") return "尚未测试。点击“测试思考”，确认是否可以设置思考开关。";
  return confidence === "accepted_bundle" ? "服务接受了思考设置，但尚未分别确认开启与关闭是否可用。" : "服务已接受思考开关设置，你可以选择开启或关闭。";
}

export function modelCapabilityKey(protocolOrBaseUrl: AppSettings["model"]["protocol"] | string, baseUrlOrModel: string, maybeModel?: string): string {
  const protocol = maybeModel === undefined ? "openai" : protocolOrBaseUrl;
  const baseUrl = maybeModel === undefined ? protocolOrBaseUrl : baseUrlOrModel;
  const model = maybeModel === undefined ? baseUrlOrModel : maybeModel;
  return `${protocol ?? "openai"}\n${(baseUrl ?? "").trim().replace(/\/+$/, "")}\n${model.trim()}`;
}

export function canMutateModelSettings(modelState: ModelState, testState: ModelTestState): boolean {
  return modelState !== "saving" && testState === "idle";
}

export function canStartSettingRequest(
  modelState: ModelState,
  narrationState: NarrationState,
  testState: ModelTestState,
): boolean {
  return modelState !== "saving" && narrationState !== "saving" && testState === "idle";
}

export function mergeSavedModelSettings(current: AppSettings, updated: AppSettings): AppSettings {
  return { ...current, model: updated.model, revision: updated.revision };
}

export function mergeSavedNarrationSettings(current: AppSettings, updated: AppSettings): AppSettings {
  return { ...current, narration: updated.narration, revision: updated.revision };
}

export function structuredOutputProbePayload(payload: Parameters<typeof api.testModel>[0]): Parameters<typeof api.testModel>[0] {
  return { ...payload, structured_output: false, probe_structured_output: true };
}

export function isCurrentModelTestResponse(current: AppSettings | null, requestedKey: string, requestToken: number, currentToken: number): boolean {
  return requestToken === currentToken && current !== null && modelCapabilityKey(current.model.protocol, current.model.base_url, current.model.model) === requestedKey;
}

export function resetStructuredOutputCapability(current: AppSettings | null, message?: string): AppSettings | null {
  if (!current) return current;
  return { ...current, model: { ...current.model, structured_output: false,
    structured_output_capability: "unknown", structured_output_message: message,
    structured_output_probed_at: null, structured_output_probe_token: undefined } };
}

export function invalidateModelCapabilities(model: AppSettings["model"]): AppSettings["model"] {
  return { ...model, structured_output: false, structured_output_capability: "unknown",
    structured_output_message: "规范回复格式尚未测试。", structured_output_probed_at: null,
    structured_output_probe_token: undefined,
    thinking_enabled: true, thinking_capability: "unknown", thinking_strategy: null,
    thinking_confidence: "unknown", thinking_message: "思考开关尚未测试，请点击“测试思考”。",
    thinking_probed_at: null };
}

export function isStructuredOutputError(error: ApiError): boolean {
  const text = [error.problem.code, error.problem.message, ...Object.keys(error.problem.field_errors ?? {})].join(" ");
  return /structured[_ ]?output|response[_ ]?format/i.test(text);
}

export function mergeModelTestCapability(
  current: AppSettings | null,
  requestedKey: string,
  result: ModelTestResult,
  structuredOutputProbe = false,
): AppSettings | null {
  if (!current || modelCapabilityKey(current.model.protocol, current.model.base_url, current.model.model) !== requestedKey) {
    return current;
  }
  const reportedCapability = result.structured_output_capability;
  const capability = !structuredOutputProbe && (!reportedCapability || reportedCapability === "unknown")
    ? current.model.structured_output_capability
    : reportedCapability ?? "unknown";
  return { ...current, model: { ...current.model,
    thinking_capability: result.thinking_capability,
    thinking_strategy: result.thinking_strategy,
    thinking_confidence: result.thinking_confidence,
    thinking_message: result.thinking_message,
    thinking_probed_at: result.thinking_probed_at,
    structured_output: structuredOutputProbe ? capability === "supported" :
      current.model.structured_output && capability === "supported",
    structured_output_capability: capability,
    structured_output_message: result.structured_output_message ?? current.model.structured_output_message,
    structured_output_probed_at: result.structured_output_probed_at ?? current.model.structured_output_probed_at,
    structured_output_probe_token: structuredOutputProbe ?
      (capability === "supported" ? result.structured_output_probe_token : undefined) :
      current.model.structured_output_probe_token } };
}
