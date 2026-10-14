import { useState, type FormEvent } from "react";
import { api, asApiError } from "../../api";
import { Modal } from "../../components/Modal";
import { playerProblemMessage } from "../../playerCopy";
import type { SaveSummary } from "../../types";

export function DeleteSaveModal({ save, onClose, onDeleted }: { save: SaveSummary; onClose: () => void; onDeleted: () => void }) {
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true);
    try {
      await api.deleteSave(save.id, save.revision, crypto.randomUUID());
      onDeleted();
    } catch (reason) {
      setError(playerProblemMessage(asApiError(reason).problem));
      setBusy(false);
    }
  };
  return (
    <Modal title="删除存档" onClose={onClose} labelledBy="delete-save-title">
      <form onSubmit={(event) => void submit(event)}>
        <div className="danger-callout"><strong>此操作无法恢复</strong><p>将删除“{save.name}”中的角色、剧情和所有记录，正在生成的内容也会停止。</p></div>
        <label className="field"><span>输入存档名称以确认</span><input autoFocus value={confirmation} onChange={(e) => setConfirmation(e.target.value)} /></label>
        {error && <p className="field-error">{error}</p>}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose}>保留存档</button>
          <button className="danger-button" disabled={busy || confirmation !== save.name}>{busy ? "正在删除…" : "永久删除存档"}</button>
        </div>
      </form>
    </Modal>
  );
}
