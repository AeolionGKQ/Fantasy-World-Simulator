import { useState, type FormEvent } from "react";
import { api, asApiError } from "../../../api";
import { Icon } from "../../../components/Icon";
import { Modal } from "../../../components/Modal";
import { playerProblemMessage } from "../../../playerCopy";
import type { MemoryEntry, MemoryProjection, NarrativeJob, StoryArc } from "../../../types";
import { currentArcMerge, isNarrativeJobActive } from "../helpers";
import { JobPanel } from "./JobPanel";

export function MemoryPanel({ memory, memories, arcBusy, arcJob, onMerge, onRebuild, saveId, memoryBusy, memoryJob, storyBusy, onCurate, onMemoryDeleted }: {
  memory: MemoryProjection;
  memories: MemoryEntry[];
  arcBusy: boolean;
  arcJob: NarrativeJob | null;
  onMerge: (ids: string[]) => void;
  /** Retry organising the next batch of earlier segments into a story arc; offered only after it failed. */
  onRebuild: () => void;
  saveId: string;
  /** A memory cleanup is starting or running. */
  memoryBusy: boolean;
  memoryJob: NarrativeJob | null;
  /** A story job is running; memories cannot change under it. */
  storyBusy: boolean;
  onCurate: () => void;
  onMemoryDeleted: () => void;
}) {
  const [deleting, setDeleting] = useState<MemoryEntry | null>(null);
  const locked = memoryBusy || storyBusy;
  const failures = memory.arc_failures;
  const currentArcs = memory.story_arcs.filter((arc) => arc.status === "current").sort((a, b) => a.start_sequence - b.start_sequence);
  const merge = currentArcMerge(currentArcs);
  return (
    <div className="projection-page">
      <header className="projection-header">
        <div><h2>记忆管理</h2><p>将较早的经历整理成摘要，帮助 GM 记住你的旅程。完整剧情仍可回看。</p></div>
        <div className="arc-merge-action">
          <div className="arc-actions">
            {failures && <button className="secondary-button" type="button" disabled={arcBusy || memory.summary_buffer.length < memory.policy.arc_turn_count} onClick={onRebuild}>重新整理故事弧</button>}
            <button className="secondary-button" type="button" disabled={arcBusy || !merge.valid} onClick={() => onMerge(merge.arcIds)}>{arcBusy ? "正在整理故事弧…" : merge.label}</button>
          </div>
          <small>{merge.message}</small>
        </div>
      </header>
      {arcJob && isNarrativeJobActive(arcJob) && <JobPanel job={arcJob} onCancel={() => undefined} cancellable={false} />}
      {failures && (
        <p className="warning-text arc-failure" role="status">
          第 {failures.start_sequence} 至 {failures.end_sequence} 段的故事弧已连续 {failures.count} 次整理失败{failures.message ? `：${failures.message.replace(/[。.]$/, "")}。` : "。"}之后每次保存新剧情都会自动再试，也可以点“重新整理故事弧”立即重试。
        </p>
      )}
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
        <div className="section-line memory-heading">
          <div>
            <h3>长期记忆</h3>
            <p className="muted-copy">可以逐条删除，也可以让 GM 回顾全部记忆，剔除已经解决、过期或不重要的内容。</p>
          </div>
          <button className="secondary-button" type="button" disabled={locked || !memories.length} onClick={onCurate}>
            {memoryBusy ? "正在整理长期记忆…" : "整理长期记忆"}
          </button>
        </div>
        {memoryJob && isNarrativeJobActive(memoryJob) && <JobPanel job={memoryJob} onCancel={() => undefined} cancellable={false} />}
        {memories.length ? (
          <ol className="memory-list">
            {memories.map((item) => (
              <li key={item.id}>
                <span className="memory-number" aria-label={`长期记忆 ${item.memory_number}`}>{item.memory_number}</span>
                <div className="memory-summary">
                  <p>{item.summary}</p>
                  <button className="icon-button memory-delete" type="button" disabled={locked} aria-label={`删除长期记忆 ${item.memory_number}`} title={locked ? "剧情生成或整理记忆期间不能删除" : "删除这条记忆"} onClick={() => setDeleting(item)}>
                    <Icon name="trash" />
                  </button>
                </div>
                {item.recall_reason && <p className="recall-reason">与本轮剧情相关：{item.recall_reason}</p>}
                {item.facts.length > 0 && <p>{item.facts.join("；")}</p>}
                {item.unresolved.length > 0 && <small>尚未解决：{item.unresolved.join("；")}</small>}
              </li>
            ))}
          </ol>
        ) : <p className="muted-copy">当前没有需要长期保留的记忆。</p>}
      </section>
      {deleting && <DeleteMemoryModal saveId={saveId} memory={deleting} onClose={() => setDeleting(null)} onDeleted={() => { setDeleting(null); onMemoryDeleted(); }} />}
    </div>
  );
}

function DeleteMemoryModal({ saveId, memory, onClose, onDeleted }: { saveId: string; memory: MemoryEntry; onClose: () => void; onDeleted: () => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const remove = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true);
    try {
      await api.deleteMemory(saveId, memory.id);
      onDeleted();
    } catch (reason) {
      setError(playerProblemMessage(asApiError(reason).problem));
      setBusy(false);
    }
  };
  return (
    <Modal title="删除长期记忆" onClose={onClose} labelledBy="delete-memory-title">
      <form onSubmit={(event) => void remove(event)}>
        <div className="danger-callout"><strong>删除后无法恢复</strong><p>GM 之后不会再记得这条记忆：“{memory.summary}”</p></div>
        {error && <p className="field-error">{error}</p>}
        <div className="modal-actions">
          <button className="secondary-button" type="button" data-modal-close>保留</button>
          <button className="danger-button" data-autofocus disabled={busy}>{busy ? "正在删除…" : "删除这条记忆"}</button>
        </div>
      </form>
    </Modal>
  );
}

function ArcRow({ arc }: { arc: StoryArc }) {
  return (
    <li>
      <div className="record-heading"><strong>{arc.title}</strong><span>第 {arc.start_sequence} 至 {arc.end_sequence} 段 · {arc.status === "current" ? "正在使用" : "已压缩到后续摘要"}</span></div>
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
