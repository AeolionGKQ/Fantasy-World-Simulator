import { useState, type FormEvent } from "react";
import { api, asApiError } from "../../../api";
import { Modal } from "../../../components/Modal";
import { playerProblemMessage } from "../../../playerCopy";
import type { Quest, QuestProjection } from "../../../types";

const statusNames: Record<string, string> = { offered: "待接受", active: "进行中", completed: "已完成", declined: "已拒绝", failed: "已失败", abandoned: "已放弃" };

function statusName(quest: Quest) {
  return quest.dismissed_by_player ? "已忽略" : statusNames[quest.status] ?? quest.status;
}

/** Quests in three groups: in progress, waiting for the player's answer, and finished (folded). */
export function QuestsPanel({ quests, saveId, stateVersion, locked, onDismissed }: {
  quests: QuestProjection;
  saveId: string;
  stateVersion: number;
  /** A story job is running; quests cannot change under it. */
  locked: boolean;
  onDismissed: (quest: Quest) => void;
}) {
  const [dismissing, setDismissing] = useState<Quest | null>(null);
  const offered = quests.offered ?? [];
  const finished = quests.finished ?? [];
  const dismiss = locked ? undefined : setDismissing;
  return (
    <div className="projection-page">
      <header className="projection-header"><div><h2>任务栏</h2><p>进行中 {quests.active.length} 项 · 待接取 {offered.length} 项</p></div></header>
      <QuestList title="进行中" items={quests.active} empty="当前没有进行中的任务。" />
      <QuestList title="待接取" items={offered} empty="目前没有等待你答复的任务。" onDismiss={dismiss} dismissible />
      <section className="plain-section">
        <details className="finished-quests">
          <summary>已结束 · {finished.length}</summary>
          {finished.length ? <QuestItems items={finished} /> : <p className="muted-copy">还没有结束的任务。</p>}
        </details>
      </section>
      {dismissing && (
        <DismissQuestModal saveId={saveId} stateVersion={stateVersion} quest={dismissing}
          onClose={() => setDismissing(null)} onDismissed={() => { setDismissing(null); onDismissed(dismissing); }} />
      )}
    </div>
  );
}

function QuestList({ title, items, empty, onDismiss, dismissible = false }: {
  title: string; items: Quest[]; empty: string; onDismiss?: (quest: Quest) => void; dismissible?: boolean;
}) {
  return (
    <section className="plain-section">
      <h3>{title}</h3>
      {items.length ? <QuestItems items={items} onDismiss={onDismiss} dismissible={dismissible} /> : <p className="muted-copy">{empty}</p>}
    </section>
  );
}

function QuestItems({ items, onDismiss, dismissible = false }: { items: Quest[]; onDismiss?: (quest: Quest) => void; dismissible?: boolean }) {
  return (
    <ul className="record-list">
      {items.map((quest) => (
        <li key={quest.id}>
          <div className="record-heading"><strong>{quest.name}</strong><span>{statusName(quest)}{quest.regional ? " · 地区" : ""}</span></div>
          <p>{quest.description}</p>
          {quest.progress && <p className="progress-copy">进度：{quest.progress}</p>}
          {quest.objectives.length > 0 && <ul>{quest.objectives.map((objective) => <li key={objective}>{objective}</li>)}</ul>}
          {dismissible && (
            <div className="quest-actions">
              <button className="text-button" type="button" disabled={!onDismiss} title={onDismiss ? undefined : "剧情生成或整理记忆期间不能忽略任务"} onClick={() => onDismiss?.(quest)}>忽略此任务</button>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function DismissQuestModal({ saveId, stateVersion, quest, onClose, onDismissed }: {
  saveId: string; stateVersion: number; quest: Quest; onClose: () => void; onDismissed: () => void;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true);
    try {
      await api.dismissQuest(saveId, quest.id, stateVersion, crypto.randomUUID());
      onDismissed();
    } catch (reason) {
      setError(playerProblemMessage(asApiError(reason).problem));
      setBusy(false);
    }
  };
  return (
    <Modal title="忽略任务" onClose={onClose} labelledBy="dismiss-quest-title">
      <form onSubmit={(event) => void submit(event)}>
        <div className="danger-callout"><strong>忽略后无法恢复</strong><p>“{quest.name}”会移到“已结束”中，这个委托会记为已拒绝，GM 之后不会再推进它。</p></div>
        {error && <p className="field-error">{error}</p>}
        <div className="modal-actions">
          <button className="secondary-button" type="button" data-modal-close>保留</button>
          <button className="danger-button" data-autofocus disabled={busy}>{busy ? "正在忽略…" : "忽略此任务"}</button>
        </div>
      </form>
    </Modal>
  );
}
