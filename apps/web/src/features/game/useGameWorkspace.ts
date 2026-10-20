import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { api, asApiError } from "../../api";
import { useNotify } from "../../app/notice";
import { scrollIntoViewIfAbove } from "../../app/scroll";
import { runViewTransition, useAppNavigate } from "../../app/viewTransition";
import { playerProblemMessage } from "../../playerCopy";
import type { ApiProblem, NarrativeJob, StartPrerequisiteResolution, Turn } from "../../types";
import { getAllGameData, type GameData } from "./gameData";
import { gameTabs, type GameTab } from "./gameTabs";
import { isNarrativeJobActive, narrativeJobMessage, refreshedViewedTurn } from "./helpers";

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
  // One-off messages go to the app's notice bar under the toolbar.
  const notify = useNotify();
  const [submittingState, setSubmittingState] = useState(false);
  const [submittingArc, setSubmittingArc] = useState(false);
  const [submittingMemory, setSubmittingMemory] = useState(false);
  const [startingImage, setStartingImage] = useState(false);
  const session = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const stateActionController = useRef<AbortController | null>(null);
  const arcActionController = useRef<AbortController | null>(null);
  const memoryController = useRef<AbortController | null>(null);
  const prerequisiteRequest = useRef<{ payloadKey: string; requestId: string } | null>(null);
  const additionalRequest = useRef<{ payloadKey: string; requestId: string } | null>(null);

  const showProblem = useCallback((reason: unknown) => {
    const error = asApiError(reason);
    const contextExceeded = error.problem.code === "MODEL_CONTEXT_LENGTH_EXCEEDED";
    notify({ tone: "error", text: contextExceeded ? "当前 AI 无法一次读取这么多故事内容。请在设置中换用能读取更长故事的模型后重试。游戏不会删减你的故事。" : playerProblemMessage(error.problem), traceId: error.problem.trace_id });
  }, [notify]);

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
    setData(null); setProblem(null); setViewedTurn(null); setTab("story");
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
          notify({ tone: "info", text: job.type === "turns_to_arc" || job.type === "arcs_to_arc" ? "故事弧已更新。" : "新剧情已保存，角色状态已更新。" });
          await refresh(true, token, job.result?.turn_id);
        } else {
          notify({ tone: "error", text: narrativeJobMessage(job) });
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
          notify({ tone: "info", text: "故事弧已更新。" });
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
          notify({ tone: "error", text: narrativeJobMessage(job) });
        }
      } catch (reason) {
        if (!disposed && !pollController.signal.aborted && token === session.current) showProblem(reason);
      }
    };
    const interval = window.setInterval(() => void poll(), 1800);
    void poll();
    return () => { disposed = true; pollController.abort(); window.clearInterval(interval); };
  }, [activeArcJob?.id, saveId, showProblem]);

  // Poll the long-term memory cleanup; story actions wait for it.
  const activeMemoryJob = data?.story.active_memory_job;
  useEffect(() => {
    if (!activeMemoryJob || !isNarrativeJobActive(activeMemoryJob)) return;
    const token = session.current;
    const requestedId = saveId;
    const pollController = new AbortController();
    let disposed = false;
    const poll = async () => {
      try {
        const job = await api.getNarrativeJob(requestedId, activeMemoryJob.id, pollController.signal);
        if (disposed || token !== session.current || job.save_id !== requestedId) return;
        if (isNarrativeJobActive(job)) {
          setData((current) => current && current.bootstrap.save_id === requestedId
            ? { ...current, story: { ...current.story, active_memory_job: job } }
            : current);
          return;
        }
        const removed = job.result?.removed_count ?? 0;
        notify(job.status === "succeeded"
          ? { tone: "info", text: removed ? `长期记忆已整理，移除了 ${removed} 条。` : "长期记忆已整理，没有需要移除的内容。" }
          : { tone: "error", text: narrativeJobMessage(job) });
        await refresh(true, token);
      } catch (reason) {
        if (!disposed && !pollController.signal.aborted && token === session.current) showProblem(reason);
      }
    };
    const interval = window.setInterval(() => void poll(), 1800);
    void poll();
    return () => { disposed = true; pollController.abort(); window.clearInterval(interval); };
  }, [activeMemoryJob?.id, saveId, refresh, showProblem]);

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
      notify({ tone: "info", text: "正在生成剧情，等待时可以查看角色、背包等页签。" });
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
      notify({ tone: "info", text: "正在整理故事摘要，你可以继续冒险。" });
    } catch (reason) {
      if (nextController.signal.aborted || token !== session.current) return;
      showProblem(reason);
    } finally { if (token === session.current) setSubmittingArc(false); }
  };

  const startMemoryCuration = async () => {
    if (!data || submittingMemory || isNarrativeJobActive(data.story.active_memory_job ?? null)) return;
    const token = session.current;
    const requestedId = saveId;
    setSubmittingMemory(true);
    try {
      const job = await api.startMemoryCuration(requestedId, data.story.state.state_version);
      if (token !== session.current || job.save_id !== requestedId) return;
      setData((current) => current && current.bootstrap.save_id === requestedId
        ? { ...current, story: { ...current.story, active_memory_job: job, can_act: false, can_open: false, can_reshape: false } }
        : current);
      notify({ tone: "info", text: "正在整理长期记忆，完成前暂时不能推进剧情。" });
    } catch (reason) {
      if (token !== session.current) return;
      showProblem(reason);
      if (asApiError(reason).status === 409) await refresh(true);
    } finally { if (token === session.current) setSubmittingMemory(false); }
  };

  /** Reload the memory tab after the player deleted a memory. */
  const reloadMemories = async () => {
    const token = session.current;
    const requestedId = saveId;
    try {
      const [memory, memories] = await Promise.all([api.getMemory(requestedId), api.getMemories(requestedId)]);
      if (token !== session.current) return;
      setData((current) => current && current.bootstrap.save_id === requestedId
        ? { ...current, projections: { ...current.projections, memory, memories } }
        : current);
      notify({ tone: "info", text: "已删除这条长期记忆。" });
    } catch (reason) { if (token === session.current) showProblem(reason); }
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
      notify({ tone: "info", text: resolution === "relocate" ? "角色起点已更换，可以开始冒险。" : "已确认所需的防护与许可，角色将从当前起点出发。" });
      await refresh(true);
    } catch (reason) {
      if (!nextController.signal.aborted && token === session.current) showProblem(reason);
    } finally { if (token === session.current) setSubmittingState(false); }
  };

  /** Saves the player's 其他补充 character setting; resolves true once it is saved. */
  const saveCharacterAdditional = async (additional: string) => {
    if (!data || submittingState || isNarrativeJobActive(data.story.active_job)) return false;
    const token = session.current;
    const payloadKey = JSON.stringify({ expected_state_version: data.story.state.state_version, additional });
    if (additionalRequest.current?.payloadKey !== payloadKey) additionalRequest.current = { payloadKey, requestId: crypto.randomUUID() };
    setSubmittingState(true);
    try {
      await api.updateCharacterAdditional(saveId, data.story.state.state_version, additional, additionalRequest.current.requestId);
      if (token !== session.current) return false;
      additionalRequest.current = null;
      notify({ tone: "info", text: "角色设定已保存，从下一段剧情开始生效。" });
      await refresh(true);
      return true;
    } catch (reason) {
      if (token === session.current) showProblem(reason);
      return false;
    } finally { if (token === session.current) setSubmittingState(false); }
  };

  const startImageSession = async () => {
    if (!data?.story.latest_turn) return;
    if (!data.imageConfigured) {
      notify({ tone: "error", text: "请先打开设置，在“生图模型配置”中填写 OpenAI 服务地址和密钥。" });
      return;
    }
    setStartingImage(true);
    try {
      // Draw the turn being read: an earlier one while browsing history, otherwise the latest.
      const source = viewedTurn ?? data.story.latest_turn;
      await api.createImageSession(saveId, source.id,
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

  // Repeated story-arc failures (3+) are surfaced once per new failure count.
  const arcFailureKey = useRef<string | null>(null);
  useEffect(() => {
    const failures = data?.projections.memory.arc_failures;
    if (!failures) { arcFailureKey.current = null; return; }
    const key = `${saveId}:${failures.start_sequence}:${failures.count}`;
    if (arcFailureKey.current === key) return;
    arcFailureKey.current = key;
    notify({ tone: "error", text: `第 ${failures.start_sequence} 至 ${failures.end_sequence} 段的故事弧已连续 ${failures.count} 次整理失败${failures.message ? `：${failures.message.replace(/[。.]$/, "")}。` : "。"}可以在“记忆管理”中重新整理。` });
  }, [data, saveId]);

  // Vector recall that fell back three turns in a row (and every three after that) is reported.
  const embeddingFailureKey = useRef<string | null>(null);
  useEffect(() => {
    const failures = data?.projections.memory.embedding_failures;
    if (!failures) { embeddingFailureKey.current = null; return; }
    const key = `${saveId}:${Math.floor(failures.count / 3)}`;
    if (embeddingFailureKey.current === key) return;
    embeddingFailureKey.current = key;
    notify({ tone: "error", text: `嵌入模型服务已连续 ${failures.count} 轮无法使用${failures.message ? `（${failures.message.replace(/[。.]$/, "")}）` : ""}，长期记忆暂时改用基础方式召回，剧情不受影响。请到设置中检查嵌入模型配置或重新测试连接。` });
  }, [data, saveId]);

  return {
    data, tab, setTab, selectTab, viewedTurn, setViewedTurn, showTurn, loading, problem,
    submittingState, submittingArc, submittingMemory, startingImage,
    refresh, startStateJob, startArcJob, cancelJob, readJournalTurn, resolveStartPrerequisite,
    saveCharacterAdditional, startMemoryCuration, reloadMemories, startImageSession,
  };
}
