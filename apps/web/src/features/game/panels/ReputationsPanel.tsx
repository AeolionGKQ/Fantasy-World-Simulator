import type { ReputationProjection } from "../../../types";
import { orderReputations, reputationNames } from "../helpers";

type ReputationItem = ReturnType<typeof orderReputations>[number];

function ReputationRow({ item, className = "" }: { item: ReputationItem; className?: string }) {
  return (
    <li className={`${className} ${item.local ? "local" : ""}`}>
      <div><strong>{reputationNames[item.key]}</strong><span>{item.level}{item.local ? " · 当前地区相关" : ""}</span></div>
      <meter min={-100} max={100} low={-20} high={50} optimum={100} value={item.value} aria-label={`${reputationNames[item.key]} ${item.value}`} />
      <b>{item.value > 0 ? "+" : ""}{item.value}</b>
    </li>
  );
}

/** Overall reputation on its own, then the faction reputations that adjust it within their regions. */
export function ReputationsPanel({ data }: { data: ReputationProjection }) {
  const items = orderReputations(data.items, data.local_modifier_key);
  const overall = items.find((item) => item.key === data.primary_key);
  const factions = items.filter((item) => item.key !== data.primary_key);
  return (
    <div className="projection-page">
      <header className="projection-header"><div><h2>声望</h2><p>查看你在大陆和各方势力中的声望。不同势力会分别评价你的行动。</p></div></header>
      {overall && (
        <section className="reputation-group">
          <h3>整体声望</h3>
          <ul className="reputation-list"><ReputationRow item={overall} className="primary" /></ul>
        </section>
      )}
      <section className="reputation-group">
        <h3>势力声望</h3>
        <ul className="reputation-list">{factions.map((item) => <ReputationRow item={item} key={item.key} />)}</ul>
      </section>
      <p className="projection-footnote">大陆综合声望是整片大陆对角色的整体评价，走到哪里都算数。势力声望只在该势力的地区内起作用，是对当地人看法的补正；角色当前所在地区对应的势力会突出显示。</p>
    </div>
  );
}
