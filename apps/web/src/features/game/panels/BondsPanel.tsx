import type { Bond } from "../../../types";
import { GameEmpty } from "./GameEmpty";

export function BondsPanel({ items }: { items: Bond[] }) {
  return (
    <div className="projection-page">
      <header className="projection-header"><div><h2>羁绊</h2><p>查看与你建立了持续关系的重要人物，以及他们对你的好感。</p></div></header>
      {items.length ? (
        <ul className="relationship-list">
          {items.map((bond) => (
            <li key={bond.id}>
              <div><strong>{bond.npc_name}</strong><span>{bond.relation_type} · {bond.level ?? "普通/陌生"}</span></div>
              <meter min={-100} max={100} low={-20} high={50} optimum={100} value={bond.value} aria-label={`${bond.npc_name} 羁绊 ${bond.value}`} />
              <b>{bond.value > 0 ? "+" : ""}{bond.value}</b>
            </li>
          ))}
        </ul>
      ) : <GameEmpty title="尚未建立羁绊" icon="people">重要人物在形成持续关系后会列入此处。</GameEmpty>}
    </div>
  );
}
