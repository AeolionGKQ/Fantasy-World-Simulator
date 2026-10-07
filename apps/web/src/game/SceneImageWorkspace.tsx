import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, asApiError } from "../api";
import { playerProblemMessage } from "../playerCopy";
import type { ImageQuality, ImageSize, SceneImageSession } from "../types";

const sizes: Array<{ value: ImageSize; label: string; detail: string }> = [
  { value: "1536x1024", label: "横图", detail: "1536 × 1024" },
  { value: "1024x1024", label: "方图", detail: "1024 × 1024" },
  { value: "1024x1536", label: "竖图", detail: "1024 × 1536" },
];
const qualities: Array<{ value: ImageQuality; label: string }> = [
  { value: "low", label: "低" }, { value: "medium", label: "中" },
  { value: "high", label: "高" }, { value: "xhigh", label: "超高" },
  { value: "max", label: "最高" }, { value: "auto", label: "自动" },
];
const active = (value?: string) => value === "queued" || value === "running" || value === "cancel_requested";

export default function SceneImageWorkspace() {
  const { saveId = "" } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState<SceneImageSession | null>(null);
  const [prompt, setPrompt] = useState("");
  const [size, setSize] = useState<ImageSize>("1536x1024");
  const [quality, setQuality] = useState<ImageQuality>("high");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [acceptUnknownCost, setAcceptUnknownCost] = useState(false);
  const [abandoning, setAbandoning] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);

  const load = useCallback(async () => {
    try {
      const next = (await api.getImageSession(saveId)).session;
      setSession(next); setAcceptUnknownCost(false);
      if (next) { setPrompt(next.prompt_draft ?? ""); setSize(next.selected_size); setQuality(next.selected_quality); }
    } catch (reason) { setError(playerProblemMessage(asApiError(reason).problem)); }
    finally { setLoading(false); }
  }, [saveId]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!session || (!active(session.prompt_attempt?.status) && !active(session.image_attempt?.status))) return;
    const timer = window.setInterval(() => void load(), 1600);
    return () => window.clearInterval(timer);
  }, [load, session]);

  const savePrompt = async () => {
    if (!session || !prompt.trim()) return null;
    setSaving(true); setError("");
    try {
      const next = await api.updateImagePrompt(saveId, session.id, prompt.trim(), session.prompt_revision, size, quality);
      setSession(next); return next;
    } catch (reason) { setError(playerProblemMessage(asApiError(reason).problem)); return null; }
    finally { setSaving(false); }
  };
  const generate = async () => {
    const next = await savePrompt();
    if (!next) return;
    try { await api.generateSceneImage(saveId, next.id, next.prompt_revision, crypto.randomUUID()); await load(); }
    catch (reason) { setError(playerProblemMessage(asApiError(reason).problem)); }
  };
  const complete = async () => {
    if (!session) return;
    try { await api.completeImageSession(saveId, session.id); setSession(null); }
    catch (reason) { setError(playerProblemMessage(asApiError(reason).problem)); }
  };
  const cancel = async () => {
    if (!session) return;
    try { setSession(await api.cancelImageSessionJob(saveId, session.id)); }
    catch (reason) { setError(playerProblemMessage(asApiError(reason).problem)); }
  };
  const abandon = async () => {
    if (!session || abandoning) return;
    setAbandoning(true); setError("");
    try {
      await api.completeImageSession(saveId, session.id, true);
      setSession(null);
      navigate(`/saves/${saveId}/game`);
    } catch (reason) { setError(playerProblemMessage(asApiError(reason).problem)); setAbandoning(false); }
  };
  if (loading) return <div className="page image-workspace"><div className="loading-panel" role="status">正在载入场景图片…</div></div>;
  if (!session) return <div className="page image-workspace"><header><div><h1>生成此刻图片</h1><p>当前没有待生成的场景图片。请返回剧情页，选择“生成此刻图片”。</p></div><Link className="secondary-button" to={`/saves/${saveId}/game`}>返回剧情</Link></header>{error && <p className="inline-error">{error}</p>}</div>;
  const promptBusy = active(session.prompt_attempt?.status);
  const imageBusy = active(session.image_attempt?.status);
  const successful = session.latest_successful_image ?? (session.image_attempt?.image_available ? session.image_attempt : null);
  const imageReady = successful?.image_available;
  const imageUrl = `${api.sceneImageUrl(saveId, session.id)}?attempt=${successful?.id ?? ""}`;
  return <div className="page image-workspace">
    <header><div><span className="ready-mark">当前剧情画面</span><h1>生成此刻图片</h1><p>先根据当前剧情整理画面描述。你可以修改描述、画幅和质量，再确认生成图片。</p></div><div className="image-header-actions"><Link className="secondary-button" to={`/saves/${saveId}/game`}>返回剧情</Link><button className="danger-button" type="button" disabled={abandoning} onClick={() => void abandon()}>{abandoning ? "正在放弃…" : "放弃并退出"}</button></div></header>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {promptBusy && <section className="image-progress" role="status"><span>◇</span><div><h2>正在整理画面描述</h2><p>可以返回剧情页，画面描述会继续生成。</p><button className="secondary-button" type="button" disabled={session.prompt_attempt?.status === "cancel_requested"} onClick={() => void cancel()}>{session.prompt_attempt?.status === "cancel_requested" ? "正在取消…" : "取消任务"}</button></div></section>}
    {!promptBusy && <div className="image-editor-layout"><section className="image-prompt-editor"><label className="field"><span>画面描述</span><textarea rows={14} maxLength={8000} value={prompt} onChange={(event) => setPrompt(event.target.value)} disabled={imageBusy} /></label><small>{prompt.length} / 8000</small></section>
      <aside className="image-options"><fieldset className="choice-field"><legend>画幅</legend><div>{sizes.map((item) => <label key={item.value}><input type="radio" name="image-size" checked={size === item.value} disabled={imageBusy} onChange={() => setSize(item.value)} /><span><strong>{item.label}</strong><small>{item.detail}</small></span></label>)}</div></fieldset><fieldset className="choice-field"><legend>图片质量</legend><div>{qualities.map((item) => <label key={item.value}><input type="radio" name="image-quality" checked={quality === item.value} disabled={imageBusy} onChange={() => setQuality(item.value)} /><span>{item.label}</span></label>)}</div></fieldset><p>每次生成一张图片。质量越高，通常等待越久、费用越高；选择“自动”可交由图片服务决定质量。</p>{session.image_attempt?.status === "outcome_unknown" && <label className="cost-confirm"><input type="checkbox" checked={acceptUnknownCost} onChange={(event) => setAcceptUnknownCost(event.target.checked)} /><span>我知道上一次请求可能已计费，仍要再次生成。</span></label>}{imageBusy ? <button className="secondary-button" type="button" disabled={session.image_attempt?.status === "cancel_requested"} onClick={() => void cancel()}>{session.image_attempt?.status === "cancel_requested" ? "正在取消…" : "取消图片生成"}</button> : <button className="primary-button" type="button" disabled={saving || !prompt.trim() || (session.image_attempt?.status === "outcome_unknown" && !acceptUnknownCost)} onClick={() => void generate()}>{saving ? "正在保存画面描述…" : imageReady ? "按当前设置重新生成" : "生成图片"}</button>}</aside></div>}
    {session.prompt_attempt?.error && <p className="inline-error">{playerProblemMessage(session.prompt_attempt.error)} <button className="text-button" type="button" onClick={() => void api.retryImagePrompt(saveId, session.id, crypto.randomUUID()).then(load).catch((reason) => setError(playerProblemMessage(asApiError(reason).problem)))}>重新生成画面描述</button></p>}
    {session.image_attempt?.error && <p className="inline-error">{playerProblemMessage(session.image_attempt.error)}{session.image_attempt.status === "outcome_unknown" ? " 上一次请求可能已经产生费用。" : ""}</p>}
    {imageReady && <section className="image-result"><button type="button" onClick={() => dialog.current?.showModal()} aria-label="放大查看生成图片"><img src={imageUrl} alt="根据当前剧情生成的画面" /></button><div><span>{sizes.find((item) => item.value === successful?.requested_size)?.label} · {qualities.find((item) => item.value === successful?.requested_quality)?.label ?? "自动"}质量</span><a className="secondary-button" href={`${api.sceneImageDownloadUrl(saveId, session.id)}?attempt=${successful?.id ?? ""}`}>保存图片</a><button className="primary-button" type="button" onClick={() => void complete()}>完成本次生成</button></div></section>}
    <dialog ref={dialog} className="image-dialog" onClick={(event) => { if (event.target === dialog.current) dialog.current?.close(); }}><button type="button" onClick={() => dialog.current?.close()} aria-label="关闭大图">×</button>{imageReady && <img src={imageUrl} alt="生成画面大图" />}</dialog>
  </div>;
}
