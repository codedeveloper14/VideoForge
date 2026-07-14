import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { listJobs } from "../api/quickRender";
import type { MultitaskJob } from "../api/quickRender";

const ESTADO_COLORS: Record<string, string> = {
  completado: "text-[var(--vf-success)] border-[var(--vf-success)]/30 bg-[var(--vf-success)]/10",
  procesando: "text-[var(--vf-c6)] border-[var(--vf-c6)]/30 bg-[var(--vf-c6)]/10",
  error: "text-[var(--vf-danger)] border-[var(--vf-danger)]/30 bg-[var(--vf-danger)]/10",
};

function estadoClass(estado?: string) {
  return (
    (estado && ESTADO_COLORS[estado]) ||
    "text-[var(--vf-muted)] border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.05)]"
  );
}

function IconPlay() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
      <polygon points="6,4 20,12 6,20" />
    </svg>
  );
}

export default function ActiveJobsPopup() {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState<MultitaskJob[]>([]);
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState<{ top: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const data = await listJobs();
        if (!cancelled) setJobs(Array.isArray(data) ? data : []);
      } catch {
        // silencioso -- este es un widget secundario, no debe interrumpir la app
      }
    }
    poll();
    timerRef.current = setInterval(poll, 4000);
    return () => {
      cancelled = true;
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (popupRef.current?.contains(target)) return;
      setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  useEffect(() => {
    if (!open || !triggerRef.current) return;
    const r = triggerRef.current.getBoundingClientRect();
    setRect({ top: r.bottom + 6, left: Math.max(8, r.right - 370) });
  }, [open]);

  const activeCount = jobs.filter((j) => j.estado === "procesando").length;
  const label = activeCount > 0 ? t("jobsPanel.taskCount", { count: activeCount }) : t("activeJobsPopup.tasks");

  return (
    <>
      <button
        ref={triggerRef}
        onClick={() => setOpen((v) => !v)}
        title={t("activeJobsPopup.activeTasks") || ""}
        className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
          activeCount > 0
            ? "border-[var(--vf-c1)]/40 bg-[var(--vf-c1)]/[0.12] text-[var(--vf-c1)]"
            : "border-[rgba(var(--vf-fg-rgb),0.1)] bg-[rgba(var(--vf-fg-rgb),0.03)] text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
        }`}
      >
        <IconPlay />
        {label}
      </button>

      {open &&
        rect &&
        createPortal(
          <div
            ref={popupRef}
            className="fixed z-[9500] max-h-[420px] w-[370px] overflow-y-auto rounded-xl py-2"
            style={{
              top: rect.top,
              left: rect.left,
              background: "var(--vf-p)",
              border: "1px solid rgba(var(--vf-fg-rgb),.08)",
              boxShadow: "0 12px 36px rgba(0,0,0,.6)",
            }}
          >
            <div className="px-3.5 pb-2 font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
              {t("activeJobsPopup.tasksInProgress")}
            </div>
            {jobs.length === 0 ? (
              <p className="px-3.5 py-3 text-sm text-[var(--vf-muted)]">
                {t("jobsPanel.noActiveOrRecentTasks")}
              </p>
            ) : (
              <ul className="flex flex-col gap-2 px-2.5">
                {jobs.map((job) => (
                  <li
                    key={job.id}
                    className="rounded-lg border border-[var(--vf-border)] bg-black/20 p-3"
                  >
                    <div className="mb-1.5 flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-[11px] text-[var(--vf-text)]">
                        {job.tipo || t("jobsPanel.taskFallback")}
                        {job.proyecto ? ` · ${job.proyecto}` : ""}
                      </span>
                      <span
                        className={`shrink-0 rounded border px-2 py-0.5 font-mono text-[9px] uppercase tracking-wide ${estadoClass(job.estado)}`}
                      >
                        {job.estado || "?"}
                      </span>
                    </div>
                    <div className="mb-1.5 h-1.5 w-full overflow-hidden rounded-full bg-[rgba(var(--vf-fg-rgb),0.05)]">
                      <div
                        className="h-full rounded-full bg-[var(--vf-accent)] transition-all"
                        style={{ width: `${Math.min(100, Math.max(0, job.progreso || 0))}%` }}
                      />
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-[11px] text-[var(--vf-muted)]">
                        {job.mensaje || ""}
                      </span>
                    </div>
                    {job.video_url && (
                      <a
                        href={job.video_url}
                        className="mt-2 inline-block text-[11px] text-[var(--vf-accent)] hover:underline"
                        download
                      >
                        {t("jobsPanel.downloadVideo")}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>,
          document.body,
        )}
    </>
  );
}
