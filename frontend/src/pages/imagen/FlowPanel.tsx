import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { Select, SelectOption } from "../../components/Select";
import {
  flowAbrirCarpeta,
  flowAccounts,
  flowChromiumStatus,
  flowImages,
  flowImageUrl,
  flowLogin,
  flowOpenAll,
  flowResetChromium,
  flowRetry,
  flowRunPrompts,
  flowStatus,
  flowStop,
} from "../../api/flow";
import type { FlowAccount, FlowChromiumProfile } from "../../api/flow";
import { ErrorText, LogConsole, countPrompts } from "./shared";
import type { GalleryImage } from "./shared";
import { HeaderArt } from "../../components/HeaderArt";

const POLL_MS = 2000;

interface FlowPanelProps {
  project: string;
  outputDir: string;
  resolvingDir: boolean;
}

interface Progress {
  done: number;
  total: number;
  label: string;
}

export default function FlowPanel({ outputDir, resolvingDir }: FlowPanelProps) {
  const [prompts, setPrompts] = useState("");
  const [slots, setSlots] = useState(2);
  const [aspect, setAspect] = useState("IMAGE_ASPECT_RATIO_LANDSCAPE");
  const [model, setModel] = useState("NANO_BANANA_2");
  const [maxRetries, setMaxRetries] = useState(2);
  const [referenceImage, setReferenceImage] = useState("");
  const [referenceImageName, setReferenceImageName] = useState("");

  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<Progress>({ done: 0, total: 0, label: "Listo para generar" });
  const [logLines, setLogLines] = useState<string[]>([]);
  const [images, setImages] = useState<GalleryImage[]>([]);
  const [error, setError] = useState("");

  const [accounts, setAccounts] = useState<FlowAccount[]>([]);
  const [chromiumProfiles, setChromiumProfiles] = useState<FlowChromiumProfile[]>([]);

  const sinceRef = useRef(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dirRef = useRef(outputDir);
  const refInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    dirRef.current = outputDir;
  }, [outputDir]);

  function handleRefFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const isImage = file.type.startsWith("image/") || /\.(jpe?g|png|gif|webp|bmp)$/i.test(file.name);
    if (!isImage) {
      setError("Elige un archivo de imagen (JPG, PNG, WebP, etc.).");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setReferenceImage(reader.result as string);
      setReferenceImageName(file.name);
    };
    reader.onerror = () => setError("No se pudo leer la imagen de referencia.");
    reader.readAsDataURL(file);
  }

  function loadAccounts() {
    flowAccounts()
      .then((d) => setAccounts(d.accounts || []))
      .catch(() => {});
  }
  function loadChromium() {
    flowChromiumStatus()
      .then((d) => setChromiumProfiles(d.profiles || []))
      .catch(() => {});
  }

  function refreshImages() {
    if (!dirRef.current) return;
    flowImages(dirRef.current)
      .then((d) => {
        const names = d.images || [];
        setImages(
          names.map((n) => ({
            key: n,
            name: n,
            src: flowImageUrl(dirRef.current, n) + `&t=${Date.now()}`,
          })),
        );
      })
      .catch(() => {});
  }

  function pollOnce() {
    flowStatus(sinceRef.current)
      .then((d) => {
        if (typeof d.since === "number") sinceRef.current = d.since;
        if (Array.isArray(d.log)) setLogLines((prev) => [...prev, ...(d.log as string[])]);
        if (typeof d.done === "number" || typeof d.total === "number") {
          setProgress({
            done: d.done ?? 0,
            total: d.total ?? 0,
            label: d.label || (d.running ? "Generando…" : "Completado"),
          });
        }
        setRunning(!!d.running);
        if (!d.running && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
        refreshImages();
      })
      .catch(() => {});
  }

  useEffect(() => {
    loadAccounts();
    loadChromium();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (running && !pollRef.current) {
      pollRef.current = setInterval(pollOnce, POLL_MS);
    }
    return () => {
      if (!running && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);

  useEffect(() => {
    refreshImages();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outputDir]);

  async function handleStart() {
    setError("");
    const list = prompts
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    if (!list.length) {
      setError("Escribe al menos un prompt.");
      return;
    }
    if (!outputDir) {
      setError("Selecciona un proyecto activo. Las imágenes se guardan en la carpeta de imágenes del proyecto.");
      return;
    }
    try {
      sinceRef.current = 0;
      setLogLines([]);
      await flowRunPrompts({
        prompts: list,
        output_dir: outputDir,
        slots,
        aspect_ratio: aspect,
        model,
        max_retries: maxRetries,
        reference_image: referenceImage || undefined,
      });
      setRunning(true);
      pollOnce();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleStop() {
    try {
      await flowStop();
      setRunning(false);
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleRetry(img: GalleryImage, index: number) {
    try {
      await flowRetry({
        output_dir: outputDir,
        index,
        filename: img.name || "",
        fallback_prompts: prompts.split("\n").map((l) => l.trim()).filter(Boolean),
      });
      refreshImages();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleLogin(idx: number) {
    try {
      await flowLogin(idx);
      loadAccounts();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleResetChromium() {
    if (!confirm("¿Reiniciar todos los perfiles de Chromium? Esto cerrará sesiones activas.")) return;
    try {
      await flowResetChromium();
      loadChromium();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const pct = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;

  return (
    <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-4 px-2">
      <div
        className="relative mb-0.5 overflow-hidden rounded-2xl border border-[rgba(124,106,255,.15)] p-5"
        style={{ background: "var(--vf-surface)" }}
      >
        <div className="flex flex-shrink-0 gap-1.5 sm:absolute sm:right-5 sm:top-5">
          <span className="rounded-md border border-[rgba(124,106,255,.22)] bg-[rgba(124,106,255,.1)] px-2 py-1 text-[9px] font-bold uppercase tracking-[0.1em] text-[var(--vf-c2)]">
            Módulo 03
          </span>
          <span className="rounded-md border border-[rgba(var(--vf-fg-rgb),.08)] bg-[rgba(var(--vf-fg-rgb),.04)] px-2 py-1 text-[9px] font-semibold tracking-[0.06em] text-[var(--vf-m2)]">
            Labs
          </span>
        </div>
        <div className="flex items-center gap-5">
          <div className="min-w-0 flex-1">
            <div className="mb-2.5 flex items-center gap-3.5">
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[10px] border border-[rgba(124,106,255,.3)]" style={{ background: "linear-gradient(135deg,rgba(124,106,255,.22),rgba(192,38,211,.12))" }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--vf-c2)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <polyline points="21 15 16 10 5 21" />
                </svg>
              </div>
              <div className="flex flex-col gap-[1px]">
                <div className="text-[10px] font-bold tracking-[0.18em] text-[rgba(124,106,255,.6)]">Módulo 03 · Producción IA</div>
                <h1 className="m-0 text-[26px] font-bold leading-[1.1] tracking-[-0.025em] text-[var(--vf-text)]">
                  Imágenes con{" "}
                  <span
                    className="bg-clip-text text-transparent"
                    style={{ backgroundImage: "linear-gradient(90deg,var(--vf-c2),var(--vf-c3))" }}
                  >
                    Google Flow
                  </span>
                </h1>
              </div>
            </div>
            <p className="mb-3.5 max-w-[560px] text-[13.5px] leading-[1.55] text-[var(--vf-m)]">
              Generación por lotes con Google Labs. Las imágenes se guardan en la carpeta de imágenes
              del proyecto activo. Ajusta slots, ratio y modelo a la derecha.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {["📦 Lotes", "👥 Multi-cuenta", "🖼 Referencia visual", "🧪 Google Labs"].map((chip, i) => (
                <span
                  key={chip}
                  className={
                    i === 0
                      ? "rounded-[7px] border border-[rgba(124,106,255,.35)] bg-[rgba(124,106,255,.16)] px-[11px] py-1 text-[11px] text-[var(--vf-c2)]"
                      : "rounded-[7px] border border-[rgba(124,106,255,.16)] bg-[rgba(124,106,255,.05)] px-[11px] py-1 text-[11px] text-[var(--vf-m)]"
                  }
                >
                  {chip}
                </span>
              ))}
            </div>
          </div>
          <HeaderArt />
        </div>
      </div>

      <div className="flex items-center gap-2 rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface)] px-3 py-2">
        <span className="font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
          Destino:
        </span>
        <span className="flex-1 truncate font-mono text-[11px] text-[var(--vf-c5)]">
          {resolvingDir
            ? "Resolviendo carpeta del proyecto…"
            : outputDir || "— selecciona un proyecto arriba —"}
        </span>
      </div>

      <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(320px,460px)] items-start gap-x-6 gap-y-4 max-[1040px]:grid-cols-1">
        <div className="flex w-full flex-col gap-3.5">
          <section className="flow-card">
            <div className="mb-3 flex items-center justify-between gap-2.5">
              <span className="font-mono text-[9px] uppercase tracking-[.14em] text-[var(--vf-m2)]">
                Prompts · {countPrompts(prompts)}
              </span>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setPrompts("")}
                  className="flow-btn flow-btn--ghost"
                >
                  ✕
                </button>
              </div>
            </div>
            <textarea
              value={prompts}
              onChange={(e) => setPrompts(e.target.value)}
              placeholder={"Un prompt por línea. Ejemplo:\nCinematic wide shot, golden hour, anamorphic flare\nMinimal product still life, soft gradient backdrop"}
              className="flow-textarea"
            />
          </section>

          <section className="flow-card">
            <div className="mb-3 flex items-center justify-between gap-2.5">
              <span className="font-mono text-[9px] uppercase tracking-[.14em] text-[var(--vf-m2)]">
                Referencia visual
              </span>
              <span className="font-mono text-[9px] text-[var(--vf-muted)] opacity-75">
                Opcional · guía de estilo
              </span>
            </div>
            <input
              ref={refInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleRefFileChange}
            />
            <div
              onClick={() => refInputRef.current?.click()}
              className={"flow-ref-zone" + (referenceImage ? " flow-ref-zone--has" : "")}
            >
              {referenceImage ? (
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="flex min-w-0 flex-col gap-1 text-left">
                    <div className="font-mono text-xs font-semibold tracking-wide text-[var(--vf-text)]">
                      Imagen adjunta
                    </div>
                    <div className="font-mono text-[9px] leading-relaxed text-[var(--vf-m2)] opacity-90">
                      Clic o arrastra para reemplazar
                    </div>
                  </div>
                  <div className="relative flex min-h-[104px] min-w-[112px] items-center justify-center p-1.5">
                    <img
                      src={referenceImage}
                      alt={referenceImageName}
                      className="mx-auto block max-h-[104px] max-w-[min(200px,42vw)] rounded-xl border border-[rgba(var(--vf-fg-rgb),.1)] object-contain shadow-[0_10px_28px_rgba(0,0,0,.4)]"
                    />
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setReferenceImage("");
                        setReferenceImageName("");
                        if (refInputRef.current) refInputRef.current.value = "";
                      }}
                      type="button"
                      className="flow-ref-x"
                      aria-label="Quitar"
                    >
                      ×
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap items-center justify-center gap-3.5">
                  <div className="flex min-w-0 max-w-full items-center gap-3.5">
                    <span className="flow-ref-ico" aria-hidden="true" />
                    <div>
                      <div className="mb-1 font-mono text-[11px] font-semibold tracking-wide text-[var(--vf-text)]">
                        Adjuntar imagen
                      </div>
                      <span className="block font-mono text-[10px] leading-relaxed text-[var(--vf-m2)]">
                        Arrastra aquí o haz clic · JPG, PNG, WebP
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>

        <div className="flex flex-col gap-3.5">
          <section className="flow-card" style={{ padding: "14px 16px" }}>
            <div className="mb-3 flex items-center justify-between gap-2.5">
              <span className="font-mono text-[9px] uppercase tracking-[.14em] text-[var(--vf-m2)]">
                Parámetros
              </span>
              <span className="font-mono text-[9px] text-[var(--vf-muted)] opacity-75">
                Slots · ratio · modelo
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 max-[400px]:grid-cols-1">
              <div className="col-span-2 flex flex-col gap-2 max-[400px]:col-span-1">
                <label className="font-mono text-[10px] tracking-wide text-[var(--vf-m)]">
                  Slots paralelos · <span className="font-semibold text-[var(--vf-c2)]">{slots}</span>
                </label>
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={slots}
                  onChange={(e) => setSlots(Number(e.target.value))}
                  className="w-full accent-[#a78bfa]"
                />
              </div>
              <div className="flex flex-col gap-2">
                <label className="font-mono text-[10px] tracking-wide text-[var(--vf-m)]">
                  Aspect ratio
                </label>
                <Select
                  value={aspect}
                  onChange={(value) => setAspect(value)}
                  className="flow-select"
                >
                  <SelectOption value="IMAGE_ASPECT_RATIO_LANDSCAPE">16:9 · Landscape</SelectOption>
                  <SelectOption value="IMAGE_ASPECT_RATIO_PORTRAIT">9:16 · Portrait</SelectOption>
                  <SelectOption value="IMAGE_ASPECT_RATIO_SQUARE">1:1 · Cuadrado</SelectOption>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <label className="font-mono text-[10px] tracking-wide text-[var(--vf-m)]">
                  Modelo
                </label>
                <select value={model} onChange={(e) => setModel(e.target.value)} className="flow-select">
                  <option value="NANO_BANANA_2">Nano Banana 2 · calidad</option>
                  <option value="IMAGE_GENERATION_001_IMAGEN4">Imagen 4 · rapidez</option>
                </select>
              </div>
              <div className="flex flex-col gap-2">
                <label className="font-mono text-[10px] tracking-wide text-[var(--vf-m)]">
                  Reintentos
                </label>
                <Select
                  value={maxRetries}
                  onChange={(value) => setMaxRetries(Number(value))}
                  className="flow-select"
                >
                  <SelectOption value={1}>1</SelectOption>
                  <SelectOption value={2}>2 · equilibrado</SelectOption>
                  <SelectOption value={3}>3 · máx. tolerancia</SelectOption>
                </Select>
              </div>
            </div>
          </section>

          <section className="flow-card" style={{ padding: "14px 16px" }}>
            <div className="mb-2.5 flex items-center justify-between">
              <span className="font-mono text-[11px] text-[var(--vf-m)]">{progress.label}</span>
              <span className="font-mono text-[11px] font-semibold text-[var(--vf-c2)]">{pct}%</span>
            </div>
            <div className="flow-progress-track mb-3.5">
              <div className="flow-progress-fill" style={{ width: `${pct}%` }} />
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={handleStart}
                disabled={running}
                className="flow-btn flow-btn--primary"
              >
                ⚡ Iniciar generación
              </button>
              <button
                type="button"
                onClick={handleStop}
                disabled={!running}
                className="flow-btn flow-btn--danger"
              >
                ⏹ Detener
              </button>
            </div>
            <ErrorText message={error} />

            <details className="mt-2.5 overflow-hidden rounded-[10px] border border-[var(--vf-border)] bg-[var(--vf-s)]">
              <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2 font-mono text-[9px] uppercase tracking-[.1em] text-[var(--vf-m)]">
                <span>// Perfiles Chromium</span>
                <span className="text-[8px] text-[var(--vf-m2)]">Cada perfil = cuota independiente</span>
              </summary>
              <div className="flex flex-col gap-1.5 px-2.5 pb-2.5">
                {accounts.length === 0 && chromiumProfiles.length === 0 ? (
                  <div className="font-mono text-[10px] text-[var(--vf-m2)]">Sin datos aún</div>
                ) : (
                  <>
                    {accounts.map((a, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between rounded-md border border-[var(--vf-border)] px-2 py-1"
                      >
                        <span className="font-mono text-[10px] text-[var(--vf-muted)]">
                          {a.name || `Cuenta ${i}`}
                        </span>
                        <div className="flex items-center gap-2">
                          <span
                            className="font-mono text-[9px]"
                            style={{ color: a.logged_in ? "var(--vf-c5)" : "var(--vf-m2)" }}
                          >
                            {a.logged_in ? "conectado" : "desconectado"}
                          </span>
                          <button
                            onClick={() => handleLogin(i)}
                            className="font-mono text-[9px] text-[var(--vf-c2)] underline"
                          >
                            Login
                          </button>
                        </div>
                      </div>
                    ))}
                    {chromiumProfiles.map((p, i) => (
                      <div key={`ch-${i}`} className="font-mono text-[9px] text-[var(--vf-m2)]">
                        Perfil {i}: {p.status || (p.active ? "activo" : "inactivo")}
                      </div>
                    ))}
                  </>
                )}
                <p className="px-0.5 font-mono text-[9px] text-[var(--vf-m2)]">
                  Abre un perfil con la extensión activa. Inicia sesión en Google.
                </p>
                <div className="mt-1 flex gap-2">
                  <button
                    type="button"
                    onClick={() => flowOpenAll().catch(() => {})}
                    className="flow-btn flow-btn--ghost flow-btn--xs flex-1"
                  >
                    Abrir todos
                  </button>
                  <button
                    type="button"
                    onClick={handleResetChromium}
                    className="flow-btn flow-btn--ghost flow-btn--xs flex-1"
                  >
                    Reset
                  </button>
                </div>
              </div>
            </details>
          </section>
        </div>
      </div>

      <section className="flow-card pb-4">
        <div className="mb-3 flex items-center justify-between gap-2.5">
          <span className="font-mono text-[9px] uppercase tracking-[.14em] text-[var(--vf-m2)]">
            Galería
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={refreshImages}
              className="flow-btn flow-btn--ghost flow-btn--xs"
            >
              ↺ Actualizar
            </button>
            <button
              type="button"
              onClick={() => flowAbrirCarpeta().catch(() => {})}
              className="flow-btn flow-btn--ghost flow-btn--xs"
            >
              📁
            </button>
          </div>
        </div>
        {images.length === 0 ? (
          <div className="flow-gallery-empty">Sin imágenes todavía</div>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-2.5">
            {images.map((img, i) => (
              <div key={img.key || i} className="flow-img-wrap aspect-square">
                <img src={img.src} alt={img.name || ""} loading="lazy" />
                <div className="flow-img-overlay">
                  <button
                    onClick={() => handleRetry(img, i)}
                    className="flow-retry-btn"
                    title="Reintentar"
                  >
                    ↺
                  </button>
                  <a href={img.src} download={img.name} className="flow-dl-btn">
                    ⬇
                  </a>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <details>
        <summary className="cursor-pointer font-mono text-[10px] text-[var(--vf-muted)]">
          Ver log completo
        </summary>
        <div className="mt-2">
          <LogConsole lines={logLines} />
        </div>
      </details>
    </div>
  );
}
