import { ResponsiveArtwork } from "../../../components/ResponsiveArtwork";
import type { FactionDefinition } from "../../../types";
import { WorldInfoSection } from "./WorldInfoSection";

export function FactionStep({ factions, activeId, setActiveId }: { factions: FactionDefinition[]; activeId: string; setActiveId: (id: string) => void }) {
  const selected = factions.find((faction) => faction.id === activeId) ?? factions[0];
  if (!selected) {
    return <div className="empty-state compact"><h3>暂无势力资料</h3><p>世界资料接口未返回势力，但本步骤无需选择，可以直接继续。</p></div>;
  }
  return (
    <div className="world-browser">
      <div className="fixed-notice"><span aria-hidden="true">i</span><strong>本步骤无需选择；可在游戏过程中自由加入符合条件的势力</strong></div>
      <div className="option-track faction-track" role="tablist" aria-label="世界势力">
        {factions.map((faction) => (
          <button type="button" role="tab" id={`faction-tab-${faction.id}`} aria-controls={`faction-panel-${faction.id}`} key={faction.id} aria-selected={selected.id === faction.id} onClick={() => setActiveId(faction.id)}>{faction.name}</button>
        ))}
      </div>
      <article className="world-profile" role="tabpanel" id={`faction-panel-${selected.id}`} aria-labelledby={`faction-tab-${selected.id}`}>
        <ResponsiveArtwork key={selected.id} item={selected} alt={`${selected.name}势力设定图`} kind="势力" />
        <div className="world-reading">
          <header className="world-heading"><span className="world-label">势力资料 · 只读</span><h3>{selected.name}</h3><p>{selected.tagline}</p></header>
          <p className="world-description">{selected.description}</p>
          <div className="world-sections">
            <WorldInfoSection title="定位、理念与组织" text={selected.ideology} extra={selected.organization} />
            <WorldInfoSection title="总部或主要地区" text={selected.headquarters} />
            <WorldInfoSection title="任务与委托" items={selected.tasks} />
            <WorldInfoSection title="可使用服务" items={selected.services} />
            <WorldInfoSection title="可参与活动" items={selected.activities} />
            <WorldInfoSection title="奖励与资源" items={selected.rewards} />
            <WorldInfoSection title="公开对象与前置" text={selected.audience} extra={selected.access_note} tone="notice" />
          </div>
        </div>
      </article>
    </div>
  );
}
