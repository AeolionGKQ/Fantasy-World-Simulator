import type { Quest, QuestProjection } from "../../../types";

const statusNames: Record<string, string> = { offered: "待接受", active: "进行中", completed: "已完成", declined: "已拒绝", failed: "已失败", abandoned: "已放弃" };

/** Quests in three groups: in progress, waiting for the player's answer, and finished (folded). */
export function QuestsPanel({ quests }: { quests: QuestProjection }) {
  const offered = quests.offered ?? [];
  const finished = quests.finished ?? [];
  return (
    <div className="projection-page">
      <header className="projection-header"><div><h2>任务栏</h2><p>进行中 {quests.active.length} 项 · 待接取 {offered.length} 项</p></div></header>
      <QuestList title="进行中" items={quests.active} empty="当前没有进行中的任务。" />
      <QuestList title="待接取" items={offered} empty="目前没有等待你答复的任务。" />
      <section className="plain-section">
        <details className="finished-quests">
          <summary>已结束 · {finished.length}</summary>
          {finished.length ? <QuestItems items={finished} /> : <p className="muted-copy">还没有结束的任务。</p>}
        </details>
      </section>
    </div>
  );
}

function QuestList({ title, items, empty }: { title: string; items: Quest[]; empty: string }) {
  return (
    <section className="plain-section">
      <h3>{title}</h3>
      {items.length ? <QuestItems items={items} /> : <p className="muted-copy">{empty}</p>}
    </section>
  );
}

function QuestItems({ items }: { items: Quest[] }) {
  return (
    <ul className="record-list">
      {items.map((quest) => (
        <li key={quest.id}>
          <div className="record-heading"><strong>{quest.name}</strong><span>{statusNames[quest.status] ?? quest.status}{quest.regional ? " · 地区" : ""}</span></div>
          <p>{quest.description}</p>
          {quest.progress && <p className="progress-copy">进度：{quest.progress}</p>}
          {quest.objectives.length > 0 && <ul>{quest.objectives.map((objective) => <li key={objective}>{objective}</li>)}</ul>}
        </li>
      ))}
    </ul>
  );
}
