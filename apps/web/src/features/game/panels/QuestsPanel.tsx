import type { Quest } from "../../../types";

const statusNames: Record<string, string> = { offered: "待接受", active: "进行中", completed: "已完成", declined: "已拒绝", failed: "已失败", abandoned: "已放弃" };

export function QuestsPanel({ active }: { active: Quest[] }) {
  return (
    <div className="projection-page">
      <header className="projection-header"><div><h2>任务栏</h2><p>进行中 {active.length} 项</p></div></header>
      <QuestList title="进行中" items={active} empty="当前没有进行中的任务。" />
    </div>
  );
}

function QuestList({ title, items, empty }: { title: string; items: Quest[]; empty: string }) {
  return (
    <section className="plain-section">
      <h3>{title}</h3>
      {items.length ? (
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
      ) : <p className="muted-copy">{empty}</p>}
    </section>
  );
}
