import type { JournalEntry } from "../../../types";
import { GameEmpty } from "./GameEmpty";

export function JournalsPanel({ items, onRead }: { items: JournalEntry[]; onRead: (turnId: string) => void }) {
  return (
    <div className="projection-page">
      <header className="projection-header"><div><h2>纪事</h2><p>回顾每一段冒险的经过，点击记录可查看完整剧情。</p></div></header>
      {items.length ? (
        <ol className="chronicle-list">
          {[...items].reverse().map((item) => (
            <li key={item.turn_id}><button type="button" onClick={() => onRead(item.turn_id)}><span>{item.sequence}</span><strong>{item.title}</strong><p>{item.summary}</p></button></li>
          ))}
        </ol>
      ) : <GameEmpty title="纪事尚未开始">开始冒险后，每段剧情都会自动留下一条记录。</GameEmpty>}
    </div>
  );
}
