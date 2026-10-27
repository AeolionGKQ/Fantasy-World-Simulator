import { useState, type FormEvent } from "react";
import { api, asApiError } from "../../../api";
import { Modal } from "../../../components/Modal";
import { playerProblemMessage } from "../../../playerCopy";
import type { Quest, QuestProjection, WorldQuest } from "../../../types";

const statusNames: Record<string, string> = { untriggered: "未触发", eligible: "可触发", offered: "待接受", active: "进行中", completed: "已完成", declined: "已拒绝", failed: "已失败", abandoned: "已放弃" };
const finishedStatuses = new Set(["completed", "declined", "failed", "abandoned"]);

function statusName(quest: Quest) {
  return quest.dismissed_by_player ? "已忽略" : statusNames[quest.status] ?? quest.status;
}

/** Quests in three groups: in progress, waiting for the player's answer, and finished (folded); then the world quests. */
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
  const world = quests.world ?? [];
  const dismiss = locked ? undefined : setDismissing;
  const count = (status: string) => world.filter((quest) => quest.status === status).length;
  return (
    <div className="projection-page">
      <header className="projection-header"><div><h2>任务栏</h2><p>进行中 {quests.active.length + count("active")} 项 · 待接取 {offered.length + count("offered")} 项</p></div></header>
      <QuestList title="进行中" items={quests.active} empty="当前没有进行中的任务。" />
      <QuestList title="待接取" items={offered} empty="目前没有等待你答复的任务。" onDismiss={dismiss} dismissible />
      <section className="plain-section">
        <details className="finished-quests">
          <summary>已结束 · {finished.length}</summary>
          {finished.length ? <QuestItems items={finished} /> : <p className="muted-copy">还没有结束的任务。</p>}
        </details>
      </section>
      {world.length > 0 && <WorldQuests items={world} onDismiss={dismiss} />}
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
          <div className="record-heading"><strong>{quest.name}</strong><span>{statusName(quest)}</span></div>
          <p>{quest.description}</p>
          {quest.progress && <p className="progress-copy">进度：{quest.progress}</p>}
          {quest.objectives.length > 0 && <ul>{quest.objectives.map((objective) => <li key={objective}>{objective}</li>)}</ul>}
          {dismissible && <DismissButton quest={quest} onDismiss={onDismiss} />}
        </li>
      ))}
    </ul>
  );
}

function DismissButton({ quest, onDismiss }: { quest: Quest; onDismiss?: (quest: Quest) => void }) {
  return (
    <div className="quest-actions">
      <button className="text-button" type="button" disabled={!onDismiss} title={onDismiss ? undefined : "剧情生成或整理记忆期间不能忽略任务"} onClick={() => onDismiss?.(quest)}>忽略此任务</button>
    </div>
  );
}

/** The regional main quests: the ones the GM sees now come first and are highlighted, finished ones last. */
function WorldQuests({ items, onDismiss }: { items: WorldQuest[]; onDismiss?: (quest: Quest) => void }) {
  const rank = (quest: WorldQuest) => quest.in_context ? 0 : finishedStatuses.has(quest.status) ? 2 : 1;
  const ordered = items.map((quest, index) => ({ quest, index }))
    .sort((a, b) => rank(a.quest) - rank(b.quest) || a.index - b.index).map(({ quest }) => quest);
  const done = items.filter((quest) => quest.status === "completed").length;
  return (
    <section className="plain-section world-quests">
      <div className="section-line"><h3>世界任务</h3><span>已完成 {done}/{items.length}</span></div>
      <p className="muted-copy">各地区的主线故事，均可自由选择是否参与。到达触发地点后，GM 才会把它写进剧情。</p>
      <ul className="record-list">
        {ordered.map((quest) => {
          const finished = finishedStatuses.has(quest.status);
          return (
            <li key={quest.id} className={quest.in_context ? "in-context" : undefined}>
              <div className="record-heading"><strong>{quest.name}</strong><span>{statusName(quest)}</span></div>
              {quest.in_context && <p className="context-flag">已进入 GM 上下文 · {contextReason(quest)}</p>}
              <p>{quest.description}</p>
              {finished ? <WorldQuestEnding quest={quest} /> : (
                <dl className="world-quest-trigger">
                  <div><dt>触发地点</dt><dd>{quest.trigger_locations.map((place) => place.name).join("、")}</dd></div>
                  <div><dt>触发条件</dt><dd>{quest.trigger}</dd></div>
                </dl>
              )}
              {!finished && quest.progress && <p className="progress-copy">进度：{quest.progress}</p>}
              {!finished && quest.objectives.length > 0 && <ul>{quest.objectives.map((objective) => <li key={objective}>{objective}</li>)}</ul>}
              {quest.status === "offered" && <DismissButton quest={quest} onDismiss={onDismiss} />}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function contextReason(quest: WorldQuest) {
  if (quest.context_reason === "location_matched") return "你正在触发地点";
  return quest.status === "offered" ? "等待你答复" : "进行中";
}

function WorldQuestEnding({ quest }: { quest: WorldQuest }) {
  const ending = quest.ending;
  return (
    <div className="world-quest-ending">
      <h4>终局总结{ending ? ` · 第 ${ending.sequence} 段「${ending.title}」` : ""}</h4>
      <p>{ending?.summary || quest.progress || (quest.dismissed_by_player ? "你在任务栏中忽略了这个任务。" : "没有留下终局记录。")}</p>
    </div>
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
        <div className="danger-callout"><strong>忽略后无法恢复</strong><p>“{quest.name}”会记为已拒绝{quest.regional ? "" : "并移到“已结束”中"}，GM 之后不会再推进它。</p></div>
        {error && <p className="field-error">{error}</p>}
        <div className="modal-actions">
          <button className="secondary-button" type="button" data-modal-close>保留</button>
          <button className="danger-button" data-autofocus disabled={busy}>{busy ? "正在忽略…" : "忽略此任务"}</button>
        </div>
      </form>
    </Modal>
  );
}
