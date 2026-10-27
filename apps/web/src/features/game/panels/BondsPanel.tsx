import { useState, type FormEvent } from "react";
import { api, asApiError } from "../../../api";
import { Icon } from "../../../components/Icon";
import { Modal } from "../../../components/Modal";
import { playerProblemMessage } from "../../../playerCopy";
import type { Bond } from "../../../types";
import { GameEmpty } from "./GameEmpty";

export function BondsPanel({ items, saveId, stateVersion, locked, onDeleted }: {
  items: Bond[];
  saveId: string;
  stateVersion: number;
  /** A story job is running; bonds cannot change under it. */
  locked: boolean;
  onDeleted: (bond: Bond) => void;
}) {
  const [deleting, setDeleting] = useState<Bond | null>(null);
  return (
    <div className="projection-page">
      <header className="projection-header"><div><h2>羁绊</h2><p>查看与你建立了持续关系的重要人物，以及他们对你的好感。</p></div></header>
      {items.length ? (
        <ul className="relationship-list">
          {items.map((bond) => (
            <li key={bond.id}>
              <div><strong>{bond.npc_name}</strong><span>{bond.relation_type}</span><span>{bond.level ?? "普通/陌生"}</span></div>
              <meter min={-100} max={100} low={-20} high={50} optimum={100} value={bond.value} aria-label={`${bond.npc_name} 羁绊 ${bond.value}`} />
              <b>{bond.value}</b>
              <button className="icon-button small danger-text bond-delete" type="button" disabled={locked}
                title={locked ? "剧情生成或整理记忆期间不能删除羁绊" : undefined} aria-label={`删除与${bond.npc_name}的羁绊`}
                onClick={() => setDeleting(bond)}><Icon name="trash" /></button>
            </li>
          ))}
        </ul>
      ) : <GameEmpty title="尚未建立羁绊" icon="people">重要人物在形成持续关系后会列入此处。</GameEmpty>}
      {deleting && (
        <DeleteBondModal saveId={saveId} stateVersion={stateVersion} bond={deleting}
          onClose={() => setDeleting(null)} onDeleted={() => { setDeleting(null); onDeleted(deleting); }} />
      )}
    </div>
  );
}

function DeleteBondModal({ saveId, stateVersion, bond, onClose, onDeleted }: {
  saveId: string; stateVersion: number; bond: Bond; onClose: () => void; onDeleted: () => void;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true);
    try {
      await api.deleteBond(saveId, bond.npc_id, stateVersion, crypto.randomUUID());
      onDeleted();
    } catch (reason) {
      setError(playerProblemMessage(asApiError(reason).problem));
      setBusy(false);
    }
  };
  return (
    <Modal title="删除羁绊" onClose={onClose} labelledBy="delete-bond-title">
      <form onSubmit={(event) => void submit(event)}>
        <div className="danger-callout"><strong>删除后无法恢复</strong><p>与“{bond.npc_name}”的羁绊会被移除，好感度清空，GM 之后不会再看到这段关系。人物本身仍在世界中，之后若重新结下羁绊，好感度从 0 开始。</p></div>
        {error && <p className="field-error">{error}</p>}
        <div className="modal-actions">
          <button className="secondary-button" type="button" data-modal-close>保留</button>
          <button className="danger-button" data-autofocus disabled={busy}>{busy ? "正在删除…" : "删除羁绊"}</button>
        </div>
      </form>
    </Modal>
  );
}
