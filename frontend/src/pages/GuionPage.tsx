import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { listProjects } from "../api/projects";
import { analyzeImage, loadScript, n8nProxy, saveScript } from "../api/script";
import type { N8nProxyResult } from "../api/script";
import { Select, SelectOption } from "../components/Select";
import type { Project } from "../types";

type ActivePanel = "prompts" | "guion";

export default function GuionPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState(searchParams.get("project") || "");

  const [guion, setGuion] = useState("");
  const [outputMode, setOutputMode] = useState("con_prompts");
  const [promptMode, setPromptMode] = useState("general");

  const [refImageFile, setRefImageFile] = useState<File | null>(null);
  const [refImagePreviewUrl, setRefImagePreviewUrl] = useState("");
  const [refImageDescription, setRefImageDescription] = useState("");
  const [analyzingImage, setAnalyzingImage] = useState(false);
  const [refImageError, setRefImageError] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [saveStatus, setSaveStatus] = useState("");

  const [result, setResult] = useState<N8nProxyResult | null>(null); // raw n8n result
  const [activePanel, setActivePanel] = useState<ActivePanel>("prompts");

  // Load projects list
  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((err: Error) => setError(err.message));
  }, []);

  // Keep ?project= in sync
  useEffect(() => {
    if (project) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("project", project);
        return next;
      });
    }
  }, [project]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load existing script when project changes
  useEffect(() => {
    if (!project) return;
    loadScript(project)
      .then((data) => {
        if (data?.existe) {
          setGuion(data.texto || "");
        }
      })
      .catch((err: Error) => setError(err.message));
  }, [project]);

  const charCount = guion.length;
  const fragEstimate = Math.max(1, Math.ceil(charCount / 1820));

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

  function fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve((reader.result as string).split(",")[1] || "");
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  async function handleRefImageChange(file: File | null) {
    if (!file) return;
    setRefImageFile(file);
    setRefImagePreviewUrl(URL.createObjectURL(file));
    setRefImageDescription("");
    setRefImageError("");
    setAnalyzingImage(true);
    try {
      const base64 = await fileToBase64(file);
      const res = await analyzeImage(base64, file.type || "image/png");
      const desc = res.descripcion_completa;
      setRefImageDescription(typeof desc === "string" ? desc : "");
    } catch (err) {
      setRefImageError((err as Error).message);
    } finally {
      setAnalyzingImage(false);
    }
  }

  function clearRefImage() {
    setRefImageFile(null);
    setRefImagePreviewUrl("");
    setRefImageDescription("");
    setRefImageError("");
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!guion.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await n8nProxy({
        guion,
        outputMode,
        promptMode,
        descripcionReferencia: refImageDescription,
      });
      setResult(data);
      setActivePanel("prompts");
    } catch (err) {
      setError((err as Error).message);
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

  return (
    <div>
      {/* Project selector topbar */}
      <div className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] px-4 py-3">
        <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
          Proyecto
        </span>
        <Select
          value={project}
          onChange={(v) => setProject(v)}
          className="min-w-[200px] rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--vf-accent)]"
        >
          <SelectOption value="">— Sin proyecto seleccionado —</SelectOption>
          {projects.map((p) => (
            <SelectOption key={p.nombre} value={p.nombre}>
              {p.nombre}
            </SelectOption>
          ))}
        </Select>
        {saveStatus && (
          <span className="ml-auto font-mono text-xs text-[var(--vf-success)]">{saveStatus}</span>
        )}
      </div>

      <div className="mb-9 max-w-2xl">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.03)] px-3 py-1 font-mono text-[9.5px] uppercase tracking-widest text-[var(--vf-muted)]">
          <span
            className="h-[5px] w-[5px] rounded-full"
            style={{ background: "var(--vf-c5)", boxShadow: "0 0 6px var(--vf-c5)" }}
          />
          Módulo 01 · Pipeline
        </div>
        <h1 className="mb-3 text-3xl font-bold tracking-tight sm:text-4xl">
          Guión{" "}
          <span
            className="bg-clip-text text-transparent"
            style={{
              backgroundImage:
                "linear-gradient(110deg, var(--vf-c2) 0%, var(--vf-c1) 40%, var(--vf-c3) 85%)",
            }}
          >
            a Escenas
          </span>
        </h1>
        <p className="font-mono text-[12.5px] leading-relaxed text-[var(--vf-muted)]">
          Ingresa tu guión completo. La IA lo fragmenta, calcula el timing y genera un prompt de
          imagen cinematográfico para cada escena.
        </p>
      </div>

      {/* Pipeline steps */}
      <div className="mb-9 flex flex-wrap overflow-hidden rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)]">
        {[
          { n: "01", name: "Dividir", desc: "~1820 chars / bloque" },
          { n: "02", name: "Timing", desc: "5–7 seg / escena" },
          { n: "03", name: "Prompts", desc: "Imagen por escena" },
          { n: "04", name: "Output", desc: "Listo para copiar" },
        ].map((s, i) => (
          <div
            key={s.n}
            className={`flex flex-1 min-w-[150px] items-center gap-3 px-4 py-4 ${
              i !== 3 ? "border-r border-[var(--vf-border)]" : ""
            }`}
          >
            <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg border border-[var(--vf-c1)]/20 bg-[var(--vf-c1)]/10 font-mono text-[11px] font-semibold text-[var(--vf-c1)]">
              {s.n}
            </div>
            <div>
              <div className="text-xs font-bold">{s.name}</div>
              <div className="font-mono text-[9.5px] text-[var(--vf-muted)]">{s.desc}</div>
            </div>
          </div>
        ))}
      </div>

      <form onSubmit={handleSubmit}>
        <div className="mb-5 rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)]">
          <div className="flex items-center justify-between px-5 pt-4">
            <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
              // Guión Completo
            </span>
            <span className="font-mono text-[10px] text-[var(--vf-muted)]">
              {charCount} caracteres
            </span>
          </div>

          <textarea
            value={guion}
            onChange={(e) => setGuion(e.target.value)}
            placeholder="Pega aquí tu guión completo. En un mundo donde la tecnología avanza a pasos agigantados..."
            className="min-h-[220px] w-full resize-y bg-transparent px-5 py-3 font-mono text-[12.5px] leading-relaxed text-[var(--vf-text)] outline-none placeholder:text-[var(--vf-muted)]"
          />

          <div className="flex items-center justify-between px-5 pb-4">
            <span className="font-mono text-[10px] text-[var(--vf-muted)]">
              ↳ El corte siempre se hace en frase completa
            </span>
            <span className="font-mono text-[10px] text-[var(--vf-muted)]">
              Escenas estimadas: <strong className="text-[var(--vf-text)]">{fragEstimate}</strong>
            </span>
          </div>

          {/* Output mode toggle */}
          <div className="flex flex-wrap items-center gap-3 border-t border-[var(--vf-border)] px-5 py-3.5">
            <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
              Salida
            </span>
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

          {outputMode === "con_prompts" && (
            <>
              {/* Prompt mode toggle */}
              <div className="flex flex-wrap items-center gap-3 border-t border-[var(--vf-border)] px-5 py-3.5">
                <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                  Modo de prompt
                </span>
                <div className="flex gap-0.5 rounded-lg border border-[var(--vf-border)] bg-[var(--vf-p)] p-0.5">
                  <button
                    type="button"
                    onClick={() => setPromptMode("general")}
                    className={`rounded-md px-3 py-1.5 font-mono text-[10.5px] font-medium transition ${
                      promptMode === "general"
                        ? "bg-[var(--vf-c1)] text-white"
                        : "text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
                    }`}
                  >
                    General
                  </button>
                  <button
                    type="button"
                    onClick={() => setPromptMode("stick")}
                    className={`rounded-md px-3 py-1.5 font-mono text-[10.5px] font-medium transition ${
                      promptMode === "stick"
                        ? "bg-[var(--vf-c1)] text-white"
                        : "text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
                    }`}
                  >
                    Figuras de palitos
                  </button>
                  <button
                    type="button"
                    onClick={() => setPromptMode("ultrarealismo")}
                    className={`rounded-md px-3 py-1.5 font-mono text-[10.5px] font-medium transition ${
                      promptMode === "ultrarealismo"
                        ? "bg-[var(--vf-c1)] text-white"
                        : "text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
                    }`}
                  >
                    Ultrarealismo
                  </button>
                </div>
              </div>

              {/* Reference image upload */}
              <div className="border-t border-[var(--vf-border)] px-5 py-3.5">
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                    Imagen de referencia (opcional)
                  </span>
                  {refImageFile && (
                    <button
                      type="button"
                      onClick={clearRefImage}
                      className="font-mono text-[10px] text-[var(--vf-danger)] hover:underline"
                    >
                      Quitar
                    </button>
                  )}
                </div>

                {!refImageFile ? (
                  <div className="relative rounded-lg border border-dashed border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.015)] p-4 text-center">
                    <input
                      type="file"
                      accept="image/*"
                      onChange={(e) => handleRefImageChange(e.target.files?.[0] || null)}
                      className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                    />
                    <div className="font-mono text-[11px] text-[var(--vf-muted)]">
                      <strong>Clic o arrastra</strong> una imagen de estilo/referencia
                    </div>
                  </div>
                ) : (
                  <div className="flex gap-3 rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.015)] p-3">
                    <img
                      src={refImagePreviewUrl}
                      alt="Referencia"
                      className="h-16 w-16 flex-shrink-0 rounded-md object-cover"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 truncate font-mono text-[10.5px] text-[var(--vf-text)]">
                        {refImageFile.name}
                      </div>
                      {analyzingImage ? (
                        <div className="font-mono text-[10px] text-[var(--vf-muted)]">
                          Analizando imagen…
                        </div>
                      ) : refImageError ? (
                        <div className="font-mono text-[10px] text-[var(--vf-danger)]">
                          {refImageError}
                        </div>
                      ) : refImageDescription ? (
                        <div className="line-clamp-2 font-mono text-[10px] text-[var(--vf-muted)]">
                          {refImageDescription}
                        </div>
                      ) : null}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {error && (
            <div className="px-5 pb-3">
              <p className="text-sm text-[var(--vf-danger)]">{error}</p>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--vf-border)] px-5 py-4">
            <button
              type="submit"
              disabled={loading || !guion.trim() || analyzingImage}
              className="rounded-lg bg-[var(--vf-accent)] px-5 py-2.5 text-sm font-medium text-white hover:bg-[var(--vf-accent-hover)] disabled:opacity-50"
            >
              {loading ? "Procesando…" : "Procesar Guión →"}
            </button>
            <div className="font-mono text-[10px] text-[var(--vf-muted)]">
              El proceso puede tardar <strong>2–5 min</strong> según la extensión
            </div>
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
              <div className="mt-1 text-2xl font-bold text-[var(--vf-c3)]">
                {result.fragmentos ?? "—"}
              </div>
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
              <div className="ml-auto flex gap-2">
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
    </div>
  );
}
