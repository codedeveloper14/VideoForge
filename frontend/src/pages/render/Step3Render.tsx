import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { formatDur } from "./wizardShared";

export interface RenderJobState {
  id?: string;
  estado: string;
  progreso?: number;
  mensaje?: string;
  logs?: string[];
  error?: string;
  video_url?: string;
  size_mb?: number | string;
  duracion?: number;
  escenas?: number;
  [key: string]: unknown;
}

interface SummaryPill {
  label: string;
}

interface Step3RenderProps {
  job: RenderJobState | null;
  pills: SummaryPill[];
  sceneCount: number;
  downloadUrl: string;
  onNewVideo: () => void;
}

const BADGE_STYLES: Record<string, string> = {
  procesando: "text-[var(--vf-c4)] border-[var(--vf-c4)]/30 bg-[var(--vf-c4)]/[0.15]",
  completado: "text-[var(--vf-success)] border-[var(--vf-success)]/30 bg-[var(--vf-success)]/[0.15]",
  error: "text-[var(--vf-danger)] border-[var(--vf-danger)]/30 bg-[var(--vf-danger)]/[0.15]",
};

export default function Step3Render({ job, pills, sceneCount, downloadUrl, onNewVideo }: Step3RenderProps) {
  const { t } = useTranslation();
  const estado = job?.estado || "procesando";
  const isDone = estado === "completado";
  const isError = estado === "error";
  const progreso = Math.min(100, Math.max(0, job?.progreso || 0));

  if (isDone) {
    return (
      <div className="text-center">
        <div className="px-0 pb-5 pt-2 text-center">
          <h2
            className="mb-2 text-[clamp(24px,4vw,38px)] font-extrabold leading-tight tracking-tight"
            style={{
              background: "linear-gradient(135deg, #fff 30%, var(--vf-c2) 70%, var(--vf-c1))",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            {t("projectRenderPanel.videoReadyExcited")}
          </h2>
          <p className="font-mono text-sm text-[var(--vf-muted)]">{t("projectRenderPanel.videoGeneratedSuccess")}</p>
        </div>

        <div
          className="mx-auto max-w-[560px] rounded-2xl border p-7"
          style={{
            background: "linear-gradient(135deg, rgba(34,211,160,.08), rgba(124,106,255,.08))",
            borderColor: "rgba(34,211,160,.3)",
          }}
        >
          <div className="mb-5 flex items-center gap-3.5 text-left">
            <div className="text-[38px]">🎉</div>
            <div>
              <div className="text-xl font-extrabold text-[var(--vf-text)]">{t("projectRenderPanel.videoReadyBang")}</div>
              <div className="font-mono text-xs text-[var(--vf-muted)]">{t("projectRenderPanel.jobIdLabel", { id: job?.id || "—" })}</div>
            </div>
          </div>
          <div className="mb-5 grid grid-cols-3 gap-3">
            <div className="rounded-xl bg-black/30 p-3.5 text-center">
              <div className="font-mono text-xl font-extrabold text-[var(--vf-c2)]">
                {job?.size_mb ? `${job.size_mb} MB` : "—"}
              </div>
              <div className="mt-0.5 text-[11px] text-[var(--vf-muted)]">{t("projectRenderPanel.sizeLabel")}</div>
            </div>
            <div className="rounded-xl bg-black/30 p-3.5 text-center">
              <div className="font-mono text-xl font-extrabold text-[var(--vf-c2)]">
                {job?.duracion ? formatDur(job.duracion) : "—"}
              </div>
              <div className="mt-0.5 text-[11px] text-[var(--vf-muted)]">{t("projectRenderPanel.durationLabel")}</div>
            </div>
            <div className="rounded-xl bg-black/30 p-3.5 text-center">
              <div className="font-mono text-xl font-extrabold text-[var(--vf-c2)]">
                {job?.escenas ?? sceneCount ?? "—"}
              </div>
              <div className="mt-0.5 text-[11px] text-[var(--vf-muted)]">{t("projectRenderPanel.scenesLabel")}</div>
            </div>
          </div>
          <a
            href={job?.video_url || downloadUrl}
            download
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--vf-success)] py-3.5 text-[15px] font-bold text-black transition-transform hover:-translate-y-px"
          >
            {t("projectRenderPanel.downloadVideoButton")}
          </a>
          <button
            type="button"
            onClick={onNewVideo}
            className="mx-auto mt-3.5 block rounded-lg border-[1.5px] border-[var(--vf-b2)] px-6 py-2.5 font-mono text-xs uppercase tracking-wide text-[var(--vf-muted)] transition-colors hover:border-[var(--vf-c2)] hover:text-[var(--vf-text)]"
          >
            {t("projectRenderPanel.generateAnotherVideo")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="text-center">
      <div className="px-0 pb-5 pt-2 text-center">
        <h2
          className="mb-2 text-[clamp(24px,4vw,38px)] font-extrabold leading-tight tracking-tight"
          style={{
            background: "linear-gradient(135deg, #fff 30%, var(--vf-c2) 70%, var(--vf-c1))",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}
        >
          {t("projectRenderPanel.renderingVideoTitle")}
        </h2>
        <p className="font-mono text-sm text-[var(--vf-muted)]">
          {t("projectRenderPanel.renderingVideoSub")}
        </p>
      </div>

      {pills.length > 0 && (
        <div className="mb-8 flex flex-wrap justify-center gap-2">
          {pills.map((p, i) => (
            <span
              key={i}
              className="rounded-full border px-3 py-1 font-mono text-[11px] text-[var(--vf-c2)]"
              style={{ background: "rgba(124,106,255,.12)", borderColor: "rgba(124,106,255,.25)" }}
            >
              {p.label}
            </span>
          ))}
        </div>
      )}

      {/* Orbit animation */}
      <div className="relative mx-auto mb-9 h-[220px] w-[220px]">
        <div
          className="absolute inset-0 rounded-full border-2 border-transparent"
          style={{
            borderTopColor: "var(--vf-accent)",
            borderRightColor: "rgba(124,106,255,.3)",
            animation: "vf-spin 2s linear infinite",
          }}
        />
        <div
          className="absolute inset-4 rounded-full border-[1.5px] border-transparent"
          style={{
            borderBottomColor: "var(--vf-c2)",
            borderLeftColor: "rgba(167,139,250,.3)",
            animation: "vf-spin 3s linear infinite reverse",
          }}
        />
        <div
          className="absolute inset-8 flex flex-col items-center justify-center gap-1.5 rounded-full border border-[var(--vf-border)] bg-[var(--vf-surface)]"
          style={{ boxShadow: "0 0 40px rgba(124,106,255,.15)" }}
        >
          <div className="animate-pulse text-[36px]">🎬</div>
          <div className="font-mono text-[10px] uppercase tracking-wide text-[var(--vf-muted)]">{t("projectRenderPanel.processingLabel")}</div>
        </div>
      </div>
      <style>{"@keyframes vf-spin{to{transform:rotate(360deg)}}"}</style>

      <div className="mx-auto mb-2.5 h-2.5 max-w-[560px] overflow-hidden rounded-full border border-[var(--vf-border)] bg-[var(--vf-p)]">
        <div
          className={`h-full rounded-full transition-all ${isError ? "" : ""}`}
          style={{
            width: `${progreso}%`,
            background: isError
              ? "var(--vf-danger)"
              : "linear-gradient(90deg, var(--vf-accent), var(--vf-c2), var(--vf-success))",
          }}
        />
      </div>
      <div className="my-2 font-mono text-2xl font-extrabold text-[var(--vf-c2)]">{progreso}%</div>
      <div
        className={`mb-7 inline-block rounded-full border px-3.5 py-1 font-mono text-[11px] uppercase tracking-wide ${
          BADGE_STYLES[estado] || BADGE_STYLES.procesando
        }`}
      >
        {estado}
      </div>

      {job?.mensaje && <p className="mb-3 text-sm text-[var(--vf-muted)]">{job.mensaje}</p>}

      {Array.isArray(job?.logs) && job.logs.length > 0 && (
        <div className="mx-auto mb-6 max-h-[180px] max-w-[620px] overflow-y-auto rounded-xl border border-[var(--vf-border)] bg-[var(--vf-p)] p-3.5 text-left font-mono text-[11px] leading-relaxed">
          {job!.logs!.map((line, i) => (
            <div
              key={i}
              className={
                line.startsWith("✓") || line.startsWith("✅")
                  ? "text-[var(--vf-success)]"
                  : line.startsWith("❌")
                    ? "text-[var(--vf-danger)]"
                    : "text-[var(--vf-text)]"
              }
            >
              {line}
            </div>
          ))}
        </div>
      )}

      {isError && !!job?.limit_reached && (
        <div className="mx-auto mt-2 max-w-[560px] rounded-lg border border-[var(--vf-c4)]/40 bg-[var(--vf-c4)]/10 p-4 text-sm">
          <p className="mb-2 text-[var(--vf-c4)]">{job?.error}</p>
          <Link to="/app/planes" className="text-[var(--vf-accent)] hover:underline">
            {t("projectRenderPanel.upgradePlan")}
          </Link>
        </div>
      )}
      {isError && !job?.limit_reached && (
        <p className="mx-auto max-w-[560px] text-sm text-[var(--vf-danger)]">
          {job?.error || t("projectRenderPanel.renderErrorGeneric")}
        </p>
      )}
    </div>
  );
}
