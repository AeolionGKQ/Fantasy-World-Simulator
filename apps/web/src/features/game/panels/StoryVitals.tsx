import { useState, type CSSProperties } from "react";
import type { CharacterState } from "../../../types";
import { resourceCondition, resourceFill, resourceLevel, type ResourceKey } from "../helpers";

const vitals = [["hp", "生命"], ["mp", "魔力"], ["sp", "精神"], ["st", "精力"]] as const;

/**
 * Compact HP/MP/SP/ST bars beside the story heading; the Character tab keeps the full breakdown.
 * Hovering a row (or tapping it on touch screens) swaps its bar for the numbers.
 */
export function StoryVitals({ resources }: { resources: CharacterState["resources"] }) {
  const [shown, setShown] = useState<ReadonlySet<ResourceKey>>(() => new Set());
  const toggle = (key: ResourceKey) => setShown((current) => {
    const next = new Set(current);
    if (!next.delete(key)) next.add(key);
    return next;
  });
  return (
    <section className="story-vitals" aria-label="角色当前状态">
      {vitals.map(([key, label], index) => {
        const { current, max } = resources[key];
        const condition = resourceCondition(current, max);
        return (
          <button type="button" className="story-vital" key={key} aria-pressed={shown.has(key)} aria-label={`${label} ${current}/${max}，${condition}`} onClick={() => toggle(key)}>
            <span>{label}</span>
            <span className="vital-slot" aria-hidden="true">
              <span className="resource-bar"><span data-level={resourceLevel[condition]} style={{ "--fill": resourceFill(current, max), "--i": index } as CSSProperties} /></span>
              <strong>{current}/{max}</strong>
            </span>
          </button>
        );
      })}
    </section>
  );
}
