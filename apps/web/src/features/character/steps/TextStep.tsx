import { useAutoFocus } from "../../../components/useAutoFocus";
export function TextStep({ label, value, onChange, maxLength, placeholder, optional = false, multiline = false }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  maxLength: number;
  placeholder: string;
  optional?: boolean;
  multiline?: boolean;
}) {
  const textRef = useAutoFocus<HTMLTextAreaElement>();
  const inputRef = useAutoFocus<HTMLInputElement>();
  return (
    <div className="focused-form">
      <label className="field">
        <span>{label}{optional && <small>（可选）</small>}</span>
        {multiline
          ? <textarea ref={textRef} rows={9} maxLength={maxLength} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
          : <input ref={inputRef} maxLength={maxLength} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />}
        <small className="char-count">{value.length} / {maxLength}</small>
      </label>
    </div>
  );
}
