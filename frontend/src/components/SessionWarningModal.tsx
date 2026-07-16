import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

interface SessionWarningModalProps {
  visible: boolean;
  onStay: () => void;
}

function IconClock() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 7 12 12 15.5 14" />
    </svg>
  );
}

/** Aviso de sesion por expirar por inactividad -- portallado a <body> igual que
 * ComingSoonToast/ActiveJobsPopup. El propio click en "Seguir conectado" ya
 * cuenta como actividad y resetea el idle timer via los listeners globales. */
export default function SessionWarningModal({ visible, onStay }: SessionWarningModalProps) {
  const { t } = useTranslation();

  if (!visible) return null;

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 p-4">
      <div
        className="w-full max-w-[360px] rounded-2xl border border-[rgba(251,191,36,.25)] p-6 text-center"
        style={{ background: "var(--vf-p)", boxShadow: "0 20px 60px rgba(0,0,0,.6)" }}
      >
        <div
          className="mx-auto mb-3.5 flex h-11 w-11 items-center justify-center rounded-[12px]"
          style={{ background: "rgba(251,191,36,.12)", color: "#fbbf24" }}
        >
          <IconClock />
        </div>
        <h2 className="mb-1.5 text-base font-bold text-[var(--vf-text)]">{t("sessionWarning.title")}</h2>
        <p className="mb-5 text-[13px] leading-relaxed text-[var(--vf-muted)]">{t("sessionWarning.message")}</p>
        <button
          type="button"
          onClick={onStay}
          className="w-full rounded-lg px-4 py-2.5 text-sm font-semibold text-white"
          style={{ background: "linear-gradient(135deg,#7c6aff,#a855f7)" }}
        >
          {t("sessionWarning.stayButton")}
        </button>
      </div>
    </div>,
    document.body,
  );
}
