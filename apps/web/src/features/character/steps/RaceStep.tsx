import { ResponsiveArtwork } from "../../../components/ResponsiveArtwork";
import { selectedRaceBranch, type CharacterDraft, type RaceDefinition, type WorldCatalog } from "../../../types";
import type { DraftUpdater } from "../wizardSteps";

function RaceFacts({ facts }: { facts: RaceDefinition["facts"] }) {
  return <dl className="race-facts">{facts.map((fact) => <div key={`${fact.label}-${fact.value}`}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}</dl>;
}

function RaceLoreSections({ lore }: { lore: RaceDefinition | NonNullable<RaceDefinition["branches"]>[number] }) {
  return (
    <div className="race-lore-sections">
      <section><h4>天赋与魔力</h4><p>{lore.magic_affinity}</p></section>
      <section><h4>战斗方式</h4><p>{lore.combat_style}</p></section>
      <section><h4>文明与技术</h4><p>{lore.technology}</p></section>
      <section><h4>社会与分布</h4><p>{lore.society}</p><p>{lore.distribution}</p></section>
      {lore.representatives && (
        <section className="race-representatives">
          <h4>代表人物</h4>
          {lore.representatives.length
            ? lore.representatives.map((person) => <p key={person.name}><strong>{person.name}</strong>：{person.description}</p>)
            : <p>暂无已收录的代表人物。</p>}
        </section>
      )}
      <section className="race-creation-notes"><h4>创建提示</h4><p>{lore.creation_notes}</p></section>
    </div>
  );
}

export function RaceStep({ catalog, draft, update }: { catalog: WorldCatalog; draft: CharacterDraft; update: DraftUpdater }) {
  const selected = catalog.races.find((race) => race.id === draft.race_id) ?? catalog.races[0];
  const branch = selectedRaceBranch(selected, draft.race_branch_id);
  return (
    <div className="race-browser">
      <div className="option-track race-track" role="radiogroup" aria-label="可玩种族">
        {catalog.races.map((race) => (
          <label key={race.id}>
            <input type="radio" name="race" checked={draft.race_id === race.id} onChange={() => { update("race_id", race.id); update("race_branch_id", null); }} />
            <span>{race.name}</span>
          </label>
        ))}
      </div>
      {selected && (
        <article className="race-profile">
          <ResponsiveArtwork key={selected.id} item={selected} alt={`${selected.name}种族设定图`} kind="种族" />
          <div className="race-reading">
            <header className="race-heading"><span className="world-label">种族资料</span><h3>{selected.name}</h3><p>{selected.tagline}</p></header>
            <RaceFacts facts={[{ label: "寿命", value: selected.lifespan_text }, ...selected.facts]} />
            <p className="race-description">{selected.description}</p>
            {selected.branches?.length ? (
              <fieldset className="race-branch-selector">
                <legend>选择兽裔分支</legend>
                <p id="race-branch-help">兽人与半兽人是两个独立种族，选择后查看对应的能力、社会与阶位资料。</p>
                <div>
                  {selected.branches.map((item) => (
                    <label key={item.id}>
                      <input type="radio" name="race-branch" checked={draft.race_branch_id === item.id} aria-describedby="race-branch-help" onChange={() => update("race_branch_id", item.id)} />
                      <span><strong>{item.name}</strong><small>{item.tagline}</small></span>
                    </label>
                  ))}
                </div>
              </fieldset>
            ) : null}
            {branch ? (
              <section className="race-branch-detail" aria-live="polite">
                <header><span className="world-label">已选分支</span><h4>{branch.name}</h4><p>{branch.tagline}</p></header>
                <RaceFacts facts={[{ label: "寿命", value: branch.lifespan_text }, ...branch.facts]} />
                <p className="race-description">{branch.description}</p>
                <RaceLoreSections lore={branch} />
              </section>
            ) : <RaceLoreSections lore={selected} />}
          </div>
        </article>
      )}
    </div>
  );
}
