import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getRenderDownloadUrl, getRenderStatus, startRender } from "../../api/render";
import type { RenderStatus } from "../../api/render";
import { loadScript } from "../../api/script";

interface ProjectRenderPanelProps {
  project: string;
}

const RESOLUCIONES = [
  { value: "1920x1080", label: "1920×1080 — YouTube" },
  { value: "1080x1920", label: "1080×1920 — Reels/TikTok" },
  { value: "1080x1080", label: "1080×1080 — Instagram" },
  { value: "1280x720", label: "1280×720 — HD" },
];

const MODELOS = [
  { value: "tiny", label: "tiny — Muy rápido" },
  { value: "base", label: "base — Recomendado" },
  { value: "small", label: "small — Preciso" },
  { value: "medium", label: "medium — Muy preciso" },
];

const WHISPER_BACKENDS = [
  { value: "whisperx", label: "WhisperX API — Timestamps precisos" },
  { value: "api", label: "API" },
  { value: "faster", label: "Faster-whisper" },
  { value: "local", label: "Local — Estándar" },
];

const RENDER_MODES = [
  { value: "smart", label: "Mezcla inteligente", desc: "Usa videos disponibles + imágenes para el resto" },
  { value: "images", label: "Solo imágenes", desc: "Ignora videos del proyecto" },
  { value: "videos", label: "Solo videos", desc: "Solo videos ya generados del proyecto" },
];

const MOTIONS = [
  { value: "none", label: "Sin movimiento" },
  { value: "ken_burns", label: "Ken Burns" },
  { value: "zoom_in", label: "Zoom In" },
  { value: "zoom_out", label: "Zoom Out" },
  { value: "pan_left", label: "Pan Izquierda" },
  { value: "pan_right", label: "Pan Derecha" },
];

const TRANSITIONS = [
  { value: "none", label: "Sin transición" },
  { value: "dissolve", label: "Desvanecido" },
  { value: "slide_left", label: "Slide Izquierda" },
  { value: "slide_right", label: "Slide Derecha" },
  { value: "zoom", label: "Zoom" },
  { value: "fade", label: "Fade negro" },
];

export default function ProjectRenderPanel({ project }: ProjectRenderPanelProps) {
  const [renderMode, setRenderMode] = useState("smart");
  const [guion, setGuion] = useState("");
  const [useProjectScript, setUseProjectScript] = useState(true);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [useProjectAudio, setUseProjectAudio] = useState(true);

  const [resolucion, setResolucion] = useState("1920x1080");
  const [modelo, setModelo] = useState("base");
  const [whisperBackend, setWhisperBackend] = useState("whisperx");
  const [transicion, setTransicion] = useState("none");
  const [transDur, setTransDur] = useState(0.8);
  const [movimiento, setMovimiento] = useState("none");
  const [shake, setShake] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [limitInfo, setLimitInfo] = useState<string | null>(null);
  const [job, setJob] = useState<RenderStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load project's saved script for preview / reuse
  useEffect(() => {
    if (!project) return;
    loadScript(project)
      .then((data) => {
        if (data?.existe) setGuion(data.texto || "");
      })
      .catch(() => {});
  }, [project]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function startPolling(jobId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const data = await getRenderStatus(jobId);
        setJob(data);
        if (data.estado === "completado" || data.estado === "error") {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch (err) {
        setError((err as Error).message);
        if (pollRef.current) clearInterval(pollRef.current);
      }
    }, 2000);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!project) {
      setError("Selecciona un proyecto primero.");
      return;
    }
    if (!useProjectAudio && !audioFile) {
      setError("Sube un archivo de audio o marca 'usar audio del proyecto'.");
      return;
    }
    setError("");
    setLimitInfo(null);
    setJob(null);
    setLoading(true);
    try {
      const data = await startRender({
        project_name: project,
        render_mode: renderMode,
        guion: useProjectScript ? "" : guion,
        resolucion,
        modelo,
        whisper_backend: whisperBackend,
        transicion,
        trans_dur: transDur,
        movimiento,
        shake,
        audioFile: useProjectAudio ? null : audioFile,
      });
      setJob({ id: data.job_id, estado: "procesando", progreso: 0, mensaje: "Iniciando..." });
      startPolling(data.job_id);
    } catch (err) {
      const error = err as Error & { limit_reached?: boolean };
      if (error.limit_reached || /l[ií]mite/i.test(error.message || "")) {
        setLimitInfo(error.message);
      } else {
        setError(error.message);
      }
    } finally {
      setLoading(false);
    }
  }

  const isRendering = job && job.estado !== "completado" && job.estado !== "error";

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        {!project && (
          <p className="rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.05)] p-3 text-sm text-[var(--vf-muted)]">
            Selecciona un proyecto arriba para renderizar.
          </p>
        )}

        {/* Render mode */}
        <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
          <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            Modo de renderizado
          </h3>
          <div className="flex flex-wrap gap-2">
            {RENDER_MODES.map((m) => (
              <label
                key={m.value}
                className={`flex cursor-pointer flex-col gap-0.5 rounded-lg border px-3 py-2 text-sm transition ${
                  renderMode === m.value
                    ? "border-[var(--vf-accent)] bg-[var(--vf-accent)]/10"
                    : "border-[var(--vf-border)] bg-black/10"
                }`}
              >
                <span className="flex items-center gap-2 font-medium">
                  <input
                    type="radio"
                    name="renderMode"
                    value={m.value}
                    checked={renderMode === m.value}
                    onChange={() => setRenderMode(m.value)}
                    className="accent-[var(--vf-accent)]"
                  />
                  {m.label}
                </span>
                <span className="pl-5 text-[11px] text-[var(--vf-muted)]">{m.desc}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Audio + Script */}
        <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
          <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            Audio
          </h3>
          <label className="mb-2 flex items-center gap-2 text-sm text-[var(--vf-muted)]">
            <input
              type="checkbox"
              checked={useProjectAudio}
              onChange={(e) => setUseProjectAudio(e.target.checked)}
              className="accent-[var(--vf-accent)]"
            />
            Usar audio del proyecto
          </label>
          {!useProjectAudio && (
            <input
              type="file"
              accept=".mp3,.wav,.m4a,.ogg,.aac"
              onChange={(e) => setAudioFile(e.target.files?.[0] || null)}
              className="block w-full text-sm text-[var(--vf-muted)]"
            />
          )}

          <h3 className="mb-3 mt-5 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            Guión
          </h3>
          <label className="mb-2 flex items-center gap-2 text-sm text-[var(--vf-muted)]">
            <input
              type="checkbox"
              checked={useProjectScript}
              onChange={(e) => setUseProjectScript(e.target.checked)}
              className="accent-[var(--vf-accent)]"
            />
            Usar guión guardado del proyecto
          </label>
          {!useProjectScript && (
            <textarea
              value={guion}
              onChange={(e) => setGuion(e.target.value)}
              rows={6}
              placeholder="Cada línea = una escena..."
              className="w-full rounded-lg border border-[var(--vf-border)] bg-black/20 p-3 text-sm text-[var(--vf-text)] outline-none focus:border-[var(--vf-accent)]"
            />
          )}
        </div>

        {/* Effects */}
        <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
          <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            Movimiento de cámara
          </h3>
          <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {MOTIONS.map((m) => (
              <button
                type="button"
                key={m.value}
                onClick={() => setMovimiento(m.value)}
                className={`rounded-lg border px-3 py-2 text-xs transition ${
                  movimiento === m.value
                    ? "border-[var(--vf-accent)] bg-[var(--vf-accent)]/10 text-[var(--vf-text)]"
                    : "border-[var(--vf-border)] text-[var(--vf-muted)]"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm text-[var(--vf-muted)]">
            <input
              type="checkbox"
              checked={shake}
              onChange={(e) => setShake(e.target.checked)}
              className="accent-[var(--vf-accent)]"
            />
            Activar sacudida de lente (Shake)
          </label>

          <h3 className="mb-3 mt-5 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            Transición entre clips
          </h3>
          <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {TRANSITIONS.map((t) => (
              <button
                type="button"
                key={t.value}
                onClick={() => setTransicion(t.value)}
                className={`rounded-lg border px-3 py-2 text-xs transition ${
                  transicion === t.value
                    ? "border-[var(--vf-accent)] bg-[var(--vf-accent)]/10 text-[var(--vf-text)]"
                    : "border-[var(--vf-border)] text-[var(--vf-muted)]"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          {transicion !== "none" && (
            <div className="flex items-center gap-3">
              <label className="text-xs text-[var(--vf-muted)]">Duración</label>
              <input
                type="range"
                min="0.3"
                max="2"
                step="0.1"
                value={transDur}
                onChange={(e) => setTransDur(parseFloat(e.target.value))}
                className="flex-1 accent-[var(--vf-accent)]"
              />
              <span className="font-mono text-xs text-[var(--vf-muted)]">{transDur}s</span>
            </div>
          )}
        </div>

        {/* Output config */}
        <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
          <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            Configuración de salida
          </h3>
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-[11px] text-[var(--vf-muted)]">Resolución</label>
              <select
                value={resolucion}
                onChange={(e) => setResolucion(e.target.value)}
                className="w-full rounded-lg border border-[var(--vf-border)] bg-black/20 p-2 text-sm text-[var(--vf-text)]"
              >
                {RESOLUCIONES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-[var(--vf-muted)]">Modelo Whisper</label>
              <select
                value={modelo}
                onChange={(e) => setModelo(e.target.value)}
                className="w-full rounded-lg border border-[var(--vf-border)] bg-black/20 p-2 text-sm text-[var(--vf-text)]"
              >
                {MODELOS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-[var(--vf-muted)]">Motor Whisper</label>
              <select
                value={whisperBackend}
                onChange={(e) => setWhisperBackend(e.target.value)}
                className="w-full rounded-lg border border-[var(--vf-border)] bg-black/20 p-2 text-sm text-[var(--vf-text)]"
              >
                {WHISPER_BACKENDS.map((w) => (
                  <option key={w.value} value={w.value}>
                    {w.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {limitInfo && (
          <div className="rounded-lg border border-[var(--vf-c4)]/40 bg-[var(--vf-c4)]/10 p-4 text-sm">
            <p className="mb-2 text-[var(--vf-c4)]">{limitInfo}</p>
            <Link to="/app/planes" className="text-[var(--vf-accent)] hover:underline">
              Mejora tu plan →
            </Link>
          </div>
        )}
        {error && <p className="text-sm text-[var(--vf-danger)]">{error}</p>}

        <button
          type="submit"
          disabled={loading || !project || !!isRendering}
          className="rounded-lg bg-[var(--vf-accent)] px-5 py-3 font-medium text-white transition hover:bg-[var(--vf-accent-hover)] disabled:opacity-50"
        >
          {loading ? "Enviando..." : isRendering ? "Renderizando..." : "Generar video"}
        </button>
      </form>

      {/* Progress / result */}
      <div className="flex flex-col gap-4">
        {job && (
          <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
            <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
              {job.estado === "completado" ? "Video listo" : "Progreso del render"}
            </h3>
            <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-[rgba(var(--vf-fg-rgb),0.05)]">
              <div
                className={`h-full rounded-full transition-all ${
                  job.estado === "error" ? "bg-[var(--vf-danger)]" : "bg-[var(--vf-accent)]"
                }`}
                style={{ width: `${Math.min(100, Math.max(0, job.progreso || 0))}%` }}
              />
            </div>
            <p className="mb-1 font-mono text-xs text-[var(--vf-muted)]">
              {job.progreso || 0}% · {job.estado}
            </p>
            {job.mensaje && <p className="text-sm text-[var(--vf-muted)]">{job.mensaje}</p>}
            {Array.isArray(job.logs) && job.logs.length > 0 && (
              <div className="mt-3 max-h-40 overflow-y-auto rounded-lg bg-black/30 p-2 font-mono text-[10px] text-[var(--vf-muted)]">
                {job.logs.map((line, i) => (
                  <div key={i}>{line}</div>
                ))}
              </div>
            )}
            {job.estado === "completado" && (
              <a
                href={job.video_url || getRenderDownloadUrl(job.id || job.job_id || "")}
                download
                className="mt-4 block rounded-lg bg-[var(--vf-success)] px-4 py-2.5 text-center font-medium text-black"
              >
                Descargar video
              </a>
            )}
            {job.estado === "error" && (
              <p className="mt-2 text-sm text-[var(--vf-danger)]">
                {job.error || "Ocurrió un error durante el render."}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
