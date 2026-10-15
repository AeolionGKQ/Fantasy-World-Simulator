import { useCallback, useEffect, useLayoutEffect, useRef, useState, type MouseEvent, type ReactNode, type SyntheticEvent } from "react";
import { prefersReducedMotion } from "../app/viewTransition";
import { Icon } from "./Icon";

/**
 * Native modal dialog that animates in and out (modal.css). Every user-initiated close — the ×
 * button, Esc, and any element inside marked `data-modal-close` (e.g. a Cancel button) — plays the
 * exit animation before `onClose` runs. A parent that unmounts the modal directly (after a
 * successful submit) skips the exit animation.
 */
export function Modal({ title, children, onClose, labelledBy }: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  labelledBy: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [closing, setClosing] = useState(false);
  // Layout effect: on unmount the dialog is closed while still in the document, so the browser
  // returns focus to the element that opened it.
  useLayoutEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    dialog.showModal();
    // showModal() focuses the first focusable element (the close button); move focus to the
    // field marked data-autofocus instead. React's autoFocus runs before showModal and is lost.
    dialog.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    return () => dialog.close();
  }, []);

  // Closing natively fires the dialog's close event, which calls onClose; focus returns to the opener.
  const closeNow = useCallback(() => { ref.current?.close(); }, []);
  const requestClose = useCallback(() => {
    if (closing) return;
    if (prefersReducedMotion()) { closeNow(); return; }
    setClosing(true);
  }, [closeNow, closing]);

  const onAnimationEnd = (event: SyntheticEvent<HTMLDialogElement>) => {
    if (closing && event.target === ref.current) closeNow();
  };
  // Fallback in case animationend never fires (e.g. animations disabled by the browser).
  useEffect(() => {
    if (!closing) return;
    const timer = window.setTimeout(closeNow, 400);
    return () => window.clearTimeout(timer);
  }, [closeNow, closing]);

  const onCancel = (event: SyntheticEvent<HTMLDialogElement>) => {
    event.preventDefault();
    requestClose();
  };
  // The close event is queued; ignore one that arrives after the dialog was reopened (StrictMode remount).
  const onDialogClose = () => { if (!ref.current?.open) onClose(); };
  const onClick = (event: MouseEvent<HTMLDialogElement>) => {
    if ((event.target as Element).closest("[data-modal-close]")) requestClose();
  };

  return (
    <dialog ref={ref} className={`modal ${closing ? "closing" : ""}`} aria-labelledby={labelledBy} onCancel={onCancel} onClose={onDialogClose} onClick={onClick} onAnimationEnd={onAnimationEnd}>
      <div className="modal-heading">
        <h2 id={labelledBy}>{title}</h2>
        <button className="icon-button" type="button" data-modal-close aria-label="关闭对话框"><Icon name="close" /></button>
      </div>
      {children}
    </dialog>
  );
}
