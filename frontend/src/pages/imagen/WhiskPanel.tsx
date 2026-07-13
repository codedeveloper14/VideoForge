import { useEffect, useRef, useState } from "react";
import {
  whiskCheckLogin,
  whiskClearImages,
  whiskClearSubject,
  whiskImages,
  whiskImageUrl,
  whiskRunPrompts,
  whiskSetSubjectFile,
  whiskStatus,
  whiskStop,
  whiskAbrirCarpeta,
} from "../../api/whisk";
import type { WhiskProfile, WhiskStatus } from "../../api/whisk";
import {
  ErrorText,
  GhostButton,
  ImageGallery,
  LogConsole,
  PrimaryButton,
  ProgressBar,
  SectionCard,
  StatBox,
  StopButton,
  countPrompts,
} from "./shared";
import type { GalleryImage } from "./shared";

const POLL_MS = 2000;

interface WhiskPanelProps {
  project: string;
  outputDir: string;
  resolvingDir: boolean;
}

export default function WhiskPanel({ outputDir, resolvingDir }: WhiskPanelProps) {
  const [prompts, setPrompts] = useState("");
  const [repeat, setRepeat] = useState<number | string>(1);
  const [slots, setSlots] = useState(1);
  const [error, setError] = useState("");

  const [running, setRunning] = useState(false);
  const [statusData, setStatusData] = useState<WhiskStatus | null>(null);
  const [accounts, setAccounts] = useState<WhiskProfile[]>([]);
  const [subjectPreview, setSubjectPreview] = useState<string | null>(null);
  const [tab, setTab] = useState("log");
  const [images, setImages] = useState<GalleryImage[]>([]);
  const [logLines, setLogLines] = useState<string[]>([]);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function refreshImages() {
    whiskImages()
      .then((data) => {
        const names = Array.isArray(data) ? data : data.images || [];
        setImages(
          names.map((n) => ({ key: n, name: n, src: whiskImageUrl(n) + `?t=${Date.now()}` })),
        );
      })
      .catch(() => {});
  }

  function pollStatus() {
    whiskStatus()
      .then((data) => {
        setStatusData(data);
        setRunning(!!data.running);
        if (Array.isArray(data.log)) setLogLines(data.log);
        if (!data.running) {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        }
      })
      .catch(() => {});
  }

  useEffect(() => {
    // Initial fetch
    pollStatus();
    refreshImages();
    whiskCheckLogin()
      .then((data) => setAccounts(data.profiles || []))
      .catch(() => {});
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (running && !pollRef.current) {
      pollRef.current = setInterval(() => {
        pollStatus();
        refreshImages();
      }, POLL_MS);
    }
    return () => {
      if (!running && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);

  async function handleCheckLogin() {
    try {
      const data = await whiskCheckLogin();
      setAccounts(data.profiles || []);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleSubjectFile(file: File | undefined) {
    if (!file) return;
    try {
      await whiskSetSubjectFile(file);
      setSubjectPreview(URL.createObjectURL(file));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleClearSubject() {
    try {
      await whiskClearSubject();
      setSubjectPreview(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleStart() {
    setError("");
    if (!prompts.trim()) {
      setError("Escribe al menos un prompt.");
      return;
    }
    if (!outputDir) {
      setError("Selecciona un proyecto activo. Las imágenes se guardan en la carpeta de imágenes del proyecto.");
      return;
    }
    try {
      await whiskRunPrompts({
        prompts,
        slots,
        repeat: Number(repeat) || 1,
        output_dir: outputDir,
      });
      setRunning(true);
      pollStatus();
      refreshImages();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleStop() {
    try {
      await whiskStop();
      setRunning(false);
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      pollStatus();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleClearImages() {
    try {
      await whiskClearImages();
      setImages([]);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const total = statusData?.total ?? 0;
  const processed = statusData?.processed ?? 0;
  const savedImages = statusData?.images ?? images.length;
  const rate = statusData?.rate ?? "—";
  const pct = total ? Math.round((processed / total) * 100) : 0;

  return (
    <div>
      <p className="mb-4 max-w-xl font-mono text-xs leading-relaxed text-[var(--vf-muted)]">
        Genera imágenes con Google Whisk y guárdalas en la carpeta del proyecto.
      </p>

      <div className="mb-4 grid grid-cols-[260px_1fr] gap-4 max-lg:grid-cols-1">
        <div className="flex flex-col gap-3">
          <SectionCard title="// Cuentas Google">
            <div className="flex flex-col gap-1.5">
              {accounts.length === 0 ? (
                <div className="font-mono text-[10px] text-[var(--vf-m2)]">Sin datos aún</div>
              ) : (
                accounts.map((a, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-md border border-[var(--vf-border)] bg-[var(--vf-p)] px-2 py-1"
                  >
                    <span className="font-mono text-[10px] text-[var(--vf-muted)]">
                      {a.name || `Cuenta ${i}`}
                    </span>
                    <span
                      className="font-mono text-[9px]"
                      style={{ color: a.logged_in || a.active ? "var(--vf-c5)" : "var(--vf-m2)" }}
                    >
                      {a.logged_in || a.active ? "conectado" : "desconectado"}
                    </span>
                  </div>
                ))
              )}
              <GhostButton onClick={handleCheckLogin} className="mt-1 w-full">
                Verificar sesiones
              </GhostButton>
            </div>
          </SectionCard>

          <SectionCard title="// Imagen sujeto (opcional)">
            <div
              onClick={() => fileInputRef.current?.click()}
              className="relative cursor-pointer rounded-lg border-2 border-dashed border-[var(--vf-b2)] bg-[rgba(var(--vf-fg-rgb),0.02)] p-3 text-center"
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => handleSubjectFile(e.target.files?.[0])}
              />
              {subjectPreview ? (
                <>
                  <img
                    src={subjectPreview}
                    alt="sujeto"
                    className="mb-1 h-[70px] w-full rounded object-contain"
                  />
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleClearSubject();
                    }}
                    className="absolute right-1 top-1 flex h-[18px] w-[18px] items-center justify-center rounded-full border border-red-400/40 bg-red-500/20 text-[9px] text-red-400"
                  >
                    ✕
                  </button>
                </>
              ) : (
                <div className="font-mono text-[10px] text-[var(--vf-m2)]">
                  Arrastra imagen o clic
                </div>
              )}
            </div>
          </SectionCard>

          <div className="rounded-lg border border-[var(--vf-c1)]/20 bg-[var(--vf-c1)]/[0.07] p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                Slots simultáneos
              </span>
              <span className="font-mono text-lg font-bold text-[var(--vf-c2)]">{slots}</span>
            </div>
            <input
              type="range"
              min={1}
              max={12}
              value={slots}
              onChange={(e) => setSlots(Number(e.target.value))}
              className="w-full accent-[var(--vf-c2)]"
            />
          </div>
        </div>

        <div className="flex flex-col gap-3">
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

          <SectionCard
            title="// Prompts"
            right={
              <span className="font-mono text-[9px] text-[var(--vf-m2)]">
                {countPrompts(prompts)} prompts
              </span>
            }
          >
            <textarea
              value={prompts}
              onChange={(e) => setPrompts(e.target.value)}
              placeholder={"Un prompt por línea.\nEjemplo:\nA cinematic portrait of a woman in golden hour light"}
              className="min-h-[140px] w-full resize-y rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] p-2.5 font-mono text-[11px] leading-relaxed text-[var(--vf-text)] outline-none"
            />
            <div className="mt-2 grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                  Repeticiones
                </label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={repeat}
                  onChange={(e) => setRepeat(e.target.value)}
                  className="w-full rounded-md border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] px-2.5 py-1.5 font-mono text-xs text-[var(--vf-text)] outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                  Total estimado
                </label>
                <div className="py-1 font-mono text-lg font-bold text-[var(--vf-c2)]">
                  {countPrompts(prompts) * (Number(repeat) || 1)}
                </div>
              </div>
            </div>
          </SectionCard>

          <div className="flex gap-2.5">
            <PrimaryButton onClick={handleStart} disabled={running}>
              ⚡ Iniciar generación
            </PrimaryButton>
            <StopButton onClick={handleStop} disabled={!running}>
              ⏹ Detener
            </StopButton>
            <GhostButton onClick={handleClearImages}>🗑</GhostButton>
            <GhostButton onClick={() => whiskAbrirCarpeta().catch(() => {})}>📁</GhostButton>
          </div>
          <ErrorText message={error} />
        </div>
      </div>

      <div className="mb-4 rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-3.5">
        <div className="mb-3 grid grid-cols-4 gap-2">
          <StatBox value={processed} label="Procesados" />
          <StatBox value={savedImages} label="Imágenes" color="var(--vf-c5)" />
          <StatBox value={total} label="Total" />
          <StatBox value={rate} label="Img/min" color="var(--vf-c2)" />
        </div>
        <ProgressBar pct={pct} />
        <div className="flex justify-between font-mono text-[10px] text-[var(--vf-m2)]">
          <span>
            {processed} / {total}
          </span>
          <span>{pct}%</span>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)]">
        <div className="flex border-b border-[var(--vf-border)] px-3">
          <button
            onClick={() => setTab("log")}
            className={
              "border-b-2 px-3 py-2.5 font-mono text-[10px] " +
              (tab === "log" ? "border-[var(--vf-c1)] text-[var(--vf-text)]" : "border-transparent text-[var(--vf-muted)]")
            }
          >
            Terminal
          </button>
          <button
            onClick={() => setTab("gal")}
            className={
              "border-b-2 px-3 py-2.5 font-mono text-[10px] " +
              (tab === "gal" ? "border-[var(--vf-c1)] text-[var(--vf-text)]" : "border-transparent text-[var(--vf-muted)]")
            }
          >
            Galería ({images.length})
          </button>
        </div>
        <div className="p-3">
          {tab === "log" ? (
            <LogConsole lines={logLines} />
          ) : (
            <div className="h-[240px] overflow-y-auto">
              <ImageGallery images={images} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
