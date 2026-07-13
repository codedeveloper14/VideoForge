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
import {
  ErrorText,
  GhostButton,
  ImageGallery,
  LogConsole,
  PrimaryButton,
  ProgressBar,
  SectionCard,
  StopButton,
  countPrompts,
} from "./shared";
import type { GalleryImage } from "./shared";

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
    <div>
      <p className="mb-4 max-w-2xl font-mono text-xs leading-relaxed text-[var(--vf-muted)]">
        Generación por lotes con Google Flow (Labs). Las imágenes se guardan en la carpeta de
        imágenes del proyecto activo.
      </p>

      <div className="mb-4 flex items-center gap-2 rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface)] px-3 py-2">
        <span className="font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
          Destino:
        </span>
        <span className="flex-1 truncate font-mono text-[11px] text-[var(--vf-c5)]">
          {resolvingDir
            ? "Resolviendo carpeta del proyecto…"
            : outputDir || "— selecciona un proyecto arriba —"}
        </span>
      </div>

      <div className="mb-4 grid grid-cols-[1.35fr_460px] gap-4 max-[1040px]:grid-cols-1">
        <div className="flex flex-col gap-3.5">
          <SectionCard
            title={`Prompts · ${countPrompts(prompts)}`}
            right={
              <button onClick={() => setPrompts("")} className="font-mono text-[10px] text-[var(--vf-muted)]">
                ✕ Vaciar
              </button>
            }
          >
            <textarea
              value={prompts}
              onChange={(e) => setPrompts(e.target.value)}
              placeholder={"Un prompt por línea. Ejemplo:\nCinematic wide shot, golden hour, anamorphic flare"}
              className="min-h-[176px] w-full resize-y rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] p-3 font-mono text-xs leading-relaxed text-[var(--vf-text)] outline-none"
            />
          </SectionCard>

          <SectionCard title="Referencia visual" right={<span className="font-mono text-[9px] text-[var(--vf-muted)]">Opcional · guía de estilo</span>}>
            <input
              ref={refInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleRefFileChange}
            />
            {referenceImage ? (
              <div className="flex items-center gap-3 rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] p-2.5">
                <img src={referenceImage} alt="" className="h-16 w-16 rounded-md object-cover" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-[10px] text-[var(--vf-text)]">{referenceImageName}</p>
                  <button
                    onClick={() => refInputRef.current?.click()}
                    className="font-mono text-[10px] text-[var(--vf-c2)] underline"
                  >
                    Reemplazar
                  </button>
                </div>
                <button
                  onClick={() => {
                    setReferenceImage("");
                    setReferenceImageName("");
                    if (refInputRef.current) refInputRef.current.value = "";
                  }}
                  className="rounded-full px-2 py-1 font-mono text-xs text-[var(--vf-danger)]"
                  aria-label="Quitar"
                >
                  ×
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => refInputRef.current?.click()}
                className="flex w-full flex-col items-center gap-1 rounded-lg border border-dashed border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.02)] px-3 py-5 text-center transition-colors hover:border-[var(--vf-c2)]"
              >
                <span className="font-mono text-[11px] text-[var(--vf-text)]">Adjuntar imagen</span>
                <span className="font-mono text-[9px] text-[var(--vf-muted)]">
                  Haz clic para elegir · JPG, PNG, WebP
                </span>
              </button>
            )}
          </SectionCard>
        </div>

        <div className="flex flex-col gap-3.5">
          <SectionCard title="Parámetros">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="mb-1.5 block font-mono text-[10px] text-[var(--vf-muted)]">
                  Slots paralelos · <span className="text-[var(--vf-c2)]">{slots}</span>
                </label>
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={slots}
                  onChange={(e) => setSlots(Number(e.target.value))}
                  className="w-full accent-[var(--vf-c2)]"
                />
              </div>
              <div>
                <label className="mb-1.5 block font-mono text-[10px] text-[var(--vf-muted)]">
                  Aspect ratio
                </label>
                <Select
                  value={aspect}
                  onChange={(v) => setAspect(v)}
                  className="w-full rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] px-2.5 py-2 font-mono text-xs text-[var(--vf-text)] outline-none"
                >
                  <SelectOption value="IMAGE_ASPECT_RATIO_LANDSCAPE">16:9 · Landscape</SelectOption>
                  <SelectOption value="IMAGE_ASPECT_RATIO_PORTRAIT">9:16 · Portrait</SelectOption>
                  <SelectOption value="IMAGE_ASPECT_RATIO_SQUARE">1:1 · Cuadrado</SelectOption>
                </Select>
              </div>
              <div>
                <label className="mb-1.5 block font-mono text-[10px] text-[var(--vf-muted)]">
                  Modelo
                </label>
                <Select
                  value={model}
                  onChange={(v) => setModel(v)}
                  className="w-full rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] px-2.5 py-2 font-mono text-xs text-[var(--vf-text)] outline-none"
                >
                  <SelectOption value="NANO_BANANA_2">Nano Banana 2 · calidad</SelectOption>
                  <SelectOption value="IMAGE_GENERATION_001_IMAGEN4">Imagen 4 · rapidez</SelectOption>
                </Select>
              </div>
              <div>
                <label className="mb-1.5 block font-mono text-[10px] text-[var(--vf-muted)]">
                  Reintentos
                </label>
                <Select
                  value={maxRetries}
                  onChange={(v) => setMaxRetries(Number(v))}
                  className="w-full rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] px-2.5 py-2 font-mono text-xs text-[var(--vf-text)] outline-none"
                >
                  <SelectOption value={1}>1</SelectOption>
                  <SelectOption value={2}>2 · equilibrado</SelectOption>
                  <SelectOption value={3}>3 · máx. tolerancia</SelectOption>
                </Select>
              </div>
            </div>
          </SectionCard>

          <SectionCard>
            <div className="mb-2.5 flex items-center justify-between">
              <span className="font-mono text-[11px] text-[var(--vf-muted)]">{progress.label}</span>
              <span className="font-mono text-[11px] font-semibold text-[var(--vf-c2)]">{pct}%</span>
            </div>
            <ProgressBar pct={pct} />
            <div className="mt-3 flex gap-3">
              <PrimaryButton onClick={handleStart} disabled={running}>
                ⚡ Iniciar generación
              </PrimaryButton>
              <StopButton onClick={handleStop} disabled={!running}>
                ⏹ Detener
              </StopButton>
            </div>
            <ErrorText message={error} />

            <details className="mt-3 overflow-hidden rounded-lg border border-[var(--vf-border)] bg-[var(--vf-p)]">
              <summary className="cursor-pointer px-3 py-2 font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                // Cuentas / Perfiles Chromium
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
                <div className="mt-1 flex gap-2">
                  <GhostButton onClick={() => flowOpenAll().catch(() => {})} className="flex-1">
                    Abrir todos
                  </GhostButton>
                  <GhostButton onClick={handleResetChromium} className="flex-1">
                    Reset
                  </GhostButton>
                </div>
              </div>
            </details>
          </SectionCard>
        </div>
      </div>

      <SectionCard
        title="Galería"
        right={
          <div className="flex gap-2">
            <GhostButton onClick={refreshImages}>↺ Actualizar</GhostButton>
            <GhostButton onClick={() => flowAbrirCarpeta().catch(() => {})}>📁</GhostButton>
          </div>
        }
        className="mb-4"
      >
        <ImageGallery
          images={images}
          renderOverlay={(img) => (
            <>
              <button
                onClick={() => handleRetry(img, images.indexOf(img))}
                className="rounded bg-[var(--vf-c1)]/90 px-2 py-1 text-[11px] font-bold text-white"
              >
                ↺
              </button>
              <a
                href={img.src}
                download={img.name}
                className="rounded bg-[var(--vf-c1)]/90 px-2 py-1 text-[11px] font-bold text-white"
              >
                ⬇
              </a>
            </>
          )}
        />
      </SectionCard>

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
