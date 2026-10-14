import { Link } from "react-router-dom";
import { Icon } from "../components/Icon";

export function AppToolbar({ context, canExport, onMenu, onNew, onImport, onExport }: {
  context: string;
  canExport: boolean;
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
        <button className="toolbar-button primary-compact" type="button" onClick={onNew}><Icon name="plus" /><span>新建存档</span></button>
        <button className="toolbar-button" type="button" onClick={onImport}><Icon name="upload" /><span>导入存档</span></button>
        <button className="toolbar-button" type="button" onClick={onExport} disabled={!canExport}><Icon name="download" /><span>导出存档</span></button>
        <Link className="toolbar-button settings-link" to="/settings"><Icon name="settings" /><span>设置</span></Link>
      </div>
    </header>
  );
}
