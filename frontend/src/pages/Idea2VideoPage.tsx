import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import {
  abrirCarpetaAutopilot,
  generateScript,
  getAutopilotStatus,
  startAutopilot,
} from "../api/idea2video";
import type { AutopilotStatus } from "../api/idea2video";
import { listVoices } from "../api/voice";
import type { Voice } from "../api/voice";

const VOICE_ID_KEY = "vf_i2v_voice_id";

const STYLE_OPTIONS = [
  { value: "cinematic", label: "Cinemático" },
  { value: "tutorial", label: "Tutorial" },
  { value: "documental", label: "Documental" },
  { value: "viral", label: "Viral" },
  { value: "corporativo", label: "Corporativo" },
];

const TONE_OPTIONS = [
  { value: "inspirador", label: "Inspirador" },
  { value: "profesional", label: "Profesional" },
  { value: "casual", label: "Casual" },
  { value: "tecnico", label: "Técnico" },
  { value: "urgente", label: "Urgente" },
];

const PHASE_LABELS: Record<string, string> = {
  recursos: "Recursos del proyecto",
  fragmentar: "Fragmentar guión",
  prompts: "Prompts visuales",
  voz: "Síntesis de voz",
  imagenes: "Generación de imágenes",
  ensamblar: "Ensamblado final",
};

const PHASE_ORDER = ["recursos", "fragmentar", "prompts", "voz", "imagenes", "ensamblar"];

interface ScenesInfo {
  scenes?: number;
  words?: number;
  dur?: number;
}

function StepEyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[var(--vf-border)] bg-white/[0.03] px-3 py-1 font-mono text-[9.5px] uppercase tracking-widest text-[var(--vf-muted)]">
      <span
        className="h-[5px] w-[5px] rounded-full"
        style={{ background: "var(--vf-c5)", boxShadow: "0 0 6px var(--vf-c5)" }}
      />
      {children}
    </div>
  );
}

function PhaseBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; color: string }> = {
    pending: { label: "Pendiente", color: "var(--vf-muted)" },
    active: { label: "En curso", color: "var(--vf-c6)" },
    done: { label: "Listo", color: "var(--vf-c5)" },
    partial: { label: "Parcial", color: "var(--vf-c4)" },
    skip: { label: "Omitido", color: "var(--vf-muted)" },
    error: { label: "Error", color: "var(--vf-danger)" },
  };
  const info = map[status] || map.pending;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-[var(--vf-border)] px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider"
      style={{ color: info.color }}
    >
      <span
        className="h-[5px] w-[5px] rounded-full"
        style={{ background: info.color, boxShadow: status === "active" ? `0 0 6px ${info.color}` : "none" }}
      />
      {info.label}
    </span>
  );
}

export default function Idea2VideoPage() {
  const [step, setStep] = useState(1);
  const [error, setError] = useState("");

  // Step 1 — idea
  const [idea, setIdea] = useState("");
  const [dur, setDur] = useState(60);
  const [style, setStyle] = useState("cinematic");
  const [tone, setTone] = useState("inspirador");
  const [audience, setAudience] = useState("general");
  const [generatingScript, setGeneratingScript] = useState(false);

  // Step 2 — script + voice + ref image
  const [script, setScript] = useState("");
  const [title, setTitle] = useState("");
  const [scenesInfo, setScenesInfo] = useState<ScenesInfo | null>(null);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voicesLoading, setVoicesLoading] = useState(true);
  const [voiceId, setVoiceId] = useState(() => localStorage.getItem(VOICE_ID_KEY) || "");
  const [refImageFile, setRefImageFile] = useState<File | null>(null);
  const [refImageBase64, setRefImageBase64] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  // Step 3 — progress
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<AutopilotStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setVoicesLoading(true);
    listVoices()
      .then((data) => {
        const list = Array.isArray(data) ? data : [];
        setVoices(list);
        const saved = localStorage.getItem(VOICE_ID_KEY);
        const ids = list.map((v) => v["ID Voz"] || v.id || v.voice_id);
        if (saved && ids.includes(saved)) {
          setVoiceId(saved);
        } else if (list.length > 0) {
          const first = list[0];
          const firstId = first["ID Voz"] || first.id || first.voice_id || "";
          setVoiceId(firstId);
        }
      })
      .catch((err) => setError((err as Error).message))
      .finally(() => setVoicesLoading(false));
  }, []);

  useEffect(() => {
    if (voiceId) localStorage.setItem(VOICE_ID_KEY, voiceId);
  }, [voiceId]);

  useEffect(() => {
    if (step !== 3 || !jobId) return;
    let cancelled = false;

    async function poll() {
      try {
        const data = await getAutopilotStatus(jobId as string);
        if (cancelled) return;
        setStatus(data);
        if (data.status === "done" || data.status === "error") {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      }
    }

    poll();
    pollRef.current = setInterval(poll, 2500);
    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [step, jobId]);

  function fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve((reader.result as string).split(",")[1] || "");
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  async function handleRefImageChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] || null;
    setRefImageFile(file);
    if (!file) {
      setRefImageBase64(null);
      return;
    }
    try {
      const b64 = await fileToBase64(file);
      setRefImageBase64(b64);
    } catch {
      setRefImageBase64(null);
    }
  }

  async function handleGenerateScript() {
    if (!idea.trim()) {
      setError("Escribe una idea primero.");
      return;
    }
    setError("");
    setGeneratingScript(true);
    try {
      const data = await generateScript({ idea, dur, style, tone, audience });
      if (!data.ok) {
        setError(data.error || "No se pudo generar el guión.");
        return;
      }
      setScript(data.script || "");
      setTitle(data.title || idea.slice(0, 60));
      setScenesInfo({ scenes: data.scenes, words: data.words, dur: data.dur });
      setStep(2);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setGeneratingScript(false);
    }
  }

  async function handleStartAutopilot() {
    if (!script.trim()) {
      setError("El guión está vacío.");
      return;
    }
    if (!voiceId) {
      setError("Selecciona una voz antes de continuar.");
      return;
    }
    setError("");
    setStarting(true);
    try {
      const data = await startAutopilot({
        script,
        title,
        voiceId,
        refImage: refImageBase64,
        mode: "rapido",
      });
      if (data.error) {
        setError(data.error);
        return;
      }
      setJobId(data.job_id);
      setStatus(null);
      setStep(3);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setStarting(false);
    }
  }

  async function handleAbrirCarpeta() {
    if (!jobId) return;
    try {
      await abrirCarpetaAutopilot(jobId);
    } catch {
      // desktop convenience — ignore failures gracefully
    }
  }

  function handleRestart() {
    if (pollRef.current) clearInterval(pollRef.current);
    setStep(1);
    setIdea("");
    setScript("");
    setTitle("");
    setScenesInfo(null);
    setRefImageFile(null);
    setRefImageBase64(null);
    setJobId(null);
    setStatus(null);
    setError("");
  }

  const donePhases = status
    ? PHASE_ORDER.filter((p) => status.phases?.[p] === "done" || status.phases?.[p] === "skip").length
    : 0;
  const progressPct = Math.round((donePhases / PHASE_ORDER.length) * 100);

  return (
    <div>
      <div className="mb-9 max-w-2xl">
        <StepEyebrow>Autopilot · Idea a Video</StepEyebrow>
        <h1 className="mb-3 text-3xl font-extrabold tracking-tight sm:text-4xl">
          Idea a{" "}
          <span
            className="bg-clip-text text-transparent"
            style={{
              backgroundImage:
                "linear-gradient(110deg, var(--vf-c2) 0%, var(--vf-c1) 40%, var(--vf-c3) 85%)",
            }}
          >
            Video
          </span>
        </h1>
        <p className="font-mono text-[12.5px] leading-relaxed text-[var(--vf-muted)]">
          Escribe una idea en una línea y deja que el autopilot genere guión, imágenes, voz y video sin
          intervención manual.
        </p>
      </div>

      {/* Step indicator */}
      <div className="mb-6 flex items-center gap-2">
        {[1, 2, 3].map((n) => (
          <div key={n} className="flex items-center gap-2">
            <div
              className={`flex h-7 w-7 items-center justify-center rounded-full font-mono text-[11px] font-semibold ${
                step === n
                  ? "bg-[var(--vf-accent)] text-white"
                  : step > n
                    ? "bg-[var(--vf-c5)] text-white"
                    : "border border-[var(--vf-border)] text-[var(--vf-muted)]"
              }`}
            >
              {n}
            </div>
            {n < 3 && <div className="h-px w-8 bg-[var(--vf-border)]" />}
          </div>
        ))}
        <span className="ml-3 font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
          {step === 1 ? "Idea" : step === 2 ? "Guión" : "Progreso"}
        </span>
      </div>

      {error && <p className="mb-4 text-sm text-[var(--vf-danger)]">{error}</p>}

      {step === 1 && (
        <div className="max-w-2xl rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
          <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
            // Tu idea
          </div>
          <textarea
            value={idea}
            onChange={(e) => setIdea(e.target.value)}
            placeholder="Ej: Los beneficios ocultos de caminar 30 minutos al día"
            className="mb-4 min-h-[100px] w-full resize-y rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--vf-accent)]"
          />

          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                Duración (s)
              </label>
              <input
                type="number"
                min={15}
                max={1200}
                value={dur}
                onChange={(e) => setDur(Number(e.target.value))}
                className="w-full rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--vf-accent)]"
              />
            </div>
            <div>
              <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                Estilo
              </label>
              <select
                value={style}
                onChange={(e) => setStyle(e.target.value)}
                className="w-full rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--vf-accent)]"
              >
                {STYLE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                Tono
              </label>
              <select
                value={tone}
                onChange={(e) => setTone(e.target.value)}
                className="w-full rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--vf-accent)]"
              >
                {TONE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                Audiencia
              </label>
              <input
                type="text"
                value={audience}
                onChange={(e) => setAudience(e.target.value)}
                className="w-full rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--vf-accent)]"
              />
            </div>
          </div>

          <button
            type="button"
            onClick={handleGenerateScript}
            disabled={generatingScript}
            className="w-full rounded-lg bg-[var(--vf-accent)] py-2.5 text-sm font-semibold text-white hover:bg-[var(--vf-accent-hover)] disabled:opacity-50"
          >
            {generatingScript ? "Generando guión…" : "✨ Generar guión"}
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="max-w-2xl">
          <div className="mb-4 rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
            <div className="mb-3 flex items-center justify-between">
              <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                // Guión generado
              </div>
              {scenesInfo && (
                <div className="font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                  {scenesInfo.scenes} escenas · {scenesInfo.words} palabras · {scenesInfo.dur}
                </div>
              )}
            </div>

            <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
              Título
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="mb-3 w-full rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--vf-accent)]"
            />

            <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
              Guión (editable)
            </label>
            <textarea
              value={script}
              onChange={(e) => setScript(e.target.value)}
              className="mb-1 min-h-[240px] w-full resize-y rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 font-mono text-[12px] leading-relaxed outline-none focus:border-[var(--vf-accent)]"
            />
          </div>

          <div className="mb-4 rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
            <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
              // Voz y referencia visual
            </div>

            <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
              Voz
            </label>
            <select
              value={voiceId}
              onChange={(e) => setVoiceId(e.target.value)}
              disabled={voicesLoading}
              className="mb-3 w-full rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--vf-accent)]"
            >
              {voicesLoading && <option>Cargando voces...</option>}
              {!voicesLoading && voices.length === 0 && (
                <option value="">Sin voces disponibles</option>
              )}
              {voices.map((v) => {
                const id = v["ID Voz"] || v.id || v.voice_id;
                const name = v["Nombre Voz"] || v.name || id;
                return (
                  <option key={id} value={id}>
                    {name}
                  </option>
                );
              })}
            </select>

            <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
              Imagen de referencia (opcional)
            </label>
            <div className="relative rounded-lg border border-dashed border-[var(--vf-border)] bg-white/[0.015] p-4 text-center">
              <input
                type="file"
                accept="image/*"
                onChange={handleRefImageChange}
                className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
              />
              <div className="mb-1 text-xl">🖼️</div>
              <div className="font-mono text-[11px] text-[var(--vf-muted)]">
                <strong>Clic o arrastra</strong> una imagen para guiar el estilo visual
              </div>
              {refImageFile && (
                <div className="mt-1 font-mono text-[10px] text-[var(--vf-success)]">
                  {refImageFile.name}
                </div>
              )}
            </div>
          </div>

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setStep(1)}
              className="rounded-lg border border-[var(--vf-border)] bg-white/[0.04] px-4 py-2.5 text-sm font-medium text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
            >
              ← Atrás
            </button>
            <button
              type="button"
              onClick={handleStartAutopilot}
              disabled={starting || !voiceId}
              className="flex-1 rounded-lg py-2.5 text-sm font-semibold text-white disabled:opacity-50"
              style={{ background: "linear-gradient(135deg, var(--vf-c1), var(--vf-c3))" }}
            >
              {starting ? "Iniciando…" : "🚀 Iniciar autopilot"}
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="max-w-2xl">
          <div className="mb-4 rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
            <div className="mb-3 flex items-center justify-between">
              <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                // Progreso del autopilot
              </div>
              {status && (
                <span className="font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                  {status.elapsed != null ? `${status.elapsed}s` : ""}
                </span>
              )}
            </div>

            {!status && (
              <p className="font-mono text-[12px] text-[var(--vf-muted)]">Conectando con el job…</p>
            )}

            {status && (
              <>
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-mono text-[10px] text-[var(--vf-muted)]">
                    {status.current_detail || "Procesando…"}
                  </span>
                  <span className="font-mono text-[10px] text-[var(--vf-muted)]">{progressPct}%</span>
                </div>
                <div className="mb-4 h-2 w-full overflow-hidden rounded-full bg-[var(--vf-surface-2)]">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${progressPct}%`,
                      background: "linear-gradient(90deg, var(--vf-c1), var(--vf-c3))",
                    }}
                  />
                </div>

                <div className="flex flex-col gap-2">
                  {PHASE_ORDER.map((p) => (
                    <div
                      key={p}
                      className="flex items-center justify-between rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2"
                    >
                      <span className="font-mono text-[11px]">{PHASE_LABELS[p]}</span>
                      <PhaseBadge status={status.phases?.[p] || "pending"} />
                    </div>
                  ))}
                </div>

                {status.status === "error" && (
                  <p className="mt-3 text-sm text-[var(--vf-danger)]">
                    {status.error || "El autopilot falló."}
                  </p>
                )}
              </>
            )}
          </div>

          {status && status.images?.length > 0 && (
            <div className="mb-4 rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
              <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                // Galería ({status.images.length})
              </div>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                {status.images.map((src) => (
                  <img
                    key={src}
                    src={src}
                    alt=""
                    className="aspect-video w-full rounded-lg border border-[var(--vf-border)] object-cover"
                  />
                ))}
              </div>
            </div>
          )}

          {status?.status === "done" && (
            <div className="mb-4 rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
              <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-[var(--vf-success)]">
                // Video final
              </div>
              {status.video_url ? (
                <video
                  src={status.video_url}
                  controls
                  className="mb-3 w-full rounded-lg border border-[var(--vf-border)]"
                />
              ) : (
                <p className="mb-3 font-mono text-[11px] text-[var(--vf-muted)]">
                  No se generó un video final (revisa el log de fases).
                </p>
              )}
              <div className="flex flex-wrap gap-3">
                {status.video_dl && (
                  <a
                    href={status.video_dl}
                    className="rounded-lg bg-[var(--vf-accent)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--vf-accent-hover)]"
                  >
                    ⬇ Descargar video
                  </a>
                )}
                <button
                  type="button"
                  onClick={handleAbrirCarpeta}
                  className="rounded-lg border border-[var(--vf-border)] bg-white/[0.04] px-4 py-2 text-sm font-medium text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
                >
                  📁 Abrir carpeta
                </button>
                <button
                  type="button"
                  onClick={handleRestart}
                  className="rounded-lg border border-[var(--vf-border)] bg-white/[0.04] px-4 py-2 text-sm font-medium text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
                >
                  + Nueva idea
                </button>
              </div>
            </div>
          )}

          {status && status.log?.length > 0 && (
            <details className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
              <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                // Log ({status.log.length})
              </summary>
              <ul className="mt-3 space-y-1 font-mono text-[10.5px] text-[var(--vf-muted)]">
                {status.log.map((l, i) => (
                  <li key={i}>{l}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
