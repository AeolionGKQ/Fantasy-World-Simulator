import { useRef, useState } from "react";
import { api, asApiError } from "../../api";
import { Icon } from "../../components/Icon";
import { Modal } from "../../components/Modal";
import { StatusDot } from "../../components/StatusDot";
import { playerProblemMessage } from "../../playerCopy";
import {
  isPendingImport,
  logicalRequestIdentity,
  phaseLabel,
  type ImportPreview,
  type LogicalRequestIdentity,
  type PendingImport,
  type SaveSummary,
} from "../../types";

const maxImportBytes = 64 * 1024 * 1024;

export function ImportSaveModal({ onClose, onImported }: { onClose: () => void; onImported: (save: SaveSummary) => void }) {
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
    if (file.size > maxImportBytes) {
      setError("文件超过 64 MB 导入上限。"); setBusy(false); return;
    }
    try {
      const result = await api.validateLargeImport(file);
      setFile(file); setPreview(result);
    } catch (reason) {
      setError(playerProblemMessage(asApiError(reason).problem));
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
    catch (reason) { setError(playerProblemMessage(asApiError(reason).problem)); setBusy(false); }
  };

  const trustAndImport = async () => {
    if (!pending || !trusted) return;
    const payloadKey = `${pending.pending_import_id}:${pending.revision_id}`;
    const identity = logicalRequestIdentity(trustIdentity.current, payloadKey);
    trustIdentity.current = identity;
    setBusy(true); setError("");
    try {
      const save = await api.trustAndImport(pending.pending_import_id, pending.revision_id, identity.request_id);
      trustIdentity.current = null;
      onImported(save);
    }
    catch (reason) { setError(playerProblemMessage(asApiError(reason).problem)); setBusy(false); }
  };

  return (
    <Modal title="导入存档" onClose={onClose} labelledBy="import-save-title">
      <div className="import-flow">
        <label className="file-picker">
          <Icon name="upload" />
          <span><strong>{filename || "选择存档文件"}</strong><small>选择从游戏中导出的 .json 存档文件，最大 64 MB。导入会新增一份存档，不覆盖已有冒险。</small></span>
          <input type="file" disabled={busy} accept="application/json,.json" onChange={(e) => void choose(e.target.files?.[0])} />
        </label>
        {busy && !preview && <p className="inline-status"><StatusDot state="busy" />正在检查存档…</p>}
        {preview && !pending && <ImportPreviewDetails preview={preview} />}
        {pending && (
          <PendingImportConfirm
            pending={pending}
            trusted={trusted}
            onTrustedChange={(value) => { trustIdentity.current = null; setTrusted(value); }}
          />
        )}
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose}>取消</button>
          {pending
            ? <button className="primary-button" type="button" disabled={!trusted || busy} onClick={() => void trustAndImport()}>{busy ? "正在导入…" : "确认来源并导入"}</button>
            : <button className="primary-button" type="button" disabled={!preview?.valid || busy} onClick={() => void submit()}>{busy && preview ? "正在导入…" : "确认导入"}</button>}
        </div>
      </div>
    </Modal>
  );
}

function ImportPreviewDetails({ preview }: { preview: ImportPreview }) {
  return (
    <div className={`import-preview ${preview.valid ? "success" : "error"}`}>
      <strong>{preview.valid ? "文件可以导入" : "此文件无法导入"}</strong>
      <dl>
        <div><dt>存档</dt><dd>{preview.save_name || "未命名"}</dd></div>
        <div><dt>阶段</dt><dd>{preview.phase ? phaseLabel[preview.phase] : "未知"}</dd></div>
        <div><dt>角色</dt><dd>{preview.character_name || "尚未确认"}</dd></div>
        <div><dt>规则版本</dt><dd>{preview.ruleset_version || "未知"}</dd></div>
      </dl>
      {preview.confirmation_required && <p className="warning-text">此存档附带了本机尚未确认的规则与世界设定，导入前需要你确认来源。</p>}
      {preview.warnings?.map((warning) => <p className="warning-text" key={warning}>注意：{warning === "导入时将分配新的本地存档ID" ? "导入会新增一份存档，不覆盖已有存档。" : warning}</p>)}
    </div>
  );
}

function PendingImportConfirm({ pending, trusted, onTrustedChange }: { pending: PendingImport; trusted: boolean; onTrustedChange: (value: boolean) => void }) {
  return (
    <div className="pending-import" role="region" aria-labelledby="pending-import-title">
      <h3 id="pending-import-title">确认存档附带的规则与设定</h3>
      <p>继续导入会保存这份存档附带的规则与世界设定。请查看下方文件清单，确认你信任存档的来源。</p>
      <dl><div><dt>确认截止时间</dt><dd>{pending.expires_at}</dd></div></dl>
      <ul>
        {pending.content_revision.documents.map((item) => (
          <li key={item.document_id}><strong>{item.source_path.split(/[\\/]/).pop()}</strong><span>{Math.ceil(item.byte_count / 1024).toLocaleString()} KB</span></li>
        ))}
      </ul>
      <label className="trust-confirm">
        <input type="checkbox" checked={trusted} onChange={(event) => onTrustedChange(event.target.checked)} />
        <span>我信任此存档的来源，同意导入附带的规则与世界设定。</span>
      </label>
    </div>
  );
}
