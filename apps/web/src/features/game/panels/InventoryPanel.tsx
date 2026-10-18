import type { InventoryProjection } from "../../../types";
import { GameEmpty } from "./GameEmpty";

export function InventoryPanel({ inventory }: { inventory: InventoryProjection }) {
  return (
    <div className="projection-page">
      <header className="projection-header">
        <div><h2>背包</h2><p>共 {inventory.items.length} 种物品</p></div>
        <dl className="currency">
          <div><dt>金币</dt><dd>{inventory.currency.gold}</dd></div>
          <div><dt>银币</dt><dd>{inventory.currency.silver}</dd></div>
          <div><dt>铜币</dt><dd>{inventory.currency.copper}</dd></div>
        </dl>
      </header>
      {inventory.items.length ? (
        <ul className="inventory-list">
          {inventory.items.map((item) => (
            <li key={item.id}>
              <div>
                <strong>{item.name}</strong>
                {item.equipped && <span className="equipped-mark">已装备</span>}
                <p>{item.description}</p>
                <small>来源：{item.source}</small>
              </div>
              <div className="item-data"><strong>× {item.quantity}</strong><span>战力 {item.power >= 0 ? "+" : ""}{item.power}</span></div>
            </li>
          ))}
        </ul>
      ) : <GameEmpty title="背包尚空" icon="bag">冒险中获得的物品会列在这里。你持有的金币、银币和铜币显示在上方。</GameEmpty>}
    </div>
  );
}
