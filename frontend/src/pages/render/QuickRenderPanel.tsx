import { useEffect, useRef, useState } from "react";
import { getQuickRenderDownloadUrl, startQuickRender } from "../../api/quickRender";

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

interface ImageEntry {
  file: File;
  url: string;
}

interface QuickJobState {
  id?: string;
  estado: string;
  progreso?: number;
  mensaje?: string;
  error?: string;
  downloadUrl?: string;
  [key: string]: unknown;
}

function formatSize(bytes: number) {
  return bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
}

export default function QuickRenderPanel() {
  const [guion, setGuion] = useState("");
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [images, setImages] = useState<ImageEntry[]>([]);

  const [resolucion, setResolucion] = useState("1920x1080");
  const [fade, setFade] = useState(0);
  const [modelo, setModelo] = useState("base");
  const [whisperBackend, setWhisperBackend] = useState("whisperx");
  const [transicion, setTransicion] = useState("none");
  const [transDur, setTransDur] = useState(0.8);
  const [movimiento, setMovimiento] = useState("none");
  const [shake, setShake] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [job, setJob] = useState<QuickJobState | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function handleImageInput(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setImages((prev) => [...prev, ...files.map((file) => ({ file, url: URL.createObjectURL(file) }))]);
    e.target.value = "";
  }

  function moveImage(index: number, dir: number) {
    setImages((prev) => {
      const next = [...prev];
      const target = index + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function removeImage(index: number) {
    setImages((prev) => prev.filter((_, i) => i !== index));
  }

  function startPolling(jobId: string, downloadUrl: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/estado/${jobId}`, { credentials: "same-origin" });
        const data = await res.json();
        if (data.error) {
          setJob({ estado: "error", error: data.error });
          if (pollRef.current) clearInterval(pollRef.current);
          return;
        }
        setJob({ ...data, downloadUrl });
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
    if (!audioFile) {
      setError("Sube un archivo de audio.");
      return;
    }
    if (!images.length) {
      setError("Sube al menos una imagen.");
      return;
    }
    if (!guion.trim()) {
      setError("Escribe el guión (una línea por escena).");
      return;
    }
    setError("");
    setJob(null);
    setLoading(true);
    try {
      const data = await startQuickRender({
        guion,
        resolucion,
        fade,
        modelo,
        whisper_backend: whisperBackend,
        transicion,
        movimiento,
        trans_dur: transDur,
        shake,
        audioFile,
        imageFiles: images.map((i) => i.file),
      });
      const jobId = data.job_id;
      setJob({ id: jobId, estado: "procesando", progreso: 0, mensaje: "Iniciando..." });
      startPolling(jobId, getQuickRenderDownloadUrl(jobId));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const isRendering = job && job.estado !== "completado" && job.estado !== "error";
  const lineCount = guion.split("\n").filter((l) => l.trim()).length;

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
          <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            Audio
          </h3>
          <input
            type="file"
            accept=".mp3,.wav,.m4a,.ogg,.aac"
            onChange={(e) => setAudioFile(e.target.files?.[0] || null)}
            className="block w-full text-sm text-[var(--vf-muted)]"
          />
          {audioFile && (
            <p className="mt-2 text-xs text-[var(--vf-muted)]">
              {audioFile.name} · {formatSize(audioFile.size)}
            </p>
          )}
        </div>

        <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
          <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            Imágenes ({images.length})
          </h3>
          <input
            type="file"
            accept=".jpg,.jpeg,.png,.webp"
            multiple
            onChange={handleImageInput}
            className="mb-3 block w-full text-sm text-[var(--vf-muted)]"
          />
          {images.length > 0 && (
            <ul className="flex flex-col gap-2">
              {images.map((img, i) => (
                <li
                  key={img.url}
                  className="flex items-center gap-3 rounded-lg border border-[var(--vf-border)] bg-black/20 p-2"
                >
                  <img src={img.url} alt="" className="h-12 w-12 rounded object-cover" />
                  <span className="flex-1 truncate text-xs text-[var(--vf-muted)]">
                    {i + 1}. {img.file.name}
                  </span>
                  <button
                    type="button"
                    onClick={() => moveImage(i, -1)}
                    disabled={i === 0}
                    className="rounded border border-[var(--vf-border)] px-2 py-1 text-xs text-[var(--vf-muted)] disabled:opacity-30"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    onClick={() => moveImage(i, 1)}
                    disabled={i === images.length - 1}
                    className="rounded border border-[var(--vf-border)] px-2 py-1 text-xs text-[var(--vf-muted)] disabled:opacity-30"
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    onClick={() => removeImage(i)}
                    className="rounded border border-[var(--vf-danger)]/40 px-2 py-1 text-xs text-[var(--vf-danger)]"
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
          <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            Guión
          </h3>
          <textarea
            value={guion}
            onChange={(e) => setGuion(e.target.value)}
            rows={6}
            placeholder={"Esta es la primera escena.\nEsta es la segunda escena.\nCada línea = una imagen en orden."}
            className="w-full rounded-lg border border-[var(--vf-border)] bg-black/20 p-3 text-sm text-[var(--vf-text)] outline-none focus:border-[var(--vf-accent)]"
          />
          <p className="mt-1 font-mono text-[11px] text-[var(--vf-muted)]">
            {guion.length} caracteres · {lineCount} líneas
          </p>
        </div>

        <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
          <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            Movimiento y transición
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
          <label className="mb-4 flex items-center gap-2 text-sm text-[var(--vf-muted)]">
            <input
              type="checkbox"
              checked={shake}
              onChange={(e) => setShake(e.target.checked)}
              className="accent-[var(--vf-accent)]"
            />
            Activar sacudida de lente (Shake)
          </label>
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

        <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
          <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            Configuración de salida
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
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
            <div>
              <label className="mb-1 block text-[11px] text-[var(--vf-muted)]">Fade (s)</label>
              <input
                type="number"
                min="0"
                step="0.1"
                value={fade}
                onChange={(e) => setFade(parseFloat(e.target.value) || 0)}
                className="w-full rounded-lg border border-[var(--vf-border)] bg-black/20 p-2 text-sm text-[var(--vf-text)]"
              />
            </div>
          </div>
        </div>

        {error && <p className="text-sm text-[var(--vf-danger)]">{error}</p>}

        <button
          type="submit"
          disabled={loading || !!isRendering}
          className="rounded-lg bg-[var(--vf-accent)] px-5 py-3 font-medium text-white transition hover:bg-[var(--vf-accent-hover)] disabled:opacity-50"
        >
          {loading ? "Enviando..." : isRendering ? "Renderizando..." : "Generar video"}
        </button>
      </form>

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
            {job.estado === "completado" && (
              <a
                href={job.downloadUrl}
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
