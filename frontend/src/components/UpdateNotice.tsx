import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { checkForUpdate } from "../api/updates";

function dismissedKey(version: string) {
  return `vf-update-dismissed-${version}`;
}

function IconClose() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

export default function UpdateNotice() {
  const { t } = useTranslation();
  const [release, setRelease] = useState<{ version: string; url: string | null } | null>(null);

  useEffect(() => {
    let cancelled = false;
    checkForUpdate()
      .then((result) => {
        if (cancelled || !result.update_available || !result.latest_version) return;
        if (sessionStorage.getItem(dismissedKey(result.latest_version))) return;
        setRelease({ version: result.latest_version, url: result.release_url });
      })
      .catch(() => {
        // silencioso -- este aviso es secundario, no debe interrumpir la app
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!release) return null;

  function dismiss() {
    if (release) sessionStorage.setItem(dismissedKey(release.version), "1");
    setRelease(null);
  }

  return (
    <div
      className="mb-3 flex items-center gap-2.5 rounded-lg border px-3.5 py-2 text-xs"
      style={{
        borderColor: "rgba(124,106,255,.25)",
        background: "rgba(124,106,255,.08)",
        color: "var(--vf-text)",
      }}
    >
      <span className="flex-1">{t("updateNotice.message", { version: release.version })}</span>
      {release.url && (
        <a
          href={release.url}
          target="_blank"
          rel="noreferrer"
          className="font-semibold transition-colors hover:text-[#a78bfa]"
          style={{ color: "#7c6aff" }}
        >
          {t("updateNotice.viewRelease")}
        </a>
      )}
      <button
        onClick={dismiss}
        title={t("updateNotice.dismiss") || ""}
        className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded opacity-60 transition-opacity hover:opacity-100"
      >
        <IconClose />
      </button>
    </div>
  );
}
