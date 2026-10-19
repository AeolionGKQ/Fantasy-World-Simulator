import type { AppSettings, EmbeddingModelSettings, EmbeddingModelTestResult } from "../../types";
import { defaultEmbeddingModel } from "./settingsLogic";
import { TestFailurePanel } from "./TestFailurePanel";
import type { SettingsController } from "./useSettingsPage";

/** The embeddings endpoint is entered in full; a URL not ending in /embeddings is probably a base URL. */
function looksLikeBaseUrl(url: string) {
  const trimmed = url.trim();
  return trimmed !== "" && !/\/embeddings\/?$/.test(trimmed);
}

export function EmbeddingModelSettingsSection({ ctl, settings }: { ctl: SettingsController; settings: AppSettings }) {
  const { embeddingModelState: state, setSettings } = ctl;
  const embeddingModel = settings.embedding_model ?? defaultEmbeddingModel;
  const busy = state !== "idle";
  const update = (patch: Partial<EmbeddingModelSettings>) => {
    setSettings({ ...settings, embedding_model: { ...embeddingModel, ...patch } });
    ctl.setEmbeddingModelTestResult(null); ctl.setEmbeddingTestError(null);
  };
  return (
    <section className="settings-section" id="embedding-model" aria-labelledby="embedding-model-title">
      <div className="settings-copy">
        <h2 id="embedding-model-title">嵌入模型配置</h2>
        <p>可选。连接测试通过后，长期记忆会按意思相近的程度召回，换一种说法提到旧事也能想起。未配置或暂时连不上时，自动改用关键词召回，剧情不受影响。</p>
        <p>启用后，长期记忆的内容和你每轮的行动描述会发送给这个服务。</p>
      </div>
      <form className="settings-form" onSubmit={(event) => void ctl.saveEmbeddingModel(event)}>
        <label className="field full">
          <span>接口网址</span>
          <input type="url" disabled={busy} placeholder="https://api.example.com/v1/embeddings" value={embeddingModel.base_url} onChange={(event) => update({ base_url: event.target.value })} />
          <small>请填写包含 /v1/embeddings 的完整接口网址，例如 https://api.siliconflow.cn/v1/embeddings。只支持 OpenAI 兼容的嵌入接口。</small>
          {looksLikeBaseUrl(embeddingModel.base_url) && <small className="field-warning">这个网址没有以 /embeddings 结尾，请确认填写的是完整的接口网址。</small>}
        </label>
        <label className="field">
          <span>模型名称</span>
          <input disabled={busy} placeholder="例如 BAAI/bge-m3" value={embeddingModel.model} onChange={(event) => update({ model: event.target.value })} />
          <small>建议选择支持中文的多语言嵌入模型。</small>
        </label>
        <label className="field">
          <span>服务密钥（API Key）</span>
          <input type="password" autoComplete="new-password" disabled={busy} placeholder={embeddingModel.api_key_configured ? "已配置，留空保持不变" : "输入服务商提供的密钥"} value={ctl.embeddingApiKey} onChange={(event) => { ctl.setEmbeddingApiKey(event.target.value); ctl.setEmbeddingModelTestResult(null); ctl.setEmbeddingTestError(null); }} />
        </label>
        <div className="switch-field full">
          <div><span id="embedding-enabled-label">使用向量召回</span><small>开启时按意思相近程度召回长期记忆；关闭后改用关键词召回，配置会保留，随时可以再打开。保存设置后生效。</small></div>
          <label className="switch"><input type="checkbox" aria-labelledby="embedding-enabled-label" disabled={busy} checked={embeddingModel.enabled} onChange={(event) => setSettings({ ...settings, embedding_model: { ...embeddingModel, enabled: event.target.checked } })} /><span aria-hidden="true" /></label>
        </div>
        {ctl.embeddingModelTestResult && <EmbeddingTestResultPanel result={ctl.embeddingModelTestResult} />}
        {ctl.embeddingTestError && <TestFailurePanel problem={ctl.embeddingTestError} hint="请检查接口网址、模型名称和密钥。在重新测试通过之前，长期记忆使用关键词召回。" />}
        <div className="form-actions full">
          <button className="secondary-button" type="button" disabled={busy || !embeddingModel.base_url.trim() || !embeddingModel.model.trim()} onClick={() => void ctl.testEmbeddingModel()}>{state === "testing" ? "正在测试…" : "测试连接"}</button>
          <span className="cost-note">测试会把一句短文本转换为向量，可能产生极少量费用。测试通过并保存后才会启用。</span>
          <button className="primary-button" disabled={busy}>{state === "saving" ? "正在保存…" : state === "saved" ? "设置已保存" : "保存嵌入设置"}</button>
        </div>
      </form>
    </section>
  );
}

/** A passing test; a failed one is shown by TestFailurePanel. */
function EmbeddingTestResultPanel({ result }: { result: EmbeddingModelTestResult }) {
  return (
    <div className="test-result full success" role="status">
      <strong>连接测试通过</strong>
      <p>嵌入服务可用。保存设置并打开“使用向量召回”后，长期记忆会改用向量召回。</p>
      <div className="capabilities">
        {result.model && <span>模型：{result.model}</span>}
        {result.dimensions !== undefined && <span>向量维度：{result.dimensions}</span>}
        {result.latency_ms !== undefined && <span>测试用时：{(result.latency_ms / 1000).toFixed(1)} 秒</span>}
      </div>
    </div>
  );
}
