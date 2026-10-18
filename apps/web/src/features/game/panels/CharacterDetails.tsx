import { useState } from "react";
import { Icon } from "../../../components/Icon";
import { Modal } from "../../../components/Modal";
import { useAutoFocus } from "../../../components/useAutoFocus";
import { chineseRankNumeral, type CharacterState, type WorldCatalog } from "../../../types";

/** Same limit as the 其他补充 step in character creation. */
const ADDITIONAL_MAX_LENGTH = 4000;

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
  ] as const;
  return { facts, texts };
}

/**
 * "角色详细信息" section of the Character tab: a button that opens a dialog with everything chosen
 * and written in character creation. The last part, 其他补充, stays editable during play.
 */
export function CharacterDetails({ character, catalog, editLocked, onSaveAdditional }: {
  character: CharacterState;
  catalog: WorldCatalog;
  editLocked: boolean;
  onSaveAdditional: (additional: string) => Promise<boolean>;
}) {
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
            <AdditionalSetting value={character.identity.additional ?? ""} locked={editLocked} onSave={onSaveAdditional} />
          </div>
        </Modal>
      )}
    </section>
  );
}

function AdditionalSetting({ value, locked, onSave }: { value: string; locked: boolean; onSave: (additional: string) => Promise<boolean> }) {
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const focusRef = useAutoFocus<HTMLTextAreaElement>();
  const editing = draft !== null;
  const unchanged = draft?.trim() === value.trim();
  const save = async () => {
    if (draft === null || unchanged) return;
    setSaving(true);
    const saved = await onSave(draft);
    setSaving(false);
    if (saved) setDraft(null);
  };
  return (
    <section className="additional-setting">
      <div className="additional-heading">
        <h3 id="additional-setting-label">其他补充</h3>
        {!editing && (
          <button type="button" className="text-button" disabled={locked} onClick={() => setDraft(value)}>
            <Icon name="edit" />修改
          </button>
        )}
      </div>
      {editing ? (
        <>
          <label className="field">
            <textarea ref={focusRef} aria-labelledby="additional-setting-label" rows={7} maxLength={ADDITIONAL_MAX_LENGTH} value={draft} disabled={saving}
              placeholder="补充或改写角色设定，例如习惯、旧伤、人际关系、想让故事记住的细节。" onChange={(event) => setDraft(event.target.value)} />
            <small className="char-count">{draft.length} / {ADDITIONAL_MAX_LENGTH}</small>
          </label>
          <div className="form-actions">
            <span className="cost-note">保存后从下一段剧情开始生效。数值、物品和能力仍要在剧情中获得。</span>
            <button type="button" className="secondary-button" disabled={saving} onClick={() => setDraft(null)}>取消</button>
            <button type="button" className="primary-button" disabled={saving || locked || unchanged} onClick={() => void save()}>{saving ? "正在保存…" : "保存"}</button>
          </div>
        </>
      ) : (
        <>
          <p className={value.trim() ? "" : "muted-copy"}>{value.trim() || "未填写"}</p>
          {locked && <small className="additional-locked">剧情生成中，完成后可以修改。</small>}
        </>
      )}
    </section>
  );
}
