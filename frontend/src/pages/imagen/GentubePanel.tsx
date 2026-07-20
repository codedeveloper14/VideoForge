import { useEffect, useRef, useState } from "react";
import { Select, SelectOption } from "../../components/Select";
import {
  gentubeCheckLogin,
  gentubeClearImages,
  gentubeImages,
  gentubeImageUrl,
  gentubeLogin,
  gentubeReset,
  gentubeRunPrompts,
  gentubeStatus,
  gentubeStop,
} from "../../api/gentube";
import type { GentubeProfile, GentubeStatus } from "../../api/gentube";
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
import { useGenerationStatus } from "../../context/GenerationStatusContext";

const POLL_MS = 2000;

interface GentubePanelProps {
  project: string;
  outputDir: string;
  resolvingDir: boolean;
}

export default function GentubePanel({ outputDir, resolvingDir }: GentubePanelProps) {
  const [prompts, setPrompts] = useState("");
  const [repeat, setRepeat] = useState<number | string>(1);
  const [slots, setSlots] = useState(1);
  const [ratio, setRatio] = useState("1:1");
  const [quality, setQuality] = useState("standard");

  const [running, setRunning] = useState(false);
  const [statusData, setStatusData] = useState<GentubeStatus | null>(null);
  const [accounts, setAccounts] = useState<GentubeProfile[]>([]);
  const [tab, setTab] = useState("log");
  const [images, setImages] = useState<GalleryImage[]>([]);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [loggingIn, setLoggingIn] = useState<number | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const genStatus = useGenerationStatus();
  const GEN_ID = "imagen:gentube";

  function refreshImages() {
    gentubeImages()
      .then((data) => {
        const names = Array.isArray(data) ? data : data.images || [];
        setImages(
          names.map((n) => ({ key: n, name: n, src: gentubeImageUrl(n) + `?t=${Date.now()}` })),
        );
      })
      .catch(() => {});
  }

  function pollStatus() {
    gentubeStatus()
      .then((data) => {
        setStatusData(data);
        setRunning(!!data.running);
        if (Array.isArray(data.log)) setLogLines(data.log);
        const total = data.total ?? 0;
        const processed = data.processed ?? 0;
        if (data.running) {
          genStatus.update(GEN_ID, {
            pct: total > 0 ? Math.round((processed / total) * 100) : null,
            message: `${processed}/${total} procesados`,
          });
        }
        if (!data.running) {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          genStatus.finish(GEN_ID, true, "Completado.");
        }
      })
      .catch(() => {});
  }

  function loadAccounts() {
    gentubeCheckLogin()
      .then((data) => setAccounts(data.profiles || []))
      .catch(() => {});
  }

  useEffect(() => {
    pollStatus();
    refreshImages();
    loadAccounts();
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
    genStatus.start(GEN_ID, "Imágenes · GenTube", "Iniciando...");
    try {
      await gentubeRunPrompts({
        prompts: list,
        slots,
        repeat: Number(repeat) || 1,
        output_dir: outputDir,
        ratio,
        quality,
      });
      setRunning(true);
      pollStatus();
      refreshImages();
    } catch (err) {
      setError((err as Error).message);
      genStatus.finish(GEN_ID, false, (err as Error).message);
    }
  }

  async function handleStop() {
    try {
      await gentubeStop();
      setRunning(false);
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      genStatus.finish(GEN_ID, false, "Detenido por el usuario.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleLogin(idx: number) {
    setLoggingIn(idx);
    setError("");
    try {
      await gentubeLogin({ profile: idx });
      loadAccounts();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoggingIn(null);
    }
  }

  async function handleReset() {
    if (!confirm("¿Reiniciar el estado de Gentube?")) return;
    try {
      await gentubeReset();
      pollStatus();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleClearImages() {
    try {
      await gentubeClearImages();
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
      <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),.03)] px-3 py-1 font-mono text-[9.5px] uppercase tracking-widest text-[var(--vf-muted)]">
        <span
          className="h-[5px] w-[5px] rounded-full"
          style={{ background: "var(--vf-c5)", boxShadow: "0 0 6px var(--vf-c5)" }}
        />
        Módulo 03 · GenTube
        <span
          className="rounded-full border px-1.5 py-[1px] font-mono text-[8px] font-semibold normal-case tracking-wider"
          style={{
            background: "rgba(34,197,94,.15)",
            color: "#22c55e",
            borderColor: "rgba(34,197,94,.3)",
          }}
        >
          Chromium
        </span>
      </div>
      <h1 className="mb-3 text-3xl font-extrabold tracking-tight sm:text-4xl">
        Generación de{" "}
        <span
          className="bg-clip-text text-transparent"
          style={{
            backgroundImage:
              "linear-gradient(110deg, var(--vf-c2) 0%, var(--vf-c1) 40%, var(--vf-c3) 85%)",
          }}
        >
          Imágenes
        </span>{" "}
        con GenTube
      </h1>
      <p className="mb-6 max-w-xl font-mono text-xs leading-relaxed text-[var(--vf-muted)]">
        Genera imágenes con GenTube (perfiles Chromium) y guárdalas directamente en la carpeta del
        proyecto.
      </p>

      <div className="mb-4 grid grid-cols-[260px_1fr] gap-4 max-lg:grid-cols-1">
        <div className="flex flex-col gap-3">
          <SectionCard
            title="// Cuentas"
            right={
              <button
                onClick={loadAccounts}
                className="font-mono text-[9px] text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
              >
                ↺ Actualizar
              </button>
            }
          >
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
                    <div className="flex items-center gap-2">
                      <span
                        className="font-mono text-[9px]"
                        style={{ color: a.logged_in ? "var(--vf-c5)" : "var(--vf-m2)" }}
                      >
                        {a.logged_in ? "conectado" : "desconectado"}
                      </span>
                      <button
                        onClick={() => handleLogin(i)}
                        disabled={loggingIn === i}
                        className="font-mono text-[9px] text-[var(--vf-c2)] underline disabled:opacity-50"
                      >
                        {loggingIn === i ? "Abriendo…" : "Login"}
                      </button>
                    </div>
                  </div>
                ))
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

          <SectionCard title="// Formato">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                  Ratio
                </label>
                <Select
                  value={ratio}
                  onChange={(v) => setRatio(v)}
                  className="w-full rounded-md border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] px-2 py-1.5 font-mono text-xs text-[var(--vf-text)] outline-none"
                >
                  <SelectOption value="1:1">1:1</SelectOption>
                  <SelectOption value="16:9">16:9</SelectOption>
                  <SelectOption value="9:16">9:16</SelectOption>
                </Select>
              </div>
              <div>
                <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                  Calidad
                </label>
                <Select
                  value={quality}
                  onChange={(v) => setQuality(v)}
                  className="w-full rounded-md border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] px-2 py-1.5 font-mono text-xs text-[var(--vf-text)] outline-none"
                >
                  <SelectOption value="standard">Standard</SelectOption>
                  <SelectOption value="high">High</SelectOption>
                </Select>
              </div>
            </div>
          </SectionCard>
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
              placeholder={"Un prompt por línea."}
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
            <GhostButton onClick={handleReset}>↺ Reset</GhostButton>
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
