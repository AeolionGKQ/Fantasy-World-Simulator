import { flushSync } from "react-dom";
import { runViewTransition } from "../../../app/viewTransition";
import { ResponsiveArtwork } from "../../../components/ResponsiveArtwork";
import type { CharacterDraft, WorldCatalog } from "../../../types";
import type { DraftUpdater } from "../wizardSteps";
import { WorldInfoSection } from "./WorldInfoSection";

export function LocationStep({ catalog, draft, update }: { catalog: WorldCatalog; draft: CharacterDraft; update: DraftUpdater }) {
  const selected = catalog.locations.find((location) => location.id === draft.location_id) ?? catalog.locations[0];
  return (
    <div className="world-browser">
      <div className="option-track location-track" role="radiogroup" aria-label="初始地点">
        {catalog.locations.map((location) => (
          <label key={location.id} className={location.disabled ? "disabled" : ""}>
            <input type="radio" name="location" disabled={location.disabled} checked={draft.location_id === location.id} onChange={() => runViewTransition("world", () => flushSync(() => update("location_id", location.id)))} />
            <span>{location.name}</span>
          </label>
        ))}
      </div>
      {selected && (
        <article className="world-profile world-entry">
          <ResponsiveArtwork key={selected.id} item={selected} alt={`${selected.name}地点设定图`} kind="地点" />
          <div className="world-reading">
            <header className="world-heading"><span className="world-label">地点资料</span><h3>{selected.name}</h3><p>{selected.tagline}</p></header>
            <dl className="world-facts">
              <div><dt>所在区域</dt><dd>{selected.region}</dd></div>
              <div><dt>环境</dt><dd>{selected.environment}</dd></div>
            </dl>
            <p className="world-description">{selected.description}</p>
            <div className="world-sections">
              <WorldInfoSection title="区域结构" text={selected.structure} />
              <WorldInfoSection title="特色" items={selected.highlights} />
              <WorldInfoSection title="交通与访问" text={selected.transport} extra={selected.access_note} />
              <WorldInfoSection title="特殊说明" text={selected.arrival_point} items={selected.safeguards} tone="notice" />
            </div>
            {selected.warning && <p className="warning-text">注意：{selected.warning}</p>}
          </div>
        </article>
      )}
    </div>
  );
}
