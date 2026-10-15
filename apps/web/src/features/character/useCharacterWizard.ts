import { useCallback, useEffect, useRef, useState } from "react";
import { api, asApiError } from "../../api";
import type { ShellActions } from "../../app/shellActions";
import { useAppNavigate } from "../../app/viewTransition";
import {
  emptyDraft,
  isActiveJobStatus,
  type CharacterCandidate,
  type CharacterDraft,
  type GenerationJob,
  type SaveSummary,
  type WorldCatalog,
} from "../../types";
import { resolveCompletedGeneration } from "./generation";
import { validateDraft, validateStep } from "./wizardSteps";

export type SaveStatus = "saved" | "dirty" | "saving" | "error" | "conflict";

/**
 * Draft editing for the character wizard: loading, debounced autosave with revision checks,
 * navigation guards, step changes and the asynchronous generation job.
 */
export function useCharacterWizard(saveId: string, step: number, actions: ShellActions) {
  const navigate = useAppNavigate();
  const [catalog, setCatalog] = useState<WorldCatalog | null>(null);
  const [save, setSave] = useState<SaveSummary | null>(null);
  const [draft, setDraft] = useState<CharacterDraft>(emptyDraft());
  const [serverDraft, setServerDraft] = useState<CharacterDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");
  const [validationError, setValidationError] = useState("");
  const [job, setJob] = useState<GenerationJob | null>(null);
  const [candidate, setCandidate] = useState<CharacterCandidate | null>(null);
  const [generationError, setGenerationError] = useState<unknown>(null);
  const [browsedFactionId, setBrowsedFactionId] = useState("");
  const loadedId = useRef("");
  const saveToken = useRef(0);
  const editVersion = useRef(0);
  const saving = useRef(false);
  const loadController = useRef<AbortController | null>(null);
  const draftRef = useRef(draft);
  const saveRef = useRef(save);
  draftRef.current = draft;
  saveRef.current = save;

  const load = useCallback(async () => {
    loadController.current?.abort();
    const controller = new AbortController();
    loadController.current = controller;
    const requestedId = saveId;
    loadedId.current = "";
    setLoading(true); setError(null); setGenerationError(null); setJob(null); setCandidate(null);
    try {
      const [nextCatalog, nextSave, nextDraft] = await Promise.all([
        api.getCatalog(controller.signal),
        api.getSave(requestedId, controller.signal),
        api.getDraft(requestedId, controller.signal),
      ]);
      if (controller.signal.aborted) return;
      if (nextSave.phase === "ready") { navigate(`/saves/${requestedId}/game`, { replace: true }); return; }
      setCatalog(nextCatalog); setSave(nextSave); setDraft(nextDraft); setServerDraft(nextDraft);
      setBrowsedFactionId(nextCatalog.factions[0]?.id ?? "");
      setSaveStatus("saved"); loadedId.current = requestedId; editVersion.current = 0;
      if (nextSave.generation?.job_id) {
        try {
          const initialJob = await api.getGeneration(requestedId, nextSave.generation.job_id, controller.signal);
          if (controller.signal.aborted || initialJob.save_id !== requestedId) return;
          setJob(initialJob);
          if (initialJob.status === "succeeded") {
            setCandidate(await api.getCandidate(requestedId, controller.signal));
          } else if (nextSave.phase === "review") {
            setCandidate(await api.getCandidate(requestedId, controller.signal));
          }
        }
        catch (reason) { if (!(reason instanceof DOMException)) setGenerationError(reason); }
      } else if (nextSave.phase === "review") {
        try { setCandidate(await api.getCandidate(requestedId, controller.signal)); }
        catch (reason) { setGenerationError(reason); }
      }
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(reason);
    } finally {
      if (loadController.current === controller) setLoading(false);
    }
  }, [navigate, saveId]);
  useEffect(() => {
    void load();
    return () => { saveToken.current += 1; loadController.current?.abort(); };
  }, [load]);

  const updateDraft = <K extends keyof CharacterDraft>(key: K, value: CharacterDraft[K]) => {
    editVersion.current += 1;
    setDraft((current) => ({ ...current, [key]: value }));
    setSaveStatus("dirty"); setValidationError("");
  };

  const persistDraft = useCallback(async (draftToSave: CharacterDraft = draftRef.current): Promise<CharacterDraft | null> => {
    if (saving.current) return null;
    saving.current = true;
    const token = ++saveToken.current;
    const savedEditVersion = editVersion.current;
    const requestedId = saveId;
    setSaveStatus("saving");
    try {
      const currentSave = saveRef.current;
      if (!currentSave) return null;
      const saved = await api.saveDraft(requestedId, draftToSave, currentSave.revision, crypto.randomUUID());
      if (token !== saveToken.current || requestedId !== loadedId.current) return null;
      setServerDraft(saved);
      const nextSave = { ...currentSave, revision: currentSave.revision + 1,
        current_step: saved.current_step };
      saveRef.current = nextSave;
      setSave(nextSave);
      if (savedEditVersion === editVersion.current) {
        setDraft(saved);
        setSaveStatus("saved");
        return saved;
      }
      setDraft((current) => ({ ...current, draft_revision: saved.draft_revision }));
      setSaveStatus("dirty");
      return null;
    } catch (reason) {
      if (token !== saveToken.current) return null;
      const apiError = asApiError(reason);
      const conflict = apiError.status === 409 || apiError.problem.code.toLowerCase().includes("conflict");
      if (conflict) {
        try {
          const latest = await api.getDraft(requestedId);
          if (token === saveToken.current && requestedId === loadedId.current) setServerDraft(latest);
        } catch {
          // The conflict remains actionable even when the follow-up read fails.
        }
      }
      setSaveStatus(conflict ? "conflict" : "error");
      return null;
    } finally {
      saving.current = false;
    }
  }, [saveId]);

  // Autosave shortly after the last edit.
  useEffect(() => {
    if (saveStatus !== "dirty" || loadedId.current !== saveId) return;
    const timer = window.setTimeout(() => void persistDraft(), 800);
    return () => window.clearTimeout(timer);
  }, [draft, persistDraft, saveId, saveStatus]);

  // Warn before closing the tab with unsaved edits.
  useEffect(() => {
    const warnBeforeClose = (event: BeforeUnloadEvent) => {
      if (saveStatus === "saved") return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeClose);
    return () => window.removeEventListener("beforeunload", warnBeforeClose);
  }, [saveStatus]);

  // Save before following in-app links; block them while saving or after a failed save.
  useEffect(() => {
    const protectInternalNavigation = (event: MouseEvent) => {
      if (saveStatus === "saved" || event.defaultPrevented || event.button !== 0) return;
      const target = event.target as Element | null;
      const anchor = target?.closest<HTMLAnchorElement>("a[href]");
      const href = anchor?.getAttribute("href");
      if (!href?.startsWith("/")) return;
      event.preventDefault();
      if (saveStatus === "dirty") {
        void persistDraft().then((saved) => { if (saved) navigate(href); });
      } else if (saveStatus === "saving") {
        actions.setNotice("草稿正在保存，请在保存完成后切换页面。");
      } else {
        actions.setNotice("草稿还没有保存，请先重试保存，或载入最新版本。");
      }
    };
    document.addEventListener("click", protectInternalNavigation, true);
    return () => document.removeEventListener("click", protectInternalNavigation, true);
  }, [actions, navigate, persistDraft, saveStatus]);

  // Poll the generation job until it leaves the active states.
  useEffect(() => {
    if (!job || !isActiveJobStatus(job.status)) return;
    const requestedId = saveId;
    const jobId = job.id;
    const controller = new AbortController();
    const timer = window.setInterval(async () => {
      try {
        const next = await api.getGeneration(requestedId, jobId, controller.signal);
        if (requestedId !== loadedId.current || next.save_id !== requestedId || next.id !== jobId) return;
        const completed = await resolveCompletedGeneration(
          next,
          () => api.getCandidate(requestedId, controller.signal),
          () => api.getSave(requestedId, controller.signal),
          setJob,
        );
        if (completed) {
          if (controller.signal.aborted || requestedId !== loadedId.current) return;
          setCandidate(completed.candidate);
          saveRef.current = completed.save;
          setSave(completed.save);
          await actions.refreshSaves();
        }
      } catch (reason) {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) setGenerationError(reason);
      }
    }, 1800);
    return () => { window.clearInterval(timer); controller.abort(); };
  }, [actions, job, saveId]);

  const go = async (nextStep: number) => {
    if (saveStatus === "saving") return;
    if (nextStep > step) {
      const message = validateStep(step, draft, catalog);
      if (message) { setValidationError(message); return; }
    }
    let latest = draft;
    if (saveStatus !== "saved") {
      const saved = await persistDraft({ ...draft, current_step: nextStep });
      if (!saved) return;
      latest = saved;
    } else if (draft.current_step !== nextStep) {
      const saved = await persistDraft({ ...draft, current_step: nextStep });
      if (!saved) return;
      latest = saved;
    }
    setDraft(latest); navigate(`/saves/${saveId}/create/${nextStep}`, { direction: nextStep > step ? "forward" : "back" });
  };

  const startGeneration = async (feedback = "") => {
    setGenerationError(null);
    if (!catalog || !save) return;
    const invalid = validateDraft(draft, catalog);
    if (invalid) {
      setValidationError(invalid.message);
      navigate(`/saves/${saveId}/create/${invalid.step}`, { direction: invalid.step > step ? "forward" : "back" });
      return;
    }
    let readyDraft = draft;
    if (saveStatus !== "saved") {
      const saved = await persistDraft({ ...draft, current_step: 13 });
      if (!saved) return;
      readyDraft = saved;
    }
    try {
      const next = await api.startGeneration(saveId, readyDraft.draft_revision,
        saveRef.current?.revision ?? save.revision, feedback);
      if (next.save_id === loadedId.current) setJob(next);
      await actions.refreshSaves();
    } catch (reason) { setGenerationError(reason); }
  };

  const cancelGeneration = async () => {
    if (!job) return;
    try { setJob(await api.cancelGeneration(saveId, job.id, crypto.randomUUID())); }
    catch (reason) { setGenerationError(reason); }
  };

  /** Discard local edits in favour of the newer server draft after a conflict. */
  const adoptServerDraft = () => {
    if (!serverDraft) return;
    editVersion.current += 1;
    setDraft(serverDraft);
    setSaveStatus("saved");
  };

  return {
    catalog, save, draft, serverDraft, loading, error, saveStatus, validationError,
    job, candidate, generationError, browsedFactionId, setBrowsedFactionId,
    load, updateDraft, persistDraft, go, startGeneration, cancelGeneration, adoptServerDraft,
  };
}
