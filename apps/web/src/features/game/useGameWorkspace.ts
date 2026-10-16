import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { api, asApiError } from "../../api";
import { scrollIntoViewIfAbove } from "../../app/scroll";
import { runViewTransition, useAppNavigate } from "../../app/viewTransition";
import { playerProblemMessage } from "../../playerCopy";
import type { ApiProblem, NarrativeJob, StartPrerequisiteResolution, Turn } from "../../types";
import { getAllGameData, type GameData } from "./gameData";
import { gameTabs, type GameTab } from "./gameTabs";
import { isNarrativeJobActive, narrativeJobMessage, refreshedViewedTurn } from "./helpers";

export interface GameNotice {
  id: number;
  tone: "info" | "error";
  text: string;
  traceId?: string;
}

type JobFactory = (version: number, signal: AbortSignal) => Promise<NarrativeJob>;

/**
 * Game session state for one save. Every async action captures a session token and the
 * requested save id so responses that arrive after a save switch are dropped.
 */
export function useGameWorkspace(saveId: string) {
  const navigate = useAppNavigate();
  const [data, setData] = useState<GameData | null>(null);
  const [tab, setTab] = useState<GameTab>("story");
  const [viewedTurn, setViewedTurn] = useState<Turn | null>(null);
  const [loading, setLoading] = useState(true);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [notice, setNotice] = useState<GameNotice | null>(null);
  const [submittingState, setSubmittingState] = useState(false);
  const [submittingArc, setSubmittingArc] = useState(false);
  const [startingImage, setStartingImage] = useState(false);
  const session = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const stateActionController = useRef<AbortController | null>(null);
  const arcActionController = useRef<AbortController | null>(null);
  const memoryController = useRef<AbortController | null>(null);
  const prerequisiteRequest = useRef<{ payloadKey: string; requestId: string } | null>(null);

  const showProblem = useCallback((reason: unknown) => {
    const error = asApiError(reason);
    const contextExceeded = error.problem.code === "MODEL_CONTEXT_LENGTH_EXCEEDED";
    setNotice({ id: Date.now(), tone: "error", text: contextExceeded ? "当前 AI 无法一次读取这么多故事内容。请在设置中换用能读取更长故事的模型后重试。游戏不会删减你的故事。" : playerProblemMessage(error.problem), traceId: error.problem.trace_id });
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
      prerequisiteRequest.current = null;
    };
  }, [refresh, saveId]);

  // Poll the story job (opening / turn / intervene / reshape) until it finishes.
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
          setNotice({ id: Date.now(), tone: "info", text: job.type === "turns_to_arc" || job.type === "arcs_to_arc" ? "故事弧已更新。" : "新剧情已保存，角色状态已更新。" });
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

  // Poll the story-arc job separately; it never blocks story actions.
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

  const startStateJob = async (factory: JobFactory) => {
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
      setNotice({ id: Date.now(), tone: "info", text: "正在生成剧情，等待时可以查看角色、背包等页签。" });
    } catch (reason) {
      if (nextController.signal.aborted || token !== session.current) return;
      showProblem(reason);
      const error = asApiError(reason);
      if (error.status === 409) await refresh(true);
    } finally { if (token === session.current) setSubmittingState(false); }
  };

  const startArcJob = async (factory: JobFactory) => {
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
      setNotice({ id: Date.now(), tone: "info", text: "正在整理故事摘要，你可以继续冒险。" });
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
      runViewTransition("tab", () => flushSync(() => { setViewedTurn(turn); setTab("story"); }), "back");
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
      setNotice({ id: Date.now(), tone: "info", text: resolution === "relocate" ? "角色起点已更换，可以开始冒险。" : "已确认所需的防护与许可，角色将从当前起点出发。" });
      await refresh(true);
    } catch (reason) {
      if (!nextController.signal.aborted && token === session.current) showProblem(reason);
    } finally { if (token === session.current) setSubmittingState(false); }
  };

  const startImageSession = async () => {
    if (!data?.story.latest_turn) return;
    if (!data.imageConfigured) {
      setNotice({ id: Date.now(), tone: "error", text: "请先打开设置，在“生图模型配置”中填写 OpenAI 服务地址和密钥。" });
      return;
    }
    setStartingImage(true);
    try {
      await api.createImageSession(saveId, data.story.latest_turn.id,
        data.story.state.state_version, crypto.randomUUID());
      navigate(`/saves/${saveId}/game/image`);
    } catch (reason) { showProblem(reason); }
    finally { setStartingImage(false); }
  };

  /** Switches tab with a slide toward the tab's side of the tab bar. */
  const selectTab = (next: GameTab) => {
    if (next === tab) return;
    const order = (id: GameTab) => gameTabs.findIndex((item) => item.id === id);
    runViewTransition("tab", () => flushSync(() => setTab(next)), order(next) > order(tab) ? "forward" : "back");
  };

  /** Pages through story history; brings the reading column back into view when it was scrolled past. */
  const showTurn = (turn: Turn) => {
    const current = viewedTurn ?? data?.story.latest_turn;
    runViewTransition("turn", () => {
      flushSync(() => setViewedTurn(turn));
      scrollIntoViewIfAbove(".story-reading");
    }, current && turn.sequence < current.sequence ? "back" : "forward");
  };

  return {
    data, tab, setTab, selectTab, viewedTurn, setViewedTurn, showTurn, loading, problem, notice, setNotice,
    submittingState, submittingArc, startingImage,
    refresh, startStateJob, startArcJob, cancelJob, readJournalTurn, resolveStartPrerequisite,
    startImageSession,
  };
}
