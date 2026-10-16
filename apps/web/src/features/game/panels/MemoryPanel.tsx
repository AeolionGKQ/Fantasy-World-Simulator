import type { MemoryEntry, MemoryProjection, NarrativeJob, StoryArc } from "../../../types";
import { currentArcMerge, isNarrativeJobActive } from "../helpers";
import { JobPanel } from "./JobPanel";

export function MemoryPanel({ memory, memories, arcBusy, arcJob, onMerge }: {
  memory: MemoryProjection;
  memories: MemoryEntry[];
  arcBusy: boolean;
  arcJob: NarrativeJob | null;
  onMerge: (ids: string[]) => void;
}) {
  const currentArcs = memory.story_arcs.filter((arc) => arc.status === "current").sort((a, b) => a.start_sequence - b.start_sequence);
  const merge = currentArcMerge(currentArcs);
  return (
    <div className="projection-page">
      <header className="projection-header">
        <div><h2>记忆管理</h2><p>将较早的经历整理成摘要，帮助 GM 记住你的旅程。完整剧情仍可回看。</p></div>
        <div className="arc-merge-action">
          <button className="secondary-button" type="button" disabled={arcBusy || !merge.valid} onClick={() => onMerge(merge.arcIds)}>{arcBusy ? "正在合并故事弧…" : merge.label}</button>
          <small>{merge.message}</small>
        </div>
      </header>
      {arcJob && isNarrativeJobActive(arcJob) && <JobPanel job={arcJob} onCancel={() => undefined} cancellable={false} />}
      <div className="memory-policy">
        <span>近期剧情 {memory.recent_full_turns.length} / {memory.policy.recent_full_count}</span>
        <span>待整理记录 {memory.summary_buffer.length}</span>
        <span>故事弧 {currentArcs.length}</span>
      </div>
      <section className="plain-section">
        <div className="section-line"><h3>故事弧</h3></div>
        {memory.story_arcs.length
          ? <ul className="arc-list">{memory.story_arcs.map((arc) => <ArcRow key={arc.id} arc={arc} />)}</ul>
          : <p className="muted-copy">较早的剧情积累到连续 25 段后，会自动整理成一个故事弧，概括这一段旅程。</p>}
      </section>
      <section className="plain-section">
        <h3>长期记忆</h3>
        {memories.length ? (
          <ol className="memory-list">
            {memories.map((item) => (
              <li key={item.id}>
                <span className="memory-number" aria-label={`长期记忆 ${item.memory_number}`}>{item.memory_number}</span>
                <div className="memory-summary"><p>{item.summary}</p><span className="memory-importance">重要度 {item.importance}</span></div>
                {item.recall_reason && <p className="recall-reason">与本轮剧情相关：{item.recall_reason}</p>}
                {item.facts.length > 0 && <p>{item.facts.join("；")}</p>}
                {item.unresolved.length > 0 && <small>尚未解决：{item.unresolved.join("；")}</small>}
              </li>
            ))}
          </ol>
        ) : <p className="muted-copy">当前没有需要长期保留的记忆。</p>}
      </section>
    </div>
  );
}

function ArcRow({ arc }: { arc: StoryArc }) {
  return (
    <li>
      <div className="record-heading"><strong>{arc.title}</strong><span>第 {arc.start_sequence} 至 {arc.end_sequence} 段 · {arc.status === "current" ? "正在使用" : "已合并到后续摘要"}</span></div>
      <p>{arc.summary}</p>
      {/* Key events are part of the summary; only open threads are listed, one per line. */}
      {arc.unresolved.length > 0 && (
        <div className="arc-unresolved">
          <h4>未解决</h4>
          <ul>{arc.unresolved.map((item, index) => <li key={index}>{item}</li>)}</ul>
        </div>
      )}
    </li>
  );
}
