import { Link } from "react-router-dom";
import { Icon } from "../components/Icon";

export function AppToolbar({ context, canExport, settingsActive, settingsAttention, onMenu, onNew, onImport, onExport }: {
  context: string;
  canExport: boolean;
  settingsActive: boolean;
  /** Set when the story AI needs the player's attention; shows a dot on the settings button. */
  settingsAttention: "not_configured" | "failed" | null;
  onMenu: () => void;
  onNew: () => void;
  onImport: () => void;
  onExport: () => void;
}) {
  return (
    <header className="toolbar">
      <button className="icon-button mobile-menu" type="button" onClick={onMenu} aria-label="打开存档列表"><Icon name="menu" /></button>
      <div className="toolbar-context">
        <span>{context}</span>
      </div>
      <div className="toolbar-actions">
        <button className="toolbar-button" type="button" onClick={onNew}><Icon name="plus" /><span>新建存档</span></button>
        <button className="toolbar-button" type="button" onClick={onImport}><Icon name="upload" /><span>导入存档</span></button>
        <button className="toolbar-button" type="button" onClick={onExport} disabled={!canExport}><Icon name="download" /><span>导出存档</span></button>
        <Link viewTransition className={`toolbar-button settings-link ${settingsActive ? "active" : ""}`} to="/settings" aria-current={settingsActive ? "page" : undefined}
          aria-label={settingsAttention ? `设置（剧情 AI ${settingsAttention === "failed" ? "连接失败" : "未配置"}，需要处理）` : "设置"}>
          <Icon name="settings" /><span>设置</span>
          {settingsAttention && <span className="attention-dot" aria-hidden="true" />}
        </Link>
      </div>
    </header>
  );
}
