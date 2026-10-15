import { useAutoFocus } from "../../../components/useAutoFocus";
import { appendPreset, groupPresets, type PresetDefinition } from "../../../types";

export function PresetTextStep({ label, presets, raceId, value, update, placeholder, note }: {
  label: string;
  presets: PresetDefinition[];
  raceId: string;
  value: string;
  update: (value: string) => void;
  placeholder: string;
  note?: string;
}) {
  const textRef = useAutoFocus<HTMLTextAreaElement>();
  const available = presets.filter((preset) => !preset.race_ids?.length || preset.race_ids.includes(raceId));
  const groups = groupPresets(available);
  return (
    <div className="focused-form wide">
      {note && <div className="rule-note preset-note"><span className="state-symbol" aria-hidden="true">i</span><p>{note}</p></div>}
      <div className="preset-section">
        <span className="field-label">点选预设词</span>
        {groups.length ? (
          <div className="preset-groups">
            {groups.map((group) => (
              <section className="preset-group" key={group.category} aria-labelledby={`preset-${group.category}`}>
                <h3 id={`preset-${group.category}`}>{group.category}</h3>
                <div className="preset-list">
                  {group.items.map((preset) => <button type="button" key={preset.id} onClick={() => update(appendPreset(value, preset.label))}>＋ {preset.label}</button>)}
                </div>
              </section>
            ))}
          </div>
        ) : <p className="muted-copy">这个种族暂时没有可用的预设词，你可以自由填写。</p>}
      </div>
      <label className="field">
        <span>{label}</span>
        <textarea ref={textRef} rows={8} maxLength={2000} value={value} placeholder={placeholder} onChange={(e) => update(e.target.value)} />
        <small className="char-count">{value.length} / 2000，加入的词也可以直接修改</small>
      </label>
    </div>
  );
}
