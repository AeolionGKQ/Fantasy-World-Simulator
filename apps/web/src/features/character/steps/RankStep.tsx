import { chineseRankNumeral, selectedRaceBranch, type CharacterDraft, type WorldCatalog } from "../../../types";
import type { DraftUpdater } from "../wizardSteps";

export function RankStep({ catalog, draft, update }: { catalog: WorldCatalog; draft: CharacterDraft; update: DraftUpdater }) {
  const race = catalog.races.find((item) => item.id === draft.race_id);
  const branch = selectedRaceBranch(race, draft.race_branch_id);
  const ranks = branch?.ranks.length ? branch.ranks : race?.ranks.length ? race.ranks : catalog.ranks;
  const selected = ranks.find((rank) => rank.rank === draft.rank);
  return (
    <div className="rank-browser">
      <section className="rank-system" aria-labelledby="rank-system-title">
        <div>
          <span className="world-label">世界通行标准</span>
          <h3 id="rank-system-title">{catalog.rank_system.title}</h3>
          <p>{catalog.rank_system.description}</p>
          {catalog.rank_system.starting_advice && <><h4>为什么推荐六阶及以下开局</h4><p>{catalog.rank_system.starting_advice}</p></>}
        </div>
        <ul>{catalog.rank_system.principles.map((principle) => <li key={principle}>{principle}</li>)}</ul>
      </section>
      <div className="rank-step">
        <div className="rank-list" role="radiogroup" aria-label="角色等阶">
          {ranks.map((rank) => {
            const displayRank = rank.display_rank || `${chineseRankNumeral(rank.rank)}阶`;
            return (
              <label key={rank.rank} className={rank.disabled ? "disabled" : ""}>
                <input type="radio" name="rank" disabled={rank.disabled} checked={draft.rank === rank.rank} onChange={() => update("rank", rank.rank)} />
                <span className="rank-number">{chineseRankNumeral(rank.rank)}</span>
                <span><strong>{displayRank}</strong><small>{rank.title || "无专属称号"}</small></span>
                {rank.base_power !== undefined && <span className="power-value">战力 {rank.base_power.toLocaleString()}</span>}
              </label>
            );
          })}
        </div>
        {selected && (
          <div className={`rank-note ${selected.rank >= 7 ? "warning" : ""}`}>
            <strong>{selected.display_rank || `${chineseRankNumeral(selected.rank)}阶`} · {selected.title || "无专属称号"}</strong>
            {selected.description && <p>{selected.description}</p>}
            {selected.warning && <p>{selected.warning}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
