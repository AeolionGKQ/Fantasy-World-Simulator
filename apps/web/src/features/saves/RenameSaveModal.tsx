import { useState, type FormEvent } from "react";
import { api, asApiError } from "../../api";
import { Modal } from "../../components/Modal";
import { playerProblemMessage } from "../../playerCopy";
import type { SaveSummary } from "../../types";

export function RenameSaveModal({ save, onClose, onRenamed }: { save: SaveSummary; onClose: () => void; onRenamed: () => void }) {
  const [name, setName] = useState(save.name);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) { setError("请输入存档名称。"); return; }
    setBusy(true);
    try {
      await api.renameSave(save.id, name.trim(), save.revision, crypto.randomUUID());
      onRenamed();
    } catch (reason) {
      setError(playerProblemMessage(asApiError(reason).problem));
      setBusy(false);
    }
  };
  return (
    <Modal title="重命名存档" onClose={onClose} labelledBy="rename-save-title">
      <form onSubmit={(event) => void submit(event)}>
        <label className="field"><span>存档名称</span><input data-autofocus value={name} maxLength={80} onChange={(e) => setName(e.target.value)} /></label>
        {error && <p className="field-error">{error}</p>}
        <div className="modal-actions">
          <button className="secondary-button" type="button" data-modal-close>取消</button>
          <button className="primary-button" disabled={busy}>{busy ? "正在保存…" : "保存名称"}</button>
        </div>
      </form>
    </Modal>
  );
}
