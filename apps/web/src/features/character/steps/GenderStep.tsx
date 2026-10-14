import type { CharacterDraft } from "../../../types";
import type { DraftUpdater } from "../wizardSteps";

export function GenderStep({ draft, update }: { draft: CharacterDraft; update: DraftUpdater }) {
  const custom = draft.gender !== "男" && draft.gender !== "女";
  return (
    <div className="focused-form">
      <fieldset className="choice-field">
        <legend>性别</legend>
        <div>
          <label><input type="radio" name="gender-choice" checked={draft.gender === "男"} onChange={() => update("gender", "男")} /><span>男</span></label>
          <label><input type="radio" name="gender-choice" checked={draft.gender === "女"} onChange={() => update("gender", "女")} /><span>女</span></label>
          <label><input type="radio" name="gender-choice" checked={custom} onChange={() => update("gender", "")} /><span>其他描述</span></label>
        </div>
      </fieldset>
      {custom && <label className="field"><span>自定义性别</span><input autoFocus maxLength={80} value={draft.gender} placeholder="输入角色的性别描述" onChange={(e) => update("gender", e.target.value)} /></label>}
    </div>
  );
}
