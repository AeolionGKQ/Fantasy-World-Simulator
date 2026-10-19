import { createContext, useContext } from "react";
import { Icon } from "../components/Icon";

/** One message for the global notice bar under the toolbar. */
export interface Notice {
  id: number;
  tone: "info" | "error";
  text: string;
  /** Shown for errors the player may need to report. */
  traceId?: string | null;
}

/** Shows a notice (replacing the current one), or hides the bar with null. */
export type Notify = (notice: Omit<Notice, "id"> | null) => void;

const NoticeContext = createContext<Notify>(() => undefined);

export const NoticeProvider = NoticeContext.Provider;

/** Every page posts its one-off messages and errors through this, so they all appear in one place. */
export function useNotify(): Notify {
  return useContext(NoticeContext);
}

/** Info notices fade on their own; errors stay until closed or replaced. */
export const INFO_NOTICE_MS = 6000;

export function NoticeBar({ notice, leaving, onDismiss }: { notice: Notice; leaving: boolean; onDismiss: () => void }) {
  return (
    <div className={`app-notice ${notice.tone} ${leaving ? "leaving" : ""}`} role={notice.tone === "error" ? "alert" : "status"}>
      <span className="notice-icon" aria-hidden="true"><Icon name={notice.tone === "error" ? "alert" : "info"} /></span>
      <p>{notice.text}{notice.traceId && <small>问题编号：{notice.traceId}</small>}</p>
      <button type="button" onClick={onDismiss} aria-label="关闭提示">×</button>
    </div>
  );
}
