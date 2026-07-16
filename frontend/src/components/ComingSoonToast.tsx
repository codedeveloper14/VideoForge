import { createPortal } from "react-dom";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

interface ComingSoonToastProps {
  visible: boolean;
  onClose: () => void;
}

function IconClock() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 7 12 12 15.5 14" />
    </svg>
  );
}

function IconClose() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

/** Branded replacement for the native alert() "coming soon" popup — a
 * self-dismissing toast, portalled to <body> like ActiveJobsPopup/Select. */
export default function ComingSoonToast({ visible, onClose }: ComingSoonToastProps) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!visible) return;
    const timer = setTimeout(onClose, 3400);
    return () => clearTimeout(timer);
  }, [visible, onClose]);

  if (!visible) return null;

  return createPortal(
    <div className="soon-toast-wrap">
      <div className="soon-toast">
        <span className="soon-toast-icon">
          <IconClock />
        </span>
        <div className="soon-toast-body">
          <span className="soon-toast-text">{t("tools.comingSoon")}</span>
        </div>
        <button type="button" onClick={onClose} className="soon-toast-close" title={t("updateNotice.dismiss") || ""}>
          <IconClose />
        </button>
      </div>
    </div>,
    document.body,
  );
}
