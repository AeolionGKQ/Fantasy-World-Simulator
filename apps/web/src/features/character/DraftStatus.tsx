import { StatusDot } from "../../components/StatusDot";
import type { SaveStatus } from "./useCharacterWizard";

const statusConfig: Record<SaveStatus, [string, string]> = {
  saved: ["saved", "已保存"], dirty: ["dirty", "有未保存更改"], saving: ["saving", "保存中"], error: ["error", "保存失败"], conflict: ["warning", "版本冲突"],
};

export function DraftStatus({ status, revision, onRetry, onReload }: { status: SaveStatus; revision: number; onRetry: () => void; onReload: () => void }) {
  const config = statusConfig[status];
  return (
    <div className="draft-status" role="status" aria-live="polite">
      <StatusDot state={status === "saved" ? "online" : status === "saving" || status === "dirty" ? "busy" : "offline"} />
      <span><strong className={config[0]}>{config[1]}</strong><small>草稿修订 {revision}</small></span>
      {status === "error" && <button type="button" className="text-button" onClick={onRetry}>重试保存</button>}
      {status === "conflict" && <button type="button" className="text-button" onClick={onReload}>载入服务器版本</button>}
    </div>
  );
}
