import type { ReactNode } from "react";
import type { CharacterCandidate } from "../../../types";

/** Splits a copper amount into gold / silver / copper (1 gold = 100 silver = 10,000 copper). */
function denominations(totalCopper: number) {
  return {
    gold: Math.floor(totalCopper / 10000),
    silver: Math.floor((totalCopper % 10000) / 100),
    copper: totalCopper % 100,
  };
}

function TextList({ items }: { items?: string[] }) {
  return items?.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p>模型未列出。</p>;
}

export function CandidatePanel({ candidate, footer }: { candidate: CharacterCandidate; footer?: ReactNode }) {
  const attributes = [["体质 CON", candidate.attributes.con], ["智力 INT", candidate.attributes.int], ["魅力 CHA", candidate.attributes.cha]] as const;
  const resources = candidate.resources ? [["生命 HP", candidate.resources.hp], ["魔力 MP", candidate.resources.mp], ["精神 SP", candidate.resources.sp], ["精力 ST", candidate.resources.st]] as const : [];
  const currency = candidate.starting_currency;
  const { gold, silver, copper } = currency ? denominations(currency.copper) : { gold: 0, silver: 0, copper: 0 };
  const description = candidate.description;
  return (
    <article className="candidate-panel">
      <header>
        <div>
          <span className="world-label">角色候选</span>
          <h2>{candidate.identity?.name || "未命名角色"}</h2>
          <p>{[candidate.identity?.race_name, candidate.identity?.race_branch_name, candidate.identity?.rank_name, candidate.identity?.location_name].filter(Boolean).join(" · ")}</p>
          <p>{[candidate.identity?.gender, candidate.identity?.age ? `${candidate.identity.age} 岁` : null].filter(Boolean).join(" · ")}</p>
        </div>
        <span className={`candidate-validity ${candidate.valid === false ? "invalid" : "valid"}`}>{candidate.valid === false ? "存在规则冲突" : "规则校验通过"}</span>
      </header>
      {candidate.summary && <section className="candidate-summary"><h3>能力概述</h3><p>{candidate.summary}</p></section>}
      <section>
        <h3>长期属性</h3>
        <div className="attribute-grid">
          {attributes.map(([label, attribute]) => (
            <div className="attribute-row" key={label}>
              <div><span>{label}</span><strong>{attribute.value}</strong></div>
              <div className="attribute-meter" aria-label={`${label} ${attribute.value}，满值 100`}><span style={{ width: `${Math.min(100, Math.max(0, attribute.value))}%` }} /></div>
              {attribute.reason && <p>{attribute.reason}</p>}
            </div>
          ))}
        </div>
      </section>
      {resources.length > 0 && (
        <section>
          <h3>短期资源</h3>
          <div className="resource-list">
            {resources.map(([label, resource]) => resource && (
              <div key={label}><span>{label}</span><strong>{resource.current} / {resource.max}</strong>{resource.reason && <small>{resource.reason}</small>}</div>
            ))}
          </div>
        </section>
      )}
      {currency && (
        <section className="starting-currency">
          <h3>初始钱财</h3>
          <div className="currency-denominations" aria-label={`初始钱财共 ${currency.copper} 铜币`}>
            <span><strong>{gold.toLocaleString()}</strong>金币</span>
            <span><strong>{silver}</strong>银币</span>
            <span><strong>{copper}</strong>铜币</span>
          </div>
          <p>{currency.reason}</p>
        </section>
      )}
      <section className="power-section">
        <div><h3>战力</h3><strong className="power-number">{candidate.power.effective.toLocaleString()}</strong><span>基础战力 {candidate.power.base.toLocaleString()}</span></div>
        <div>
          {candidate.power.modifiers?.length ? (
            <ul>
              {candidate.power.modifiers.map((modifier) => (
                <li key={`${modifier.label}-${modifier.value}`}><strong>{modifier.label} {modifier.value >= 0 ? "+" : ""}{modifier.value}</strong>{modifier.reason && <span>{modifier.reason}</span>}</li>
              ))}
            </ul>
          ) : <p>当前没有已裁决的战力修正。</p>}
          {candidate.power.explanation && <p>{candidate.power.explanation}</p>}
        </div>
      </section>
      <section className="candidate-columns">
        <div><h3>优势</h3><TextList items={candidate.strengths} /></div>
        <div><h3>局限</h3><TextList items={candidate.limitations} /></div>
      </section>
      <section className="description-section">
        <h3>角色描述</h3>
        <dl>
          {description?.appearance && <div><dt>外貌</dt><dd>{description.appearance}</dd></div>}
          {description?.personality && <div><dt>性格</dt><dd>{description.personality}</dd></div>}
          {description?.talent && <div><dt>天赋</dt><dd>{description.talent}</dd></div>}
          {description?.background && <div><dt>身世</dt><dd>{description.background}</dd></div>}
          {description?.additional && <div><dt>其他补充</dt><dd>{description.additional}</dd></div>}
        </dl>
      </section>
      {footer}
    </article>
  );
}
