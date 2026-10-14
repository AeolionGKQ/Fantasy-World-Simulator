import { useState } from "react";
import type { StartPrerequisite, StartPrerequisiteResolution, WorldCatalog } from "../../../types";

const requirementNames: Record<string, string> = {
  underwater_breathing: "水下呼吸能力",
  pressure_protection: "深水压力防护",
  heat_protection: "高温防护",
  environment_protection: "极端环境防护",
  elf_forest_entry_permission: "精灵之森通行许可",
};

export function StartPrerequisitePanel({ prerequisite, catalog, busy, onResolve }: {
  prerequisite: StartPrerequisite;
  catalog: WorldCatalog;
  busy: boolean;
  onResolve: (resolution: StartPrerequisiteResolution, locationId: string | null) => void;
}) {
  const relocate = prerequisite.options.find((item) => item.kind === "relocate");
  const acceptsLegacy = prerequisite.options.some((item) => item.kind === "accept_legacy_protection");
  const locations = relocate?.kind === "relocate" ? relocate.location_ids.map((id) => catalog.locations.find((item) => item.id === id)).filter((item): item is NonNullable<typeof item> => Boolean(item)) : [];
  const [locationId, setLocationId] = useState(locations[0]?.id ?? "");
  return (
    <section className="start-prerequisite" aria-labelledby="start-prerequisite-title">
      <div className="prerequisite-copy">
        <span className="state-symbol" aria-hidden="true">!</span>
        <div>
          <h2 id="start-prerequisite-title">开始前，请确认角色如何进入起点</h2>
          <p>角色进入当前起点需要下列防护或通行许可。你可以确认使用旧存档所需的防护与许可，或更换起点后开始冒险。</p>
          <ul>{prerequisite.requirements.map((requirement) => <li key={requirement}>{requirementNames[requirement] ?? requirement}</li>)}</ul>
          <p className="command-note">这些防护与许可用于让旧存档继续冒险，不代表角色在故事中获得了人物赠送的物品或能力。</p>
        </div>
      </div>
      <div className="prerequisite-actions">
        {acceptsLegacy && (
          <section>
            <h3>保留当前起点</h3>
            <p>确认使用上述防护或许可，让角色从原地点继续冒险。</p>
            <button className="secondary-button" type="button" disabled={busy} onClick={() => onResolve("accept_legacy_protection", null)}>确认并保留起点</button>
          </section>
        )}
        {locations.length > 0 && (
          <section>
            <h3>更换起点</h3>
            <label className="field">
              <span>可选起点</span>
              <select value={locationId} disabled={busy} onChange={(event) => setLocationId(event.target.value)}>
                {locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}
              </select>
            </label>
            <button className="primary-button" type="button" disabled={busy || !locationId} onClick={() => onResolve("relocate", locationId)}>确认新起点</button>
          </section>
        )}
      </div>
    </section>
  );
}
