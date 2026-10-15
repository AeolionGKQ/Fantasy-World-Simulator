import type { ShellActions } from "../../app/shellActions";
import { ErrorPanel } from "../../components/ErrorPanel";
import { LoadingPanel } from "../../components/LoadingPanel";
import { ImageModelSettingsSection } from "./ImageModelSettingsSection";
import { ModelSettingsSection } from "./ModelSettingsSection";
import { NarrationSettingsSection } from "./NarrationSettingsSection";
import { useSettingsPage } from "./useSettingsPage";

export function SettingsPage({ actions }: { actions: ShellActions }) {
  const ctl = useSettingsPage(actions);
  const { settings } = ctl;
  if (ctl.loading) return <div className="page settings-page page-loading" key="loading"><LoadingPanel label="正在载入设置" /></div>;
  if (ctl.error || !settings) return <div className="page settings-page page-enter" key="error"><ErrorPanel playerFacing error={ctl.error} onRetry={() => void ctl.load()} title="无法载入设置" /></div>;
  return (
    <div className="page settings-page page-enter" key="ready">
      <header className="page-header"><div><h1>设置</h1><p>在这里连接 AI 服务，调整故事节奏和描写方式。设置保存在本机，导出的存档不包含服务密钥。</p></div></header>
      {ctl.actionError && <div className="inline-error" role="alert">{ctl.actionError}</div>}
      <ModelSettingsSection ctl={ctl} settings={settings} />
      <ImageModelSettingsSection ctl={ctl} settings={settings} />
      <NarrationSettingsSection ctl={ctl} settings={settings} />
    </div>
  );
}
