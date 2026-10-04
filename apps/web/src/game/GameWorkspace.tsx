import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, asApiError } from "../api";
import type { ApiProblem, GameBootstrap, GameProjections, NarrativeJob, SaveSummary, StartPrerequisiteResolution, StoryView, Turn, WorldCatalog } from "../types";
import {
  BondsPanel, CharacterPanel, gameTabs, type GameTab, InventoryPanel, JournalsPanel,
  MemoryPanel, QuestsPanel, ReputationsPanel, StoryPanel,
} from "./GamePanels";
import { isNarrativeJobActive, narrativeJobMessage, refreshedViewedTurn } from "./helpers";

interface GameData {
  save: SaveSummary;
  bootstrap: GameBootstrap;
  catalog: WorldCatalog;
  story: StoryView;
  turns: Turn[];
  projections: GameProjections;
}

function LoadingGame() {
  return <div className="page game-page"><div className="loading-panel" role="status"><div className="skeleton wide" /><div className="skeleton medium" /><div className="skeleton wide" /><span className="sr-only">正在载入游戏工作区</span></div></div>;
}

function ProblemPanel({ problem, onRetry }: { problem: ApiProblem; onRetry: () => void }) {
  const conflict = problem.code.includes("CONFLICT") || problem.code === "NARRATIVE_JOB_ACTIVE";
  const contextExceeded = problem.code === "MODEL_CONTEXT_LENGTH_EXCEEDED";
  return <section className={`state-panel ${conflict ? "warning" : "error"}`} role="alert"><span className="state-symbol" aria-hidden="true">{conflict ? "!" : "×"}</span><div><h2>{contextExceeded ? "模型上下文长度不足" : conflict ? "权威状态已变化" : "无法载入游戏工作区"}</h2><p>{contextExceeded ? "请在设置中更换支持更长上下文的模型后重试。本次不会自动裁剪上下文或重试。" : problem.message}</p>{problem.trace_id && <p className="trace">追踪编号：{problem.trace_id}</p>}<button className="secondary-button" type="button" onClick={onRetry}>重新载入</button></div></section>;
}

async function getAllGameData(saveId: string, signal?: AbortSignal): Promise<GameData> {
  const [save, bootstrap, catalog, story, turns, character, inventory, quests, journals, memory, memories, bonds, reputations] = await Promise.all([
    api.getSave(saveId, signal), api.getGameBootstrap(saveId, signal), api.getCatalog(signal), api.getStory(saveId, signal), api.listTurns(saveId, signal),
    api.getCharacterState(saveId, signal), api.getInventory(saveId, signal), api.getQuests(saveId, signal),
    api.getJournals(saveId, signal), api.getMemory(saveId, signal), api.getMemories(saveId, signal),
    api.getBonds(saveId, signal), api.getReputations(saveId, signal),
  ]);
  return { save, bootstrap, catalog, story, turns: turns.items, projections: { character, inventory, quests, journals, memory, memories, bonds, reputations } };
}

export default function GameWorkspace({ onSaveChanged }: { onSaveChanged: () => Promise<void> }) {
  const { saveId = "" } = useParams();
  const [data, setData] = useState<GameData | null>(null);
  const [tab, setTab] = useState<GameTab>("story");
  const [viewedTurn, setViewedTurn] = useState<Turn | null>(null);
  const [loading, setLoading] = useState(true);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [notice, setNotice] = useState<{ id: number; tone: "info" | "error"; text: string; traceId?: string } | null>(null);
  const [submittingState, setSubmittingState] = useState(false);
  const [submittingArc, setSubmittingArc] = useState(false);
  const [savingPreferences, setSavingPreferences] = useState(false);
  const session = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const stateActionController = useRef<AbortController | null>(null);
  const arcActionController = useRef<AbortController | null>(null);
  const memoryController = useRef<AbortController | null>(null);
  const preferenceController = useRef<AbortController | null>(null);
  const prerequisiteRequest = useRef<{ payloadKey: string; requestId: string } | null>(null);

  const showProblem = useCallback((reason: unknown) => {
    const error = asApiError(reason);
    const contextExceeded = error.problem.code === "MODEL_CONTEXT_LENGTH_EXCEEDED";
    setNotice({ id: Date.now(), tone: "error", text: contextExceeded ? "模型上下文长度不足，请更换支持更长上下文的模型。本次不会自动裁剪重试。" : error.problem.message, traceId: error.problem.trace_id });
  }, []);

  const refresh = useCallback(async (
    background = false,
    expectedSession = session.current,
    completedTurnId?: string | null,
  ) => {
    const token = session.current;
    if (token !== expectedSession) return;
    const requestedId = saveId;
    const nextController = new AbortController();
    controller.current?.abort();
    controller.current = nextController;
    if (!background) setLoading(true);
    try {
      const next = await getAllGameData(requestedId, nextController.signal);
      if (nextController.signal.aborted || token !== session.current || next.bootstrap.save_id !== requestedId) return;
      setData(next); setProblem(null);
      setViewedTurn((current) => refreshedViewedTurn(
        next.turns, next.story.latest_turn, current, completedTurnId,
      ));
    } catch (reason) {
      if (nextController.signal.aborted || token !== session.current) return;
      const error = asApiError(reason);
      if (background) showProblem(reason);
      else setProblem(error.problem);
    } finally {
      if (token === session.current && !nextController.signal.aborted) setLoading(false);
    }
  }, [saveId, showProblem]);

  useEffect(() => {
    const token = ++session.current;
    setData(null); setProblem(null); setNotice(null); setViewedTurn(null); setTab("story");
    void refresh(false, token);
    return () => {
      session.current += 1;
      controller.current?.abort();
      stateActionController.current?.abort();
      arcActionController.current?.abort();
      memoryController.current?.abort();
      preferenceController.current?.abort();
      prerequisiteRequest.current = null;
    };
  }, [refresh, saveId]);

  const activeJob = data?.story.active_job;
  useEffect(() => {
    if (!activeJob || !isNarrativeJobActive(activeJob)) return;
    const token = session.current;
    const requestedId = saveId;
    const pollController = new AbortController();
    let disposed = false;
    const poll = async () => {
      try {
        const job = await api.getNarrativeJob(requestedId, activeJob.id, pollController.signal);
        if (disposed || token !== session.current || job.save_id !== requestedId) return;
        setData((current) => current ? { ...current, story: { ...current.story, active_job: job } } : current);
        if (isNarrativeJobActive(job)) return;
        if (job.status === "succeeded") {
          setNotice({ id: Date.now(), tone: "info", text: job.type === "turns_to_arc" || job.type === "arcs_to_arc" ? "故事弧已更新。" : "新剧情与权威状态已写入。" });
          await refresh(true, token, job.result?.turn_id);
        } else {
          setNotice({ id: Date.now(), tone: "error", text: narrativeJobMessage(job) });
          await refresh(true);
        }
      } catch (reason) { if (!disposed && !pollController.signal.aborted && token === session.current) showProblem(reason); }
    };
    const interval = window.setInterval(() => void poll(), 1800);
    void poll();
    return () => { disposed = true; pollController.abort(); window.clearInterval(interval); };
  }, [activeJob?.id, saveId, refresh, showProblem]);

  const activeArcJob = data?.story.active_arc_job;
  useEffect(() => {
    if (!activeArcJob || !isNarrativeJobActive(activeArcJob)) return;
    const token = session.current;
    const requestedId = saveId;
    const pollController = new AbortController();
    let disposed = false;
    const poll = async () => {
      try {
        const job = await api.getNarrativeJob(requestedId, activeArcJob.id, pollController.signal);
        if (disposed || token !== session.current || job.save_id !== requestedId) return;
        if (isNarrativeJobActive(job)) {
          setData((current) => current && current.bootstrap.save_id === requestedId
            ? { ...current, story: { ...current.story, active_arc_job: job } }
            : current);
          return;
        }
        if (job.status === "succeeded") {
          setNotice({ id: Date.now(), tone: "info", text: "故事弧已更新。" });
          const nextController = new AbortController();
          memoryController.current?.abort();
          memoryController.current = nextController;
          const memory = await api.getMemory(requestedId, nextController.signal);
          if (disposed || nextController.signal.aborted || token !== session.current) return;
          setData((current) => current && current.bootstrap.save_id === requestedId
            ? { ...current, story: { ...current.story, active_arc_job: null },
                projections: { ...current.projections, memory } }
            : current);
        } else {
          setData((current) => current && current.bootstrap.save_id === requestedId
            ? { ...current, story: { ...current.story, active_arc_job: null } }
            : current);
          setNotice({ id: Date.now(), tone: "error", text: narrativeJobMessage(job) });
        }
      } catch (reason) {
        if (!disposed && !pollController.signal.aborted && token === session.current) showProblem(reason);
      }
    };
    const interval = window.setInterval(() => void poll(), 1800);
    void poll();
    return () => { disposed = true; pollController.abort(); window.clearInterval(interval); };
  }, [activeArcJob?.id, saveId, showProblem]);

  const startStateJob = async (factory: (version: number, signal: AbortSignal) => Promise<NarrativeJob>) => {
    if (!data || submittingState || isNarrativeJobActive(data.story.active_job)) return;
    const token = session.current;
    const requestedId = saveId;
    const nextController = new AbortController();
    stateActionController.current?.abort();
    stateActionController.current = nextController;
    setSubmittingState(true);
    try {
      const job = await factory(data.story.state.state_version, nextController.signal);
      if (nextController.signal.aborted || token !== session.current || job.save_id !== requestedId) return;
      setData((current) => current ? { ...current, story: { ...current.story, active_job: job, can_act: false, can_open: false, can_reshape: false } } : current);
      setNotice({ id: Date.now(), tone: "info", text: "任务已提交。你可以继续浏览其他页签。" });
    } catch (reason) {
      if (nextController.signal.aborted || token !== session.current) return;
      showProblem(reason);
      const error = asApiError(reason);
      if (error.status === 409) await refresh(true);
    } finally { if (token === session.current) setSubmittingState(false); }
  };

  const startArcJob = async (factory: (version: number, signal: AbortSignal) => Promise<NarrativeJob>) => {
    if (!data || submittingArc || isNarrativeJobActive(data.story.active_arc_job)) return;
    const token = session.current;
    const requestedId = saveId;
    const nextController = new AbortController();
    arcActionController.current?.abort();
    arcActionController.current = nextController;
    setSubmittingArc(true);
    try {
      const job = await factory(data.story.state.state_version, nextController.signal);
      if (nextController.signal.aborted || token !== session.current || job.save_id !== requestedId) return;
      setData((current) => current && current.bootstrap.save_id === requestedId
        ? { ...current, story: { ...current.story, active_arc_job: job } }
        : current);
      setNotice({ id: Date.now(), tone: "info", text: "故事弧任务已提交，剧情操作仍可继续。" });
    } catch (reason) {
      if (nextController.signal.aborted || token !== session.current) return;
      showProblem(reason);
    } finally { if (token === session.current) setSubmittingArc(false); }
  };

  const cancelJob = async () => {
    if (!data?.story.active_job) return;
    const token = session.current;
    const requestedId = saveId;
    const nextController = new AbortController();
    stateActionController.current?.abort();
    stateActionController.current = nextController;
    try {
      const job = await api.cancelNarrativeJob(requestedId, data.story.active_job.id, data.story.state.state_version, crypto.randomUUID(), nextController.signal);
      if (nextController.signal.aborted || token !== session.current || job.save_id !== requestedId) return;
      setData((current) => current ? { ...current, story: { ...current.story, active_job: job } } : current);
    } catch (reason) { if (!nextController.signal.aborted && token === session.current) showProblem(reason); }
  };

  const readJournalTurn = async (turnId: string) => {
    try {
      const turn = data?.turns.find((item) => item.id === turnId) ?? await api.getTurn(saveId, turnId, stateActionController.current?.signal);
      setViewedTurn(turn); setTab("story");
    } catch (reason) { showProblem(reason); }
  };

  const resolveStartPrerequisite = async (resolution: StartPrerequisiteResolution, locationId: string | null) => {
    if (!data || submittingState) return;
    const token = session.current;
    const requestedId = saveId;
    const payloadKey = JSON.stringify({ expected_state_version: data.story.state.state_version, resolution, location_id: locationId });
    if (prerequisiteRequest.current?.payloadKey !== payloadKey) prerequisiteRequest.current = { payloadKey, requestId: crypto.randomUUID() };
    const requestId = prerequisiteRequest.current.requestId;
    const nextController = new AbortController();
    stateActionController.current?.abort();
    stateActionController.current = nextController;
    setSubmittingState(true);
    try {
      await api.resolveStartPrerequisite(requestedId, data.story.state.state_version, resolution, locationId, requestId, nextController.signal);
      if (nextController.signal.aborted || token !== session.current) return;
      prerequisiteRequest.current = null;
      setNotice({ id: Date.now(), tone: "info", text: resolution === "relocate" ? "角色已迁移到公开起点。" : "已记录对旧存档兼容防护的明确接受。" });
      await refresh(true);
    } catch (reason) {
      if (!nextController.signal.aborted && token === session.current) showProblem(reason);
    } finally { if (token === session.current) setSubmittingState(false); }
  };

  const updatePlayerAddress = async (playerAddress: "full_name" | "given_name" | "second_person") => {
    if (!data || savingPreferences || submittingState || isNarrativeJobActive(data.story.active_job)) return;
    const token = session.current;
    const requestedId = saveId;
    const nextController = new AbortController();
    preferenceController.current?.abort();
    preferenceController.current = nextController;
    const narration = data.save.narration ?? data.story.state.narration;
    setSavingPreferences(true);
    try {
      const save = await api.updateSavePreferences(requestedId, { ...narration, player_address: playerAddress }, data.save.revision, crypto.randomUUID(), nextController.signal);
      if (nextController.signal.aborted || token !== session.current || save.id !== requestedId) return;
      setData((current) => current && current.bootstrap.save_id === requestedId ? {
        ...current,
        save,
        bootstrap: { ...current.bootstrap, save_revision: save.revision },
        story: { ...current.story, state: { ...current.story.state, narration: save.narration ?? { ...current.story.state.narration, player_address: playerAddress } } },
      } : current);
      await onSaveChanged();
      setNotice({ id: Date.now(), tone: "info", text: "该存档的GM称呼已更新，下一次生成起生效。" });
    } catch (reason) {
      if (!nextController.signal.aborted && token === session.current) {
        showProblem(reason);
        if (asApiError(reason).status === 409) await refresh(true);
      }
    } finally { if (token === session.current) setSavingPreferences(false); }
  };

  if (loading && !data) return <LoadingGame />;
  if (problem && !data) return <div className="page game-page"><ProblemPanel problem={problem} onRetry={() => void refresh()} /></div>;
  if (!data) return null;
  if (data.bootstrap.save_id !== saveId) return <LoadingGame />;
  const stateBusy = submittingState || isNarrativeJobActive(data.story.active_job);
  const arcBusy = submittingArc || isNarrativeJobActive(data.story.active_arc_job);
  return <div className="page game-page">
    <header className="game-header"><div><span className="ready-mark">游戏档案</span><h1>{data.projections.character.identity.name || data.bootstrap.character.identity?.name || "未命名角色"}</h1><p>{data.story.state.time.label} · {data.story.state.location.name}</p></div></header>
    {notice && <div key={notice.id} className={`game-notice ${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}><span aria-hidden="true">{notice.tone === "error" ? "!" : "◇"}</span><p>{notice.text}{notice.traceId && <small>追踪编号：{notice.traceId}</small>}</p><button type="button" onClick={() => setNotice(null)} aria-label="关闭游戏提示">×</button></div>}
    <nav className="game-tabs" role="tablist" aria-label="游戏工作区" onKeyDown={(event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      const tabs = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
      const current = tabs.indexOf(document.activeElement as HTMLButtonElement);
      if (current < 0) return;
      event.preventDefault();
      const target = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
        (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      tabs[target].focus(); tabs[target].click();
    }}>{gameTabs.map((item) => <button id={`tab-${item.id}`} aria-controls={`panel-${item.id}`} aria-selected={tab === item.id} role="tab" tabIndex={tab === item.id ? 0 : -1} type="button" key={item.id} onClick={() => setTab(item.id)}>{item.label}</button>)}</nav>
    <section className="game-panel" id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} tabIndex={0}>
      {tab === "story" && <StoryPanel story={data.story} turns={data.turns} viewedTurn={viewedTurn} busy={stateBusy} catalog={data.catalog} onNavigate={setViewedTurn} onOpen={(guidance) => void startStateJob((version, signal) => api.startOpening(saveId, version, guidance, crypto.randomUUID(), signal))} onResolvePrerequisite={(resolution, locationId) => void resolveStartPrerequisite(resolution, locationId)} onTurn={(action, optionId) => void startStateJob((version, signal) => api.startTurn(saveId, version, action, optionId, crypto.randomUUID(), signal))} onIntervene={(guidance) => void startStateJob((version, signal) => api.intervene(saveId, version, guidance, crypto.randomUUID(), signal))} onReshape={(guidance) => data.story.latest_turn && void startStateJob((version, signal) => api.reshape(saveId, data.story.latest_turn!.id, version, guidance, crypto.randomUUID(), signal))} onCancel={() => void cancelJob()} />}
      {tab === "character" && <CharacterPanel character={data.projections.character} catalog={data.catalog} playerAddress={data.save.narration?.player_address ?? data.story.state.narration.player_address} addressBusy={savingPreferences || stateBusy} onPlayerAddress={(value) => void updatePlayerAddress(value)} />}
      {tab === "inventory" && <InventoryPanel inventory={data.projections.inventory} />}
      {tab === "quests" && <QuestsPanel active={data.projections.quests.active} />}
      {tab === "journals" && <JournalsPanel items={data.projections.journals.items} onRead={(id) => void readJournalTurn(id)} />}
      {tab === "memory" && <MemoryPanel memory={data.projections.memory} memories={data.projections.memories.items} arcBusy={arcBusy} arcJob={data.story.active_arc_job} onMerge={(ids) => void startArcJob((version, signal) => api.mergeStoryArcs(saveId, version, ids, crypto.randomUUID(), signal))} />}
      {tab === "bonds" && <BondsPanel items={data.projections.bonds.items} />}
      {tab === "reputations" && <ReputationsPanel data={data.projections.reputations} />}
    </section>
  </div>;
}
