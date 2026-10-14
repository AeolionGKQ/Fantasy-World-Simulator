import { useCallback, useEffect, useMemo, useState } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, asApiError } from "../api";
import { playerProblemMessage } from "../playerCopy";
import { saveRoute, type SaveSummary } from "../types";
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
import { SaveSidebar } from "./SaveSidebar";
import type { ShellActions } from "./shellActions";

type ShellModal = "new" | "import" | "rename" | "delete";

export default function App() {
  const [saves, setSaves] = useState<SaveSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [modal, setModal] = useState<ShellModal | null>(null);
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
      downloadBlob(blob, filename);
      setNotice("存档已导出，不包含模型服务密钥。");
    } catch (error) {
      setNotice(playerProblemMessage(asApiError(error).problem));
    }
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <SaveSidebar
        saves={saves}
        currentId={currentId}
        loading={loading}
        loadError={loadError}
        open={drawerOpen}
        settingsActive={location.pathname === "/settings"}
        onClose={() => setDrawerOpen(false)}
        onRetry={() => void refreshSaves()}
        onNew={() => setModal("new")}
        onRename={(save) => openFor("rename", save)}
        onDelete={(save) => openFor("delete", save)}
      />
      {drawerOpen && <button className="drawer-backdrop" type="button" aria-label="关闭存档列表" onClick={() => setDrawerOpen(false)} />}

      <div className="workspace">
        <AppToolbar
          context={location.pathname === "/settings" ? "应用设置" : currentSave?.name ?? "档案总览"}
          canExport={Boolean(currentSave)}
          onMenu={() => setDrawerOpen(true)}
          onNew={() => setModal("new")}
          onImport={() => setModal("import")}
          onExport={() => void exportCurrent()}
        />
        <main id="main-content" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<HomePage saves={saves} loading={loading} onNew={() => setModal("new")} />} />
            <Route path="/settings" element={<SettingsPage actions={actions} />} />
            <Route path="/saves/:saveId/create/:step" element={<CharacterWizard actions={actions} />} />
            <Route path="/saves/:saveId/review" element={<ReviewPage actions={actions} />} />
            <Route path="/saves/:saveId/game" element={<GameWorkspace onSaveChanged={refreshSaves} />} />
            <Route path="/saves/:saveId/game/image" element={<SceneImageWorkspace />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </main>
      </div>

      {notice && <div className="toast" role="status">{notice}</div>}
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
          onRenamed={async () => { setModal(null); await refreshSaves(); setNotice("存档已重命名。"); }}
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
            setNotice("存档已删除，无法恢复。");
          }}
        />
      )}
      {modal === "import" && (
        <ImportSaveModal
          onClose={() => setModal(null)}
          onImported={async (save) => { setModal(null); await refreshSaves(); navigate(saveRoute(save)); setNotice("存档已导入，原有存档不会被覆盖。"); }}
        />
      )}
    </div>
  );
}
