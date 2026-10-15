import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../../api";
import type { ShellActions } from "../../app/shellActions";
import { useAppNavigate } from "../../app/viewTransition";
import { ErrorPanel } from "../../components/ErrorPanel";
import { LoadingPanel } from "../../components/LoadingPanel";
import { StatusDot } from "../../components/StatusDot";
import type { CharacterCandidate, SaveSummary } from "../../types";
import { CandidatePanel } from "./candidate/CandidatePanel";
import { RegeneratePanel } from "./candidate/RegeneratePanel";

export function ReviewPage({ actions }: { actions: ShellActions }) {
  const { saveId = "" } = useParams();
  const navigate = useAppNavigate();
  const [save, setSave] = useState<SaveSummary | null>(null);
  const [candidate, setCandidate] = useState<CharacterCandidate | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [confirming, setConfirming] = useState(false);
  const [regenBusy, setRegenBusy] = useState(false);
  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError(null);
    try {
      const [nextSave, nextCandidate] = await Promise.all([api.getSave(saveId, signal), api.getCandidate(saveId, signal)]);
      if (signal?.aborted || nextCandidate.save_id !== saveId) return;
      if (nextSave.phase === "ready") { navigate(`/saves/${saveId}/game`, { replace: true }); return; }
      setSave(nextSave); setCandidate(nextCandidate);
    } catch (reason) { if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(reason); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [navigate, saveId]);
  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [load]);
  const confirm = async () => {
    if (!save || !candidate || candidate.valid === false) return;
    setConfirming(true); setError(null);
    try {
      await api.confirmCharacter(saveId, candidate.id, save.revision, candidate.draft_revision, crypto.randomUUID());
      await actions.refreshSaves();
      navigate(`/saves/${saveId}/game`);
    }
    catch (reason) { setError(reason); setConfirming(false); }
  };
  const regenerate = async (feedback = "") => {
    if (!candidate) return;
    setRegenBusy(true); setError(null);
    if (!save) return;
    try {
      const next = await api.startGeneration(saveId, candidate.draft_revision, save.revision, feedback);
      await actions.refreshSaves();
      navigate(`/saves/${saveId}/create/13`, { state: { jobId: next.id } });
    }
    catch (reason) { setError(reason); setRegenBusy(false); }
  };
  if (loading) return <div className="page page-loading" key="loading"><LoadingPanel label="正在载入候选角色" /></div>;
  if (error && !candidate) return <div className="page page-enter" key="error"><ErrorPanel error={error} onRetry={() => void load()} title="无法载入角色候选" /></div>;
  if (!save || !candidate) return <div className="page page-enter" key="missing"><ErrorPanel error={new ApiError(404, { code: "candidate_not_found", message: "当前存档没有可审阅的角色候选。" })} /></div>;
  return (
    <div className="page review-page page-enter" key="ready">
      <header className="page-header"><div><span className="step-count">接受前检查</span><h1>确认角色候选</h1><p>这是 AI 生成的角色候选，接受后才会正式成为你的角色。</p></div></header>
      {Boolean(error) && <ErrorPanel error={error} onRetry={() => void load()} />}
      {regenBusy && <div className="inline-status"><StatusDot state="busy" />正在按你的意见重新生成…</div>}
      <CandidatePanel
        candidate={candidate}
        footer={(
          <div className="candidate-footer">
            <button className="secondary-button" type="button" onClick={() => navigate(`/saves/${saveId}/create/13`)}>返回生成页</button>
            <button className="primary-button" type="button" disabled={confirming || candidate.valid === false} onClick={() => void confirm()}>{confirming ? "正在接受…" : "接受角色"}</button>
          </div>
        )}
      />
      <RegeneratePanel onGenerate={regenerate} />
    </div>
  );
}
