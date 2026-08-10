import type { ReactNode } from "react";

export function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="settings-section">
      <div className="settings-section-heading">
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      <div className="settings-section-card">{children}</div>
    </section>
  );
}

export function SettingRow({
  title,
  description,
  wide = false,
  inlineControl = false,
  children,
}: {
  title: string;
  description?: string;
  wide?: boolean;
  inlineControl?: boolean;
  children: ReactNode;
}) {
  const className = [
    "setting-row",
    wide ? "setting-row-wide" : "",
    inlineControl ? "setting-row-inline-control" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={className}>
      <div className="setting-copy">
        <div className="setting-label">{title}</div>
        {description ? <div className="setting-description">{description}</div> : null}
      </div>
      <div className="setting-control">{children}</div>
    </div>
  );
}

export function NullableNumberInput({
  value,
  placeholder,
  min,
  max,
  step,
  ariaLabel,
  onChange,
}: {
  value: number | null;
  placeholder: string;
  min?: number;
  max?: number;
  step?: number;
  ariaLabel: string;
  onChange: (value: number | null) => void;
}) {
  return (
    <input
      className="settings-number-input"
      type="number"
      value={value ?? ""}
      placeholder={placeholder}
      min={min}
      max={max}
      step={step}
      aria-label={ariaLabel}
      onChange={(event) => {
        const next = event.target.value;
        onChange(next === "" ? null : Number(next));
      }}
    />
  );
}

export function StringListEditor({
  values,
  placeholder,
  addLabel,
  onChange,
}: {
  values: string[];
  placeholder: string;
  addLabel: string;
  onChange: (values: string[]) => void;
}) {
  return (
    <div className="settings-list-editor">
      {values.map((value, index) => (
        <div className="settings-list-row" key={`${index}-${value}`}>
          <input
            value={value}
            placeholder={placeholder}
            aria-label={`${addLabel} ${index + 1}`}
            onChange={(event) => {
              const next = [...values];
              next[index] = event.target.value;
              onChange(next);
            }}
          />
          <button
            className="settings-icon-button"
            type="button"
            aria-label={`删除${addLabel}`}
            onClick={() => onChange(values.filter((_, item) => item !== index))}
          >
            ×
          </button>
        </div>
      ))}
      <button
        className="settings-add-button"
        type="button"
        onClick={() => onChange([...values, ""])}
      >
        <span aria-hidden="true">＋</span>
        {addLabel}
      </button>
    </div>
  );
}
