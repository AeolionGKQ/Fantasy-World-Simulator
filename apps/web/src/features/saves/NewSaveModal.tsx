import { useRef, useState, type FormEvent } from "react";
import { api, asApiError } from "../../api";
import { Modal } from "../../components/Modal";
import { playerProblemMessage } from "../../playerCopy";
import { logicalRequestIdentity, type LogicalRequestIdentity, type SaveSummary } from "../../types";

export function NewSaveModal({ onClose, onCreated }: { onClose: () => void; onCreated: (save: SaveSummary) => void }) {
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
    try {
      const created = await api.createSave(payloadName, identity.request_id);
      requestIdentity.current = null;
      onCreated(created);
    } catch (reason) {
      setError(playerProblemMessage(asApiError(reason).problem));
      setBusy(false);
    }
  };
  return (
    <Modal title="新建存档" onClose={onClose} labelledBy="new-save-title">
      <form onSubmit={(event) => void submit(event)}>
        <label className="field">
          <span>存档名称</span>
          <input data-autofocus disabled={busy} value={name} maxLength={80} onChange={(e) => { requestIdentity.current = null; setName(e.target.value); }} aria-describedby={error ? "new-save-error" : undefined} />
        </label>
        {error && <p className="field-error" id="new-save-error">{error}</p>}
        <div className="modal-actions">
          <button className="secondary-button" type="button" data-modal-close>取消</button>
          <button className="primary-button" disabled={busy}>{busy ? "正在创建…" : "创建存档"}</button>
        </div>
      </form>
    </Modal>
  );
}
