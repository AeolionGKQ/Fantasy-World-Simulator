import { useEffect, useRef, type ReactNode } from "react";
import { Icon } from "./Icon";

export function Modal({ title, children, onClose, labelledBy }: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  labelledBy: string;
}) {
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
