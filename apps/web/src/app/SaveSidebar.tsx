import { Link } from "react-router-dom";
import { ErrorPanel } from "../components/ErrorPanel";
import { Icon } from "../components/Icon";
import { LoadingPanel } from "../components/LoadingPanel";
import { StatusDot } from "../components/StatusDot";
import { useSlidingIndicator } from "../components/useSlidingIndicator";
import { stepProgressLabel } from "../features/character/wizardSteps";
import { isActiveJobStatus, jobLabel, phaseLabel, saveRoute, type SaveSummary, type ServiceStatuses } from "../types";
import { ServiceStatusPanel } from "./ServiceStatusPanel";

export function SaveSidebar({ saves, currentId, loading, loadError, open, services, offline, onClose, onRetry, onNew, onRename, onDelete }: {
  saves: SaveSummary[];
  currentId: string | undefined;
  loading: boolean;
  loadError: unknown;
  open: boolean;
  services: ServiceStatuses | null;
  offline: boolean;
  onClose: () => void;
  onRetry: () => void;
  onNew: () => void;
  onRename: (save: SaveSummary) => void;
  onDelete: (save: SaveSummary) => void;
}) {
  const { containerRef, indicator } = useSlidingIndicator<HTMLElement>(".save-row.active", [currentId, saves, loading]);
  return (
    <aside className={`sidebar ${open ? "open" : ""}`} aria-label="存档列表">
      <div className="brand-block">
        <Link viewTransition to="/" className="brand-mark" aria-label="Fantasy Simulator 首页"><span>F</span></Link>
        <div><strong>Fantasy Simulator</strong><small>冒险档案</small></div>
        <button className="icon-button sidebar-close" type="button" onClick={onClose} aria-label="关闭存档列表"><Icon name="close" /></button>
      </div>
      <div className="sidebar-title"><span>存档</span><span>{saves.length}</span></div>
      <nav className="save-list" aria-label="已有存档" ref={containerRef}>
        <span className={`slide-indicator save-indicator ${indicator.className}`} style={indicator.style} aria-hidden="true" />
        {loading && <LoadingPanel label="正在载入存档" />}
        {!loading && Boolean(loadError) && <ErrorPanel playerFacing error={loadError} onRetry={onRetry} title="无法载入存档" />}
        {!loading && !loadError && saves.length === 0 && (
          <div className="sidebar-empty"><p>还没有冒险档案。</p><button type="button" className="text-button" onClick={onNew}>创建第一个存档</button></div>
        )}
        {saves.map((save) => (
          <div className={`save-row ${save.id === currentId ? "active" : ""}`} key={save.id}>
            <Link viewTransition to={saveRoute(save)} className="save-link" aria-current={save.id === currentId ? "page" : undefined}>
              <span className="save-name">{save.name}</span>
              {/* Status and character on separate lines so neither is cut off; a draft shows its step instead. */}
              <span className="save-phase">{phaseLabel[save.phase]}</span>
              {save.phase === "draft"
                ? <span className="save-detail">{stepProgressLabel(save.current_step ?? 1)}</span>
                : save.character_name && <span className="save-detail">{save.character_name}</span>}
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
        <ServiceStatusPanel services={services} offline={offline} />
      </div>
    </aside>
  );
}
