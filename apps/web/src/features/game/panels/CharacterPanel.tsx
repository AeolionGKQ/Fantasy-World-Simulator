import type { CSSProperties } from "react";
import type { CharacterState, WorldCatalog } from "../../../types";
import { resourceCondition, resourceExhaustion, resourceFill, resourceLevel } from "../helpers";
import { CharacterDetails } from "./CharacterDetails";

const resources = [["生命 HP", "hp"], ["魔力 MP", "mp"], ["精神 SP", "sp"], ["精力 ST", "st"]] as const;

const attributes = [["体质 CON", "con"], ["智力 INT", "int"], ["魅力 CHA", "cha"]] as const;

export function CharacterPanel({ character, catalog }: { character: CharacterState; catalog: WorldCatalog }) {
  const identity = character.identity;
  const race = catalog.races.find((item) => item.id === identity.race_id);
  const raceBranch = race?.branches?.find((item) => item.id === identity.race_branch_id);
  return (
    <div className="projection-page">
      <header className="projection-header">
        <div>
          <span className="ready-mark">{character.alive ? "存活" : "已死亡"}</span>
          {/* Race (the branch for therians) and name; gender, age and the rest are in 角色详细信息. */}
          <h2 className="identity-line">{[raceBranch?.name ?? race?.name ?? identity.race_id, identity.name].filter(Boolean).join(" · ") || "未命名角色"}</h2>
          <p>{[character.profession, character.growth_path].filter(Boolean).join(" · ") || "尚无职业与成长路径"}</p>
        </div>
        <strong className="rank-mark">{character.rank} 阶</strong>
      </header>
      <section className="status-strip">
        {resources.map(([label, key], index) => {
          const resource = character.resources[key];
          const condition = resourceCondition(resource.current, resource.max);
          return (
            <div key={key}>
              <span>{label}</span>
              <strong>{resource.current} / {resource.max}</strong>
              <div className="resource-bar" role="meter" aria-valuemin={0} aria-valuemax={resource.max} aria-valuenow={resource.current} aria-label={`${label} ${resource.current}/${resource.max}，${condition}`}>
                <span data-level={resourceLevel[condition]} style={{ "--fill": resourceFill(resource.current, resource.max), "--i": index } as CSSProperties} />
              </div>
              <small className={`resource-condition ${condition === "耗尽" ? "exhausted" : ""}`}>{condition}</small>
              <small>{condition === "耗尽" ? resourceExhaustion[key] : resource.reason}</small>
            </div>
          );
        })}
      </section>
      <div className="projection-columns">
        <div>
          <section className="plain-section">
            <h3>长期属性</h3>
            <dl className="attribute-list">
              {attributes.map(([label, key]) => <div key={key}><dt>{label}</dt><dd>{character.attributes[key].value}</dd><small>{character.attributes[key].reason}</small></div>)}
            </dl>
          </section>
          <AbilitySection title="天赋" items={character.talents} empty="尚未获得天赋。" />
          <AbilitySection title="技能" items={character.skills} empty="尚未习得技能。" />
        </div>
        <aside>
          <CharacterDetails character={character} catalog={catalog} />
          <section className="plain-section">
            <h3>成长</h3>
            <dl className="key-values">
              <div><dt>EXP</dt><dd>{character.exp}{character.exp_to_next !== null ? ` / ${character.exp_to_next}` : " · 已达最高阶"}</dd></div>
              <div><dt>突破资格</dt><dd>{character.breakthrough_eligible ? "已具备" : "未具备"}</dd></div>
            </dl>
          </section>
          <section className="plain-section">
            <h3>战力构成</h3>
            <dl className="key-values">
              <div><dt>基础战力</dt><dd>{character.base_power.toLocaleString()}</dd></div>
              <div><dt>装备战力</dt><dd>{character.equipment_power.toLocaleString()}</dd></div>
              <div className="effective"><dt>有效战力</dt><dd>{character.effective_power.toLocaleString()}</dd></div>
            </dl>
            {character.power_modifiers.length > 0 && <ul className="detail-list">{character.power_modifiers.map((item) => <li key={item.id}><strong>{item.value >= 0 ? "+" : ""}{item.value}</strong><span>{item.reason}{item.temporary ? "（临时）" : ""}</span></li>)}</ul>}
          </section>
        </aside>
      </div>
    </div>
  );
}

function AbilitySection({ title, items, empty }: { title: string; items: CharacterState["skills"]; empty: string }) {
  return (
    <section className="plain-section">
      <h3>{title}</h3>
      {items.length ? <ul className="detail-list">{items.map((item) => <li key={item.id}><strong>{item.name}</strong><span>{item.description}</span><small>{item.source}</small></li>)}</ul> : <p className="muted-copy">{empty}</p>}
    </section>
  );
}
