import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { flushSync } from "react-dom";
import { scrollIntoViewIfAbove } from "../../../app/scroll";
import { runViewTransition } from "../../../app/viewTransition";
import { usePresence } from "../../../components/usePresence";
import { useSlidingIndicator } from "../../../components/useSlidingIndicator";
import type { StartPrerequisiteResolution, StoryView, Turn, WorldCatalog } from "../../../types";
import { isNarrativeJobActive, isStoryReadOnly, visibleAuthoritativeChanges } from "../helpers";
import { JobPanel } from "./JobPanel";
import { StartPrerequisitePanel } from "./StartPrerequisitePanel";

type CommandMode = "action" | "intervene" | "reshape";

/** Position in the arrival stagger (motion.css); capped so long turns do not keep the reader waiting. */
const stagger = (index: number) => ({ "--i": Math.min(index, 10) }) as CSSProperties;

/**
 * Returns the key of a turn that just arrived (a new latest turn, or a reshaped version of it) while
 * this panel was open, for about two seconds. Initial load and paging through history return null.
 */
function useArrivedTurn(latest: Turn | null) {
  const key = latest ? `${latest.id}:${latest.current_version_id}` : null;
  const seen = useRef(key);
  const [arrived, setArrived] = useState<string | null>(null);
  useEffect(() => {
    if (!key || key === seen.current) return;
    seen.current = key;
    setArrived(key);
    // Bring the new title into view if the reader had scrolled past the top of the column.
    requestAnimationFrame(() => scrollIntoViewIfAbove(".story-reading", "smooth"));
    const timer = window.setTimeout(() => setArrived(null), 2000);
    return () => window.clearTimeout(timer);
  }, [key]);
  return arrived;
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
  const [mode, setMode] = useState<CommandMode>("action");
  const turn = viewedTurn ?? story.latest_turn;
  const turnIndex = turn ? turns.findIndex((item) => item.id === turn.id) : -1;
  const displayedChanges = turn ? visibleAuthoritativeChanges(turn.authoritative_changes) : [];
  const readOnly = turn ? isStoryReadOnly(turn, story.latest_turn?.id ?? null, story.active_job) : busy;
  const arrivedKey = useArrivedTurn(story.latest_turn);
  const arriving = Boolean(turn && arrivedKey === `${turn.id}:${turn.current_version_id}`);
  const job = usePresence(story.active_job && isNarrativeJobActive(story.active_job) ? story.active_job : null);
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
  if (!turn && story.start_prerequisite?.status === "required") {
    return <StartPrerequisitePanel prerequisite={story.start_prerequisite} catalog={catalog} busy={busy} onResolve={onResolvePrerequisite} />;
  }
  if (!turn) {
    return (
      <section className="story-start">
        <span className="archive-glyph" aria-hidden="true">◇</span>
        <div>
          <h2>故事尚未落笔</h2>
          <p>GM 会根据你的角色、世界设定和叙事偏好写下开场。你也可以填写想从哪里开始。等待时可查看其他页签。</p>
          <label className="field"><span>开场引导 <small>可选</small></span><textarea maxLength={12000} value={guidance} onChange={(event) => setGuidance(event.target.value)} placeholder="例如：从抵达城市后的清晨开始。" /></label>
          <button className="primary-button" type="button" disabled={busy} onClick={() => onOpen(guidance.trim())}>{busy ? "正在生成…" : "开始冒险"}</button>
        </div>
      </section>
    );
  }
  return (
    <div className={`story-layout ${arriving ? "arriving" : ""}`}>
      <article className="story-reading">
        <header className="story-heading">
          <div className="scene-meta"><span>{story.state.time.label}</span><span>{story.state.location.name}</span><span>第 {turn.sequence} 段</span>{readOnly && !isNarrativeJobActive(story.active_job) && <strong>正在回看</strong>}</div>
          <h2 style={stagger(0)}>{turn.title}</h2>
        </header>
        <div className="story-body">{turn.body.split(/\n+/).filter(Boolean).map((paragraph, index) => <p key={`${turn.id}-${index}`} style={stagger(index + 1)}>{paragraph}</p>)}</div>
        {turn.warnings && turn.warnings.length > 0 && <section className="gm-warnings" aria-label="叙事提示"><h3>GM 提示</h3>{turn.warnings.map((warning) => <p key={warning}>{warning}</p>)}</section>}
        {displayedChanges.length > 0 && (
          <details className="changes" open style={stagger(11)}>
            <summary>本段带来的变化 · {displayedChanges.length}</summary>
            <ul>{displayedChanges.map((change, index) => <li key={`${change.label}-${index}`}><strong>{change.label}</strong><span>{change.value}</span><small>{change.reason}</small></li>)}</ul>
          </details>
        )}
        <nav className="history-nav" aria-label="剧情历史">
          <button className="secondary-button" type="button" disabled={turnIndex <= 0} onClick={() => { const previous = turns[turnIndex - 1]; if (previous) onNavigate(previous); }}>上一段</button>
          <span>{turnIndex + 1} / {turns.length}</span>
          <button className="secondary-button" type="button" disabled={turnIndex < 0 || turnIndex >= turns.length - 1} onClick={() => { const next = turns[turnIndex + 1]; if (next) onNavigate(next); }}>下一段</button>
        </nav>
      </article>
      <aside className="story-actions" aria-label="剧情操作">
        {job.current && <div className={job.leaving ? "job-leaving" : undefined}><JobPanel job={job.current} onCancel={onCancel} /></div>}
        {!story.active_job && turn.suggested_options.length > 0 && (
          <section>
            <h3>建议行动</h3>
            <div className="option-list">
              {turn.suggested_options.map((option) => <button className="option-button" type="button" key={option.id} style={stagger(turn.suggested_options.indexOf(option) + 2)} disabled={readOnly} onClick={() => onTurn(option.text, option.id)}><strong>{option.text}</strong><span>{option.intent}</span></button>)}
            </div>
          </section>
        )}
        <StoryCommandForm mode={mode} onModeChange={(next) => { if (next !== mode) runViewTransition("mode", () => flushSync(() => setMode(next))); }} value={mode === "action" ? action : guidance} onValueChange={mode === "action" ? setAction : setGuidance} readOnly={readOnly} onSubmit={submit} />
      </aside>
    </div>
  );
}

const commandModes: Array<{ id: CommandMode; label: string; field: string; placeholder: string; submit: string }> = [
  { id: "action", label: "自由行动", field: "你的行动", placeholder: "描述角色想做的事，例如向店主打听消息。", submit: "提交行动" },
  { id: "intervene", label: "干涉命运", field: "命运引导", placeholder: "描述你希望接下来发生什么。", submit: "干涉命运" },
  { id: "reshape", label: "重塑命运", field: "改写要求", placeholder: "说明最近一段剧情需要怎样改写。", submit: "重塑命运" },
];

function StoryCommandForm({ mode, onModeChange, value, onValueChange, readOnly, onSubmit }: {
  mode: CommandMode;
  onModeChange: (mode: CommandMode) => void;
  value: string;
  onValueChange: (value: string) => void;
  readOnly: boolean;
  onSubmit: (event: FormEvent) => void;
}) {
  const current = commandModes.find((item) => item.id === mode) ?? commandModes[0];
  const { containerRef, indicator } = useSlidingIndicator<HTMLDivElement>("button.active", [mode]);
  return (
    <form className="story-command" onSubmit={onSubmit}>
      <div className="command-modes" role="group" aria-label="叙事操作类型" ref={containerRef}>
        <span className={`slide-indicator command-mode-indicator ${indicator.className}`} style={indicator.style} aria-hidden="true" />
        {commandModes.map((item) => <button type="button" key={item.id} className={mode === item.id ? "active" : ""} aria-pressed={mode === item.id} onClick={() => onModeChange(item.id)}>{item.label}</button>)}
      </div>
      <div className="command-body">
        <label className="field">
          <span>{current.field}</span>
          <textarea maxLength={12000} disabled={readOnly} value={value} onChange={(event) => onValueChange(event.target.value)} placeholder={readOnly ? "请回到最新剧情，并等待当前生成结束后再行动。" : current.placeholder} />
        </label>
        <button className={mode === "action" ? "primary-button" : "secondary-button"} disabled={readOnly || !value.trim()}>{current.submit}</button>
        {mode === "intervene" && <p className="command-note">向 GM 提出后续故事的走向，不会重写已有剧情。</p>}
        {mode === "reshape" && <p className="command-note">重塑会重写最近一段剧情，并撤销这一段造成的变化。</p>}
      </div>
    </form>
  );
}
