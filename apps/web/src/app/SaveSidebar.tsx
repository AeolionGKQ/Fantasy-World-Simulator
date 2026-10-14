import { Link } from "react-router-dom";
import { ErrorPanel } from "../components/ErrorPanel";
import { Icon } from "../components/Icon";
import { LoadingPanel } from "../components/LoadingPanel";
import { StatusDot } from "../components/StatusDot";
import { isActiveJobStatus, jobLabel, phaseLabel, saveRoute, type SaveSummary } from "../types";

export function SaveSidebar({ saves, currentId, loading, loadError, open, settingsActive, onClose, onRetry, onNew, onRename, onDelete }: {
  saves: SaveSummary[];
  currentId: string | undefined;
  loading: boolean;
  loadError: unknown;
  open: boolean;
  settingsActive: boolean;
  onClose: () => void;
  onRetry: () => void;
  onNew: () => void;
  onRename: (save: SaveSummary) => void;
  onDelete: (save: SaveSummary) => void;
}) {
  return (
    <aside className={`sidebar ${open ? "open" : ""}`} aria-label="存档列表">
      <div className="brand-block">
        <Link to="/" className="brand-mark" aria-label="Fantasy Simulator 首页"><span>F</span></Link>
        <div><strong>Fantasy Simulator</strong><small>冒险档案</small></div>
        <button className="icon-button sidebar-close" type="button" onClick={onClose} aria-label="关闭存档列表"><Icon name="close" /></button>
      </div>
      <div className="sidebar-title"><span>存档</span><span>{saves.length}</span></div>
      <nav className="save-list" aria-label="已有存档">
        {loading && <LoadingPanel label="正在载入存档" />}
        {!loading && Boolean(loadError) && <ErrorPanel playerFacing error={loadError} onRetry={onRetry} title="无法载入存档" />}
        {!loading && !loadError && saves.length === 0 && (
          <div className="sidebar-empty"><p>还没有冒险档案。</p><button type="button" className="text-button" onClick={onNew}>创建第一个存档</button></div>
        )}
        {saves.map((save) => (
          <div className={`save-row ${save.id === currentId ? "active" : ""}`} key={save.id}>
            <Link to={saveRoute(save)} className="save-link" aria-current={save.id === currentId ? "page" : undefined}>
              <span className="save-name">{save.name}</span>
              <span className="save-meta"><span>{phaseLabel[save.phase]}</span>{save.character_name && <span>{save.character_name}</span>}</span>
              {save.generation && isActiveJobStatus(save.generation.status) && (
                <span className="generation-mini"><StatusDot state="busy" />{jobLabel[save.generation.status]}</span>
              )}
            </Link>
            <div className="save-actions">
              <button type="button" className="icon-button small" onClick={() => onRename(save)} aria-label={`重命名 ${save.name}`}><Icon name="edit" /></button>
              <button type="button" className="icon-button small danger-text" onClick={() => onDelete(save)} aria-label={`删除 ${save.name}`}><Icon name="trash" /></button>
            </div>
          </div>
        ))}
      </nav>
      <div className="sidebar-footer">
        <Link className={settingsActive ? "sidebar-settings active" : "sidebar-settings"} to="/settings"><Icon name="settings" /><span>设置</span></Link>
        <div className="connection-line"><StatusDot state={loadError ? "offline" : "online"} />{loadError ? "游戏服务未连接" : "游戏服务已连接"}</div>
      </div>
    </aside>
  );
}
