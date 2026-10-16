import { useState } from "react";
import { Modal } from "../../../components/Modal";
import { chineseRankNumeral, type CharacterState, type WorldCatalog } from "../../../types";

/** What the player chose and wrote during character creation, as kept in the confirmed character. */
function creationEntries(identity: CharacterState["identity"], catalog: WorldCatalog) {
  const race = catalog.races.find((item) => item.id === identity.race_id);
  const branch = race?.branches?.find((item) => item.id === identity.race_branch_id);
  const location = catalog.locations.find((item) => item.id === identity.start_location_id);
  const facts = [
    ["种族", [race?.name ?? identity.race_id, branch?.name ?? identity.race_branch_id].filter(Boolean).join(" · ")],
    ["姓名", identity.name],
    ["性别", identity.gender],
    ["年龄", identity.age ? `${identity.age} 岁` : ""],
    ["初始等阶", identity.rank ? `${chineseRankNumeral(identity.rank)}阶` : ""],
    ["初始地点", location?.name ?? identity.start_location_id],
  ] as const;
  const texts = [
    ["外貌", identity.appearance],
    ["性格", identity.personality],
    ["天赋", identity.talent],
    ["身世与经历", identity.backstory],
    ["其他补充", identity.additional],
  ] as const;
  return { facts, texts };
}

/**
 * "角色详细信息" section of the Character tab: a button that opens a dialog with everything chosen
 * and written in character creation.
 */
export function CharacterDetails({ character, catalog }: { character: CharacterState; catalog: WorldCatalog }) {
  const [open, setOpen] = useState(false);
  const { facts, texts } = creationEntries(character.identity, catalog);
  return (
    <section className="plain-section">
      <h3>角色详细信息</h3>
      <button type="button" className="secondary-button character-details-button" aria-haspopup="dialog" onClick={() => setOpen(true)}>
        查看创建角色时的完整设定<span aria-hidden="true">→</span>
      </button>
      {open && (
        <Modal title="角色详细信息" labelledBy="character-details-title" className="character-details-modal" onClose={() => setOpen(false)}>
          <div className="character-details">
            <dl className="details-facts">
              {facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || "未填写"}</dd></div>)}
            </dl>
            {texts.map(([label, value]) => (
              <section key={label}>
                <h3>{label}</h3>
                <p className={value?.trim() ? "" : "muted-copy"}>{value?.trim() || "未填写"}</p>
              </section>
            ))}
          </div>
        </Modal>
      )}
    </section>
  );
}
