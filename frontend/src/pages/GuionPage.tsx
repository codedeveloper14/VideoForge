import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { analyzeImage, loadScript, n8nProxy, saveScript } from "../api/script";
import type { N8nProxyResult } from "../api/script";
import { PipelineStepper } from "../components/PipelineStepper";
import { GuionHeaderArt } from "../components/GuionHeaderArt";
import { useGenerationStatus } from "../context/GenerationStatusContext";

type ActivePanel = "prompts" | "guion";
type PromptMode = "general" | "stick" | "ultrarealismo";

const PROMPT_MODE_LABELS: Record<PromptMode, string> = {
  general: "General",
  stick: "Stick Animado",
  ultrarealismo: "Ultrarrealismo",
};

export default function GuionPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [project, setProject] = useState(searchParams.get("project") || "");

  const [guion, setGuion] = useState("");
  const [outputMode, setOutputMode] = useState("con_prompts");
  const [promptMode, setPromptMode] = useState<PromptMode>("general");
  const [promptStyle, setPromptStyle] = useState<"default" | "history">("default");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [saveStatus, setSaveStatus] = useState("");

  const [result, setResult] = useState<N8nProxyResult | null>(null);
  const [activePanel, setActivePanel] = useState<ActivePanel>("prompts");

  const [refImage, setRefImage] = useState("");
  const [refName, setRefName] = useState("");
  const [refDescription, setRefDescription] = useState("");
  const [refAnalyzing, setRefAnalyzing] = useState(false);
  const refInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const genStatus = useGenerationStatus();

  useEffect(() => {
    if (project) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("project", project);
        return next;
      });
    }
  }, [project]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const fromUrl = searchParams.get("project") || "";
    setProject((prev) => (fromUrl && fromUrl !== prev ? fromUrl : prev));
  }, [searchParams]);

  useEffect(() => {
    if (!project) return;
    loadScript(project)
      .then((data) => {
        if (data?.existe) setGuion(data.texto || "");
      })
      .catch((err: Error) => setError(err.message));
  }, [project]);

  const charCount = guion.length;
  const fragEstimate = Math.max(1, Math.ceil(charCount / 1820));
  const wordCount = guion.trim() ? guion.trim().split(/\s+/).length : 0;
  const lineCount = guion.split("\n").length;
  const lineNumbers = useMemo(
    () => Array.from({ length: lineCount }, (_, i) => i + 1).join("\n"),
    [lineCount],
  );

  const estimatedDuration = (() => {
    const totalSeconds = fragEstimate * 6;
    if (!guion.trim()) return "—";
    if (totalSeconds < 60) return `${totalSeconds}s`;
    return `${Math.floor(totalSeconds / 60)}m ${totalSeconds % 60}s`;
  })();

  const estimatedReadTime = (() => {
    if (!wordCount) return "—";
    const seconds = Math.round((wordCount / 150) * 60);
    if (seconds < 60) return `${seconds}s`;
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  })();

  const complexity = (() => {
    if (!guion.trim()) return { label: "—", pct: 0 };
    const sentences = guion.split(/[.!?]+/).filter((s) => s.trim());
    const avgWordsPerSentence = sentences.length ? wordCount / sentences.length : 0;
    if (avgWordsPerSentence < 12) return { label: "Baja", pct: 30 };
    if (avgWordsPerSentence < 22) return { label: "Media", pct: 62 };
    return { label: "Alta", pct: 90 };
  })();

  function extractText(res: N8nProxyResult | string | null, keys: string[]): string {
    if (!res) return "";
    if (typeof res === "string") return res;
    for (const k of keys) {
      const val = res[k];
      if (typeof val === "string") return val;
    }
    return JSON.stringify(res, null, 2);
  }

  const promptsText = result
    ? extractText(result, ["prompts", "prompts_texto", "output", "resultado", "texto_prompts"])
    : "";
  const guionOutText = result
    ? extractText(result, ["guion", "guion_con_saltos", "guion_texto", "texto"])
    : "";

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!guion.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);
    genStatus.start("guion:" + (project || "sin-proyecto"), "Guión", "Generando escenas y prompts...");
    try {
      const data = await n8nProxy({
        guion,
        outputMode,
        promptMode,
        promptStyle: promptMode === "stick" ? promptStyle : "default",
        descripcionReferencia: refDescription,
      });
      setResult(data);
      setActivePanel("prompts");
      genStatus.finish("guion:" + (project || "sin-proyecto"), true, "Guión procesado.");
    } catch (err) {
      setError((err as Error).message);
      genStatus.finish("guion:" + (project || "sin-proyecto"), false, (err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveScript() {
    if (!project) {
      setError("Selecciona un proyecto antes de guardar.");
      return;
    }
    setSaveStatus("Guardando…");
    setError("");
    try {
      await saveScript(project, guion, promptsText || "");
      setSaveStatus("Guardado ✓");
      setTimeout(() => setSaveStatus(""), 2500);
    } catch (err) {
      setError((err as Error).message);
      setSaveStatus("");
    }
  }

  function copyActive() {
    const text = activePanel === "prompts" ? promptsText : guionOutText;
    if (text) navigator.clipboard.writeText(text);
  }

  function handleRefFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      const dataUrl = reader.result as string;
      const base64 = dataUrl.split(",")[1] || "";
      const mime = file.type || "image/png";
      setRefImage(dataUrl);
      setRefName(file.name);
      setRefAnalyzing(true);
      try {
        const analysis = await analyzeImage(base64, mime);
        const desc = typeof analysis.descripcion_completa === "string" ? analysis.descripcion_completa : "";
        setRefDescription(desc);
      } catch {
        setRefDescription("");
      } finally {
        setRefAnalyzing(false);
      }
    };
    reader.readAsDataURL(file);
  }

  function clearRefImage() {
    setRefImage("");
    setRefName("");
    setRefDescription("");
    if (refInputRef.current) refInputRef.current.value = "";
  }

  function notImplemented() {
    alert("Próximamente.");
  }

  function syncLineScroll() {
    const lineEl = document.getElementById("vf-line-nums-el");
    if (lineEl && textareaRef.current) lineEl.scrollTop = textareaRef.current.scrollTop;
  }

  return (
    <div>
      {project && <PipelineStepper project={project} current="guion" />}

      {/* Header */}
      <div
        className="relative mb-3.5 flex items-center justify-between overflow-hidden rounded-2xl border border-[rgba(124,106,255,.2)] px-9 py-[30px]"
        style={{
          gap: 28,
          background: "linear-gradient(135deg,rgba(var(--vf-bg-rgb),.97),rgba(var(--vf-bg-rgb),.99))",
          boxShadow: "0 12px 36px rgba(0,0,0,.3),inset 0 1px 0 rgba(var(--vf-fg-rgb),.05)",
        }}
      >
        <div
          className="pointer-events-none absolute inset-0 rounded-2xl"
          style={{ background: "radial-gradient(ellipse at 15% 55%,rgba(124,106,255,.1),transparent 55%)" }}
        />
        <div className="relative z-[1] min-w-0 flex-1">
          <div className="mb-2.5 flex items-center gap-3.5">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[10px] border border-[rgba(124,106,255,.3)]" style={{ background: "linear-gradient(135deg,rgba(124,106,255,.22),rgba(192,38,211,.12))" }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--vf-c2)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
                <line x1="10" y1="9" x2="8" y2="9" />
              </svg>
            </div>
            <div className="min-w-0">
              <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "rgba(124,106,255,.6)" }}>
                Pipeline · Producción IA
              </div>
              <h1 className="text-[26px] font-bold leading-[1.1] tracking-[-0.025em] text-[var(--vf-text)]">
                Guión{" "}
                <span
                  className="bg-clip-text text-transparent"
                  style={{ backgroundImage: "linear-gradient(90deg,var(--vf-c2),var(--vf-c3))" }}
                >
                  y Escenas
                </span>
              </h1>
            </div>
            <div className="ml-auto flex flex-shrink-0 flex-col items-end gap-[5px]">
              <span className="rounded-md border border-[rgba(124,106,255,.22)] bg-[rgba(124,106,255,.1)] px-2 py-1 text-[9px] font-bold uppercase tracking-[0.1em] text-[var(--vf-c2)]">
                Módulo 01
              </span>
              <span className="rounded-md border border-[rgba(var(--vf-fg-rgb),.08)] bg-[rgba(var(--vf-fg-rgb),.04)] px-2 py-1 text-[9px] font-semibold tracking-[0.06em] text-[var(--vf-m2)]">
                Paso 1 de 5
              </span>
            </div>
          </div>
          <p className="mb-3.5 max-w-[560px] text-[13.5px] leading-[1.55]" style={{ color: "var(--vf-m)" }}>
            Escribe tu guión completo y divídelo en escenas estructuradas para el pipeline de producción IA.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {["✂  Escenas", "🤖  Asistente IA", "🌐  Traducción", "↔  Expansión", "⚡  Análisis"].map((chip, i) => (
              <span
                key={chip}
                className={
                  "rounded-[7px] border px-[11px] py-1 text-[11px] font-medium transition-colors " +
                  (i === 0
                    ? "border-[rgba(124,106,255,.35)] bg-[rgba(124,106,255,.16)] text-[var(--vf-c2)]"
                    : "border-[rgba(124,106,255,.16)] bg-[rgba(124,106,255,.05)] text-[var(--vf-m)]")
                }
              >
                {chip}
              </span>
            ))}
          </div>
        </div>
        <GuionHeaderArt />
      </div>

      {/* Action toolbar */}
      <div className="mb-5 flex flex-wrap gap-1.5">
        <button
          type="button"
          onClick={notImplemented}
          className="rounded-lg border border-[rgba(124,106,255,.3)] bg-[rgba(124,106,255,.16)] px-3 py-1.5 text-[12px] font-medium text-[var(--vf-text)]"
        >
          🤖 Asistente IA
        </button>
        {["✦ Mejorar guión", "↔ Expander", "🌐 Traducir", "Más ▾"].map((label) => (
          <button
            key={label}
            type="button"
            onClick={notImplemented}
            className="rounded-lg border border-[rgba(var(--vf-fg-rgb),.08)] bg-[rgba(var(--vf-fg-rgb),.03)] px-3 py-1.5 text-[12px] font-medium text-[var(--vf-m)] transition-colors hover:bg-[rgba(124,106,255,.12)] hover:text-[var(--vf-text)]"
          >
            {label}
          </button>
        ))}
      </div>

      <div className="grid items-start gap-x-5" style={{ gridTemplateColumns: "1fr 240px" }}>
        {/* Main column */}
        <div className="min-w-0">
          <form onSubmit={handleSubmit}>
            <div className="mb-5 rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)]">
              <div className="flex items-center justify-between px-5 pt-4">
                <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                  // Guión Completo
                </span>
                <span className="font-mono text-[10px] text-[var(--vf-muted)]">{charCount} caracteres</span>
              </div>

              <div className="mx-5 mt-2 flex overflow-hidden rounded-lg border border-[var(--vf-border)] bg-black/20">
                <pre
                  id="vf-line-nums-el"
                  className="select-none overflow-hidden px-2.5 py-3 text-right font-mono text-[12.5px] leading-relaxed text-[var(--vf-m2)]"
                >
                  {lineNumbers}
                </pre>
                <textarea
                  ref={textareaRef}
                  value={guion}
                  onChange={(e) => setGuion(e.target.value)}
                  onScroll={syncLineScroll}
                  placeholder="Pega aquí tu guión completo. En un mundo donde la tecnología avanza a pasos agigantados..."
                  className="min-h-[220px] w-full resize-y bg-transparent px-3 py-3 font-mono text-[12.5px] leading-relaxed text-[var(--vf-text)] outline-none placeholder:text-[var(--vf-muted)]"
                />
              </div>

              <div className="flex items-center justify-between px-5 pb-4 pt-2">
                <span className="font-mono text-[10px] text-[var(--vf-muted)]">
                  ↳ El corte siempre se hace en frase completa
                </span>
                <span className="font-mono text-[10px] text-[var(--vf-muted)]">
                  Escenas estimadas: <strong className="text-[var(--vf-text)]">{fragEstimate}</strong>
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-3 border-t border-[var(--vf-border)] px-5 py-3.5">
                <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">Salida</span>
                <div className="flex gap-0.5 rounded-lg border border-[var(--vf-border)] bg-[var(--vf-p)] p-0.5">
                  <button
                    type="button"
                    onClick={() => setOutputMode("solo_saltos")}
                    className={`rounded-md px-3 py-1.5 font-mono text-[10.5px] font-medium transition ${
                      outputMode === "solo_saltos"
                        ? "bg-[var(--vf-c6)] text-white"
                        : "text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
                    }`}
                  >
                    💬 Solo saltos
                  </button>
                  <button
                    type="button"
                    onClick={() => setOutputMode("con_prompts")}
                    className={`rounded-md px-3 py-1.5 font-mono text-[10.5px] font-medium transition ${
                      outputMode === "con_prompts"
                        ? "bg-[var(--vf-c1)] text-white"
                        : "text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
                    }`}
                  >
                    🖼 + Prompts
                  </button>
                </div>
              </div>

              {error && (
                <div className="px-5 pb-3">
                  <p className="text-sm text-[var(--vf-danger)]">{error}</p>
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--vf-border)] px-5 py-4">
                <button
                  type="submit"
                  disabled={loading || !guion.trim()}
                  className="rounded-lg bg-[var(--vf-accent)] px-5 py-2.5 text-sm font-medium text-white hover:bg-[var(--vf-accent-hover)] disabled:opacity-50"
                >
                  {loading ? "Procesando…" : "Procesar Guión →"}
                </button>
                <div className="font-mono text-[10px] text-[var(--vf-muted)]">
                  El proceso puede tardar <strong>2–5 min</strong> según la extensión
                </div>
              </div>

              {/* Reference image */}
              <div className="m-5 mt-0 rounded-2xl border border-[rgba(124,106,255,.15)] p-[18px_20px]" style={{ background: "var(--vf-surface-2)" }}>
                <div className="mb-3.5 flex items-center gap-1.5 border-b border-[rgba(124,106,255,.12)] pb-3 font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--vf-m2)]">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <circle cx="8.5" cy="8.5" r="1.5" />
                    <polyline points="21 15 16 10 5 21" />
                  </svg>
                  Imagen de referencia
                  <span className="font-normal normal-case tracking-normal text-[var(--vf-m2)] opacity-60">
                    Opcional · para guiar el estilo visual
                  </span>
                </div>
                {refImage ? (
                  <div className="flex items-center gap-3 rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),.03)] p-2.5">
                    <img src={refImage} alt="" className="h-14 w-14 flex-shrink-0 rounded-md object-cover" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-mono text-[11px] text-[var(--vf-text)]">{refName}</p>
                      <p className="font-mono text-[10px] text-[var(--vf-c5)]">
                        {refAnalyzing ? "Analizando imagen…" : refDescription ? "Estilo listo ✓" : "Sin análisis disponible"}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={clearRefImage}
                      className="flex-shrink-0 rounded-full px-2 py-1 font-mono text-xs text-[var(--vf-danger)]"
                    >
                      ✕
                    </button>
                  </div>
                ) : (
                  <div className="relative cursor-pointer" onClick={() => refInputRef.current?.click()}>
                    <input
                      ref={refInputRef}
                      type="file"
                      accept="image/*"
                      onChange={handleRefFileChange}
                      className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0"
                    />
                    <div className="rounded-xl border-2 border-dashed border-[rgba(124,106,255,.28)] bg-[rgba(124,106,255,.03)] px-5 py-5 text-center transition-colors hover:border-[rgba(167,139,250,.5)] hover:bg-[rgba(124,106,255,.07)]">
                      <div className="mx-auto mb-2.5 flex h-[42px] w-[42px] items-center justify-center rounded-xl border border-[rgba(124,106,255,.22)] bg-[rgba(124,106,255,.12)] text-[var(--vf-c2)]">
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="16 16 12 12 8 16" />
                          <line x1="12" y1="12" x2="12" y2="21" />
                          <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3" />
                        </svg>
                      </div>
                      <p className="mb-1 text-[13px] text-[var(--vf-muted)]">
                        Arrastra imagen o <span className="text-[var(--vf-c2)] underline underline-offset-2">haz clic</span>
                      </p>
                      <p className="font-mono text-[10px] text-[var(--vf-m2)]">
                        JPG · PNG · WEBP — referencia de estilo para los prompts IA
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </form>

          {result && (
            <div>
              <div className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div className="rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-4">
                  <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                    Prompts generados
                  </div>
                  <div className="mt-1 text-2xl font-bold text-[var(--vf-c1)]">
                    {Array.isArray(result.prompts) ? result.prompts.length : "—"}
                  </div>
                </div>
                <div className="rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-4">
                  <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                    Total de escenas
                  </div>
                  <div className="mt-1 text-2xl font-bold text-[var(--vf-c2)]">
                    {result.escenas ?? result.total_escenas ?? "—"}
                  </div>
                </div>
                <div className="rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-4">
                  <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                    Fragmentos
                  </div>
                  <div className="mt-1 text-2xl font-bold text-[var(--vf-c3)]">{result.fragmentos ?? "—"}</div>
                </div>
              </div>

              <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)]">
                <div className="flex flex-wrap items-center gap-2 border-b border-[var(--vf-border)] px-5 py-3">
                  <div className="flex gap-0.5 rounded-lg border border-[var(--vf-border)] bg-[var(--vf-p)] p-0.5">
                    <button
                      type="button"
                      onClick={() => setActivePanel("prompts")}
                      className={`rounded-md px-3 py-1.5 font-mono text-[10.5px] font-medium transition ${
                        activePanel === "prompts"
                          ? "bg-[var(--vf-c1)] text-white"
                          : "text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
                      }`}
                    >
                      Prompts de imagen
                    </button>
                    <button
                      type="button"
                      onClick={() => setActivePanel("guion")}
                      className={`rounded-md px-3 py-1.5 font-mono text-[10.5px] font-medium transition ${
                        activePanel === "guion"
                          ? "bg-[var(--vf-c1)] text-white"
                          : "text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
                      }`}
                    >
                      Guión con saltos
                    </button>
                  </div>
                  <span className="font-mono text-[10px] text-[var(--vf-muted)]">
                    {activePanel === "prompts"
                      ? "// Prompts de imagen — listos para copiar"
                      : "// Guión con saltos"}
                  </span>
                  <div className="ml-auto flex items-center gap-2">
                    {saveStatus && (
                      <span className="font-mono text-[10.5px] text-[var(--vf-success)]">{saveStatus}</span>
                    )}
                    <button
                      type="button"
                      onClick={copyActive}
                      className="rounded-lg border border-[var(--vf-border)] px-3 py-1.5 font-mono text-[10.5px] hover:bg-[var(--vf-surface-2)]"
                    >
                      Copiar todo
                    </button>
                    <button
                      type="button"
                      onClick={handleSaveScript}
                      className="rounded-lg border border-[var(--vf-success)]/30 bg-[var(--vf-success)]/10 px-3 py-1.5 font-mono text-[10.5px] text-[var(--vf-success)] hover:bg-[var(--vf-success)]/20"
                    >
                      💾 Guardar en proyecto
                    </button>
                  </div>
                </div>
                <pre className="max-h-[500px] overflow-auto whitespace-pre-wrap px-5 py-4 font-mono text-[12px] leading-relaxed text-[var(--vf-text)]">
                  {activePanel === "prompts" ? promptsText : guionOutText}
                </pre>
              </div>
            </div>
          )}

          {/* Footer */}
          <div className="mt-5 flex items-center justify-between border-t border-[rgba(var(--vf-fg-rgb),.06)] pt-4">
            <button
              type="button"
              onClick={() => navigate("/app/home")}
              className="rounded-lg border border-[rgba(var(--vf-fg-rgb),.1)] bg-[rgba(var(--vf-fg-rgb),.05)] px-4 py-2 text-[13px] font-medium text-[var(--vf-m)] hover:bg-[rgba(var(--vf-fg-rgb),.08)] hover:text-[var(--vf-text)]"
            >
              ← Volver
            </button>
            <span className="font-mono text-[11px] font-medium uppercase tracking-[0.05em] text-[var(--vf-m2)]">
              Paso 1 de 5
            </span>
            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={handleSaveScript}
                className="rounded-lg border border-[rgba(var(--vf-fg-rgb),.1)] bg-[rgba(var(--vf-fg-rgb),.05)] px-4 py-2 text-[13px] font-medium text-[var(--vf-m)] hover:bg-[rgba(var(--vf-fg-rgb),.08)] hover:text-[var(--vf-text)]"
              >
                Guardar borrador
              </button>
              <button
                type="button"
                onClick={() => navigate(`/app/imagen?project=${encodeURIComponent(project)}`)}
                className="rounded-lg bg-[rgba(124,106,255,.82)] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#7c6aff]"
              >
                Continuar →
              </button>
            </div>
          </div>
        </div>

        {/* Side panel */}
        <div className="flex flex-col gap-3">
          <div
            className="overflow-hidden rounded-xl border border-[rgba(124,106,255,.13)]"
            style={{ background: "var(--vf-surface-2)" }}
          >
            <div
              className="border-b border-[rgba(124,106,255,.08)] px-3.5 py-2.5 text-[8px] font-bold uppercase tracking-[0.18em]"
              style={{ color: "rgba(124,106,255,.45)", background: "rgba(var(--vf-bg-rgb),.5)" }}
            >
              Ajustes del guión
            </div>
            <label className="flex items-center justify-between border-b border-[rgba(var(--vf-fg-rgb),.04)] px-3.5 py-[7px] text-[12.5px] font-medium text-[var(--vf-m)]">
              Idioma
              <select className="max-w-[112px] rounded-md border-0 bg-transparent text-right text-[11px] text-[var(--vf-text)] outline-none">
                <option>Español</option>
                <option>Inglés</option>
                <option>Portugués</option>
                <option>Francés</option>
                <option>Alemán</option>
              </select>
            </label>
            <label className="flex items-center justify-between border-b border-[rgba(var(--vf-fg-rgb),.04)] px-3.5 py-[7px] text-[12.5px] font-medium text-[var(--vf-m)]">
              Tono
              <select className="max-w-[112px] rounded-md border-0 bg-transparent text-right text-[11px] text-[var(--vf-text)] outline-none">
                <option>Inspirador</option>
                <option>Formal</option>
                <option>Casual</option>
                <option>Educativo</option>
                <option>Dramático</option>
              </select>
            </label>
            <label className="flex items-center justify-between border-b border-[rgba(var(--vf-fg-rgb),.04)] px-3.5 py-[7px] text-[12.5px] font-medium text-[var(--vf-m)]">
              Público objetivo
              <select className="max-w-[112px] rounded-md border-0 bg-transparent text-right text-[11px] text-[var(--vf-text)] outline-none">
                <option>General</option>
                <option>Profesional</option>
                <option>Jóvenes</option>
                <option>Empresarial</option>
              </select>
            </label>
            <label className="flex items-center justify-between border-b border-[rgba(var(--vf-fg-rgb),.04)] px-3.5 py-[7px] text-[12.5px] font-medium text-[var(--vf-m)]">
              Modo de prompts
              <select
                value={PROMPT_MODE_LABELS[promptMode]}
                onChange={(e) => {
                  const entry = Object.entries(PROMPT_MODE_LABELS).find(([, label]) => label === e.target.value);
                  setPromptMode((entry?.[0] as PromptMode) || "general");
                }}
                className="max-w-[112px] rounded-md border-0 bg-transparent text-right text-[11px] text-[var(--vf-text)] outline-none"
              >
                <option>General</option>
                <option>Stick Animado</option>
                <option>Ultrarrealismo</option>
              </select>
            </label>
            {promptMode === "stick" && (
              <label className="flex items-center justify-between border-b border-[rgba(var(--vf-fg-rgb),.04)] px-3.5 py-[7px] text-[12.5px] font-medium text-[var(--vf-m)]">
                Estilos
                <select
                  value={promptStyle === "history" ? "History Telling" : "Default"}
                  onChange={(e) => setPromptStyle(e.target.value === "History Telling" ? "history" : "default")}
                  className="max-w-[112px] rounded-md border-0 bg-transparent text-right text-[11px] text-[var(--vf-text)] outline-none"
                >
                  <option>Default</option>
                  <option>History Telling</option>
                </select>
              </label>
            )}
            <div className="flex items-center justify-between border-t border-[rgba(var(--vf-fg-rgb),.05)] px-3.5 py-2 text-[12.5px] font-medium text-[var(--vf-m)]">
              Duración estimada
              <span className="text-[11px] font-semibold text-[var(--vf-text)]">{estimatedDuration}</span>
            </div>
            <div className="flex items-center justify-between px-3.5 py-2 text-[12.5px] font-medium text-[var(--vf-m)]">
              Escenas
              <span className="text-[11px] font-semibold text-[var(--vf-text)]">{guion.trim() ? fragEstimate : "—"}</span>
            </div>
          </div>

          <div
            className="overflow-hidden rounded-xl border border-[rgba(124,106,255,.13)]"
            style={{ background: "var(--vf-surface-2)" }}
          >
            <div
              className="border-b border-[rgba(124,106,255,.08)] px-3.5 py-2.5 text-[8px] font-bold uppercase tracking-[0.18em]"
              style={{ color: "rgba(124,106,255,.45)", background: "rgba(var(--vf-bg-rgb),.5)" }}
            >
              Análisis del guión
            </div>
            <div className="flex items-center justify-between border-b border-[rgba(var(--vf-fg-rgb),.04)] px-3.5 py-1.5 text-[12.5px] font-medium text-[var(--vf-m)]">
              Palabras
              <span className="text-[11px] font-semibold text-[var(--vf-text)]">{wordCount}</span>
            </div>
            <div className="flex items-center justify-between border-b border-[rgba(var(--vf-fg-rgb),.04)] px-3.5 py-1.5 text-[12.5px] font-medium text-[var(--vf-m)]">
              Caracteres
              <span className="text-[11px] font-semibold text-[var(--vf-text)]">{charCount}</span>
            </div>
            <div className="flex items-center justify-between border-b border-[rgba(var(--vf-fg-rgb),.04)] px-3.5 py-1.5 text-[12.5px] font-medium text-[var(--vf-m)]">
              Tiempo estimado
              <span className="text-[11px] font-semibold text-[var(--vf-text)]">{estimatedReadTime}</span>
            </div>
            <div className="flex items-center justify-between px-3.5 py-1.5 text-[12.5px] font-medium text-[var(--vf-m)]">
              Complejidad
              <div className="flex flex-col items-end gap-1">
                <span className="text-[11px] font-semibold text-[var(--vf-text)]">{complexity.label}</span>
                <div className="h-[3px] w-[72px] overflow-hidden rounded-full bg-[rgba(var(--vf-fg-rgb),.08)]">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{ width: `${complexity.pct}%`, background: "linear-gradient(90deg,#7c6aff,#a78bfa)" }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
