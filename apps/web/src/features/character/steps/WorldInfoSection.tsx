/** One titled block of location/faction lore: optional paragraphs followed by an optional list. */
export function WorldInfoSection({ title, text, extra, items, tone }: { title: string; text?: string; extra?: string; items?: string[]; tone?: "notice" }) {
  return (
    <section className={`world-section ${tone || ""}`}>
      <h4>{title}</h4>
      {text && <p>{text}</p>}
      {extra && <p>{extra}</p>}
      {items?.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : null}
    </section>
  );
}
