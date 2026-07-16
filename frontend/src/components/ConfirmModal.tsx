import { createPortal } from "react-dom";

interface ConfirmModalProps {
  visible: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Reemplazo estilizado del confirm() nativo del navegador -- mismo patron
 * (createPortal a <body>, tarjeta oscura redondeada) que CreateProjectModal
 * en AppLayout.tsx. */
export default function ConfirmModal({
  visible,
  title,
  message,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  if (!visible) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/60 p-4"
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[380px] rounded-2xl border border-[rgba(var(--vf-fg-rgb),.08)] bg-[var(--vf-s)] p-5 shadow-[0_20px_60px_rgba(0,0,0,.6)]"
      >
        <h2 className="mb-2 break-words text-lg font-bold text-[var(--vf-text)]">{title}</h2>
        <p className="mb-5 break-words text-sm leading-relaxed text-[var(--vf-m)]">{message}</p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-[rgba(var(--vf-fg-rgb),.1)] px-4 py-2 text-sm text-[var(--vf-m)] hover:bg-[rgba(var(--vf-fg-rgb),.04)]"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-lg px-4 py-2 text-sm font-semibold text-white"
            style={{ background: "var(--vf-danger)" }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
