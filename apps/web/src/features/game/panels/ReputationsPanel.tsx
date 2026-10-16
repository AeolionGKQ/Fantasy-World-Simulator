import type { ReputationProjection } from "../../../types";
import { orderReputations, reputationNames } from "../helpers";

export function ReputationsPanel({ data }: { data: ReputationProjection }) {
  const items = orderReputations(data.items, data.local_modifier_key);
  return (
    <div className="projection-page">
      <header className="projection-header"><div><h2>声望</h2><p>查看你在大陆和各方势力中的声望。不同势力会分别评价你的行动。</p></div></header>
      <ul className="reputation-list">
        {items.map((item) => (
          <li className={`${item.key === data.primary_key ? "primary" : ""} ${item.local ? "local" : ""}`} key={item.key}>
            <div><strong>{reputationNames[item.key]}</strong><span>{item.level}{item.local ? " · 当前地区相关" : ""}</span></div>
            <meter min={-100} max={100} low={-20} high={50} optimum={100} value={item.value} aria-label={`${reputationNames[item.key]} ${item.value}`} />
            <b>{item.value > 0 ? "+" : ""}{item.value}</b>
          </li>
        ))}
      </ul>
      <p className="projection-footnote">大陆综合声望是整片大陆对角色的整体评价，走到哪里都算数。势力声望只在该势力的地区内起作用，是对当地人看法的补正；角色当前所在地区对应的势力会突出显示。</p>
    </div>
  );
}
