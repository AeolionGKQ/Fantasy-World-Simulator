import { StatusDot } from "../../../components/StatusDot";
import type { NarrativeJob } from "../../../types";
import { isNarrativeJobActive, narrativeJobMessage } from "../helpers";

export function JobPanel({ job, onCancel, cancellable = true }: { job: NarrativeJob; onCancel: () => void; cancellable?: boolean }) {
  const active = isNarrativeJobActive(job);
  return (
    <section className={`narrative-job ${job.status}`} role="status" aria-live="polite">
      <div className="job-title">
        <StatusDot state="busy" />
        <div>
          <strong>{job.type === "turns_to_arc" || job.type === "arcs_to_arc" ? "正在整理故事弧" : "正在书写剧情"}</strong>
          <small>{job.status === "queued" ? "等待开始生成" : job.status === "cancel_requested" ? "正在取消" : "正在生成"}</small>
        </div>
      </div>
      <p>{narrativeJobMessage(job)}</p>
      {active && cancellable && <button className="secondary-button" type="button" disabled={job.status === "cancel_requested"} onClick={onCancel}>{job.status === "cancel_requested" ? "正在取消…" : "取消任务"}</button>}
    </section>
  );
}
