import { useEffect, useRef, useState } from "react";
import { listJobs } from "../../api/quickRender";
import type { MultitaskJob } from "../../api/quickRender";

const ESTADO_COLORS: Record<string, string> = {
  completado: "text-[var(--vf-success)] border-[var(--vf-success)]/30 bg-[var(--vf-success)]/10",
  procesando: "text-[var(--vf-c6)] border-[var(--vf-c6)]/30 bg-[var(--vf-c6)]/10",
  error: "text-[var(--vf-danger)] border-[var(--vf-danger)]/30 bg-[var(--vf-danger)]/10",
};

function estadoClass(estado?: string) {
  return (
    (estado && ESTADO_COLORS[estado]) ||
    "text-[var(--vf-muted)] border-[var(--vf-border)] bg-white/5"
  );
}

function formatTime(ts?: number) {
  if (!ts) return "";
  try {
    const d = new Date(ts * 1000);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleTimeString();
  } catch {
    return "";
  }
}

export default function JobsPanel() {
  const [jobs, setJobs] = useState<MultitaskJob[]>([]);
  const [error, setError] = useState("");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const data = await listJobs();
        if (!cancelled) {
          setJobs(Array.isArray(data) ? data : []);
          setError("");
        }
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      }
    }

    poll();
    timerRef.current = setInterval(poll, 4000);
    return () => {
      cancelled = true;
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  return (
    <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
          Actividad reciente
        </h2>
        <span className="font-mono text-[10px] text-[var(--vf-muted)]">
          {jobs.length} tarea{jobs.length !== 1 ? "s" : ""}
        </span>
      </div>

      {error && <p className="mb-2 text-xs text-[var(--vf-danger)]">{error}</p>}

      {jobs.length === 0 ? (
        <p className="text-sm text-[var(--vf-muted)]">
          No hay tareas activas ni recientes.
        </p>
      ) : (
        <ul className="flex flex-col gap-2 max-h-[420px] overflow-y-auto pr-1">
          {jobs.map((job) => (
            <li
              key={job.id}
              className="rounded-lg border border-[var(--vf-border)] bg-black/20 p-3"
            >
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <span className="truncate font-mono text-[11px] text-[var(--vf-text)]">
                  {job.tipo || "tarea"}
                  {job.proyecto ? ` · ${job.proyecto}` : ""}
                </span>
                <span
                  className={`shrink-0 rounded border px-2 py-0.5 font-mono text-[9px] uppercase tracking-wide ${estadoClass(job.estado)}`}
                >
                  {job.estado || "?"}
                </span>
              </div>
              <div className="mb-1.5 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
                <div
                  className="h-full rounded-full bg-[var(--vf-accent)] transition-all"
                  style={{ width: `${Math.min(100, Math.max(0, job.progreso || 0))}%` }}
                />
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-[11px] text-[var(--vf-muted)]">
                  {job.mensaje || ""}
                </span>
                <span className="shrink-0 font-mono text-[9px] text-[var(--vf-muted)]">
                  {formatTime(job.inicio)}
                </span>
              </div>
              {job.video_url && (
                <a
                  href={job.video_url}
                  className="mt-2 inline-block text-[11px] text-[var(--vf-accent)] hover:underline"
                  download
                >
                  Descargar video
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
