import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { Select, SelectOption } from "../components/Select";
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

const DUR_OPTIONS = [
  { value: 60, label: "60 segundos" },
  { value: 90, label: "90 segundos" },
  { value: 120, label: "2 minutos" },
  { value: 180, label: "3 minutos" },
  { value: 300, label: "5 minutos" },
  { value: 600, label: "10 minutos" },
];

const STYLE_OPTIONS = [
  { value: "cinematic", label: "Cinemático" },
  { value: "tutorial", label: "Tutorial / Explainer" },
  { value: "documental", label: "Documental" },
  { value: "viral", label: "Viral / Social Media" },
  { value: "corporativo", label: "Corporativo / B2B" },
];

const TONE_OPTIONS = [
  { value: "inspirador", label: "Inspirador" },
  { value: "profesional", label: "Profesional" },
  { value: "casual", label: "Casual / Cercano" },
  { value: "tecnico", label: "Técnico / Experto" },
  { value: "urgente", label: "Urgente / Impactante" },
];

const AUDIENCE_OPTIONS = [
  { value: "general", label: "Audiencia general" },
  { value: "profesional", label: "Profesionales" },
  { value: "jovenes", label: "Jóvenes (18-30)" },
  { value: "empresarial", label: "Empresarial" },
  { value: "educativo", label: "Estudiantes" },
];

const LOADING_LABELS = [
  "Analizando concepto e idea central...",
  "Estructurando narrativa y arco dramático...",
  "Escribiendo escenas y narración...",
  "Ajustando timing y finalizando guión...",
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

function formatDur(secs?: number): string {
  if (secs == null) return "—";
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return s ? `${m}m ${s}s` : `${m}m`;
}

/** Steps bar shown at the top of the overlay: "1 Tu Idea / 2 Generando / 3 Tu Guión" */
function StepsBar({ step }: { step: number }) {
  const items = [
    { n: 1, label: "Tu Idea" },
    { n: 2, label: "Generando" },
    { n: 3, label: "Tu Guión" },
  ];
  return (
    <div className="mx-auto flex items-center gap-0">
      {items.map((it, idx) => {
        const isActive = step === it.n;
        const isDone = step > it.n;
        return (
          <div key={it.n} className="flex items-center gap-0">
            <div
              className="flex items-center gap-[7px] whitespace-nowrap rounded-full px-3.5 py-[5px] text-[11.5px] font-semibold transition-all"
              style={{
                background: isActive ? "rgba(124,106,255,.18)" : "transparent",
                color: isActive ? "#a89aff" : isDone ? "#4ade80" : "var(--vf-m2)",
              }}
            >
              <div
                className="flex h-[18px] w-[18px] flex-shrink-0 items-center justify-center rounded-full text-[9px] font-extrabold"
                style={{
                  background: isActive
                    ? "#7c6aff"
                    : isDone
                      ? "#22c55e"
                      : "rgba(var(--vf-fg-rgb),.06)",
                  color: isActive ? "#fff" : isDone ? "#000" : "inherit",
                }}
              >
                {it.n}
              </div>
              <span>{it.label}</span>
            </div>
            {idx < items.length - 1 && (
              <div className="h-px w-7 flex-shrink-0" style={{ background: "rgba(var(--vf-fg-rgb),.08)" }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Hero decoration: concentric spinning rings + glow orb, used in step 1. */
function HeroDecoration() {
  return (
    <div
      className="relative flex flex-1 flex-col justify-end overflow-hidden px-10 py-11"
      style={{
        flex: "0 0 38%",
        background: "linear-gradient(145deg,rgba(30,16,80,.95) 0%,rgba(10,6,30,.98) 100%)",
      }}
    >
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 120% 90% at 30% 20%,rgba(124,106,255,.45) 0%,transparent 60%)",
        }}
      />
      <div
        className="xi2v-hero-orb pointer-events-none absolute rounded-full"
        style={{
          width: 280,
          height: 280,
          top: "38%",
          left: "50%",
          background: "radial-gradient(circle,rgba(124,106,255,.35),transparent 70%)",
        }}
      />
      <div
        className="xi2v-ring-1 pointer-events-none absolute rounded-full"
        style={{ width: 160, height: 160, top: "38%", left: "50%", border: "1px solid rgba(124,106,255,.2)" }}
      >
        <div
          className="absolute rounded-full"
          style={{
            width: 7,
            height: 7,
            top: -3.5,
            left: "50%",
            transform: "translateX(-50%)",
            background: "#7c6aff",
            boxShadow: "0 0 10px rgba(124,106,255,.9)",
          }}
        />
      </div>
      <div
        className="xi2v-ring-2 pointer-events-none absolute rounded-full"
        style={{
          width: 240,
          height: 240,
          top: "38%",
          left: "50%",
          border: "1px solid rgba(124,106,255,.2)",
          opacity: 0.5,
        }}
      />
      <div
        className="xi2v-ring-3 pointer-events-none absolute rounded-full"
        style={{
          width: 340,
          height: 340,
          top: "38%",
          left: "50%",
          border: "1px solid rgba(124,106,255,.2)",
          opacity: 0.3,
        }}
      />

      <div className="relative z-[1] mb-2.5 text-[10px] font-bold uppercase tracking-[.18em]" style={{ color: "rgba(124,106,255,.75)" }}>
        VideoForge AI Studio
      </div>
      <div className="relative z-[1] mb-2.5 text-[28px] font-black leading-[1.15]" style={{ color: "#eeeef5" }}>
        De idea a
        <br />
        <span style={{ color: "#7c6aff" }}>video</span>
        <br />
        profesional
      </div>
      {/* Texto fijo claro: el fondo de este panel es siempre morado oscuro,
          no sigue el tema del sitio (ver el gradiente en el div padre). */}
      <p className="relative z-[1] text-[13px] leading-relaxed" style={{ color: "rgba(238,238,245,.38)" }}>
        Escribe tu concepto. La IA genera el guión completo, listo para el pipeline de producción.
      </p>
    </div>
  );
}

/** Spinning orb decoration used in the step-2 loading state. */
function LoadingOrb() {
  return (
    <div className="relative" style={{ width: 100, height: 100 }}>
      <div
        className="absolute rounded-full"
        style={{
          width: 42,
          height: 42,
          top: "50%",
          left: "50%",
          transform: "translate(-50%,-50%)",
          background: "linear-gradient(135deg,#7c6aff,#5b42f3)",
          boxShadow: "0 0 28px rgba(124,106,255,.55)",
        }}
      />
      <div
        className="xi2v-orb-ring absolute inset-0 rounded-full"
        style={{ border: "2px solid rgba(124,106,255,.35)" }}
      >
        <div
          className="absolute rounded-full"
          style={{
            width: 7,
            height: 7,
            top: -3.5,
            left: "50%",
            transform: "translateX(-50%)",
            background: "#a089ff",
          }}
        />
      </div>
      <div
        className="xi2v-orb-ring-slow absolute rounded-full"
        style={{ inset: -16, border: "2px solid rgba(124,106,255,.15)" }}
      />
    </div>
  );
}

function StatBox({ value, label, wide }: { value: string | number; label: string; wide?: boolean }) {
  return (
    <div
      className="rounded-lg border px-3 py-[11px]"
      style={{
        background: "var(--vf-s)",
        borderColor: "rgba(var(--vf-fg-rgb),.05)",
        gridColumn: wide ? "1 / -1" : undefined,
      }}
    >
      <div className="text-[19px] font-black" style={{ color: "var(--vf-text)" }}>
        {value}
      </div>
      <div className="mt-0.5 text-[9.5px] font-bold uppercase tracking-[.08em]" style={{ color: "var(--vf-m2)" }}>
        {label}
      </div>
    </div>
  );
}

function PipelineStep({ icon, label, active }: { icon: string; label: string; active: boolean }) {
  return (
    <div
      className="flex items-center gap-[9px] py-[5px] text-xs"
      style={{ color: active ? "var(--vf-text)" : "var(--vf-m2)" }}
    >
      <div
        className="flex h-[22px] w-[22px] flex-shrink-0 items-center justify-center rounded-[6px] text-[10px]"
        style={{
          background: active ? "rgba(124,106,255,.25)" : "rgba(var(--vf-fg-rgb),.04)",
          color: active ? "#a089ff" : "inherit",
        }}
      >
        {icon}
      </div>
      {label}
    </div>
  );
}

function PhaseRow({ label, status }: { label: string; status: string }) {
  const iconMap: Record<string, { icon: string; bg: string; color: string; glow?: boolean }> = {
    pending: { icon: "·", bg: "rgba(var(--vf-fg-rgb),.04)", color: "var(--vf-m2)" },
    active: { icon: "●", bg: "rgba(124,106,255,.25)", color: "#a089ff", glow: true },
    done: { icon: "✓", bg: "rgba(34,197,94,.15)", color: "#22c55e" },
    skip: { icon: "–", bg: "rgba(var(--vf-fg-rgb),.03)", color: "var(--vf-m2)" },
    partial: { icon: "◐", bg: "rgba(251,191,36,.1)", color: "#fbbf24" },
    error: { icon: "✕", bg: "rgba(239,68,68,.15)", color: "#f87171" },
  };
  const info = iconMap[status] || iconMap.pending;
  const rowColor = status === "active" ? "var(--vf-text)" : status === "done" || status === "skip" ? "var(--vf-m)" : "var(--vf-m2)";
  return (
    <div
      className="mb-[3px] flex items-center gap-[11px] rounded-[10px] px-[11px] py-2.5 text-[12.5px] transition-all"
      style={{
        background: status === "active" ? "rgba(124,106,255,.07)" : "transparent",
        color: rowColor,
      }}
    >
      <div
        className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-[11px] font-extrabold ${
          status === "active" ? "xi2v-blink" : ""
        }`}
        style={{
          background: info.bg,
          color: info.color,
          boxShadow: info.glow ? "0 0 10px rgba(124,106,255,.5)" : "none",
        }}
      >
        {info.icon}
      </div>
      <span>{label}</span>
    </div>
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
  const [renderMode, setRenderMode] = useState<"rapido" | "profesional">("rapido");

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

  function handleClearRefImage() {
    setRefImageFile(null);
    setRefImageBase64(null);
  }

  async function handleGenerateScript() {
    if (!idea.trim()) {
      setError("Escribe una idea primero.");
      return;
    }
    setError("");
    setGeneratingScript(true);
    setStep(2);
    try {
      const data = await generateScript({ idea, dur, style, tone, audience });
      if (!data.ok) {
        setError(data.error || "No se pudo generar el guión.");
        setStep(1);
        return;
      }
      setScript(data.script || "");
      setTitle(data.title || idea.slice(0, 60));
      setScenesInfo({ scenes: data.scenes, words: data.words, dur: data.dur });
      setStep(3);
    } catch (err) {
      setError((err as Error).message);
      setStep(1);
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
        mode: renderMode,
      });
      if (data.error) {
        setError(data.error);
        return;
      }
      setJobId(data.job_id);
      setStatus(null);
      setStep(4);
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
  const modeHint =
    renderMode === "profesional"
      ? "WhisperX + render profesional (más lento)"
      : "Slideshow rápido con FFmpeg";

  // Steps-bar step (1 = idea, 2 = generando, 3 = guión) collapses our internal
  // step 3 (script review) and step 4 (execution) both onto steps-bar position 3,
  // since the reference design hands off script review -> a separate execution HUD,
  // but our data/flow keeps them as one screen after generation.
  const barStep = step >= 3 ? 3 : step;

  return (
    <div className="-mx-6 -mb-6 flex min-h-[640px] flex-col overflow-hidden sm:-mx-8 sm:-mb-8" style={{ background: "var(--vf-bg)" }}>
      <style>{`
        @keyframes xi2vPulse{0%,100%{opacity:.5;transform:translate(-50%,-50%) scale(.95)}50%{opacity:1;transform:translate(-50%,-50%) scale(1.1)}}
        @keyframes xi2vSpin{from{transform:translate(-50%,-50%) rotate(0)}to{transform:translate(-50%,-50%) rotate(360deg)}}
        @keyframes xi2vSpinRev{from{transform:translate(-50%,-50%) rotate(360deg)}to{transform:translate(-50%,-50%) rotate(0)}}
        @keyframes xi2vBlink{0%,100%{opacity:.3}50%{opacity:1}}
        .xi2v-hero-orb{animation:xi2vPulse 3.5s ease-in-out infinite}
        .xi2v-ring-1{animation:xi2vSpin 5s linear infinite}
        .xi2v-ring-2{animation:xi2vSpinRev 8s linear infinite}
        .xi2v-ring-3{animation:xi2vSpin 12s linear infinite}
        .xi2v-orb-ring{animation:xi2vSpin 2.2s linear infinite}
        .xi2v-orb-ring-slow{animation:xi2vSpinRev 4s linear infinite}
        .xi2v-blink{animation:xi2vBlink 1s infinite}
        .xi2v-ta:focus, .xi2v-sel:focus, .xi2v-vsel:focus{border-color:rgba(124,106,255,.45) !important;}
      `}</style>

      {/* Top bar: back-style eyebrow + steps bar + badge */}
      <div
        className="flex flex-shrink-0 items-center gap-4 border-b px-6 py-3.5"
        style={{ borderColor: "rgba(124,106,255,.13)", background: "var(--vf-s)" }}
      >
        <span className="font-mono text-[13px]" style={{ color: "var(--vf-m)" }}>
          Idea → Video
        </span>
        <StepsBar step={barStep} />
        <span
          className="ml-auto text-[10px] font-bold uppercase tracking-[.15em]"
          style={{ color: "rgba(124,106,255,.6)" }}
        >
          Idea → Video
        </span>
      </div>

      {error && (
        <p className="px-6 pt-3 text-sm" style={{ color: "var(--vf-danger)" }}>
          {error}
        </p>
      )}

      {/* Step 1 — hero + idea form */}
      {step === 1 && (
        <div className="flex flex-1 overflow-hidden">
          <HeroDecoration />
          <div className="flex-1 overflow-y-auto px-12 py-9">
            <div className="mb-1 text-[21px] font-extrabold" style={{ color: "var(--vf-text)" }}>
              ¿Cuál es tu idea?
            </div>
            <p className="mb-6 text-[13px] leading-relaxed" style={{ color: "var(--vf-m)" }}>
              Describe tu concepto con el mayor detalle posible. Mientras más contexto des, mejor será el
              guión.
            </p>

            <label className="mb-[7px] block text-[10.5px] font-bold uppercase tracking-[.1em]" style={{ color: "var(--vf-m)" }}>
              Concepto
            </label>
            <textarea
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
              rows={4}
              placeholder="Ej: Un video sobre cómo la inteligencia artificial está transformando la medicina..."
              className="xi2v-ta w-full resize-y rounded-[10px] border-[1.5px] px-[15px] py-[13px] text-sm outline-none transition-colors"
              style={{ background: "var(--vf-s)", borderColor: "rgba(var(--vf-fg-rgb),.07)", color: "var(--vf-text)", minHeight: 108 }}
            />

            <div className="mt-[18px] grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="flex flex-col">
                <label className="mb-[7px] block text-[10.5px] font-bold uppercase tracking-[.1em]" style={{ color: "var(--vf-m)" }}>
                  Duración
                </label>
                <Select
                  value={dur}
                  onChange={(v) => setDur(Number(v))}
                  className="xi2v-sel rounded-lg border-[1.5px] px-3 py-2 text-[13px] outline-none"
                  style={{ background: "var(--vf-s)", borderColor: "rgba(var(--vf-fg-rgb),.07)", color: "var(--vf-text)" }}
                >
                  {DUR_OPTIONS.map((o) => (
                    <SelectOption key={o.value} value={o.value}>
                      {o.label}
                    </SelectOption>
                  ))}
                </Select>
              </div>
              <div className="flex flex-col">
                <label className="mb-[7px] block text-[10.5px] font-bold uppercase tracking-[.1em]" style={{ color: "var(--vf-m)" }}>
                  Estilo
                </label>
                <Select
                  value={style}
                  onChange={(v) => setStyle(v)}
                  className="xi2v-sel rounded-lg border-[1.5px] px-3 py-2 text-[13px] outline-none"
                  style={{ background: "var(--vf-s)", borderColor: "rgba(var(--vf-fg-rgb),.07)", color: "var(--vf-text)" }}
                >
                  {STYLE_OPTIONS.map((o) => (
                    <SelectOption key={o.value} value={o.value}>
                      {o.label}
                    </SelectOption>
                  ))}
                </Select>
              </div>
              <div className="flex flex-col">
                <label className="mb-[7px] block text-[10.5px] font-bold uppercase tracking-[.1em]" style={{ color: "var(--vf-m)" }}>
                  Tono
                </label>
                <Select
                  value={tone}
                  onChange={(v) => setTone(v)}
                  className="xi2v-sel rounded-lg border-[1.5px] px-3 py-2 text-[13px] outline-none"
                  style={{ background: "var(--vf-s)", borderColor: "rgba(var(--vf-fg-rgb),.07)", color: "var(--vf-text)" }}
                >
                  {TONE_OPTIONS.map((o) => (
                    <SelectOption key={o.value} value={o.value}>
                      {o.label}
                    </SelectOption>
                  ))}
                </Select>
              </div>
              <div className="flex flex-col">
                <label className="mb-[7px] block text-[10.5px] font-bold uppercase tracking-[.1em]" style={{ color: "var(--vf-m)" }}>
                  Audiencia
                </label>
                <Select
                  value={audience}
                  onChange={(v) => setAudience(v)}
                  className="xi2v-sel rounded-lg border-[1.5px] px-3 py-2 text-[13px] outline-none"
                  style={{ background: "var(--vf-s)", borderColor: "rgba(var(--vf-fg-rgb),.07)", color: "var(--vf-text)" }}
                >
                  {AUDIENCE_OPTIONS.map((o) => (
                    <SelectOption key={o.value} value={o.value}>
                      {o.label}
                    </SelectOption>
                  ))}
                </Select>
              </div>
            </div>

            <button
              type="button"
              onClick={handleGenerateScript}
              disabled={generatingScript}
              className="mt-6 flex w-full items-center justify-center gap-2.5 rounded-[10px] py-3.5 text-[14.5px] font-bold text-white transition-transform disabled:opacity-50"
              style={{ background: "linear-gradient(135deg,#7c6aff 0%,#5b42f3 100%)" }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 4V2M15 16v-2M8 9h2M20 9h2M17.8 11.8 19 13M17.8 6.2 19 5M3 21l9-9M12.2 6.2 11 5" />
              </svg>
              {generatingScript ? "Generando guión…" : "Generar guión con IA"}
            </button>
          </div>
        </div>
      )}

      {/* Step 2 — loading state: spinning orb + sequential checklist */}
      {step === 2 && (
        <div className="flex flex-1 flex-col items-center justify-center gap-9">
          <LoadingOrb />
          <div className="flex min-w-[270px] flex-col gap-2">
            {LOADING_LABELS.map((label, i) => (
              <div
                key={label}
                className="flex items-center gap-3 rounded-lg px-3.5 py-2.5 text-[13px] transition-all"
                style={{
                  background: i === 0 ? "rgba(124,106,255,.1)" : "transparent",
                  color: i === 0 ? "var(--vf-text)" : "var(--vf-m2)",
                }}
              >
                <div
                  className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${i === 0 ? "xi2v-blink" : ""}`}
                  style={{
                    background: i === 0 ? "#7c6aff" : "var(--vf-m2)",
                    boxShadow: i === 0 ? "0 0 8px rgba(124,106,255,.8)" : "none",
                  }}
                />
                {label}
              </div>
            ))}
          </div>
          <div className="text-xs" style={{ color: "var(--vf-m2)" }}>
            Esto tarda entre 3 y 15 segundos
          </div>
        </div>
      )}

      {/* Step 3 — script review: editable script + meta column */}
      {step === 3 && (
        <div className="flex flex-1 overflow-hidden">
          <div className="flex flex-1 flex-col overflow-hidden border-r px-8 py-7" style={{ borderColor: "rgba(var(--vf-fg-rgb),.05)" }}>
            <div className="mb-2.5 text-[10px] font-bold uppercase tracking-[.1em]" style={{ color: "var(--vf-m)" }}>
              Guión generado — puedes editarlo antes de continuar
            </div>
            <textarea
              value={script}
              onChange={(e) => setScript(e.target.value)}
              className="flex-1 resize-none overflow-y-auto rounded-[10px] border p-[15px] text-[12.5px] leading-[1.75] outline-none"
              style={{
                background: "var(--vf-bg)",
                borderColor: "rgba(var(--vf-fg-rgb),.06)",
                color: "var(--vf-text)",
                fontFamily: "ui-monospace, monospace",
              }}
            />
          </div>

          <div className="flex w-[300px] flex-shrink-0 flex-col gap-4 overflow-y-auto px-6 py-7">
            <div>
              <label className="mb-[7px] block text-[9.5px] font-bold uppercase tracking-[.12em]" style={{ color: "var(--vf-m2)" }}>
                Título sugerido
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full rounded-lg border bg-transparent px-2.5 py-1.5 text-[15px] font-extrabold outline-none"
                style={{ borderColor: "transparent", color: "var(--vf-text)" }}
                onFocus={(e) => (e.currentTarget.style.borderColor = "rgba(124,106,255,.4)")}
                onBlur={(e) => (e.currentTarget.style.borderColor = "transparent")}
              />
            </div>

            <div className="grid grid-cols-2 gap-[7px]">
              <StatBox value={scenesInfo?.scenes ?? "—"} label="Escenas" />
              <StatBox value={formatDur(scenesInfo?.dur)} label="Duración" />
              <StatBox value={scenesInfo?.words ?? "—"} label="Palabras" wide />
            </div>

            <div className="h-px" style={{ background: "rgba(var(--vf-fg-rgb),.05)" }} />

            <div>
              <div className="mb-[7px] text-[9.5px] font-bold uppercase tracking-[.12em]" style={{ color: "var(--vf-m2)" }}>
                Voz narradora <span className="font-normal" style={{ fontSize: 10, color: "var(--vf-m2)" }}>(opcional)</span>
              </div>
              <Select
                value={voiceId}
                onChange={(v) => setVoiceId(v)}
                disabled={voicesLoading}
                className="xi2v-vsel w-full rounded-lg border px-2.5 py-[7px] text-xs outline-none"
                style={{ background: "var(--vf-s)", borderColor: "rgba(var(--vf-fg-rgb),.1)", color: "var(--vf-text)" }}
              >
                {voicesLoading && <SelectOption value="">Cargando voces...</SelectOption>}
                {!voicesLoading && voices.length === 0 && <SelectOption value="">Sin voces disponibles</SelectOption>}
                {voices.map((v) => {
                  const id = v["ID Voz"] || v.id || v.voice_id;
                  const name = v["Nombre Voz"] || v.name || id;
                  return (
                    <SelectOption key={id} value={id || ""}>
                      {name}
                    </SelectOption>
                  );
                })}
              </Select>
            </div>

            <div>
              <div className="mb-[7px] text-[9.5px] font-bold uppercase tracking-[.12em]" style={{ color: "var(--vf-m2)" }}>
                Imagen de referencia <span className="font-normal" style={{ fontSize: 10, color: "var(--vf-m2)" }}>(opcional)</span>
              </div>
              {!refImageFile ? (
                <label
                  className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-all"
                  style={{ color: "#a089ff", background: "rgba(124,106,255,.1)", borderColor: "rgba(124,106,255,.3)" }}
                >
                  📎 Adjuntar imagen
                  <input type="file" accept="image/*" onChange={handleRefImageChange} className="hidden" />
                </label>
              ) : (
                <div className="mt-2 flex items-center gap-2">
                  {refImageBase64 && (
                    <img
                      src={`data:image/*;base64,${refImageBase64}`}
                      alt=""
                      className="h-14 w-20 rounded-md border object-cover"
                      style={{ borderColor: "rgba(124,106,255,.3)" }}
                    />
                  )}
                  <button
                    type="button"
                    onClick={handleClearRefImage}
                    className="bg-transparent text-[11px]"
                    style={{ color: "var(--vf-m)" }}
                  >
                    ✕ Quitar
                  </button>
                </div>
              )}
            </div>

            <div>
              <div className="mb-[7px] text-[9.5px] font-bold uppercase tracking-[.12em]" style={{ color: "var(--vf-m2)" }}>
                Modo de render
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setRenderMode("rapido")}
                  className="rounded-lg border px-3.5 py-1.5 text-[11.5px] font-semibold transition-all"
                  style={
                    renderMode === "rapido"
                      ? { background: "rgba(124,106,255,.2)", color: "var(--vf-text)", borderColor: "rgba(124,106,255,.5)" }
                      : { background: "rgba(var(--vf-fg-rgb),.04)", color: "var(--vf-m)", borderColor: "rgba(124,106,255,.25)" }
                  }
                >
                  ⚡ Rápido
                </button>
                <button
                  type="button"
                  onClick={() => setRenderMode("profesional")}
                  className="rounded-lg border px-3.5 py-1.5 text-[11.5px] font-semibold transition-all"
                  style={
                    renderMode === "profesional"
                      ? { background: "rgba(124,106,255,.2)", color: "var(--vf-text)", borderColor: "rgba(124,106,255,.5)" }
                      : { background: "rgba(var(--vf-fg-rgb),.04)", color: "var(--vf-m)", borderColor: "rgba(124,106,255,.25)" }
                  }
                >
                  🎬 Profesional
                </button>
              </div>
              <div className="mt-[5px] text-[10px]" style={{ color: "var(--vf-m2)" }}>
                {modeHint}
              </div>
            </div>

            <div className="rounded-[10px] border px-4 py-3.5" style={{ background: "var(--vf-s)", borderColor: "rgba(var(--vf-fg-rgb),.05)" }}>
              <div className="mb-2.5 text-[9.5px] font-bold uppercase tracking-[.12em]" style={{ color: "var(--vf-m2)" }}>
                Flujo de producción
              </div>
              <PipelineStep icon="✎" label="Guión" active />
              <div className="ml-1.5 my-0.5 text-[8px]" style={{ color: "var(--vf-m2)" }}>↓</div>
              <PipelineStep icon="▢" label="Imágenes" active={false} />
              <div className="ml-1.5 my-0.5 text-[8px]" style={{ color: "var(--vf-m2)" }}>↓</div>
              <PipelineStep icon="♪" label="Voz" active={false} />
              <div className="ml-1.5 my-0.5 text-[8px]" style={{ color: "var(--vf-m2)" }}>↓</div>
              <PipelineStep icon="▶" label="Video" active={false} />
              <div className="ml-1.5 my-0.5 text-[8px]" style={{ color: "var(--vf-m2)" }}>↓</div>
              <PipelineStep icon="★" label="Render" active={false} />
            </div>

            <button
              type="button"
              onClick={handleStartAutopilot}
              disabled={starting || !voiceId}
              className="w-full rounded-[10px] py-[13px] text-[13.5px] font-bold text-white transition-transform disabled:opacity-50"
              style={{ background: "linear-gradient(135deg,#7c6aff,#5b42f3)" }}
            >
              {starting ? "Iniciando…" : "▶ Generar Video Automático"}
            </button>
            <button
              type="button"
              onClick={() => setStep(1)}
              className="w-full rounded-[10px] border py-[9px] text-[12.5px] transition-all"
              style={{ background: "transparent", borderColor: "rgba(var(--vf-fg-rgb),.08)", color: "var(--vf-m)" }}
            >
              ↺ Regenerar
            </button>
          </div>
        </div>
      )}

      {/* Step 4 — execution HUD: phases list, image gallery, video player, log */}
      {step === 4 && (
        <div className="flex flex-1 overflow-hidden">
          <div className="flex flex-1 overflow-hidden">
            <div className="w-[240px] flex-shrink-0 overflow-y-auto border-r px-3.5 py-[22px]" style={{ borderColor: "rgba(var(--vf-fg-rgb),.05)", background: "rgba(0,0,0,.2)" }}>
              <div className="mb-3.5 text-[9px] font-bold uppercase tracking-[.14em]" style={{ color: "var(--vf-m2)" }}>
                Fases del pipeline
              </div>
              {PHASE_ORDER.map((p) => (
                <PhaseRow key={p} label={PHASE_LABELS[p]} status={status?.phases?.[p] || "pending"} />
              ))}
            </div>

            <div className="flex flex-1 flex-col gap-4 overflow-hidden px-6 py-[22px]">
              <div
                className="flex flex-shrink-0 items-center gap-3.5 rounded-xl border px-[17px] py-[13px]"
                style={{ background: "rgba(124,106,255,.08)", borderColor: "rgba(124,106,255,.2)" }}
              >
                <div className="flex-shrink-0 text-xl">⚡</div>
                <div className="min-w-0 flex-1">
                  <div className="text-[13.5px] font-bold" style={{ color: "var(--vf-text)" }}>
                    {title || "Autopilot"}
                  </div>
                  <div className="overflow-hidden text-ellipsis whitespace-nowrap text-[11.5px]" style={{ color: "var(--vf-m)" }}>
                    {status?.current_detail || "Procesando…"}
                  </div>
                </div>
                <div
                  className="flex-shrink-0 rounded-md px-2 py-1 text-[11px] font-bold"
                  style={{ background: "rgba(var(--vf-fg-rgb),.04)", color: "var(--vf-m)", fontVariantNumeric: "tabular-nums" }}
                >
                  {status?.elapsed != null ? `${status.elapsed}s` : "0s"} · {progressPct}%
                </div>
              </div>

              <div className="flex-shrink-0 text-[11.5px] font-bold" style={{ color: "var(--vf-m)" }}>
                Imágenes ({status?.images?.length || 0}/{scenesInfo?.scenes || 0})
              </div>

              {!status?.images?.length ? (
                <div className="flex-shrink-0 py-3 text-[12.5px] italic" style={{ color: "var(--vf-m2)" }}>
                  Las imágenes aparecerán conforme se generen...
                </div>
              ) : (
                <div className="grid flex-1 gap-2 overflow-y-auto" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))" }}>
                  {status.images.map((src) => (
                    <img
                      key={src}
                      src={src}
                      alt=""
                      className="w-full rounded-lg border object-cover"
                      style={{ aspectRatio: "16/9", borderColor: "rgba(var(--vf-fg-rgb),.06)" }}
                    />
                  ))}
                </div>
              )}

              {status?.status === "done" && (
                <div
                  className="flex flex-shrink-0 flex-col gap-2.5 rounded-[10px] border px-4 py-3"
                  style={{ background: "rgba(34,197,94,.07)", borderColor: "rgba(34,197,94,.2)" }}
                >
                  {status.video_url && (
                    <video
                      src={status.video_url}
                      controls
                      className="w-full rounded-lg"
                      style={{ maxHeight: 420, background: "#000" }}
                    />
                  )}
                  <div className="flex w-full items-center gap-2.5">
                    <span className="flex-1 text-xs font-bold" style={{ color: "#4ade80" }}>
                      ✓ Video listo
                    </span>
                    {status.video_dl && (
                      <a
                        href={status.video_dl}
                        download
                        className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-bold text-white no-underline"
                        style={{ background: "linear-gradient(135deg,#22c55e,#16a34a)" }}
                      >
                        ↓ Descargar
                      </a>
                    )}
                    <button
                      type="button"
                      onClick={handleAbrirCarpeta}
                      className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-bold"
                      style={{ background: "rgba(var(--vf-fg-rgb),.06)", border: "1px solid rgba(var(--vf-fg-rgb),.12)", color: "var(--vf-text)" }}
                    >
                      📁 Abrir carpeta
                    </button>
                    <button
                      type="button"
                      onClick={handleRestart}
                      className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-bold"
                      style={{ background: "rgba(var(--vf-fg-rgb),.06)", border: "1px solid rgba(var(--vf-fg-rgb),.12)", color: "var(--vf-text)" }}
                    >
                      + Nueva idea
                    </button>
                  </div>
                </div>
              )}

              {status?.status === "error" && (
                <p className="flex-shrink-0 text-sm" style={{ color: "var(--vf-danger)" }}>
                  {status.error || "El autopilot falló."}
                </p>
              )}

              {status && status.log?.length > 0 && (
                <details className="flex-shrink-0 border-t pt-2.5" style={{ borderColor: "rgba(var(--vf-fg-rgb),.05)" }}>
                  <summary className="cursor-pointer text-[11px]" style={{ color: "var(--vf-m2)" }}>
                    Registro de ejecución
                  </summary>
                  <div className="max-h-[100px] overflow-y-auto pt-1.5">
                    {status.log.map((l, i) => (
                      <div key={i} className="py-[1.5px] text-[10.5px]" style={{ color: "var(--vf-m2)", fontFamily: "ui-monospace, monospace" }}>
                        {l}
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
