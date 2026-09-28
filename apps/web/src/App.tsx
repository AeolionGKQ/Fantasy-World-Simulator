import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { api, ApiError, asApiError } from "./api";
import GameWorkspace from "./game/GameWorkspace";
import {
  appendPreset,
  chineseRankNumeral,
  emptyDraft,
  groupPresets,
  isPendingImport,
  jobLabel,
  logicalRequestIdentity,
  mediaPictureSources,
  phaseLabel,
  saveRoute,
  selectedRaceBranch,
  type AppSettings,
  type CharacterCandidate,
  type CharacterDraft,
  type FactionDefinition,
  type GenerationJob,
  type ImportPreview,
  type PendingImport,
  type LogicalRequestIdentity,
  type LocationDefinition,
  type MediaPaths,
  type ModelTestResult,
  type PresetDefinition,
  type RaceDefinition,
  type RankDefinition,
  type SaveSummary,
  type WorldCatalog,
} from "./types";

const steps = [
  "种族",
  "姓名",
  "性别",
  "年龄",
  "外貌",
  "性格",
  "等阶",
  "天赋",
  "身世",
  "地区",
  "势力",
  "其他补充",
  "模型生成",
] as const;

type SaveStatus = "saved" | "dirty" | "saving" | "error" | "conflict";
type ModelState = "idle" | "saving" | "saved";
type ModelTestState = "idle" | "testing" | "probing";
type NarrationState = "idle" | "saving" | "saved";

function Icon({ name }: { name: "menu" | "plus" | "settings" | "upload" | "download" | "edit" | "trash" | "close" }) {
  const paths: Record<typeof name, ReactNode> = {
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    plus: <path d="M12 5v14M5 12h14" />,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
    upload: <><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" /><path d="M5 14v5h14v-5" /></>,
    download: <><path d="M12 4v12m0 0 4.5-4.5M12 16l-4.5-4.5" /><path d="M5 19h14" /></>,
    edit: <><path d="m4 20 4.2-1 10.6-10.6-3.2-3.2L5 15.8 4 20Z" /><path d="m13.8 7 3.2 3.2" /></>,
    trash: <><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7" /><path d="M10 11v5m4-5v5" /></>,
    close: <path d="m6 6 12 12M18 6 6 18" />,
  };
  return <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>;
}

function StatusDot({ state }: { state: "online" | "offline" | "busy" }) {
  return <span className={`status-dot ${state}`} aria-hidden="true" />;
}

function Modal({ title, children, onClose, labelledBy }: { title: string; children: ReactNode; onClose: () => void; labelledBy: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog ref={ref} className="modal" aria-labelledby={labelledBy} onCancel={onClose} onClose={onClose}>
      <div className="modal-heading">
        <h2 id={labelledBy}>{title}</h2>
        <button className="icon-button" type="button" onClick={onClose} aria-label="关闭对话框"><Icon name="close" /></button>
      </div>
      {children}
    </dialog>
  );
}

function ErrorPanel({ error, onRetry, title = "无法完成请求" }: { error: unknown; onRetry?: () => void; title?: string }) {
  const apiError = asApiError(error);
  const conflict = apiError.status === 409 || apiError.problem.code.toLowerCase().includes("conflict");
  return (
    <section className={`state-panel ${conflict ? "warning" : "error"}`} role="alert">
      <span className="state-symbol" aria-hidden="true">{conflict ? "!" : "×"}</span>
      <div>
        <h2>{conflict ? "检测到版本冲突" : title}</h2>
        <p>{apiError.problem.message}</p>
        {apiError.problem.trace_id && <p className="trace">追踪编号：{apiError.problem.trace_id}</p>}
        {conflict && <p>服务器保留了较新的版本。请重新载入后检查内容，再继续编辑。</p>}
        {onRetry && <button className="secondary-button" type="button" onClick={onRetry}>{conflict ? "载入最新版本" : "重试请求"}</button>}
      </div>
    </section>
  );
}

function LoadingPanel({ label = "正在读取档案" }: { label?: string }) {
  return (
    <div className="loading-panel" role="status" aria-live="polite">
      <div className="skeleton wide" />
      <div className="skeleton medium" />
      <div className="skeleton wide" />
      <span className="sr-only">{label}</span>
    </div>
  );
}

interface ShellActions {
  refreshSaves: () => Promise<void>;
  setNotice: (notice: string) => void;
}

export default function App() {
  const [saves, setSaves] = useState<SaveSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [modal, setModal] = useState<"new" | "import" | "rename" | "delete" | null>(null);
  const [targetSave, setTargetSave] = useState<SaveSummary | null>(null);
  const navigate = useNavigate();
  const location = useLocation();

  const refreshSaves = useCallback(async () => {
    try {
      setLoadError(null);
      const next = await api.listSaves();
      setSaves(next);
    } catch (error) {
      setLoadError(error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refreshSaves(); }, [refreshSaves]);
  useEffect(() => { setDrawerOpen(false); }, [location.pathname]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 4200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const currentId = /^\/saves\/([^/]+)/.exec(location.pathname)?.[1];
  const currentSave = saves.find((save) => save.id === currentId) ?? null;
  const actions = useMemo<ShellActions>(() => ({ refreshSaves, setNotice }), [refreshSaves]);

  const openFor = (kind: "rename" | "delete", save: SaveSummary) => {
    setTargetSave(save);
    setModal(kind);
  };

  const exportCurrent = async () => {
    if (!currentSave) return;
    try {
      const { blob, filename } = await api.exportSave(currentSave.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setNotice("存档已导出，文件不包含 API Key。");
    } catch (error) {
      setNotice(asApiError(error).message);
    }
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <aside className={`sidebar ${drawerOpen ? "open" : ""}`} aria-label="存档列表">
        <div className="brand-block">
          <Link to="/" className="brand-mark" aria-label="Fantasy Simulator 首页"><span>F</span></Link>
          <div><strong>Fantasy Simulator</strong><small>冒险档案</small></div>
          <button className="icon-button sidebar-close" type="button" onClick={() => setDrawerOpen(false)} aria-label="关闭存档列表"><Icon name="close" /></button>
        </div>
        <div className="sidebar-title"><span>存档</span><span>{saves.length}</span></div>
        <nav className="save-list" aria-label="已有存档">
          {loading && <LoadingPanel label="正在载入存档" />}
          {!loading && Boolean(loadError) && <ErrorPanel error={loadError} onRetry={() => void refreshSaves()} title="无法载入存档" />}
          {!loading && !loadError && saves.length === 0 && (
            <div className="sidebar-empty"><p>还没有冒险档案。</p><button type="button" className="text-button" onClick={() => setModal("new")}>创建第一个存档</button></div>
          )}
          {saves.map((save) => (
            <div className={`save-row ${save.id === currentId ? "active" : ""}`} key={save.id}>
              <Link to={saveRoute(save)} className="save-link" aria-current={save.id === currentId ? "page" : undefined}>
                <span className="save-name">{save.name}</span>
                <span className="save-meta"><span>{phaseLabel[save.phase]}</span>{save.character_name && <span>{save.character_name}</span>}</span>
                {save.generation && ["queued", "running", "cancel_requested"].includes(save.generation.status) && (
                  <span className="generation-mini"><StatusDot state="busy" />{jobLabel[save.generation.status]}</span>
                )}
              </Link>
              <div className="save-actions">
                <button type="button" className="icon-button small" onClick={() => openFor("rename", save)} aria-label={`重命名 ${save.name}`}><Icon name="edit" /></button>
                <button type="button" className="icon-button small danger-text" onClick={() => openFor("delete", save)} aria-label={`删除 ${save.name}`}><Icon name="trash" /></button>
              </div>
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <Link className={location.pathname === "/settings" ? "sidebar-settings active" : "sidebar-settings"} to="/settings"><Icon name="settings" /><span>设置</span></Link>
          <div className="connection-line"><StatusDot state={loadError ? "offline" : "online"} />{loadError ? "后端未连接" : "后端已连接"}</div>
        </div>
      </aside>
      {drawerOpen && <button className="drawer-backdrop" type="button" aria-label="关闭存档列表" onClick={() => setDrawerOpen(false)} />}

      <div className="workspace">
        <header className="toolbar">
          <button className="icon-button mobile-menu" type="button" onClick={() => setDrawerOpen(true)} aria-label="打开存档列表"><Icon name="menu" /></button>
          <div className="toolbar-context">
            <span>{location.pathname === "/settings" ? "应用设置" : currentSave?.name ?? "档案总览"}</span>
            {currentSave && <small>修订 {currentSave.revision}</small>}
          </div>
          <div className="toolbar-actions">
            <button className="toolbar-button primary-compact" type="button" onClick={() => setModal("new")}><Icon name="plus" /><span>新建存档</span></button>
            <button className="toolbar-button" type="button" onClick={() => setModal("import")}><Icon name="upload" /><span>导入 JSON</span></button>
            <button className="toolbar-button" type="button" onClick={() => void exportCurrent()} disabled={!currentSave}><Icon name="download" /><span>导出存档</span></button>
            <Link className="toolbar-button settings-link" to="/settings"><Icon name="settings" /><span>设置</span></Link>
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<Home saves={saves} loading={loading} onNew={() => setModal("new")} />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/saves/:saveId/create/:step" element={<CharacterWizard actions={actions} />} />
            <Route path="/saves/:saveId/review" element={<ReviewPage actions={actions} />} />
            <Route path="/saves/:saveId/game" element={<GameWorkspace />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
      </div>

      {notice && <div className="toast" role="status">{notice}</div>}
      {modal === "new" && <NewSaveModal onClose={() => setModal(null)} onCreated={async (save) => { setModal(null); await refreshSaves(); navigate(saveRoute(save)); }} />}
      {modal === "rename" && targetSave && <RenameSaveModal save={targetSave} onClose={() => setModal(null)} onRenamed={async () => { setModal(null); await refreshSaves(); setNotice("存档已重命名。"); }} />}
      {modal === "delete" && targetSave && <DeleteSaveModal save={targetSave} onClose={() => setModal(null)} onDeleted={async () => { const wasCurrent = targetSave.id === currentId; setModal(null); await refreshSaves(); if (wasCurrent) navigate("/"); setNotice("存档已删除，无法恢复。"); }} />}
      {modal === "import" && <ImportSaveModal onClose={() => setModal(null)} onImported={async (save) => { setModal(null); await refreshSaves(); navigate(saveRoute(save)); setNotice("存档已使用新的本地 ID 导入。"); }} />}
    </div>
  );
}

function Home({ saves, loading, onNew }: { saves: SaveSummary[]; loading: boolean; onNew: () => void }) {
  return (
    <div className="page home-page">
      <div className="home-heading">
        <span className="archive-glyph" aria-hidden="true">◇</span>
        <div><h1>冒险档案</h1><p>管理独立存档，配置叙事模型，并完成角色创建。</p></div>
      </div>
      {loading ? <LoadingPanel /> : saves.length ? (
        <section className="recent-list" aria-labelledby="recent-title">
          <div className="section-heading"><h2 id="recent-title">继续最近的档案</h2><button className="primary-button" type="button" onClick={onNew}><Icon name="plus" />新建存档</button></div>
          {saves.slice(0, 5).map((save) => (
            <Link className="recent-row" key={save.id} to={saveRoute(save)}>
              <span className={`phase-shape ${save.phase}`} aria-hidden="true" />
              <span><strong>{save.name}</strong><small>{save.character_name || (save.phase === "draft" ? "角色尚未完成" : "角色待确认")}</small></span>
              <span className="phase-label">{phaseLabel[save.phase]}</span><span aria-hidden="true">→</span>
            </Link>
          ))}
        </section>
      ) : (
        <section className="empty-state">
          <div className="empty-symbol" aria-hidden="true">＋</div>
          <h2>建立第一份档案</h2>
          <p>每个存档都拥有独立的角色草稿、生成任务与叙事偏好。你可以随时切换，不会混淆响应。</p>
          <button className="primary-button" type="button" onClick={onNew}><Icon name="plus" />创建存档</button>
        </section>
      )}
    </div>
  );
}

function NewSaveModal({ onClose, onCreated }: { onClose: () => void; onCreated: (save: SaveSummary) => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const requestIdentity = useRef<LogicalRequestIdentity | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const payloadName = name.trim();
    if (!payloadName) { setError("请输入存档名称。"); return; }
    const identity = logicalRequestIdentity(requestIdentity.current, payloadName);
    requestIdentity.current = identity;
    setBusy(true); setError("");
    try { const created = await api.createSave(payloadName, identity.request_id); requestIdentity.current = null; onCreated(created); }
    catch (reason) { setError(asApiError(reason).message); setBusy(false); }
  };
  return <Modal title="新建存档" onClose={onClose} labelledBy="new-save-title"><form onSubmit={(event) => void submit(event)}><label className="field"><span>存档名称</span><input autoFocus disabled={busy} value={name} maxLength={80} onChange={(e) => { requestIdentity.current = null; setName(e.target.value); }} aria-describedby={error ? "new-save-error" : undefined} /></label>{error && <p className="field-error" id="new-save-error">{error}</p>}<div className="modal-actions"><button className="secondary-button" type="button" onClick={onClose}>取消</button><button className="primary-button" disabled={busy}>{busy ? "正在创建…" : "创建存档"}</button></div></form></Modal>;
}

function RenameSaveModal({ save, onClose, onRenamed }: { save: SaveSummary; onClose: () => void; onRenamed: () => void }) {
  const [name, setName] = useState(save.name);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) { setError("请输入存档名称。"); return; }
    setBusy(true);
    try { await api.renameSave(save.id, name.trim(), save.revision, crypto.randomUUID()); onRenamed(); }
    catch (reason) { setError(asApiError(reason).message); setBusy(false); }
  };
  return <Modal title="重命名存档" onClose={onClose} labelledBy="rename-save-title"><form onSubmit={(event) => void submit(event)}><label className="field"><span>存档名称</span><input autoFocus value={name} maxLength={80} onChange={(e) => setName(e.target.value)} /></label>{error && <p className="field-error">{error}</p>}<div className="modal-actions"><button className="secondary-button" type="button" onClick={onClose}>取消</button><button className="primary-button" disabled={busy}>{busy ? "正在保存…" : "保存名称"}</button></div></form></Modal>;
}

function DeleteSaveModal({ save, onClose, onDeleted }: { save: SaveSummary; onClose: () => void; onDeleted: () => void }) {
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true);
    try { await api.deleteSave(save.id, save.revision, crypto.randomUUID()); onDeleted(); }
    catch (reason) { setError(asApiError(reason).message); setBusy(false); }
  };
  return <Modal title="删除存档" onClose={onClose} labelledBy="delete-save-title"><form onSubmit={(event) => void submit(event)}><div className="danger-callout"><strong>此操作无法恢复</strong><p>将删除“{save.name}”及其角色草稿、候选和生成记录。运行中的生成会被取消。</p></div><label className="field"><span>输入存档名称以确认</span><input autoFocus value={confirmation} onChange={(e) => setConfirmation(e.target.value)} /></label>{error && <p className="field-error">{error}</p>}<div className="modal-actions"><button className="secondary-button" type="button" onClick={onClose}>保留存档</button><button className="danger-button" disabled={busy || confirmation !== save.name}>{busy ? "正在删除…" : "永久删除存档"}</button></div></form></Modal>;
}

function ImportSaveModal({ onClose, onImported }: { onClose: () => void; onImported: (save: SaveSummary) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [pending, setPending] = useState<PendingImport | null>(null);
  const [trusted, setTrusted] = useState(false);
  const [filename, setFilename] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const requestIdentity = useRef<LogicalRequestIdentity | null>(null);
  const trustIdentity = useRef<LogicalRequestIdentity | null>(null);
  const choose = async (file?: File) => {
    if (!file) return;
    requestIdentity.current = null;
    trustIdentity.current = null;
    setFile(null); setBusy(true); setError(""); setPreview(null); setPending(null); setTrusted(false); setFilename(file.name);
    if (file.size > 64 * 1024 * 1024) {
      setError("文件超过 64 MB 导入上限。"); setBusy(false); return;
    }
    try {
      const result = await api.validateLargeImport(file);
      setFile(file); setPreview(result);
    } catch (reason) {
      setError(asApiError(reason).message);
    } finally { setBusy(false); }
  };
  const submit = async () => {
    if (!file || !preview?.valid) return;
    const payloadKey = `${file.name}:${file.size}:${file.lastModified}:${file.type}`;
    const identity = logicalRequestIdentity(requestIdentity.current, payloadKey);
    requestIdentity.current = identity;
    setBusy(true); setError("");
    try {
      const result = await api.importLargeSave(file, identity.request_id);
      if (isPendingImport(result)) { setPending(result); setBusy(false); return; }
      requestIdentity.current = null; onImported(result);
    }
    catch (reason) { setError(asApiError(reason).message); setBusy(false); }
  };
  const trustAndImport = async () => {
    if (!pending || !trusted) return;
    const payloadKey = `${pending.pending_import_id}:${pending.revision_id}`;
    const identity = logicalRequestIdentity(trustIdentity.current, payloadKey);
    trustIdentity.current = identity;
    setBusy(true); setError("");
    try { const save = await api.trustAndImport(pending.pending_import_id, pending.revision_id, identity.request_id); trustIdentity.current = null; onImported(save); }
    catch (reason) { setError(asApiError(reason).message); setBusy(false); }
  };
  return <Modal title="导入存档" onClose={onClose} labelledBy="import-save-title"><div className="import-flow"><label className="file-picker"><Icon name="upload" /><span><strong>{filename || "选择 JSON 存档"}</strong><small>支持最大 64 MB。导入会分配新的本地存档 ID，不覆盖现有存档。</small></span><input type="file" disabled={busy} accept="application/json,.json" onChange={(e) => void choose(e.target.files?.[0])} /></label>{busy && !preview && <p className="inline-status"><StatusDot state="busy" />正在校验文件…</p>}{preview && !pending && <div className={`import-preview ${preview.valid ? "success" : "error"}`}><strong>{preview.valid ? "文件可以导入" : "文件不兼容"}</strong><dl><div><dt>存档</dt><dd>{preview.save_name || "未命名"}</dd></div><div><dt>阶段</dt><dd>{preview.phase ? phaseLabel[preview.phase] : "未知"}</dd></div><div><dt>角色</dt><dd>{preview.character_name || "尚未确认"}</dd></div><div><dt>规则版本</dt><dd>{preview.ruleset_version || "未知"}</dd></div></dl>{preview.confirmation_required && <p className="warning-text">此存档包含本机尚未信任的内容版本，提交后需要单独确认。</p>}{preview.warnings?.map((warning) => <p className="warning-text" key={warning}>注意：{warning}</p>)}</div>}{pending && <div className="pending-import" role="region" aria-labelledby="pending-import-title"><h3 id="pending-import-title">确认导入内容版本</h3><p>存档携带本机尚未信任的规则与设定快照。哈希已由后端校验，仍需你明确确认后才能安装。</p><dl><div><dt>内容版本</dt><dd>{pending.revision_id}</dd></div><div><dt>提示版本</dt><dd>{pending.content_revision.prompt_version || "未标注"}</dd></div><div><dt>失效时间</dt><dd>{pending.expires_at}</dd></div></dl><ul>{pending.content_revision.documents.map((item) => <li key={item.document_id}><strong>{item.source_path}</strong><span>{item.byte_count.toLocaleString()} 字节</span><code title={item.raw_sha256}>{item.raw_sha256.slice(0, 12)}…</code></li>)}</ul><label className="trust-confirm"><input type="checkbox" checked={trusted} onChange={(event) => { trustIdentity.current = null; setTrusted(event.target.checked); }} /><span>我已核对内容版本和文档哈希摘要，并信任此快照。</span></label></div>}{error && <p className="field-error" role="alert">{error}</p>}<div className="modal-actions"><button className="secondary-button" type="button" onClick={onClose}>取消</button>{pending ? <button className="primary-button" type="button" disabled={!trusted || busy} onClick={() => void trustAndImport()}>{busy ? "正在信任并导入…" : "信任版本并导入"}</button> : <button className="primary-button" type="button" disabled={!preview?.valid || busy} onClick={() => void submit()}>{busy && preview ? "正在导入…" : "确认导入"}</button>}</div></div></Modal>;
}

function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [modelState, setModelState] = useState<ModelState>("idle");
  const [narrationState, setNarrationState] = useState<NarrationState>("idle");
  const [testState, setTestState] = useState<ModelTestState>("idle");
  const [testResult, setTestResult] = useState<{ key: string; result: ModelTestResult } | null>(null);
  const [structuredProbeFeedback, setStructuredProbeFeedback] = useState<{ kind: "success" | "error"; message: string } | null>(null);
  const [actionError, setActionError] = useState("");
  const testRequestToken = useRef(0);
  const settingRequestInFlight = useRef(false);

  const beginSettingRequest = () => {
    if (settingRequestInFlight.current) return false;
    settingRequestInFlight.current = true;
    return true;
  };

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setSettings(await api.getSettings()); }
    catch (reason) { setError(reason); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const modelPayload = () => {
    if (!settings) throw new Error("设置尚未载入");
    const model = {
      base_url: settings.model.base_url,
      model: settings.model.model,
      timeout_seconds: settings.model.timeout_seconds,
      structured_output: settings.model.structured_output && settings.model.structured_output_capability === "supported",
      thinking_enabled: settings.model.thinking_enabled,
      max_concurrency: settings.model.max_concurrency,
      ...(apiKey ? { api_key: apiKey } : {}),
    };
    return model;
  };
  const saveModel = async (event: FormEvent) => {
    event.preventDefault();
    if (!settings || !canStartSettingRequest(modelState, narrationState, testState) || !beginSettingRequest()) return;
    const requestedKey = modelCapabilityKey(settings.model.base_url, settings.model.model);
    setModelState("saving"); setActionError(""); setTestResult(null); setStructuredProbeFeedback(null);
    try {
      const updated = await api.updateModel({ ...modelPayload(),
        ...(settings.model.structured_output_probe_token ? {
          structured_output_probe_token: settings.model.structured_output_probe_token,
        } : {}) }, settings.revision, crypto.randomUUID());
      setSettings((current) => {
        if (!current || modelCapabilityKey(current.model.base_url, current.model.model) !== requestedKey) return current;
        return mergeSavedModelSettings(current, updated);
      });
      setApiKey(""); setModelState("saved");
      window.setTimeout(() => setModelState("idle"), 2200);
    } catch (reason) {
      const apiError = asApiError(reason);
      setActionError(apiError.message);
      if (isStructuredOutputError(apiError)) {
        setSettings((current) => resetStructuredOutputCapability(current, apiError.message));
      }
      setModelState("idle");
    } finally {
      settingRequestInFlight.current = false;
    }
  };
  const testModel = async (forceThinkingProbe = false) => {
    if (!settings || !canStartSettingRequest(modelState, narrationState, testState) || !beginSettingRequest()) return;
    const requestedKey = modelCapabilityKey(settings.model.base_url, settings.model.model);
    const requestToken = ++testRequestToken.current;
    setTestState("testing"); setActionError(""); setTestResult(null); setStructuredProbeFeedback(null);
    try {
      const result = await api.testModel({ ...modelPayload(), force_thinking_probe: forceThinkingProbe });
      if (!isCurrentModelTestResponse(settings, requestedKey, requestToken, testRequestToken.current)) return;
      setTestResult({ key: requestedKey, result });
      setSettings((current) => {
        if (!isCurrentModelTestResponse(current, requestedKey, requestToken, testRequestToken.current)) return current;
        return mergeModelTestCapability(current, requestedKey, result);
      });
    } catch (reason) {
      if (requestToken === testRequestToken.current) setActionError(asApiError(reason).message);
    }
    finally {
      settingRequestInFlight.current = false;
      if (requestToken === testRequestToken.current) setTestState("idle");
    }
  };
  const probeStructuredOutput = async () => {
    if (!settings || !canStartSettingRequest(modelState, narrationState, testState) || !beginSettingRequest()) return;
    const requestedKey = modelCapabilityKey(settings.model.base_url, settings.model.model);
    const requestToken = ++testRequestToken.current;
    setTestState("probing"); setActionError(""); setTestResult(null); setStructuredProbeFeedback(null);
    setSettings((current) => resetStructuredOutputCapability(current, "正在探测 response_format 支持情况…"));
    try {
      const result = await api.testModel(structuredOutputProbePayload(modelPayload()));
      if (!isCurrentModelTestResponse(settings, requestedKey, requestToken, testRequestToken.current)) return;
      setTestResult({ key: requestedKey, result });
      setSettings((current) => {
        if (!isCurrentModelTestResponse(current, requestedKey, requestToken, testRequestToken.current)) return current;
        return mergeModelTestCapability(current, requestedKey, result, true);
      });
      if (result.structured_output_capability === "supported") {
        setStructuredProbeFeedback({ kind: "success", message: result.structured_output_message || "当前模型服务支持 response_format，已开启。" });
      } else {
        setStructuredProbeFeedback({ kind: "error", message: "当前模型服务不支持 response_format，已保持关闭" });
      }
    } catch (reason) {
      if (requestToken !== testRequestToken.current) return;
      const apiError = asApiError(reason);
      setSettings((current) => resetStructuredOutputCapability(current, apiError.message));
      setActionError(apiError.message);
    } finally {
      settingRequestInFlight.current = false;
      if (requestToken === testRequestToken.current) setTestState("idle");
    }
  };
  const invalidateModelTest = (update: (model: AppSettings["model"]) => AppSettings["model"]) => {
    testRequestToken.current += 1;
    setSettings((current) => current ? { ...current, model: invalidateModelCapabilities(update(current.model)) } : current);
    setTestResult(null); setStructuredProbeFeedback(null); setTestState("idle");
  };
  const saveNarration = async (event: FormEvent) => {
    event.preventDefault();
    if (!settings || !canStartSettingRequest(modelState, narrationState, testState) || !beginSettingRequest()) return;
    setNarrationState("saving"); setActionError("");
    try {
      const updated = await api.updateNarration(settings.narration, settings.revision, crypto.randomUUID());
      setSettings((current) => current ? mergeSavedNarrationSettings(current, updated) : current);
      setNarrationState("saved");
      window.setTimeout(() => setNarrationState("idle"), 2200);
    } catch (reason) {
      setActionError(asApiError(reason).message); setNarrationState("idle");
    } finally {
      settingRequestInFlight.current = false;
    }
  };

  if (loading) return <div className="page settings-page"><LoadingPanel label="正在载入设置" /></div>;
  if (error || !settings) return <div className="page settings-page"><ErrorPanel error={error} onRetry={() => void load()} title="无法载入设置" /></div>;
  const displayedTestResult = (testResult?.key === modelCapabilityKey(
    settings.model.base_url, settings.model.model
  )) ? testResult.result : null;
  const canMutateModel = canMutateModelSettings(modelState, testState);
  const canSubmitSettingRequest = canStartSettingRequest(modelState, narrationState, testState);
  return (
    <div className="page settings-page">
      <header className="page-header"><div><h1>设置</h1><p>模型配置保存在本机后端，存档导出不会包含 API Key。</p></div></header>
      {actionError && <div className="inline-error" role="alert">{actionError}</div>}
      <section className="settings-section" aria-labelledby="model-settings-title">
        <div className="settings-copy"><h2 id="model-settings-title">模型服务</h2><p>连接兼容 OpenAI HTTP 协议的服务。自定义地址将由后端访问，请只使用你信任的端点。</p></div>
        <form className="settings-form" onSubmit={(event) => void saveModel(event)}>
          <label className="field full"><span>API Base URL</span><input type="url" required disabled={!canMutateModel} placeholder="https://api.example.com/v1" value={settings.model.base_url} onChange={(e) => invalidateModelTest((model) => ({ ...model, base_url: e.target.value }))} /></label>
          <label className="field"><span>模型名称</span><input required disabled={!canMutateModel} placeholder="模型标识" value={settings.model.model} onChange={(e) => invalidateModelTest((model) => ({ ...model, model: e.target.value }))} /></label>
          <label className="field"><span>API Key</span><input type="password" disabled={!canMutateModel} autoComplete="new-password" placeholder={settings.model.api_key_configured ? "已配置，留空则保持不变" : "输入后仅发送一次"} value={apiKey} onChange={(e) => { setApiKey(e.target.value); invalidateModelTest((model) => model); }} aria-describedby="key-help" /><small id="key-help">读取设置时只显示配置状态，不回显任何密钥内容。</small></label>
          <label className="field"><span>请求超时（秒）</span><input type="number" min={5} max={600} required disabled={!canMutateModel} value={settings.model.timeout_seconds} onChange={(e) => setSettings({ ...settings, model: { ...settings.model, timeout_seconds: Number(e.target.value) } })} /></label>
          <label className="field"><span>最大并发</span><input type="number" min={1} max={16} required disabled={!canMutateModel} value={settings.model.max_concurrency} onChange={(e) => setSettings({ ...settings, model: { ...settings.model, max_concurrency: Number(e.target.value) } })} /></label>
          <div className="switch-field full">
            <div><span id="structured-output-label">Response Format（结构化输出）</span><small id="structured-output-help" role="status" aria-live="polite">多数兼容服务可能不支持，默认关闭。开启时会发送一次极小测试请求，可能产生少量费用；关闭不会探测。当前状态：{testState === "probing" ? "正在探测" : capabilityLabel(settings.model.structured_output_capability)}。</small></div>
            <label className="switch"><input type="checkbox" aria-labelledby="structured-output-label" aria-describedby="structured-output-help" aria-busy={testState === "probing"} disabled={!canMutateModel || narrationState === "saving"} checked={settings.model.structured_output} onChange={(e) => { if (e.target.checked) void probeStructuredOutput(); else { testRequestToken.current += 1; setSettings((current) => resetStructuredOutputCapability(current, "结构化输出已关闭。")); setTestResult(null); setStructuredProbeFeedback(null); setTestState("idle"); } }} /><span aria-hidden="true" /></label>
          </div>
          {structuredProbeFeedback && <div className={`test-result full ${structuredProbeFeedback.kind}`} role={structuredProbeFeedback.kind === "error" ? "alert" : "status"}><strong>{structuredProbeFeedback.kind === "success" ? "结构化输出探测通过" : "结构化输出未开启"}</strong><p>{structuredProbeFeedback.message}</p></div>}
          <div className="switch-field full">
            <div><span id="model-thinking-label">模型思考</span><small>{settings.model.thinking_message || thinkingCapabilityMessage(settings.model.thinking_capability, settings.model.thinking_confidence, settings.model.thinking_strategy)}</small></div>
            <label className="switch"><input type="checkbox" aria-labelledby="model-thinking-label" disabled={!canMutateModel || settings.model.thinking_capability !== "controlled"} checked={settings.model.thinking_capability === "controlled" ? settings.model.thinking_enabled : true} onChange={(e) => setSettings({ ...settings, model: { ...settings.model, thinking_enabled: e.target.checked } })} /><span aria-hidden="true" /></label>
          </div>
          {displayedTestResult && <div className={`test-result full ${displayedTestResult.ok ? "success" : "error"}`} role="status"><strong>{displayedTestResult.ok ? "连接测试通过" : "连接测试未通过"}</strong><p>{displayedTestResult.message}</p><div className="capabilities"><span>目标模型：{displayedTestResult.model_available === false ? "不可用" : "可用"}</span>{displayedTestResult.latency_ms !== undefined && <span>响应：{displayedTestResult.latency_ms} ms</span>}<span>思考：{thinkingCapabilityLabel(displayedTestResult.thinking_capability)}</span><span>置信度：{thinkingConfidenceLabel(displayedTestResult.thinking_confidence)}</span>{displayedTestResult.thinking_strategy && <span>识别方式：{thinkingStrategyLabel(displayedTestResult.thinking_strategy)}</span>}<span>结构化输出：{capabilityLabel(displayedTestResult.structured_output_capability)}</span></div><p>{displayedTestResult.thinking_message}</p></div>}
          {settings.model.api_key_persistence === "memory_only" && <p className="warning-text full">当前环境无法使用 Windows DPAPI，API Key 只保存在本进程内存中，服务重启后需重新输入。</p>}
          <div className="form-actions full"><button className="secondary-button" type="button" disabled={!canSubmitSettingRequest} onClick={() => void testModel()}>{testState === "testing" ? "正在测试连接与思考控制…" : "测试连接"}</button>{settings.model.thinking_capability !== "unknown" && <button className="secondary-button" type="button" disabled={!canSubmitSettingRequest} onClick={() => void testModel(true)}>重新探测思考控制</button>}<span className="cost-note">普通测试复用已缓存能力；结构化输出关闭时不会探测 response_format。强制重测可能产生少量费用。</span><button className="primary-button" disabled={!canSubmitSettingRequest}>{modelState === "saving" ? "正在保存…" : modelState === "saved" ? "设置已保存" : "保存模型设置"}</button></div>
        </form>
      </section>
      <section className="settings-section" aria-labelledby="narration-title">
        <div className="settings-copy"><h2 id="narration-title">叙事默认值</h2><p>新建存档时复制这些偏好，已有存档不会被覆盖。</p></div>
        <form className="settings-form narration" onSubmit={(event) => void saveNarration(event)}>
          <SegmentedField label="步进速度" value={settings.narration.pace} options={[{ value: "slow", label: "慢速" }, { value: "fast", label: "快速" }, { value: "dynamic", label: "动态" }]} disabled={narrationState === "saving"} onChange={(pace) => setSettings((current) => current ? { ...current, narration: { ...current.narration, pace } } : current)} />
          <SegmentedField label="叙事倾向" value={settings.narration.tendency} options={[{ value: "casual", label: "日常" }, { value: "balanced", label: "平衡" }, { value: "combat", label: "战斗" }]} disabled={narrationState === "saving"} onChange={(tendency) => setSettings((current) => current ? { ...current, narration: { ...current.narration, tendency } } : current)} />
          <SegmentedField label="内容详细度" value={settings.narration.detail} options={[{ value: "concise", label: "简洁" }, { value: "standard", label: "标准" }, { value: "detailed", label: "详细" }]} disabled={narrationState === "saving"} onChange={(detail) => setSettings((current) => current ? { ...current, narration: { ...current.narration, detail } } : current)} />
          <div className="form-actions full"><button className="primary-button" disabled={!canSubmitSettingRequest}>{narrationState === "saving" ? "正在保存…" : narrationState === "saved" ? "偏好已保存" : "保存叙事设置"}</button></div>
        </form>
      </section>
    </div>
  );
}

function capabilityLabel(value?: "supported" | "unsupported" | "unknown") {
  return value === "supported" ? "支持" : value === "unsupported" ? "不支持" : "未知";
}

function thinkingCapabilityLabel(value: "controlled" | "unsupported" | "unknown") {
  return value === "controlled" ? "已验证" : value === "unsupported" ? "服务不支持关闭" : "未测试";
}

function thinkingConfidenceLabel(value: "verified" | "accepted_bundle" | "unsupported" | "unknown") {
  return value === "verified" ? "verified（逐项验证）" : value === "accepted_bundle" ? "accepted_bundle（组合接受）" : value === "unsupported" ? "unsupported" : "unknown";
}

export function thinkingStrategyLabel(value: ModelTestResult["thinking_strategy"]) {
  const labels = { bundle: "七种兼容参数组合", enable_thinking: "enable_thinking", thinking: "thinking.type", reasoning_effort: "reasoning_effort", chat_template_kwargs: "chat_template_kwargs.enable_thinking", reasoning_enabled: "reasoning.enabled", reasoning_effort_nested: "reasoning.effort", thinking_budget: "thinking_config.thinking_budget" };
  return value ? labels[value] : "未识别";
}

export function thinkingCapabilityMessage(capability: "controlled" | "unsupported" | "unknown", confidence: "verified" | "accepted_bundle" | "unsupported" | "unknown", strategy?: ModelTestResult["thinking_strategy"]) {
  if (capability === "unsupported") return "当前服务不支持关闭思考；模型保持开启、默认思考或不受应用控制。";
  if (capability === "unknown") return "未测试。请先测试连接，确认服务是否接受思考控制参数。";
  return confidence === "accepted_bundle" ? "服务接受兼容参数组合，无法逐项证明。" : `已验证思考控制参数：${thinkingStrategyLabel(strategy)}。`;
}

export function modelCapabilityKey(baseUrl: string, model: string): string {
  return `${baseUrl.trim().replace(/\/+$/, "")}\n${model.trim()}`;
}

export function canMutateModelSettings(modelState: ModelState, testState: ModelTestState): boolean {
  return modelState !== "saving" && testState === "idle";
}

export function canStartSettingRequest(
  modelState: ModelState,
  narrationState: NarrationState,
  testState: ModelTestState,
): boolean {
  return modelState !== "saving" && narrationState !== "saving" && testState === "idle";
}

export function mergeSavedModelSettings(current: AppSettings, updated: AppSettings): AppSettings {
  return { ...current, model: updated.model, revision: updated.revision };
}

export function mergeSavedNarrationSettings(current: AppSettings, updated: AppSettings): AppSettings {
  return { ...current, narration: updated.narration, revision: updated.revision };
}

export function structuredOutputProbePayload(payload: Parameters<typeof api.testModel>[0]): Parameters<typeof api.testModel>[0] {
  return { ...payload, structured_output: false, probe_structured_output: true };
}

export function isCurrentModelTestResponse(current: AppSettings | null, requestedKey: string, requestToken: number, currentToken: number): boolean {
  return requestToken === currentToken && current !== null && modelCapabilityKey(current.model.base_url, current.model.model) === requestedKey;
}

export function resetStructuredOutputCapability(current: AppSettings | null, message?: string): AppSettings | null {
  if (!current) return current;
  return { ...current, model: { ...current.model, structured_output: false,
    structured_output_capability: "unknown", structured_output_message: message,
    structured_output_probed_at: null, structured_output_probe_token: undefined } };
}

export function invalidateModelCapabilities(model: AppSettings["model"]): AppSettings["model"] {
  return { ...model, structured_output: false, structured_output_capability: "unknown",
    structured_output_message: "结构化输出能力未探测。", structured_output_probed_at: null,
    structured_output_probe_token: undefined,
    thinking_enabled: true, thinking_capability: "unknown", thinking_strategy: null,
    thinking_confidence: "unknown", thinking_message: "思考控制能力未测试，请先测试连接。",
    thinking_probed_at: null };
}

export function isStructuredOutputError(error: ApiError): boolean {
  const text = [error.problem.code, error.problem.message, ...Object.keys(error.problem.field_errors ?? {})].join(" ");
  return /structured[_ ]?output|response[_ ]?format/i.test(text);
}

export function mergeModelTestCapability(
  current: AppSettings | null,
  requestedKey: string,
  result: ModelTestResult,
  structuredOutputProbe = false,
): AppSettings | null {
  if (!current || modelCapabilityKey(current.model.base_url, current.model.model) !== requestedKey) {
    return current;
  }
  const reportedCapability = result.structured_output_capability;
  const capability = !structuredOutputProbe && (!reportedCapability || reportedCapability === "unknown")
    ? current.model.structured_output_capability
    : reportedCapability ?? "unknown";
  return { ...current, model: { ...current.model,
    thinking_capability: result.thinking_capability,
    thinking_strategy: result.thinking_strategy,
    thinking_confidence: result.thinking_confidence,
    thinking_message: result.thinking_message,
    thinking_probed_at: result.thinking_probed_at,
    structured_output: structuredOutputProbe ? capability === "supported" :
      current.model.structured_output && capability === "supported",
    structured_output_capability: capability,
    structured_output_message: result.structured_output_message ?? current.model.structured_output_message,
    structured_output_probed_at: result.structured_output_probed_at ?? current.model.structured_output_probed_at,
    structured_output_probe_token: structuredOutputProbe ?
      (capability === "supported" ? result.structured_output_probe_token : undefined) :
      current.model.structured_output_probe_token } };
}

function SegmentedField<T extends string>({ label, value, options, disabled = false, onChange }: { label: string; value: T; options: Array<{ value: T; label: string }>; disabled?: boolean; onChange: (value: T) => void }) {
  return <fieldset className="segmented-field full" disabled={disabled}><legend>{label}</legend><div>{options.map((option) => <label key={option.value}><input type="radio" name={label} value={option.value} checked={value === option.value} onChange={() => onChange(option.value)} /><span>{option.label}</span></label>)}</div></fieldset>;
}

function CharacterWizard({ actions }: { actions: ShellActions }) {
  const { saveId = "", step: stepParam = "1" } = useParams();
  const navigate = useNavigate();
  const step = Math.min(13, Math.max(1, Number(stepParam) || 1));
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

  useEffect(() => {
    if (saveStatus !== "dirty" || loadedId.current !== saveId) return;
    const timer = window.setTimeout(() => void persistDraft(), 800);
    return () => window.clearTimeout(timer);
  }, [draft, persistDraft, saveId, saveStatus]);

  useEffect(() => {
    const warnBeforeClose = (event: BeforeUnloadEvent) => {
      if (saveStatus === "saved") return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeClose);
    return () => window.removeEventListener("beforeunload", warnBeforeClose);
  }, [saveStatus]);

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
        actions.setNotice("草稿尚未保存，请先重试保存或处理版本冲突。");
      }
    };
    document.addEventListener("click", protectInternalNavigation, true);
    return () => document.removeEventListener("click", protectInternalNavigation, true);
  }, [actions, navigate, persistDraft, saveStatus]);

  useEffect(() => {
    const active = job && ["queued", "running", "cancel_requested"].includes(job.status);
    if (!active) return;
    const requestedId = saveId;
    const jobId = job.id;
    const controller = new AbortController();
    const timer = window.setInterval(async () => {
      try {
        const next = await api.getGeneration(requestedId, jobId, controller.signal);
        if (requestedId !== loadedId.current || next.save_id !== requestedId || next.id !== jobId) return;
        setJob(next);
        if (next.status === "succeeded") {
          const [completedCandidate, completedSave] = await Promise.all([
            api.getCandidate(requestedId, controller.signal),
            api.getSave(requestedId, controller.signal),
          ]);
          if (controller.signal.aborted || requestedId !== loadedId.current) return;
          setCandidate(completedCandidate);
          saveRef.current = completedSave;
          setSave(completedSave);
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
    setDraft(latest); navigate(`/saves/${saveId}/create/${nextStep}`);
  };

  const startGeneration = async (feedback = "") => {
    setGenerationError(null);
    if (!catalog || !save) return;
    const invalid = validateDraft(draft, catalog);
    if (invalid) {
      setValidationError(invalid.message);
      navigate(`/saves/${saveId}/create/${invalid.step}`);
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

  if (loading) return <div className="page"><LoadingPanel label="正在载入角色草稿" /></div>;
  if (error || !catalog || !save) return <div className="page"><ErrorPanel error={error} onRetry={() => void load()} title="无法载入角色草稿" /></div>;

  return (
    <div className="page wizard-page">
      <header className="wizard-header">
        <div><span className="step-count">第 {step} 步，共 13 步</span><h1>{steps[step - 1]}</h1></div>
        <DraftStatus status={saveStatus} revision={draft.draft_revision} onRetry={() => void persistDraft()} onReload={() => void load()} />
      </header>
      <div className="wizard-layout">
        <nav className="step-nav" aria-label="角色创建步骤">
          {steps.map((label, index) => {
            const number = index + 1;
            return <button type="button" key={label} className={`${number === step ? "active" : ""} ${number < step ? "complete" : ""}`} aria-current={number === step ? "step" : undefined} onClick={() => void go(number)}><span>{number < step ? "✓" : number}</span><span>{label}<small>{stepSummary(number, draft, catalog)}</small></span></button>;
          })}
        </nav>
        <section className="step-content" aria-labelledby="step-title">
          <div className="step-title"><h2 id="step-title">{stepTitle(step)}</h2><p>{stepDescription(step)}</p></div>
          {validationError && <p className="validation-banner" role="alert">{validationError}</p>}
          {saveStatus === "conflict" && <DraftConflict serverDraft={serverDraft} catalog={catalog} onUseServer={() => { if (!serverDraft) return; editVersion.current += 1; setDraft(serverDraft); setSaveStatus("saved"); }} onReload={() => void load()} />}
          {step === 1 && <RaceStep catalog={catalog} draft={draft} update={updateDraft} />}
          {step === 2 && <TextStep label="角色姓名" value={draft.name} onChange={(value) => updateDraft("name", value)} maxLength={80} placeholder="输入角色姓名" />}
          {step === 3 && <GenderStep draft={draft} update={updateDraft} />}
          {step === 4 && <AgeStep catalog={catalog} draft={draft} update={updateDraft} />}
          {step === 5 && <PresetTextStep label="外貌描述" presets={catalog.presets.appearance} raceId={draft.race_id} value={draft.appearance} update={(value) => updateDraft("appearance", value)} placeholder="描述体态、面容、发色、衣着或显著特征" />}
          {step === 6 && <PresetTextStep label="性格描述" presets={catalog.presets.personality} raceId={draft.race_id} value={draft.personality} update={(value) => updateDraft("personality", value)} placeholder="描述性情、习惯、价值观与待人方式" />}
          {step === 7 && <RankStep catalog={catalog} draft={draft} update={updateDraft} />}
          {step === 8 && <PresetTextStep label="天赋描述" presets={catalog.presets.talent} raceId={draft.race_id} value={draft.talent} update={(value) => updateDraft("talent", value)} placeholder="描述与生俱来或后天形成的突出能力" note="这些预设是玩家描述词，不直接提供程序数值加成。最终属性由模型结合完整角色设定生成，并由程序校验。" />}
          {step === 9 && <TextStep label="身世与经历" value={draft.background} onChange={(value) => updateDraft("background", value)} maxLength={4000} optional multiline placeholder="可以留空。写下角色的成长环境、重要经历或未解心结。" />}
          {step === 10 && <LocationStep catalog={catalog} draft={draft} update={updateDraft} />}
          {step === 11 && <FactionStep factions={catalog.factions} activeId={browsedFactionId} setActiveId={setBrowsedFactionId} />}
          {step === 12 && <TextStep label="其他补充" value={draft.additional} onChange={(value) => updateDraft("additional", value)} maxLength={4000} optional multiline placeholder="可以留空。补充上述步骤没有覆盖、但希望模型理解的角色信息。" />}
          {step === 13 && <GenerationStep catalog={catalog} draft={draft} job={job} candidate={candidate} error={generationError} onGenerate={startGeneration} onCancel={cancelGeneration} />}
          {step < 13 && <div className="wizard-actions"><button className="secondary-button" type="button" disabled={step === 1 || saveStatus === "saving"} onClick={() => void go(step - 1)}>上一步</button><button className="primary-button" type="button" disabled={saveStatus === "saving"} onClick={() => void go(step + 1)}>{saveStatus === "saving" ? "正在保存…" : "保存并下一步"}</button></div>}
        </section>
      </div>
    </div>
  );
}

function DraftStatus({ status, revision, onRetry, onReload }: { status: SaveStatus; revision: number; onRetry: () => void; onReload: () => void }) {
  const config = {
    saved: ["saved", "已保存"], dirty: ["dirty", "有未保存更改"], saving: ["saving", "保存中"], error: ["error", "保存失败"], conflict: ["warning", "版本冲突"],
  }[status];
  return <div className="draft-status" role="status" aria-live="polite"><StatusDot state={status === "saved" ? "online" : status === "saving" || status === "dirty" ? "busy" : "offline"} /><span><strong className={config[0]}>{config[1]}</strong><small>草稿修订 {revision}</small></span>{status === "error" && <button type="button" className="text-button" onClick={onRetry}>重试保存</button>}{status === "conflict" && <button type="button" className="text-button" onClick={onReload}>载入服务器版本</button>}</div>;
}

function DraftConflict({ serverDraft, catalog, onUseServer, onReload }: { serverDraft: CharacterDraft | null; catalog: WorldCatalog; onUseServer: () => void; onReload: () => void }) {
  const race = catalog.races.find((item) => item.id === serverDraft?.race_id)?.name;
  const location = catalog.locations.find((item) => item.id === serverDraft?.location_id)?.name;
  return <section className="draft-conflict" role="alert"><div className="state-symbol" aria-hidden="true">!</div><div><h3>服务器上存在更新的草稿</h3><p>本地编辑没有覆盖服务器内容。请比较服务器摘要，再决定是否放弃本地更改。</p>{serverDraft ? <details><summary>查看服务器修订 {serverDraft.draft_revision} 摘要</summary><dl><div><dt>姓名</dt><dd>{serverDraft.name || "未填写"}</dd></div><div><dt>种族</dt><dd>{race || "未选择"}</dd></div><div><dt>等阶</dt><dd>{serverDraft.rank ? `${serverDraft.rank} 阶` : "未选择"}</dd></div><div><dt>地区</dt><dd>{location || "未选择"}</dd></div><div><dt>当前步骤</dt><dd>{serverDraft.current_step} / 13</dd></div></dl></details> : <p>暂时无法读取服务器摘要，可以重新请求最新草稿。</p>}<div className="conflict-actions"><button className="secondary-button" type="button" onClick={onReload}>重新读取服务器草稿</button><button className="danger-button" type="button" disabled={!serverDraft} onClick={onUseServer}>放弃本地更改并使用服务器版本</button></div></div></section>;
}

function validateStep(step: number, draft: CharacterDraft, catalog: WorldCatalog | null): string {
  if (step === 1 && !draft.race_id) return "请选择角色种族。";
  const race = catalog?.races.find((item) => item.id === draft.race_id);
  if (step === 1 && race?.branches?.length && !draft.race_branch_id) return "请选择该种族的分支。";
  if (step === 2 && !draft.name.trim()) return "请输入角色姓名。";
  if (step === 3 && !draft.gender.trim()) return "请选择或输入角色性别。";
  if (step === 4 && (!draft.age || draft.age < 1)) return "请输入大于 0 的整数年龄。";
  if (step === 5 && !draft.appearance.trim()) return "请补充角色外貌。";
  if (step === 6 && !draft.personality.trim()) return "请补充角色性格。";
  if (step === 7 && !draft.rank) return "请选择角色等阶。";
  if (step === 8 && !draft.talent.trim()) return "请补充角色天赋。";
  if (step === 10 && !draft.location_id) return "请选择初始地点。";
  return "";
}

function validateDraft(draft: CharacterDraft, catalog: WorldCatalog): { step: number; message: string } | null {
  for (const step of [1, 2, 3, 4, 5, 6, 7, 8, 10]) {
    const message = validateStep(step, draft, catalog);
    if (message) return { step, message };
  }
  return null;
}

function stepTitle(step: number) {
  return ["选择角色种族", "为角色命名", "确定角色性别", "填写角色年龄", "描绘角色外貌", "塑造角色性格", "选择初始等阶", "描述角色天赋", "补充角色身世", "选择初始地点", "浏览世界势力", "添加其他信息", "生成并确认角色"][step - 1];
}
function stepDescription(step: number) {
  return ["浏览可玩种族的特征与寿命提示，然后作出选择。", "姓名将进入正式角色档案，确认前仍可修改。", "使用预设选项，或直接输入更符合角色的描述。", "平均寿命仅供参考，不作为年龄上限。", "预设词会追加到文本中，你可以继续编辑。", "用明确的性格特征帮助模型理解角色。", "等阶影响基础战力与游戏体验，请留意高阶警告。", "预设词只提供方向，最终文本由你决定。", "此项可留空，不会阻止后续生成。", "浏览地点资料并选择角色开始冒险的位置。", "势力资料只供了解，不会写入角色草稿。", "此项可留空，用于记录额外约束或想法。", "检查输入，发起异步生成，并在接受前审阅完整候选。 "][step - 1];
}

function stepSummary(step: number, draft: CharacterDraft, catalog: WorldCatalog) {
  if (step === 1) return catalog.races.find((r) => r.id === draft.race_id)?.name ?? "未选择";
  if (step === 2) return draft.name || "未填写";
  if (step === 3) return draft.gender || "未填写";
  if (step === 4) return draft.age ? `${draft.age} 岁` : "未填写";
  if (step === 7) return draft.rank ? `${draft.rank} 阶` : "未选择";
  if (step === 10) return catalog.locations.find((l) => l.id === draft.location_id)?.name ?? "未选择";
  if (step === 11) return "只读浏览";
  if ([5, 6, 8, 9, 12].includes(step)) {
    const value = ({ 5: draft.appearance, 6: draft.personality, 8: draft.talent, 9: draft.background, 12: draft.additional } as Record<number, string>)[step];
    return value ? "已填写" : "未填写";
  }
  return "";
}

function ArtworkPlaceholder({ title, imagePath }: { title: string; imagePath?: string | null }) {
  return <div className="art-placeholder" role="img" aria-label={`${title}设定图占位，图片尚未提供`}><div className="art-lines" aria-hidden="true"><span /><span /><span /></div><span>设定图待补充</span>{imagePath && <small>资源位置：{imagePath}</small>}</div>;
}

function ResponsiveArtwork({ item, alt, kind }: { item: MediaPaths; alt: string; kind: "种族" | "地点" | "势力" }) {
  const [imageAvailable, setImageAvailable] = useState(true);
  const sources = mediaPictureSources(item);
  return <figure className="responsive-artwork">
    {imageAvailable ? <picture>
      {sources.map((source) => <source key={source.media} media={source.media} srcSet={source.srcSet} />)}
      <img src={item.image_landscape_path} alt={alt} onError={() => setImageAvailable(false)} />
    </picture> : <div className="responsive-artwork-placeholder" role="img" aria-label={`${alt}占位，图片尚未提供`}>
      <span aria-hidden="true">◇</span>
      <strong>{alt.replace(`${kind}设定图`, "")}</strong>
      <small>{kind}设定图待补充</small>
    </div>}
  </figure>;
}

function RaceFacts({ facts }: { facts: RaceDefinition["facts"] }) {
  return <dl className="race-facts">{facts.map((fact) => <div key={`${fact.label}-${fact.value}`}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}</dl>;
}

function RaceLoreSections({ lore }: { lore: RaceDefinition | NonNullable<RaceDefinition["branches"]>[number] }) {
  return <div className="race-lore-sections">
    <section><h4>天赋与魔力</h4><p>{lore.magic_affinity}</p></section>
    <section><h4>战斗方式</h4><p>{lore.combat_style}</p></section>
    <section><h4>文明与技术</h4><p>{lore.technology}</p></section>
    <section><h4>社会与分布</h4><p>{lore.society}</p><p>{lore.distribution}</p></section>
    <section className="race-creation-notes"><h4>创建提示</h4><p>{lore.creation_notes}</p></section>
  </div>;
}

function RaceStep({ catalog, draft, update }: { catalog: WorldCatalog; draft: CharacterDraft; update: <K extends keyof CharacterDraft>(key: K, value: CharacterDraft[K]) => void }) {
  const selected = catalog.races.find((race) => race.id === draft.race_id) ?? catalog.races[0];
  const branch = selectedRaceBranch(selected, draft.race_branch_id);
  return <div className="race-browser"><div className="option-track race-track" role="radiogroup" aria-label="可玩种族">{catalog.races.map((race) => <label key={race.id}><input type="radio" name="race" checked={draft.race_id === race.id} onChange={() => { update("race_id", race.id); update("race_branch_id", null); }} /><span>{race.name}</span></label>)}</div>{selected && <article className="race-profile">
    <ResponsiveArtwork key={selected.id} item={selected} alt={`${selected.name}种族设定图`} kind="种族" />
    <div className="race-reading">
      <header className="race-heading"><span className="world-label">种族资料</span><h3>{selected.name}</h3><p>{selected.tagline}</p></header>
      <RaceFacts facts={[{ label: "寿命", value: selected.lifespan_text }, ...selected.facts]} />
      <p className="race-description">{selected.description}</p>
      {selected.branches?.length ? <fieldset className="race-branch-selector"><legend>选择兽裔分支</legend><p id="race-branch-help">兽人与半兽人是两个独立种族，选择后查看对应的能力、社会与阶位资料。</p><div>{selected.branches.map((item) => <label key={item.id}><input type="radio" name="race-branch" checked={draft.race_branch_id === item.id} aria-describedby="race-branch-help" onChange={() => update("race_branch_id", item.id)} /><span><strong>{item.name}</strong><small>{item.tagline}</small></span></label>)}</div></fieldset> : null}
      {branch ? <section className="race-branch-detail" aria-live="polite"><header><span className="world-label">已选分支</span><h4>{branch.name}</h4><p>{branch.tagline}</p></header><RaceFacts facts={[{ label: "寿命", value: branch.lifespan_text }, ...branch.facts]} /><p className="race-description">{branch.description}</p><RaceLoreSections lore={branch} /></section> : <RaceLoreSections lore={selected} />}
    </div>
  </article>}</div>;
}

function TextStep({ label, value, onChange, maxLength, placeholder, optional = false, multiline = false }: { label: string; value: string; onChange: (value: string) => void; maxLength: number; placeholder: string; optional?: boolean; multiline?: boolean }) {
  return <div className="focused-form"><label className="field"><span>{label}{optional && <small>（可选）</small>}</span>{multiline ? <textarea autoFocus rows={9} maxLength={maxLength} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} /> : <input autoFocus maxLength={maxLength} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />}<small className="char-count">{value.length} / {maxLength}</small></label></div>;
}

function GenderStep({ draft, update }: { draft: CharacterDraft; update: <K extends keyof CharacterDraft>(key: K, value: CharacterDraft[K]) => void }) {
  const custom = draft.gender !== "男" && draft.gender !== "女";
  return <div className="focused-form"><fieldset className="choice-field"><legend>性别</legend><div><label><input type="radio" name="gender-choice" checked={draft.gender === "男"} onChange={() => update("gender", "男")} /><span>男</span></label><label><input type="radio" name="gender-choice" checked={draft.gender === "女"} onChange={() => update("gender", "女")} /><span>女</span></label><label><input type="radio" name="gender-choice" checked={custom} onChange={() => update("gender", "")} /><span>其他描述</span></label></div></fieldset>{custom && <label className="field"><span>自定义性别</span><input autoFocus maxLength={80} value={draft.gender} placeholder="输入角色的性别描述" onChange={(e) => update("gender", e.target.value)} /></label>}</div>;
}

function AgeStep({ catalog, draft, update }: { catalog: WorldCatalog; draft: CharacterDraft; update: <K extends keyof CharacterDraft>(key: K, value: CharacterDraft[K]) => void }) {
  const race = catalog.races.find((item) => item.id === draft.race_id);
  const branch = race?.branches?.find((item) => item.id === draft.race_branch_id);
  return <div className="focused-form"><div className="rule-note"><span className="state-symbol" aria-hidden="true">i</span><div><strong>{branch?.name || race?.name || "所选种族"}寿命提示</strong><p>{branch?.lifespan_text || race?.lifespan_text || "世界资料尚未提供寿命文案。"} 平均寿命不是年龄上限，系统不会据此自创成年年龄限制。</p></div></div><label className="field compact"><span>年龄</span><div className="input-suffix"><input autoFocus type="number" min={1} max={99999} value={draft.age ?? ""} onChange={(e) => update("age", e.target.value ? Number(e.target.value) : null)} /><span>岁</span></div></label></div>;
}

function PresetTextStep({ label, presets, raceId, value, update, placeholder, note }: { label: string; presets: PresetDefinition[]; raceId: string; value: string; update: (value: string) => void; placeholder: string; note?: string }) {
  const available = presets.filter((preset) => !preset.race_ids?.length || preset.race_ids.includes(raceId));
  const groups = groupPresets(available);
  return <div className="focused-form wide">{note && <div className="rule-note preset-note"><span className="state-symbol" aria-hidden="true">i</span><p>{note}</p></div>}<div className="preset-section"><span className="field-label">追加预设词</span>{groups.length ? <div className="preset-groups">{groups.map((group) => <section className="preset-group" key={group.category} aria-labelledby={`preset-${group.category}`}><h3 id={`preset-${group.category}`}>{group.category}</h3><div className="preset-list">{group.items.map((preset) => <button type="button" key={preset.id} onClick={() => update(appendPreset(value, preset.label))}>＋ {preset.label}</button>)}</div></section>)}</div> : <p className="muted-copy">当前种族暂无适用预设词，你仍可自由填写。</p>}</div><label className="field"><span>{label}</span><textarea autoFocus rows={8} maxLength={2000} value={value} placeholder={placeholder} onChange={(e) => update(e.target.value)} /><small className="char-count">{value.length} / 2000，可直接修改已追加的词</small></label></div>;
}

function RankStep({ catalog, draft, update }: { catalog: WorldCatalog; draft: CharacterDraft; update: <K extends keyof CharacterDraft>(key: K, value: CharacterDraft[K]) => void }) {
  const race = catalog.races.find((item) => item.id === draft.race_id);
  const branch = selectedRaceBranch(race, draft.race_branch_id);
  const ranks = branch?.ranks.length ? branch.ranks : race?.ranks.length ? race.ranks : catalog.ranks;
  const selected = ranks.find((rank) => rank.rank === draft.rank);
  return <div className="rank-browser"><section className="rank-system" aria-labelledby="rank-system-title"><div><span className="world-label">世界通行标准</span><h3 id="rank-system-title">{catalog.rank_system.title}</h3><p>{catalog.rank_system.description}</p></div><ul>{catalog.rank_system.principles.map((principle) => <li key={principle}>{principle}</li>)}</ul></section><div className="rank-step"><div className="rank-list" role="radiogroup" aria-label="角色等阶">{ranks.map((rank) => { const displayRank = rank.display_rank || `${chineseRankNumeral(rank.rank)}阶`; return <label key={rank.rank} className={rank.disabled ? "disabled" : ""}><input type="radio" name="rank" disabled={rank.disabled} checked={draft.rank === rank.rank} onChange={() => update("rank", rank.rank)} /><span className="rank-number">{chineseRankNumeral(rank.rank)}</span><span><strong>{displayRank}</strong><small>{rank.title || "无专属称号"}</small></span>{rank.base_power !== undefined && <span className="power-value">战力 {rank.base_power.toLocaleString()}</span>}</label>; })}</div>{selected && <div className={`rank-note ${selected.rank >= 7 ? "warning" : ""}`}><strong>{selected.display_rank || `${chineseRankNumeral(selected.rank)}阶`} · {selected.title || "无专属称号"}</strong>{selected.rank >= 7 ? <p>七阶及以上会显著压缩前期挑战空间。推荐选择六阶及以下，以保留更完整的成长与冒险体验。</p> : <p>当前选择位于推荐范围内，适合保留成长与探索空间。</p>}{selected.warning && <p>{selected.warning}</p>}</div>}</div></div>;
}

function LocationStep({ catalog, draft, update }: { catalog: WorldCatalog; draft: CharacterDraft; update: <K extends keyof CharacterDraft>(key: K, value: CharacterDraft[K]) => void }) {
  const selected = catalog.locations.find((location) => location.id === draft.location_id) ?? catalog.locations[0];
  return <div className="world-browser"><div className="option-track location-track" role="radiogroup" aria-label="初始地点">{catalog.locations.map((location) => <label key={location.id} className={location.disabled ? "disabled" : ""}><input type="radio" name="location" disabled={location.disabled} checked={draft.location_id === location.id} onChange={() => update("location_id", location.id)} /><span>{location.name}</span></label>)}</div>{selected && <article className="world-profile"><ResponsiveArtwork key={selected.id} item={selected} alt={`${selected.name}地点设定图`} kind="地点" /><div className="world-reading"><header className="world-heading"><span className="world-label">地点资料</span><h3>{selected.name}</h3><p>{selected.tagline}</p></header><dl className="world-facts"><div><dt>所在区域</dt><dd>{selected.region}</dd></div><div><dt>环境</dt><dd>{selected.environment}</dd></div></dl><p className="world-description">{selected.description}</p><div className="world-sections"><InfoSection title="区域结构" text={selected.structure} /><InfoSection title="特色" items={selected.highlights} /><InfoSection title="交通与访问" text={selected.transport} extra={selected.access_note} /><InfoSection title="开局说明" text={selected.arrival_point} items={selected.safeguards} tone="notice" /></div>{selected.warning && <p className="warning-text">注意：{selected.warning}</p>}</div></article>}</div>;
}

function FactionStep({ factions, activeId, setActiveId }: { factions: FactionDefinition[]; activeId: string; setActiveId: (id: string) => void }) {
  const selected = factions.find((faction) => faction.id === activeId) ?? factions[0];
  if (!selected) return <div className="empty-state compact"><h3>暂无势力资料</h3><p>世界资料接口未返回势力，但本步骤无需选择，可以直接继续。</p></div>;
  return <div className="world-browser"><div className="fixed-notice"><span aria-hidden="true">i</span><strong>本步骤无需选择；符合条件的势力可在游戏过程中加入。公开任务与服务不代表正式加入。</strong></div><div className="option-track faction-track" role="tablist" aria-label="世界势力">{factions.map((faction) => <button type="button" role="tab" id={`faction-tab-${faction.id}`} aria-controls={`faction-panel-${faction.id}`} key={faction.id} aria-selected={selected.id === faction.id} onClick={() => setActiveId(faction.id)}>{faction.name}</button>)}</div><article className="world-profile" role="tabpanel" id={`faction-panel-${selected.id}`} aria-labelledby={`faction-tab-${selected.id}`}><ResponsiveArtwork key={selected.id} item={selected} alt={`${selected.name}势力设定图`} kind="势力" /><div className="world-reading"><header className="world-heading"><span className="world-label">势力资料 · 只读</span><h3>{selected.name}</h3><p>{selected.tagline}</p></header><p className="world-description">{selected.description}</p><div className="world-sections"><InfoSection title="定位、理念与组织" text={selected.ideology} extra={selected.organization} /><InfoSection title="总部或主要地区" text={selected.headquarters} /><InfoSection title="公开任务" items={selected.tasks} /><InfoSection title="可使用服务" items={selected.services} /><InfoSection title="可参与活动" items={selected.activities} /><InfoSection title="奖励与资源" items={selected.rewards} /><InfoSection title="公开对象与前置" text={selected.audience} extra={selected.access_note} tone="notice" /></div></div></article></div>;
}

function InfoSection({ title, text, extra, items, tone }: { title: string; text?: string; extra?: string; items?: string[]; tone?: "notice" }) {
  return <section className={`world-section ${tone || ""}`}><h4>{title}</h4>{text && <p>{text}</p>}{extra && <p>{extra}</p>}{items?.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : null}</section>;
}

function GenerationStep({ catalog, draft, job, candidate, error, onGenerate, onCancel }: { catalog: WorldCatalog; draft: CharacterDraft; job: GenerationJob | null; candidate: CharacterCandidate | null; error: unknown; onGenerate: (feedback?: string) => Promise<void>; onCancel: () => Promise<void> }) {
  const navigate = useNavigate();
  const { saveId = "" } = useParams();
  const active = job && ["queued", "running", "cancel_requested"].includes(job.status);
  const failed = job && ["failed", "cancelled", "stale", "interrupted"].includes(job.status);
  const race = catalog.races.find((item) => item.id === draft.race_id);
  const location = catalog.locations.find((item) => item.id === draft.location_id);
  return <div className="generation-step"><section className="input-summary"><div className="section-heading"><h3>输入摘要</h3><button className="text-button" type="button" onClick={() => navigate(`/saves/${saveId}/create/1`)}>返回修改</button></div><dl><div><dt>身份</dt><dd>{draft.name || "未填写"} · {draft.gender || "未填写"} · {draft.age ? `${draft.age} 岁` : "未填写"}</dd></div><div><dt>种族</dt><dd>{race?.name || "未选择"}</dd></div><div><dt>等阶</dt><dd>{draft.rank ? `${draft.rank} 阶` : "未选择"}</dd></div><div><dt>起点</dt><dd>{location?.name || "未选择"}</dd></div><div><dt>外貌</dt><dd>{draft.appearance || "未填写"}</dd></div><div><dt>性格</dt><dd>{draft.personality || "未填写"}</dd></div><div><dt>天赋</dt><dd>{draft.talent || "未填写"}</dd></div>{draft.background && <div><dt>身世</dt><dd>{draft.background}</dd></div>}{draft.additional && <div><dt>补充</dt><dd>{draft.additional}</dd></div>}</dl></section>{Boolean(error) && <ErrorPanel error={error} title="生成请求出现问题" />}{active && <section className="generation-progress" aria-live="polite"><div className="pulse-rune" aria-hidden="true">◇</div><div><span className="world-label">任务 {job.id.slice(0, 8)}</span><h3>{jobLabel[job.status]}</h3><p>{job.progress_message || "模型正在依据当前草稿生成属性、资源与战力候选。你可以切换到其他存档，任务会在后端继续。"}</p></div><button type="button" className="secondary-button" disabled={job.status === "cancel_requested"} onClick={() => void onCancel()}>{job.status === "cancel_requested" ? "正在取消…" : "取消生成"}</button></section>}{failed && <section className="state-panel warning"><span className="state-symbol" aria-hidden="true">!</span><div><h3>{jobLabel[job.status]}</h3><p>{job.error?.message || (job.status === "stale" ? "草稿已更新，旧结果不会覆盖当前版本。" : "可以使用当前草稿重新发起生成。")}</p><button className="primary-button" type="button" onClick={() => void onGenerate()}>重试生成</button></div></section>}{candidate && <><CandidatePanel candidate={candidate} footer={<div className="candidate-footer"><span /><button className="primary-button" type="button" onClick={() => navigate(`/saves/${saveId}/review`)}>审阅并接受角色</button></div>} /><RegeneratePanel onGenerate={onGenerate} /></>}{!active && !candidate && !failed && <div className="generation-ready"><div><h3>准备生成角色候选</h3><p>生成是异步任务，结果会绑定当前存档与草稿修订。切换存档不会串入其他角色。</p></div><button className="primary-button" type="button" onClick={() => void onGenerate()}>生成角色</button></div>}</div>;
}

function RegeneratePanel({ onGenerate }: { onGenerate: (feedback?: string) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [feedback, setFeedback] = useState("");
  return <section className="regenerate-panel"><div><h3>需要调整候选？</h3><p>提供明确修改意见会创建新的生成任务，当前候选在新结果完成前仍会保留。</p></div>{open ? <div className="regenerate-form"><label className="field"><span>修改意见</span><textarea rows={4} maxLength={1200} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="例如：提高魅力，但降低体质，并保留当前背景解释。" /></label><div className="form-actions"><button className="secondary-button" type="button" onClick={() => setOpen(false)}>取消修改</button><button className="primary-button" type="button" disabled={!feedback.trim()} onClick={() => void onGenerate(feedback.trim())}>按意见重新生成</button></div></div> : <button className="secondary-button" type="button" onClick={() => setOpen(true)}>填写修改意见</button>}</section>;
}

function CandidatePanel({ candidate, footer }: { candidate: CharacterCandidate; footer?: ReactNode }) {
  const attributes = [["体质 CON", candidate.attributes.con], ["智力 INT", candidate.attributes.int], ["魅力 CHA", candidate.attributes.cha]] as const;
  const resources = candidate.resources ? [["生命 HP", candidate.resources.hp], ["魔力 MP", candidate.resources.mp], ["精神 SP", candidate.resources.sp], ["精力 ST", candidate.resources.st]] as const : [];
  return <article className="candidate-panel"><header><div><span className="world-label">角色候选</span><h2>{candidate.identity?.name || "未命名角色"}</h2><p>{[candidate.identity?.race_name, candidate.identity?.race_branch_name, candidate.identity?.rank_name, candidate.identity?.location_name].filter(Boolean).join(" · ")}</p><p>{[candidate.identity?.gender, candidate.identity?.age ? `${candidate.identity.age} 岁` : null].filter(Boolean).join(" · ")}</p></div><span className={`candidate-validity ${candidate.valid === false ? "invalid" : "valid"}`}>{candidate.valid === false ? "存在规则冲突" : "规则校验通过"}</span></header>{candidate.warnings?.length ? <div className="candidate-warnings">{candidate.warnings.map((warning) => <p key={warning}><span aria-hidden="true">!</span>{warning}</p>)}</div> : null}{candidate.summary && <section className="candidate-summary"><h3>能力概述</h3><p>{candidate.summary}</p></section>}<section><h3>长期属性</h3><div className="attribute-grid">{attributes.map(([label, attribute]) => <div className="attribute-row" key={label}><div><span>{label}</span><strong>{attribute.value}</strong></div><div className="attribute-meter" aria-label={`${label} ${attribute.value}，满值 100`}><span style={{ width: `${Math.min(100, Math.max(0, attribute.value))}%` }} /></div>{attribute.reason && <p>{attribute.reason}</p>}</div>)}</div></section>{resources.length > 0 && <section><h3>短期资源</h3><div className="resource-list">{resources.map(([label, resource]) => resource && <div key={label}><span>{label}</span><strong>{resource.current} / {resource.max}</strong>{resource.reason && <small>{resource.reason}</small>}</div>)}</div></section>}<section className="power-section"><div><h3>战力</h3><strong className="power-number">{candidate.power.effective.toLocaleString()}</strong><span>基础战力 {candidate.power.base.toLocaleString()}</span></div><div>{candidate.power.modifiers?.length ? <ul>{candidate.power.modifiers.map((modifier) => <li key={`${modifier.label}-${modifier.value}`}><strong>{modifier.label} {modifier.value >= 0 ? "+" : ""}{modifier.value}</strong>{modifier.reason && <span>{modifier.reason}</span>}</li>)}</ul> : <p>当前没有已裁决的战力修正。</p>}{candidate.power.explanation && <p>{candidate.power.explanation}</p>}</div></section><section className="candidate-columns"><div><h3>优势</h3>{candidate.strengths?.length ? <ul>{candidate.strengths.map((item) => <li key={item}>{item}</li>)}</ul> : <p>模型未列出。</p>}</div><div><h3>局限</h3>{candidate.limitations?.length ? <ul>{candidate.limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>模型未列出。</p>}</div></section><section className="description-section"><h3>角色描述</h3><dl>{candidate.description?.appearance && <div><dt>外貌</dt><dd>{candidate.description.appearance}</dd></div>}{candidate.description?.personality && <div><dt>性格</dt><dd>{candidate.description.personality}</dd></div>}{candidate.description?.talent && <div><dt>天赋</dt><dd>{candidate.description.talent}</dd></div>}{candidate.description?.background && <div><dt>身世</dt><dd>{candidate.description.background}</dd></div>}{candidate.description?.additional && <div><dt>其他补充</dt><dd>{candidate.description.additional}</dd></div>}</dl></section>{footer}</article>;
}

function ReviewPage({ actions }: { actions: ShellActions }) {
  const { saveId = "" } = useParams();
  const navigate = useNavigate();
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
    try { await api.confirmCharacter(saveId, candidate.id, save.revision, candidate.draft_revision, crypto.randomUUID()); await actions.refreshSaves(); navigate(`/saves/${saveId}/game`); }
    catch (reason) { setError(reason); setConfirming(false); }
  };
  const regenerate = async (feedback = "") => {
    if (!candidate) return;
    setRegenBusy(true); setError(null);
    if (!save) return;
    try { const next = await api.startGeneration(saveId, candidate.draft_revision, save.revision, feedback); await actions.refreshSaves(); navigate(`/saves/${saveId}/create/13`, { state: { jobId: next.id } }); }
    catch (reason) { setError(reason); setRegenBusy(false); }
  };
  if (loading) return <div className="page"><LoadingPanel label="正在载入候选角色" /></div>;
  if (error && !candidate) return <div className="page"><ErrorPanel error={error} onRetry={() => void load()} title="无法载入角色候选" /></div>;
  if (!save || !candidate) return <div className="page"><ErrorPanel error={new ApiError(404, { code: "candidate_not_found", message: "当前存档没有可审阅的角色候选。" })} /></div>;
  return <div className="page review-page"><header className="page-header"><div><span className="step-count">接受前检查</span><h1>确认角色候选</h1><p>模型建议不是正式状态。接受后，程序才会将此候选原子写入存档。</p></div></header>{Boolean(error) && <ErrorPanel error={error} onRetry={() => void load()} />}{regenBusy && <div className="inline-status"><StatusDot state="busy" />正在创建新的生成任务…</div>}<CandidatePanel candidate={candidate} footer={<div className="candidate-footer"><button className="secondary-button" type="button" onClick={() => navigate(`/saves/${saveId}/create/13`)}>返回生成页</button><button className="primary-button" type="button" disabled={confirming || candidate.valid === false} onClick={() => void confirm()}>{confirming ? "正在接受…" : "接受角色"}</button></div>} /><RegeneratePanel onGenerate={regenerate} /></div>;
}

function NotFound() {
  return <div className="page"><section className="empty-state"><div className="empty-symbol" aria-hidden="true">?</div><h1>页面不存在</h1><p>此档案路径无效，或对应内容已被删除。</p><Link className="primary-button" to="/">返回档案总览</Link></section></div>;
}
