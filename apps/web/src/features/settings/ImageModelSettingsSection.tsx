import type { AppSettings, ImageModelTestResult } from "../../types";
import { defaultImageModel, IMAGE_MODEL_NAME } from "./settingsLogic";
import type { SettingsController } from "./useSettingsPage";

export function ImageModelSettingsSection({ ctl, settings }: { ctl: SettingsController; settings: AppSettings }) {
  const { imageModelState, setSettings } = ctl;
  const imageModel = settings.image_model ?? defaultImageModel;
  return (
    <section className="settings-section" aria-labelledby="image-model-title">
      <div className="settings-copy"><h2 id="image-model-title">场景图片</h2><p>把当前剧情变成图片。需要单独填写 OpenAI 密钥，目前支持 GPT Image 2.5 Sunburst。图片生成费用由服务商收取。</p></div>
      <form className="settings-form" onSubmit={(event) => void ctl.saveImageModel(event)}>
        <label className="field full">
          <span>服务地址</span>
          <input type="url" required disabled={imageModelState !== "idle"} value={imageModel.base_url} onChange={(event) => setSettings({ ...settings, image_model: { ...imageModel, base_url: event.target.value } })} />
          <small>请使用 OpenAI 官方服务地址：https://api.openai.com/v1。当前不支持其他图片服务。</small>
        </label>
        <label className="field"><span>模型名称</span><input readOnly value={IMAGE_MODEL_NAME} /></label>
        <label className="field">
          <span>图片服务密钥（API Key）</span>
          <input type="password" autoComplete="new-password" disabled={imageModelState !== "idle"} placeholder={imageModel.api_key_configured ? "已配置，留空保持不变" : "输入 OpenAI API Key"} value={ctl.imageApiKey} onChange={(event) => ctl.setImageApiKey(event.target.value)} />
        </label>
        <label className="field">
          <span>最长等待时间（秒）</span>
          <input type="number" min={1} max={600} value={imageModel.timeout_seconds} onChange={(event) => setSettings({ ...settings, image_model: { ...imageModel, timeout_seconds: Number(event.target.value) } })} />
          <small>图片生成可能较慢，可设置 1–600 秒的等待时间。</small>
        </label>
        {ctl.imageModelTestResult && <ImageModelTestResultPanel result={ctl.imageModelTestResult} />}
        <div className="form-actions full">
          <button className="secondary-button" type="button" disabled={imageModelState !== "idle"} onClick={() => void ctl.testImageModel()}>{imageModelState === "testing" ? "正在测试…" : "测试连接"}</button>
          <span className="cost-note">测试会检查是否能连接并使用此模型，不会生成图片。</span>
          <button className="primary-button" disabled={imageModelState !== "idle"}>{imageModelState === "saving" ? "正在保存…" : imageModelState === "saved" ? "设置已保存" : "保存图片设置"}</button>
        </div>
      </form>
    </section>
  );
}

function ImageModelTestResultPanel({ result }: { result: ImageModelTestResult }) {
  return (
    <div className={`test-result full ${result.ok ? "success" : "error"}`} role="status">
      <strong>{result.ok ? "连接测试通过" : "连接测试未通过"}</strong>
      <p>{result.ok ? "已连接 OpenAI 图片服务。测试完成后，点击“保存图片设置”保存你的配置。" : "连接未成功，请检查服务地址和密钥。"}</p>
      <div className="capabilities">
        <span>目标模型：{result.model ?? IMAGE_MODEL_NAME}</span>
        <span>模型状态：{result.model_available === true ? "可用" : result.model_available === false ? "不可用" : "尚未确认"}</span>
        {result.latency_ms !== undefined && <span>测试用时：{(result.latency_ms / 1000).toFixed(1)} 秒</span>}
        <span>测试方式：仅检查模型，不生成图片</span>
      </div>
    </div>
  );
}
