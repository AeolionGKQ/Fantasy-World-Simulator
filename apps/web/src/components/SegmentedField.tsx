export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

/**
 * Radio group rendered as a segmented control (`.segmented-field`).
 * `full` spans both columns of a settings form grid; `name` defaults to the label.
 */
export function SegmentedField<T extends string>({ label, value, options, disabled = false, onChange, name = label, full = true }: {
  label: string;
  value: T;
  options: ReadonlyArray<SegmentedOption<T>>;
  disabled?: boolean;
  onChange: (value: T) => void;
  name?: string;
  full?: boolean;
}) {
  return (
    <fieldset className={full ? "segmented-field full" : "segmented-field"} disabled={disabled}>
      <legend>{label}</legend>
      <div>
        {options.map((option) => (
          <label key={option.value}>
            <input type="radio" name={name} value={option.value} checked={value === option.value} onChange={() => onChange(option.value)} />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
