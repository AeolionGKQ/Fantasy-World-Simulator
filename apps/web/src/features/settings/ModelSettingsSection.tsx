import { SegmentedField } from "../../components/SegmentedField";
import type { AppSettings, ModelTestResult } from "../../types";
import {
  canMutateModelSettings,
  canStartSettingRequest,
  capabilityLabel,
  modelCapabilityKey,
  thinkingCapabilityLabel,
  thinkingCapabilityMessage,
} from "./settingsLogic";
import type { SettingsController } from "./useSettingsPage";

export function ModelSettingsSection({ ctl, settings }: { ctl: SettingsController; settings: AppSettings }) {
  const { modelState, narrationState, testState, setSettings, invalidateModelTest } = ctl;
  const displayedTestResult = (ctl.testResult?.key === modelCapabilityKey(
    settings.model.protocol, settings.model.base_url, settings.model.model
  )) ? ctl.testResult.result : null;
  const canMutateModel = canMutateModelSettings(modelState, testState);
  const canSubmitSettingRequest = canStartSettingRequest(modelState, narrationState, testState);
  const feedback = ctl.structuredProbeFeedback;
  return (
    <section className="settings-section" id="story-model" aria-labelledby="model-settings-title">
      <div className="settings-copy"><h2 id="model-settings-title">剧情模型配置</h2><p>模型会扮演 GM，根据你的角色和行动讲述故事。按服务商提供的信息填写下方设置；服务地址请使用你信任的来源。</p></div>
      <form className="settings-form" onSubmit={(event) => void ctl.saveModel(event)}>
        <SegmentedField label="服务类型" value={settings.model.protocol ?? "openai"} options={[{ value: "openai", label: "OpenAI 兼容" }, { value: "anthropic", label: "Anthropic 兼容" }]} disabled={!canMutateModel} onChange={(protocol) => invalidateModelTest((model) => ({ ...model, protocol }))} />
        <p className="field-help full">按服务商的接入说明选择。Claude 官方服务选 Anthropic 兼容；其他服务请确认支持哪一种。</p>
        <label className="field full">
          <span>服务地址</span>
          <input type="url" required disabled={!canMutateModel} placeholder={settings.model.protocol === "anthropic" ? "https://api.anthropic.com/v1" : "https://api.example.com/v1"} value={settings.model.base_url} onChange={(e) => invalidateModelTest((model) => ({ ...model, base_url: e.target.value }))} />
          <small>{settings.model.protocol === "anthropic" ? "填写服务商提供的 Anthropic 兼容地址。如果服务商未特别说明，官方地址可使用上方示例。" : "填写服务商提供的 OpenAI 兼容地址。请使用 API 服务地址，不是聊天网站的网页地址。"}</small>
        </label>
        <label className="field">
          <span>模型名称</span>
          <input required disabled={!canMutateModel} placeholder="填写服务商提供的模型名称" value={settings.model.model} onChange={(e) => invalidateModelTest((model) => ({ ...model, model: e.target.value }))} />
        </label>
        <label className="field">
          <span>服务密钥（API Key）</span>
          <input type="password" disabled={!canMutateModel} autoComplete="new-password" placeholder={settings.model.api_key_configured ? "已配置，留空则保持不变" : "粘贴服务商提供的密钥"} value={ctl.apiKey} onChange={(e) => { ctl.setApiKey(e.target.value); invalidateModelTest((model) => model); }} aria-describedby="key-help" />
          <small id="key-help">密钥可在服务商账户中获取。保存后不会显示原文；更换密钥时再填写，留空会保留已有密钥。</small>
        </label>
        <label className="field">
          <span>最长等待时间（秒）</span>
          <input type="number" min={5} max={600} required disabled={!canMutateModel} value={settings.model.timeout_seconds} onChange={(e) => setSettings({ ...settings, model: { ...settings.model, timeout_seconds: Number(e.target.value) } })} />
          <small>等待 AI 回复的最长时间，范围 5–600 秒。回复较慢时可适当调高。</small>
        </label>
        <label className="field">
          <span>同时生成数量</span>
          <input type="number" min={1} max={16} required disabled={!canMutateModel} value={settings.model.max_concurrency} aria-describedby="max-concurrency-help" onChange={(e) => setSettings({ ...settings, model: { ...settings.model, max_concurrency: Number(e.target.value) } })} />
          <small id="max-concurrency-help">最多同时进行 {settings.model.max_concurrency} 次 AI 生成，默认 2。服务商只允许一次生成时，游戏会自动改为 1，并等待前一次结束。</small>
        </label>
        <div className="switch-field full">
          <div><span id="structured-output-label">规范回复格式</span><small id="structured-output-help" role="status" aria-live="polite">让 AI 按游戏需要的格式回复。默认关闭；不确定服务是否支持时，可保持关闭。开启会先测试，可能产生少量费用，关闭无需测试。支持情况：{testState === "probing" ? "正在测试" : capabilityLabel(settings.model.structured_output_capability)}。</small></div>
          <label className="switch"><input type="checkbox" aria-labelledby="structured-output-label" aria-describedby="structured-output-help" aria-busy={testState === "probing"} disabled={!canMutateModel || narrationState === "saving"} checked={settings.model.structured_output} onChange={(e) => { if (e.target.checked) void ctl.probeStructuredOutput(); else ctl.disableStructuredOutput(); }} /><span aria-hidden="true" /></label>
        </div>
        {feedback && (
          <div className={`test-result full ${feedback.kind}`} role={feedback.kind === "error" ? "alert" : "status"}>
            <strong>{feedback.kind === "success" ? "已开启规范回复格式" : "规范回复格式未开启"}</strong>
            <p>{feedback.message}</p>
          </div>
        )}
        <div className="switch-field full">
          <div><span id="model-thinking-label">生成剧情前思考</span><small>让 AI 在写剧情前先思考，等待时间可能更长。此开关用于开场和后续剧情；整理故事记忆时始终开启。{thinkingCapabilityMessage(settings.model.thinking_capability, settings.model.thinking_confidence, settings.model.thinking_strategy)}</small></div>
          <label className="switch"><input type="checkbox" aria-labelledby="model-thinking-label" disabled={!canMutateModel || settings.model.thinking_capability !== "controlled"} checked={settings.model.thinking_capability === "controlled" ? settings.model.thinking_enabled : true} onChange={(e) => setSettings({ ...settings, model: { ...settings.model, thinking_enabled: e.target.checked } })} /><span aria-hidden="true" /></label>
        </div>
        {displayedTestResult && <ModelTestResultPanel result={displayedTestResult} />}
        {settings.model.api_key_persistence === "memory_only" && <p className="warning-text full">当前环境只能临时保存密钥。重新启动游戏服务后，需要再次填写。</p>}
        <div className="form-actions full">
          <button className="secondary-button" type="button" disabled={!canSubmitSettingRequest} onClick={() => void ctl.testModel()}>{testState === "testing" ? "正在测试连接…" : "测试连接"}</button>
          <button className="secondary-button" type="button" disabled={!canSubmitSettingRequest} onClick={() => void ctl.testModel(true)}>{testState === "thinking" ? "正在测试思考…" : "测试思考"}</button>
          <span className="cost-note">先测试连接，再保存设置。思考开关需单独点击“测试思考”；测试过程中可能产生少量 AI 服务费用。</span>
          <button className="primary-button" disabled={!canSubmitSettingRequest}>{modelState === "saving" ? "正在保存…" : modelState === "saved" ? "设置已保存" : "保存模型设置"}</button>
        </div>
      </form>
    </section>
  );
}

function ModelTestResultPanel({ result }: { result: ModelTestResult }) {
  return (
    <div className={`test-result full ${result.ok ? "success" : "error"}`} role="status">
      <strong>{result.ok ? "连接测试通过" : "连接测试未通过"}</strong>
      <p>{result.ok ? "已连接当前 AI 服务。测试完成后，点击“保存模型设置”保存你的配置。" : "连接未成功，请检查服务类型、地址、模型名称和密钥。"}</p>
      <div className="capabilities">
        <span>目标模型：{result.model_available === false ? "不可用" : result.model_available === true ? "可用" : "尚未确认"}</span>
        {result.latency_ms !== undefined && <span>测试用时：{(result.latency_ms / 1000).toFixed(1)} 秒</span>}
        <span>思考：{thinkingCapabilityLabel(result.thinking_capability)}</span>
        <span>规范回复格式：{capabilityLabel(result.structured_output_capability)}</span>
      </div>
      <p>{thinkingCapabilityMessage(result.thinking_capability, result.thinking_confidence, result.thinking_strategy)}</p>
    </div>
  );
}
