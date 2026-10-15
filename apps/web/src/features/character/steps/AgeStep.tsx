import { useAutoFocus } from "../../../components/useAutoFocus";
import type { CharacterDraft, WorldCatalog } from "../../../types";
import type { DraftUpdater } from "../wizardSteps";

export function AgeStep({ catalog, draft, update }: { catalog: WorldCatalog; draft: CharacterDraft; update: DraftUpdater }) {
  const inputRef = useAutoFocus<HTMLInputElement>();
  const race = catalog.races.find((item) => item.id === draft.race_id);
  const branch = race?.branches?.find((item) => item.id === draft.race_branch_id);
  return (
    <div className="focused-form">
      <div className="rule-note">
        <span className="state-symbol" aria-hidden="true">i</span>
        <div>
          <strong>{branch?.name || race?.name || "所选种族"}寿命提示</strong>
          <p>{branch?.lifespan_text || race?.lifespan_text || "世界资料尚未提供寿命文案。"} 平均寿命不是年龄上限，系统不会据此自创成年年龄限制。</p>
        </div>
      </div>
      <label className="field compact">
        <span>年龄</span>
        <div className="input-suffix"><input ref={inputRef} type="number" min={1} max={99999} value={draft.age ?? ""} onChange={(e) => update("age", e.target.value ? Number(e.target.value) : null)} /><span>岁</span></div>
      </label>
    </div>
  );
}
