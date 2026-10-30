import { SegmentedField } from "../../components/SegmentedField";
import type { AppSettings } from "../../types";
import { canStartSettingRequest, playerAddressOptions } from "./settingsLogic";
import type { SettingsController } from "./useSettingsPage";

export function NarrationSettingsSection({ ctl, settings }: { ctl: SettingsController; settings: AppSettings }) {
  const { narrationState, setSettings } = ctl;
  const saving = narrationState === "saving";
  const update = <K extends keyof AppSettings["narration"]>(key: K, value: AppSettings["narration"][K]) =>
    setSettings((current) => current ? { ...current, narration: { ...current.narration, [key]: value } } : current);
  return (
    <section className="settings-section" id="narration" aria-labelledby="narration-title">
      <div className="settings-copy"><h2 id="narration-title">叙事设置</h2><p>选择你喜欢的故事节奏和描写方式。保存后会应用到全部存档。</p></div>
      <form className="settings-form narration" onSubmit={(event) => void ctl.saveNarration(event)}>
        <SegmentedField label="剧情推进速度" value={settings.narration.pace} options={[{ value: "slow", label: "慢速" }, { value: "fast", label: "快速" }, { value: "dynamic", label: "动态" }]} disabled={saving} onChange={(pace) => update("pace", pace)} />
        <p className="field-help full">慢速：每轮推进较少，方便细致互动。快速：概括普通赶路、等待等过程。动态：按场景调整节奏。重要决定仍由你来做。</p>
        <SegmentedField label="叙事倾向" value={settings.narration.tendency} options={[{ value: "casual", label: "日常" }, { value: "balanced", label: "平衡" }, { value: "combat", label: "战斗" }]} disabled={saving} onChange={(tendency) => update("tendency", tendency)} />
        <p className="field-help full">日常偏向旅行、交友和生活；战斗更容易遇到冒险与危险；平衡兼顾两者。日常模式也不会消除危险地区的风险。</p>
        <SegmentedField label="内容详细度" value={settings.narration.detail} options={[{ value: "concise", label: "简洁" }, { value: "standard", label: "标准" }, { value: "detailed", label: "详细" }]} disabled={saving} onChange={(detail) => update("detail", detail)} />
        <p className="field-help full">简洁着重交代发生了什么；标准保留适量场景描写；详细会展开环境、动作和对话。详细度不会改变每轮推进的剧情多少。</p>
        <SegmentedField label="GM 对角色的称呼" value={settings.narration.player_address} options={playerAddressOptions} disabled={saving} onChange={(playerAddress) => update("player_address", playerAddress)} />
        <p className="field-help full">选择 GM 在剧情中如何称呼你：全名如“菲亚·维洛拉”，名字如“菲亚”，或直接用“你”。故事中的人物仍会根据关系和场合使用各自的称呼。</p>
        <label className="field full">
          <span>破甲提示词 <small>可选</small></span>
          <textarea maxLength={20000} disabled={saving} value={settings.narration.jailbreak_prompt} onChange={(event) => update("jailbreak_prompt", event.target.value)} />
          <small>填写的内容会原样放入每轮剧情生成，以及故事弧生成和压缩时发给模型的提示词中；留空则不发送任何内容。</small>
          <small className="field-warning">请谨慎设置此项。如果设置后出现频繁生成失败或其他问题，请清空此项后重试。</small>
        </label>
        <div className="form-actions full">
          <button className="primary-button" disabled={!canStartSettingRequest(ctl.modelState, narrationState, ctl.testState)}>{narrationState === "saving" ? "正在保存…" : narrationState === "saved" ? "偏好已保存" : "保存叙事设置"}</button>
        </div>
      </form>
    </section>
  );
}
