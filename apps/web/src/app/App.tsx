import { useCallback, useEffect, useMemo, useState } from "react";
import { Route, Routes, ScrollRestoration, useLocation } from "react-router-dom";
import { api, asApiError } from "../api";
import { usePresence } from "../components/usePresence";
import { playerProblemMessage } from "../playerCopy";
import { saveRoute, type SaveSummary, type ServiceStatuses } from "../types";
import { CharacterWizard } from "../features/character/CharacterWizard";
import { ReviewPage } from "../features/character/ReviewPage";
import GameWorkspace from "../features/game/GameWorkspace";
import { HomePage } from "../features/home/HomePage";
import { NotFoundPage } from "../features/home/NotFoundPage";
import { DeleteSaveModal } from "../features/saves/DeleteSaveModal";
import { downloadBlob } from "../features/saves/downloadBlob";
import { ImportSaveModal } from "../features/saves/ImportSaveModal";
import { NewSaveModal } from "../features/saves/NewSaveModal";
import { RenameSaveModal } from "../features/saves/RenameSaveModal";
import SceneImageWorkspace from "../features/scene-image/SceneImageWorkspace";
import { SettingsPage } from "../features/settings/SettingsPage";
import { AppToolbar } from "./AppToolbar";
import { INFO_NOTICE_MS, NoticeBar, NoticeProvider, NoticeViewProvider, type Notice, type NoticeView, type Notify } from "./notice";
import { SaveSidebar } from "./SaveSidebar";
import type { ShellActions } from "./shellActions";
import { useAppNavigate } from "./viewTransition";

type ShellModal = "new" | "import" | "rename" | "delete";

export default function App() {
  const [saves, setSaves] = useState<SaveSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [modal, setModal] = useState<ShellModal | null>(null);
  const [targetSave, setTargetSave] = useState<SaveSummary | null>(null);
  const [services, setServices] = useState<ServiceStatuses | null>(null);
  const [servicesError, setServicesError] = useState(false);
  const navigate = useAppNavigate();
  const location = useLocation();

  /** Model service status for the sidebar. Reads stored outcomes only, so it is free to call often. */
  const refreshServiceStatus = useCallback(async () => {
    try {
      setServices(await api.getServiceStatus());
      setServicesError(false);
    } catch {
      setServicesError(true);
    }
  }, []);

  // Saves are refreshed after every job finishes, so the service status rides along with them.
  const refreshSaves = useCallback(async () => {
    void refreshServiceStatus();
    try {
      setLoadError(null);
      const next = await api.listSaves();
      setSaves(next);
    } catch (error) {
      setLoadError(error);
    } finally {
      setLoading(false);
    }
  }, [refreshServiceStatus]);

  useEffect(() => { void refreshSaves(); }, [refreshSaves]);
  useEffect(() => {
    const onFocus = () => { void refreshServiceStatus(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshServiceStatus]);
  // Every navigation closes the drawer, including a jump to a section of the current page (/settings#…).
  useEffect(() => { setDrawerOpen(false); }, [location.key]);
  /** The one place every page shows its one-off messages and errors (the bar under the toolbar). */
  const notify = useCallback<Notify>((next) => setNotice(next ? { ...next, id: Date.now() } : null), []);
  useEffect(() => {
    if (notice?.tone !== "info") return;
    const timer = window.setTimeout(() => setNotice((current) => current?.id === notice.id ? null : current), INFO_NOTICE_MS);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const currentId = /^\/saves\/([^/]+)/.exec(location.pathname)?.[1];
  const currentSave = saves.find((save) => save.id === currentId) ?? null;
  const shownNotice = usePresence(notice);
  // Pages show the bar under their own header (NoticeSlot); the count tells whether one is mounted.
  const [noticeSlots, setNoticeSlots] = useState(0);
  const registerNoticeSlot = useCallback(() => {
    setNoticeSlots((count) => count + 1);
    return () => setNoticeSlots((count) => count - 1);
  }, []);
  const noticeView = useMemo<NoticeView>(() => ({
    current: shownNotice.current, leaving: shownNotice.leaving,
    dismiss: () => notify(null), register: registerNoticeSlot,
  }), [shownNotice.current, shownNotice.leaving, notify, registerNoticeSlot]);
  const actions = useMemo<ShellActions>(() => ({ refreshSaves, refreshServiceStatus }), [refreshSaves, refreshServiceStatus]);
  const offline = Boolean(loadError) || servicesError;
  const storyState = services?.story_model.state;
  const settingsAttention = !offline && (storyState === "not_configured" || storyState === "failed") ? storyState : null;

  const openFor = (kind: "rename" | "delete", save: SaveSummary) => {
    setTargetSave(save);
    setModal(kind);
  };

  const exportCurrent = async () => {
    if (!currentSave) return;
    try {
      const { blob, filename } = await api.exportSave(currentSave.id);
      downloadBlob(blob, filename);
      notify({ tone: "info", text: "存档已导出，文件中不含 AI 服务密钥。" });
    } catch (error) {
      const problem = asApiError(error).problem;
      notify({ tone: "error", text: playerProblemMessage(problem), traceId: problem.trace_id });
    }
  };

  return (
    <NoticeProvider value={notify}>
    <NoticeViewProvider value={noticeView}>
    <div className="app-shell">
      <ScrollRestoration />
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <SaveSidebar
        saves={saves}
        currentId={currentId}
        loading={loading}
        loadError={loadError}
        open={drawerOpen}
        services={services}
        offline={offline}
        onClose={() => setDrawerOpen(false)}
        onRetry={() => void refreshSaves()}
        onNew={() => setModal("new")}
        onRename={(save) => openFor("rename", save)}
        onDelete={(save) => openFor("delete", save)}
      />
      {/* Always rendered on mobile so it can fade out; inert while the drawer is closed. */}
      <button className={`drawer-backdrop ${drawerOpen ? "open" : ""}`} type="button" aria-label="关闭存档列表" aria-hidden={!drawerOpen} tabIndex={drawerOpen ? 0 : -1} onClick={() => setDrawerOpen(false)} />

      <div className="workspace">
        <AppToolbar
          context={location.pathname === "/settings" ? "应用设置" : currentSave?.name ?? "档案总览"}
          canExport={Boolean(currentSave)}
          settingsActive={location.pathname === "/settings"}
          settingsAttention={settingsAttention}
          onMenu={() => setDrawerOpen(true)}
          onNew={() => setModal("new")}
          onImport={() => setModal("import")}
          onExport={() => void exportCurrent()}
        />
        <main id="main-content" tabIndex={-1}>
          {/* Fallback for screens without a NoticeSlot (loading and error states, not found). */}
          {noticeSlots === 0 && shownNotice.current && (
            <div className="notice-fallback">
              <NoticeBar key={shownNotice.current.id} notice={shownNotice.current} leaving={shownNotice.leaving} onDismiss={() => notify(null)} />
            </div>
          )}
          <Routes>
            <Route path="/" element={<HomePage saves={saves} loading={loading} onNew={() => setModal("new")} />} />
            <Route path="/settings" element={<SettingsPage actions={actions} />} />
            <Route path="/saves/:saveId/create/:step" element={<CharacterWizard actions={actions} />} />
            <Route path="/saves/:saveId/review" element={<ReviewPage actions={actions} />} />
            <Route path="/saves/:saveId/game" element={<GameWorkspace />} />
            <Route path="/saves/:saveId/game/image" element={<SceneImageWorkspace />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </main>
      </div>

      {modal === "new" && (
        <NewSaveModal
          onClose={() => setModal(null)}
          onCreated={async (save) => { setModal(null); await refreshSaves(); navigate(saveRoute(save)); }}
        />
      )}
      {modal === "rename" && targetSave && (
        <RenameSaveModal
          save={targetSave}
          onClose={() => setModal(null)}
          onRenamed={async () => { setModal(null); await refreshSaves(); notify({ tone: "info", text: "存档已重命名。" }); }}
        />
      )}
      {modal === "delete" && targetSave && (
        <DeleteSaveModal
          save={targetSave}
          onClose={() => setModal(null)}
          onDeleted={async () => {
            const wasCurrent = targetSave.id === currentId;
            setModal(null);
            await refreshSaves();
            if (wasCurrent) navigate("/");
            notify({ tone: "info", text: "存档已删除，无法恢复。" });
          }}
        />
      )}
      {modal === "import" && (
        <ImportSaveModal
          onClose={() => setModal(null)}
          onImported={async (save) => { setModal(null); await refreshSaves(); navigate(saveRoute(save)); notify({ tone: "info", text: "存档已导入，原有存档不会被覆盖。" }); }}
        />
      )}
    </div>
    </NoticeViewProvider>
    </NoticeProvider>
  );
}
