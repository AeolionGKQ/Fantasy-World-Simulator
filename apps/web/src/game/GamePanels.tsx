import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import type {
  Bond, CharacterState, InventoryProjection, JournalEntry, MemoryProjection, NarrativeJob,
  Quest, ReputationProjection, StartPrerequisite, StartPrerequisiteResolution, StoryArc, StoryView, Turn, WorldCatalog,
} from "../types";
import { currentArcMerge, isNarrativeJobActive, isStoryReadOnly, narrativeJobMessage, orderReputations, reputationNames, resourceCondition, resourceExhaustion, visibleAuthoritativeChanges } from "./helpers";

export type GameTab = "story" | "character" | "inventory" | "quests" | "journals" | "memory" | "bonds" | "reputations";

export const gameTabs: Array<{ id: GameTab; label: string }> = [
  { id: "story", label: "剧情" }, { id: "character", label: "角色" },
  { id: "inventory", label: "背包" }, { id: "quests", label: "任务栏" },
  { id: "journals", label: "纪事" }, { id: "memory", label: "记忆管理" },
  { id: "bonds", label: "羁绊" }, { id: "reputations", label: "声望" },
];

function Empty({ title, children }: { title: string; children: ReactNode }) {
  return <div className="game-empty"><span aria-hidden="true">◇</span><h3>{title}</h3><p>{children}</p></div>;
}

export function StoryPanel({ story, turns, viewedTurn, busy, catalog, onNavigate, onOpen, onResolvePrerequisite, onTurn, onIntervene, onReshape, onCancel }: {
  story: StoryView; turns: Turn[]; viewedTurn: Turn | null; busy: boolean;
  catalog: WorldCatalog;
  onNavigate: (turn: Turn) => void; onOpen: (guidance: string) => void;
  onResolvePrerequisite: (resolution: StartPrerequisiteResolution, locationId: string | null) => void;
  onTurn: (action: string, optionId: string | null) => void; onIntervene: (guidance: string) => void;
  onReshape: (guidance: string) => void; onCancel: () => void;
}) {
  const [action, setAction] = useState("");
  const [guidance, setGuidance] = useState("");
  const [mode, setMode] = useState<"action" | "intervene" | "reshape">("action");
  const turn = viewedTurn ?? story.latest_turn;
  const turnIndex = turn ? turns.findIndex((item) => item.id === turn.id) : -1;
  const displayedChanges = turn ? visibleAuthoritativeChanges(turn.authoritative_changes) : [];
  const readOnly = turn ? isStoryReadOnly(turn, story.latest_turn?.id ?? null, story.active_job) : busy;
  useEffect(() => {
    setAction("");
    setGuidance("");
  }, [story.latest_turn?.id]);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = mode === "action" ? action.trim() : guidance.trim();
    if (!value) return;
    if (mode === "action") onTurn(value, null);
    else if (mode === "intervene") onIntervene(value);
    else onReshape(value);
  };
  if (!turn && story.start_prerequisite?.status === "required") return <StartPrerequisitePanel prerequisite={story.start_prerequisite} catalog={catalog} busy={busy} onResolve={onResolvePrerequisite} />;
  if (!turn) return <section className="story-start"><span className="archive-glyph" aria-hidden="true">◇</span><div><h2>故事尚未落笔</h2><p>GM 会根据你的角色、世界设定和叙事偏好写下开场。你也可以填写想从哪里开始。等待时可查看其他页签。</p><label className="field"><span>开场引导 <small>可选</small></span><textarea maxLength={12000} value={guidance} onChange={(event) => setGuidance(event.target.value)} placeholder="例如：从抵达城市后的清晨开始。" /></label><button className="primary-button" type="button" disabled={busy} onClick={() => onOpen(guidance.trim())}>{busy ? "正在生成…" : "开始冒险"}</button></div></section>;
  return <div className="story-layout">
    <article className="story-reading">
      <header className="story-heading"><div className="scene-meta"><span>{story.state.time.label}</span><span>{story.state.location.name}</span><span>第 {turn.sequence} 段</span>{readOnly && !isNarrativeJobActive(story.active_job) && <strong>正在回看</strong>}</div><h2>{turn.title}</h2></header>
      <div className="story-body">{turn.body.split(/\n+/).filter(Boolean).map((paragraph, index) => <p key={`${turn.id}-${index}`}>{paragraph}</p>)}</div>
      {turn.warnings && turn.warnings.length > 0 && <section className="gm-warnings" aria-label="叙事提示"><h3>GM 提示</h3>{turn.warnings.map((warning) => <p key={warning}>{warning}</p>)}</section>}
      {displayedChanges.length > 0 && <details className="changes" open><summary>本段带来的变化 · {displayedChanges.length}</summary><ul>{displayedChanges.map((change, index) => <li key={`${change.label}-${index}`}><strong>{change.label}</strong><span>{change.value}</span><small>{change.reason}</small></li>)}</ul></details>}
      <nav className="history-nav" aria-label="剧情历史"><button className="secondary-button" type="button" disabled={turnIndex <= 0} onClick={() => { const previous = turns[turnIndex - 1]; if (previous) onNavigate(previous); }}>上一段</button><span>{turnIndex + 1} / {turns.length}</span><button className="secondary-button" type="button" disabled={turnIndex < 0 || turnIndex >= turns.length - 1} onClick={() => { const next = turns[turnIndex + 1]; if (next) onNavigate(next); }}>下一段</button></nav>
    </article>
    <aside className="story-actions" aria-label="剧情操作">
      {story.active_job && isNarrativeJobActive(story.active_job) && <JobPanel job={story.active_job} onCancel={onCancel} />}
      {!story.active_job && turn.suggested_options.length > 0 && <section><h3>建议行动</h3><div className="option-list">{turn.suggested_options.map((option) => <button className="option-button" type="button" key={option.id} disabled={readOnly} onClick={() => onTurn(option.text, option.id)}><strong>{option.text}</strong><span>{option.intent}</span></button>)}</div></section>}
      <form className="story-command" onSubmit={submit}><div className="command-modes" role="group" aria-label="叙事操作类型"><button type="button" className={mode === "action" ? "active" : ""} onClick={() => setMode("action")}>自由行动</button><button type="button" className={mode === "intervene" ? "active" : ""} onClick={() => setMode("intervene")}>干涉命运</button><button type="button" className={mode === "reshape" ? "active" : ""} onClick={() => setMode("reshape")}>重塑命运</button></div><label className="field"><span>{mode === "action" ? "你的行动" : mode === "intervene" ? "命运引导" : "改写要求"}</span><textarea maxLength={12000} disabled={readOnly} value={mode === "action" ? action : guidance} onChange={(event) => mode === "action" ? setAction(event.target.value) : setGuidance(event.target.value)} placeholder={readOnly ? "请回到最新剧情，并等待当前生成结束后再行动。" : mode === "action" ? "描述角色想做的事，例如向店主打听消息。" : mode === "intervene" ? "描述你希望接下来发生什么。" : "说明最近一段剧情需要怎样改写。"} /></label><button className={mode === "action" ? "primary-button" : "secondary-button"} disabled={readOnly || !(mode === "action" ? action : guidance).trim()}>{mode === "action" ? "提交行动" : mode === "intervene" ? "干涉命运" : "重塑命运"}</button>{mode === "intervene" && <p className="command-note">向 GM 提出后续故事的走向，不会重写已有剧情。</p>}{mode === "reshape" && <p className="command-note">重塑会重写最近一段剧情，并撤销这一段造成的变化。</p>}</form>
    </aside>
  </div>;
}

const requirementNames: Record<string, string> = {
  underwater_breathing: "水下呼吸能力",
  pressure_protection: "深水压力防护",
  heat_protection: "高温防护",
  environment_protection: "极端环境防护",
  elf_forest_entry_permission: "精灵之森通行许可",
};

function StartPrerequisitePanel({ prerequisite, catalog, busy, onResolve }: { prerequisite: StartPrerequisite; catalog: WorldCatalog; busy: boolean; onResolve: (resolution: StartPrerequisiteResolution, locationId: string | null) => void }) {
  const relocate = prerequisite.options.find((item) => item.kind === "relocate");
  const acceptsLegacy = prerequisite.options.some((item) => item.kind === "accept_legacy_protection");
  const locations = relocate?.kind === "relocate" ? relocate.location_ids.map((id) => catalog.locations.find((item) => item.id === id)).filter((item): item is NonNullable<typeof item> => Boolean(item)) : [];
  const [locationId, setLocationId] = useState(locations[0]?.id ?? "");
  return <section className="start-prerequisite" aria-labelledby="start-prerequisite-title"><div className="prerequisite-copy"><span className="state-symbol" aria-hidden="true">!</span><div><h2 id="start-prerequisite-title">开始前，请确认角色如何进入起点</h2><p>角色进入当前起点需要下列防护或通行许可。你可以确认使用旧存档所需的防护与许可，或更换起点后开始冒险。</p><ul>{prerequisite.requirements.map((requirement) => <li key={requirement}>{requirementNames[requirement] ?? requirement}</li>)}</ul><p className="command-note">这些防护与许可用于让旧存档继续冒险，不代表角色在故事中获得了人物赠送的物品或能力。</p></div></div><div className="prerequisite-actions">{acceptsLegacy && <section><h3>保留当前起点</h3><p>确认使用上述防护或许可，让角色从原地点继续冒险。</p><button className="secondary-button" type="button" disabled={busy} onClick={() => onResolve("accept_legacy_protection", null)}>确认并保留起点</button></section>}{locations.length > 0 && <section><h3>更换起点</h3><label className="field"><span>可选起点</span><select value={locationId} disabled={busy} onChange={(event) => setLocationId(event.target.value)}>{locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label><button className="primary-button" type="button" disabled={busy || !locationId} onClick={() => onResolve("relocate", locationId)}>确认新起点</button></section>}</div></section>;
}

export function JobPanel({ job, onCancel, cancellable = true }: { job: NarrativeJob; onCancel: () => void; cancellable?: boolean }) {
  const active = isNarrativeJobActive(job);
  return <section className={`narrative-job ${job.status}`} role="status" aria-live="polite"><div className="job-title"><span className="status-dot busy" aria-hidden="true" /><div><strong>{job.type === "turns_to_arc" || job.type === "arcs_to_arc" ? "正在整理故事弧" : "正在书写剧情"}</strong><small>{job.status === "queued" ? "等待开始生成" : job.status === "cancel_requested" ? "正在取消" : "正在生成"}</small></div></div><p>{narrativeJobMessage(job)}</p>{active && cancellable && <button className="secondary-button" type="button" disabled={job.status === "cancel_requested"} onClick={onCancel}>{job.status === "cancel_requested" ? "正在取消…" : "取消任务"}</button>}</section>;
}

export function CharacterPanel({ character, catalog, playerAddress, addressBusy, onPlayerAddress }: { character: CharacterState; catalog: WorldCatalog; playerAddress: "full_name" | "given_name" | "second_person"; addressBusy: boolean; onPlayerAddress: (value: "full_name" | "given_name" | "second_person") => void }) {
  const identity = character.identity;
  const race = catalog.races.find((item) => item.id === identity.race_id);
  const raceBranch = race?.branches?.find((item) => item.id === identity.race_branch_id);
  const resources = [["生命 HP", "hp"], ["魔力 MP", "mp"], ["精神 SP", "sp"], ["精力 ST", "st"]] as const;
  const attributes = [["体质 CON", "con"], ["智力 INT", "int"], ["魅力 CHA", "cha"]] as const;
  return <div className="projection-page"><header className="projection-header"><div><span className="ready-mark">{character.alive ? "存活" : "已死亡"}</span><h2>{identity.name || "未命名角色"}</h2><p>{[identity.gender, identity.age ? `${identity.age} 岁` : null, race?.name ?? identity.race_id, raceBranch?.name ?? identity.race_branch_id, character.profession, character.growth_path].filter(Boolean).join(" · ") || "尚无职业与成长路径"}</p></div><strong className="rank-mark">{character.rank} 阶</strong></header><section className="status-strip">{resources.map(([label, key]) => { const resource = character.resources[key]; const condition = resourceCondition(resource.current, resource.max); return <div key={key}><span>{label}</span><strong>{resource.current} / {resource.max}</strong><meter min={0} max={resource.max} value={resource.current} aria-label={`${label} ${resource.current}/${resource.max}，${condition}`} /><small className={`resource-condition ${condition === "耗尽" ? "exhausted" : ""}`}>{condition}</small><small>{condition === "耗尽" ? resourceExhaustion[key] : resource.reason}</small></div>; })}</section><div className="projection-columns"><div><section className="plain-section"><h3>长期属性</h3><dl className="attribute-list">{attributes.map(([label, key]) => <div key={key}><dt>{label}</dt><dd>{character.attributes[key].value}</dd><small>{character.attributes[key].reason}</small></div>)}</dl></section><AbilitySection title="天赋" items={character.talents} empty="尚未获得天赋。" /><AbilitySection title="技能" items={character.skills} empty="尚未习得技能。" /></div><aside><section className="plain-section"><h3>存档叙事设置</h3><fieldset className="segmented-field" disabled={addressBusy}><legend>GM对玩家角色的称呼</legend><div>{([{ value: "full_name", label: "全名" }, { value: "given_name", label: "名字" }, { value: "second_person", label: "你" }] as const).map((option) => <label key={option.value}><input type="radio" name="存档GM称呼" checked={playerAddress === option.value} onChange={() => onPlayerAddress(option.value)} /><span>{option.label}</span></label>)}</div></fieldset><p className="projection-footnote">选择 GM 在这个存档中使用全名、名字或“你”来称呼角色。故事中的人物会按各自的关系和场合称呼你。</p></section><section className="plain-section"><h3>成长</h3><dl className="key-values"><div><dt>EXP</dt><dd>{character.exp}{character.exp_to_next !== null ? ` / ${character.exp_to_next}` : " · 已达最高阶"}</dd></div><div><dt>突破资格</dt><dd>{character.breakthrough_eligible ? "已具备" : "未具备"}</dd></div></dl></section><section className="plain-section"><h3>战力构成</h3><dl className="key-values"><div><dt>基础战力</dt><dd>{character.base_power.toLocaleString()}</dd></div><div><dt>装备战力</dt><dd>{character.equipment_power.toLocaleString()}</dd></div><div className="effective"><dt>有效战力</dt><dd>{character.effective_power.toLocaleString()}</dd></div></dl>{character.power_modifiers.length > 0 && <ul className="detail-list">{character.power_modifiers.map((item) => <li key={item.id}><strong>{item.value >= 0 ? "+" : ""}{item.value}</strong><span>{item.reason}{item.temporary ? "（临时）" : ""}</span></li>)}</ul>}</section></aside></div></div>;
}

function AbilitySection({ title, items, empty }: { title: string; items: CharacterState["skills"]; empty: string }) {
  return <section className="plain-section"><h3>{title}</h3>{items.length ? <ul className="detail-list">{items.map((item) => <li key={item.id}><strong>{item.name}</strong><span>{item.description}</span><small>{item.source}</small></li>)}</ul> : <p className="muted-copy">{empty}</p>}</section>;
}

export function InventoryPanel({ inventory }: { inventory: InventoryProjection }) {
  return <div className="projection-page"><header className="projection-header"><div><h2>背包</h2><p>{inventory.items.length} 类物品</p></div><dl className="currency"><div><dt>金币</dt><dd>{inventory.currency.gold}</dd></div><div><dt>银币</dt><dd>{inventory.currency.silver}</dd></div><div><dt>铜币</dt><dd>{inventory.currency.copper}</dd></div></dl></header>{inventory.items.length ? <ul className="inventory-list">{inventory.items.map((item) => <li key={item.id}><div><strong>{item.name}</strong>{item.equipped && <span className="equipped-mark">已装备</span>}<p>{item.description}</p><small>来源：{item.source}</small></div><div className="item-data"><strong>× {item.quantity}</strong><span>战力 {item.power >= 0 ? "+" : ""}{item.power}</span></div></li>)}</ul> : <Empty title="背包尚空">冒险中获得的物品会列在这里。你持有的金币、银币和铜币显示在上方。</Empty>}</div>;
}

export function QuestsPanel({ active }: { active: Quest[] }) {
  return <div className="projection-page"><header className="projection-header"><div><h2>任务栏</h2><p>进行中 {active.length} 项</p></div></header><QuestList title="进行中" items={active} empty="当前没有进行中的任务。" /></div>;
}

function QuestList({ title, items, empty }: { title: string; items: Quest[]; empty: string }) {
  const statusNames: Record<string, string> = { offered: "待接受", active: "进行中", completed: "已完成", declined: "已拒绝", failed: "已失败", abandoned: "已放弃" };
  return <section className="plain-section"><h3>{title}</h3>{items.length ? <ul className="record-list">{items.map((quest) => <li key={quest.id}><div className="record-heading"><strong>{quest.name}</strong><span>{statusNames[quest.status] ?? quest.status}{quest.regional ? " · 地区" : ""}</span></div><p>{quest.description}</p>{quest.progress && <p className="progress-copy">进度：{quest.progress}</p>}{quest.objectives.length > 0 && <ul>{quest.objectives.map((objective) => <li key={objective}>{objective}</li>)}</ul>}</li>)}</ul> : <p className="muted-copy">{empty}</p>}</section>;
}

export function JournalsPanel({ items, onRead }: { items: JournalEntry[]; onRead: (turnId: string) => void }) {
  return <div className="projection-page"><header className="projection-header"><div><h2>纪事</h2><p>回顾每一段冒险的经过，点击记录可查看完整剧情。</p></div></header>{items.length ? <ol className="chronicle-list">{[...items].reverse().map((item) => <li key={item.turn_id}><button type="button" onClick={() => onRead(item.turn_id)}><span>{item.sequence}</span><strong>{item.title}</strong><p>{item.summary}</p></button></li>)}</ol> : <Empty title="纪事尚未开始">开始冒险后，每段剧情都会自动留下一条记录。</Empty>}</div>;
}

export function MemoryPanel({ memory, memories, arcBusy, arcJob, onMerge }: { memory: MemoryProjection; memories: import("../types").MemoryEntry[]; arcBusy: boolean; arcJob: NarrativeJob | null; onMerge: (ids: string[]) => void }) {
  const currentArcs = memory.story_arcs.filter((arc) => arc.status === "current").sort((a, b) => a.start_sequence - b.start_sequence);
  const merge = currentArcMerge(currentArcs);
  return <div className="projection-page"><header className="projection-header"><div><h2>记忆管理</h2><p>将较早的经历整理成摘要，帮助 GM 记住你的旅程。完整剧情仍可回看。</p></div><div className="arc-merge-action"><button className="secondary-button" type="button" disabled={arcBusy || !merge.valid} onClick={() => onMerge(merge.arcIds)}>{arcBusy ? "正在合并故事弧…" : merge.label}</button><small>{merge.message}</small></div></header>{arcJob && isNarrativeJobActive(arcJob) && <JobPanel job={arcJob} onCancel={() => undefined} cancellable={false} />}<div className="memory-policy"><span>近期剧情 {memory.recent_full_turns.length} / {memory.policy.recent_full_count}</span><span>待整理记录 {memory.summary_buffer.length}</span><span>故事弧 {currentArcs.length}</span></div><section className="plain-section"><div className="section-line"><h3>故事弧</h3></div>{memory.story_arcs.length ? <ul className="arc-list">{memory.story_arcs.map((arc) => <ArcRow key={arc.id} arc={arc} />)}</ul> : <p className="muted-copy">较早的剧情积累到连续 25 段后，会自动整理成一个故事弧，概括这一段旅程。</p>}</section><section className="plain-section"><h3>长期记忆</h3>{memories.length ? <ol className="memory-list">{memories.map((item) => <li key={item.id}><span className="memory-number" aria-label={`长期记忆 ${item.memory_number}`}>{item.memory_number}</span><div><strong>{item.summary}</strong><span>重要度 {item.importance}</span></div>{item.recall_reason && <p className="recall-reason">与本轮剧情相关：{item.recall_reason}</p>}{item.facts.length > 0 && <p>{item.facts.join("；")}</p>}{item.unresolved.length > 0 && <small>尚未解决：{item.unresolved.join("；")}</small>}</li>)}</ol> : <p className="muted-copy">当前没有需要长期保留的记忆。</p>}</section></div>;
}

function ArcRow({ arc }: { arc: StoryArc }) { return <li><div className="record-heading"><strong>{arc.title}</strong><span>第 {arc.start_sequence} 至 {arc.end_sequence} 段 · {arc.status === "current" ? "正在使用" : "已合并到后续摘要"}</span></div><p>{arc.summary}</p>{arc.key_events.length > 0 && <small>关键事件：{arc.key_events.join("；")}</small>}{arc.unresolved.length > 0 && <small>尚未解决：{arc.unresolved.join("；")}</small>}</li>; }

export function BondsPanel({ items }: { items: Bond[] }) {
  return <div className="projection-page"><header className="projection-header"><div><h2>羁绊</h2><p>查看与你建立了持续关系的重要人物，以及他们对你的好感。</p></div></header>{items.length ? <ul className="relationship-list">{items.map((bond) => <li key={bond.id}><div><strong>{bond.npc_name}</strong><span>{bond.relation_type} · {bond.level ?? "普通/陌生"}</span></div><meter min={-100} max={100} low={-20} high={50} optimum={100} value={bond.value} aria-label={`${bond.npc_name} 羁绊 ${bond.value}`} /><b>{bond.value > 0 ? "+" : ""}{bond.value}</b></li>)}</ul> : <Empty title="尚未建立羁绊">重要人物在形成持续关系后会列入此处。</Empty>}</div>;
}

export function ReputationsPanel({ data }: { data: ReputationProjection }) {
  const items = orderReputations(data.items, data.local_modifier_key);
  return <div className="projection-page"><header className="projection-header"><div><h2>声望</h2><p>查看你在大陆和各方势力中的声望。不同势力会分别评价你的行动。</p></div></header><ul className="reputation-list">{items.map((item) => <li className={`${item.key === data.primary_key ? "primary" : ""} ${item.local ? "local" : ""}`} key={item.key}><div><strong>{reputationNames[item.key]}</strong><span>{item.level}{item.local ? " · 当前地区相关" : ""}</span></div><meter min={-100} max={100} low={-20} high={50} optimum={100} value={item.value} aria-label={`${reputationNames[item.key]} ${item.value}`} /><b>{item.value > 0 ? "+" : ""}{item.value}</b></li>)}</ul><p className="projection-footnote">大陆综合声望显示在最前面，当前所在地区对应的势力会突出显示。</p></div>;
}
