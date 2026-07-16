import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  SectionCard,
  ProgressBar,
  LogConsole,
  TerminalCard,
  PrimaryButton,
  StopButton,
  GhostButton,
  ErrorText,
  ImageSlots,
  AccountSessions,
  SlotPicker,
  VideoGallery,
} from "./shared";
import type { AccountSessionInfo } from "./shared";
import ConfirmModal from "../../components/ConfirmModal";

const LOG_POLL_MS = 1200;
const GALLERY_POLL_MS = 4000;

export interface ProviderSesionesResult {
  accounts?: AccountSessionInfo[];
}

export interface ProviderIniciarParams {
  project_name: string;
  prompt?: string;
  slots?: number;
  images: File[];
  [key: string]: unknown;
}

export interface ProviderIniciarResult {
  project_dir?: string;
  project_name?: string;
  pid?: number | string;
}

export interface ProviderRegenerarParams {
  video_name: string;
  project_name: string;
  prompt?: string;
  [key: string]: unknown;
}

export interface ProviderRegenerarResult {
  ok: boolean;
  error?: string;
}

export interface ProviderLogResult {
  lines?: string[];
  next_offset?: number;
  finished?: boolean;
}

export interface ProviderVideosResult {
  videos?: string[];
  done?: number;
  total?: number;
}

// Shape of the per-provider API bundle passed into ProviderPanel.
export interface ProviderApi {
  sesiones: () => Promise<ProviderSesionesResult>;
  loginCuenta: (account: string) => Promise<{ ok: boolean }>;
  borrarSesion: (account: string) => Promise<{ ok: boolean }>;
  iniciar: (params: ProviderIniciarParams) => Promise<ProviderIniciarResult>;
  regenerar?: (params: ProviderRegenerarParams) => Promise<ProviderRegenerarResult>;
  detener: () => Promise<{ ok: boolean }>;
  log: (offset: number) => Promise<ProviderLogResult>;
  videos: (project: string) => Promise<ProviderVideosResult>;
  videoUrl: (project: string, file: string, dl?: number) => string;
  descargarTodasUrl: (project: string) => string;
  abrirCarpeta: (project: string) => Promise<unknown>;
}

export type ProviderOptions = Record<string, unknown>;

export interface ExtraOptionsArgs {
  options: ProviderOptions;
  setOption: (key: string, value: unknown) => void;
}

export interface ProviderPanelProps {
  project: string;
  providerLabel: string;
  api: ProviderApi;
  defaultSlots?: number;
  maxSlots?: number;
  extraOptions?: (args: ExtraOptionsArgs) => ReactNode;
  initialOptions?: ProviderOptions;
  extraActions?: () => ReactNode;
  supportsRegenerate?: boolean;
  // Vibes genera video+imagen desde el prompt en un solo paso — no anima
  // imagenes subidas, a diferencia de Grok/Qwen/Meta. showImages=false oculta
  // la seccion de imagenes y usa `slots` (en vez de images.length) como el
  // total de la barra de progreso.
  showImages?: boolean;
}

// Generic panel shared by Grok / Qwen / Vibes — the backends are near-identical
// in shape (sesiones/login_cuenta/borrar_sesion/iniciar/detener/log/videos/video/
// descargar_todas/abrir_carpeta). Provider-specific bits (extra iniciar fields,
// regenerar support, extra actions, whether images apply at all) are injected via
// props.
export default function ProviderPanel({
  project,
  providerLabel,
  api,
  defaultSlots = 3,
  maxSlots = 12,
  extraOptions,
  initialOptions = {},
  extraActions,
  supportsRegenerate = false,
  showImages = true,
}: ProviderPanelProps) {
  const { t } = useTranslation();
  const [images, setImages] = useState<File[]>([]);
  const [prompt, setPrompt] = useState("Cinematic slow zoom");
  const [slots, setSlots] = useState(defaultSlots);
  const [options, setOptions] = useState<ProviderOptions>(initialOptions);

  const [accounts, setAccounts] = useState<AccountSessionInfo[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [accountsError, setAccountsError] = useState("");

  const [running, setRunning] = useState(false);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [videos, setVideos] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [projectDir, setProjectDir] = useState("");
  const [deleteSessionTarget, setDeleteSessionTarget] = useState<string | null>(null);

  const logOffsetRef = useRef<number>(0);
  const logTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const galleryTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const currentProjectRef = useRef(project);
  const totalImagesRef = useRef(0);

  const setOption = useCallback((key: string, value: unknown) => {
    setOptions((prev) => ({ ...prev, [key]: value }));
  }, []);

  // ── Sessions ──────────────────────────────────────────────────
  const loadSesiones = useCallback(() => {
    setAccountsLoading(true);
    setAccountsError("");
    api
      .sesiones()
      .then((d) => setAccounts(d.accounts || []))
      .catch((err) => setAccountsError((err as Error).message))
      .finally(() => setAccountsLoading(false));
  }, [api]);

  useEffect(() => {
    loadSesiones();
    return () => {
      if (logTimerRef.current) clearInterval(logTimerRef.current);
      if (galleryTimerRef.current) clearInterval(galleryTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleLogin(account: string) {
    api
      .loginCuenta(account)
      .then(() => appendLog(t("providerPanel.chromeOpenedFor", { account })))
      .catch((err) => appendLog(t("providerPanel.errorPrefix", { message: (err as Error).message })));
  }

  function handleDeleteSession(account: string) {
    setDeleteSessionTarget(account);
  }

  function performDeleteSession() {
    const account = deleteSessionTarget;
    if (!account) return;
    setDeleteSessionTarget(null);
    api
      .borrarSesion(account)
      .then(() => {
        loadSesiones();
        appendLog(t("providerPanel.sessionDeleted", { account }));
      })
      .catch((err) => appendLog(t("providerPanel.errorPrefix", { message: (err as Error).message })));
  }

  // ── Load videos when project changes ─────────────────────────
  useEffect(() => {
    currentProjectRef.current = project;
    setVideos([]);
    setProgress({ done: 0, total: 0 });
    if (!project) return;
    api
      .videos(project)
      .then((d) => setVideos(d.videos || []))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  // ── Log ───────────────────────────────────────────────────────
  function appendLog(line: string) {
    setLogLines((prev) => [...prev, line]);
  }

  function clearLog() {
    setLogLines([]);
    logOffsetRef.current = 0;
  }

  // ── Polling ───────────────────────────────────────────────────
  function stopPolling() {
    if (logTimerRef.current) clearInterval(logTimerRef.current);
    if (galleryTimerRef.current) clearInterval(galleryTimerRef.current);
    logTimerRef.current = null;
    galleryTimerRef.current = null;
  }

  const pollGallery = useCallback(() => {
    const proj = currentProjectRef.current;
    if (!proj) return;
    api
      .videos(proj)
      .then((d) => {
        setVideos(d.videos || []);
        const total = d.total || totalImagesRef.current;
        setProgress({ done: d.done || 0, total });
      })
      .catch(() => {});
  }, [api]);

  const pollLog = useCallback(() => {
    api
      .log(logOffsetRef.current)
      .then((d) => {
        if (d.lines && d.lines.length) {
          setLogLines((prev) => [...prev, ...(d.lines as string[])]);
        }
        logOffsetRef.current = d.next_offset ?? logOffsetRef.current;
        if (d.finished) {
          setRunning(false);
          stopPolling();
          pollGallery();
          appendLog(t("providerPanel.processCompleted"));
        }
      })
      .catch(() => {});
  }, [api, pollGallery]);

  function startPolling() {
    stopPolling();
    logTimerRef.current = setInterval(pollLog, LOG_POLL_MS);
    pollGallery();
    galleryTimerRef.current = setInterval(pollGallery, GALLERY_POLL_MS);
  }

  // ── Start / stop ──────────────────────────────────────────────
  async function handleStart() {
    if (running) {
      try {
        await api.detener();
        appendLog(t("providerPanel.stoppedByUser"));
      } catch (err) {
        appendLog(t("providerPanel.errorPrefix", { message: (err as Error).message }));
      }
      setRunning(false);
      stopPolling();
      return;
    }

    setError("");
    if (!project) {
      setError(t("providerPanel.selectProjectFirst"));
      return;
    }
    if (showImages && images.length === 0) {
      setError(t("providerPanel.uploadAtLeastOneImage"));
      return;
    }
    if (!showImages && !prompt.trim()) {
      setError(t("providerPanel.writePromptFirst"));
      return;
    }

    const total = showImages ? images.length : slots;
    totalImagesRef.current = total;
    clearLog();
    setProgress({ done: 0, total });
    if (showImages) {
      appendLog(t("providerPanel.uploadingImagesToProject", { count: images.length, project }));
    }

    try {
      const d = await api.iniciar({
        project_name: project,
        prompt: prompt.trim() || undefined,
        slots,
        images,
        ...options,
      });
      setProjectDir(d.project_dir || "");
      setRunning(true);
      appendLog(t("providerPanel.startedProjectPid", { project: d.project_name || project, pid: d.pid ?? "?" }));
      logOffsetRef.current = 0;
      startPolling();
    } catch (err) {
      setError((err as Error).message);
      appendLog(t("providerPanel.errorPrefix", { message: (err as Error).message }));
    }
  }

  async function handleRegenerate(videoName: string) {
    if (!supportsRegenerate || !api.regenerar) return;
    appendLog(t("providerPanel.regenerating", { name: videoName }));
    try {
      const d = await api.regenerar({
        video_name: videoName,
        project_name: project,
        prompt,
        ...options,
      });
      if (d.ok) {
        appendLog(t("providerPanel.regeneratingInBackground", { name: videoName }));
        if (!galleryTimerRef.current) {
          galleryTimerRef.current = setInterval(pollGallery, GALLERY_POLL_MS);
        }
        if (!logTimerRef.current) {
          logTimerRef.current = setInterval(pollLog, LOG_POLL_MS);
        }
      } else {
        appendLog(t("providerPanel.errorPrefix", { message: d.error || t("providerPanel.unknownError") }));
      }
    } catch (err) {
      appendLog(t("providerPanel.errorPrefix", { message: (err as Error).message }));
    }
  }

  function handleDownloadAll() {
    if (!project) return;
    const a = document.createElement("a");
    a.href = api.descargarTodasUrl(project);
    a.download = `${project}_videos.zip`;
    a.click();
  }

  async function handleOpenFolder() {
    try {
      await api.abrirCarpeta(project);
    } catch (err) {
      appendLog(`Error: ${(err as Error).message}`);
    }
  }

  const pct =
    progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;
  const allDone = progress.total > 0 && progress.done >= progress.total;

  return (
    <div>
      <div className={"grid grid-cols-1 gap-4" + (showImages ? " lg:grid-cols-2" : "")}>
        {showImages && (
          <SectionCard
            title={t("providerPanel.images")}
            right={
              images.length > 0 ? (
                <span className="font-mono text-[10px] text-[var(--vf-c5)]">
                  {images.length} cargada{images.length !== 1 ? "s" : ""}
                </span>
              ) : undefined
            }
          >
            <ImageSlots files={images} onChange={setImages} />
          </SectionCard>
        )}

        <SectionCard title={t("providerPanel.configuration")}>
          <div className="mb-3">
            <label className="mb-1 block font-mono text-[9.5px] uppercase tracking-wider text-[var(--vf-muted)]">
              {t("providerPanel.activeProject")}
            </label>
            <div className="py-1 font-mono text-xs font-semibold text-[var(--vf-c2)]">
              {project || t("providerPanel.selectInTopbar")}
            </div>
          </div>

          <label className="mb-1 block font-mono text-[9.5px] uppercase tracking-wider text-[var(--vf-muted)]">
            {t("providerPanel.animationPrompt")}
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={2}
            placeholder={t("providerPanel.animationPromptPlaceholder") || ""}
            className="w-full rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.04)] px-3.5 py-2.5 font-mono text-xs text-[var(--vf-text)] outline-none transition-colors placeholder:text-[var(--vf-m2)] focus:border-[color-mix(in_srgb,var(--vf-c1)_40%,transparent)]"
          />

          <div className="mt-4">
            <label className="mb-2 block font-mono text-[9.5px] uppercase tracking-wider text-[var(--vf-muted)]">
              {t("providerPanel.simultaneousSlots")}{" "}
              <span className="text-[var(--vf-c2)]">{slots}</span> {t("providerPanel.inParallel")}
            </label>
            <SlotPicker value={slots} onChange={setSlots} max={maxSlots} />
          </div>

          {extraOptions && (
            <div className="mt-4 border-t border-[var(--vf-border)] pt-3">
              {extraOptions({ options, setOption })}
            </div>
          )}

          <div className="mt-4 border-t border-[var(--vf-border)] pt-3">
            <AccountSessions
              accounts={accounts}
              loading={accountsLoading}
              error={accountsError}
              onLogin={handleLogin}
              onDelete={handleDeleteSession}
              onRefresh={loadSesiones}
            />
          </div>

          {extraActions && <div className="mt-4 border-t border-[var(--vf-border)] pt-3">{extraActions()}</div>}
        </SectionCard>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-4">
        <PrimaryButton
          onClick={handleStart}
          disabled={!running && (showImages ? images.length === 0 : !prompt.trim())}
          className={
            (running ? "flex-none" : "flex-1 sm:flex-none") +
            " inline-flex items-center justify-center gap-2 !rounded-[10px] !px-7 !py-3 text-[11.5px] uppercase tracking-[.06em] shadow-[0_4px_18px_rgba(124,106,255,.4)] hover:enabled:-translate-y-0.5 hover:enabled:shadow-[0_8px_28px_rgba(124,106,255,.55)]" +
            (running ? " !bg-gradient-to-br !from-[#ef4444] !to-[#dc2626] !shadow-[0_4px_18px_rgba(239,68,68,.4)]" : "")
          }
        >
          {running ? t("providerPanel.processing") : t("providerPanel.startAnimation", { label: providerLabel })}
        </PrimaryButton>
        {running && <StopButton onClick={handleStart} />}
        <div className="font-mono text-[10px] leading-[1.6] text-[var(--vf-muted)]">
          {showImages
            ? images.length === 0
              ? t("providerPanel.uploadImagesToStart")
              : t("providerPanel.imagesReadyCount", { count: images.length })
            : t("providerPanel.batchesReadyCount", { count: slots })}
          {projectDir && (
            <div className="mt-0.5 text-[var(--vf-m2)]">📁 {projectDir}</div>
          )}
        </div>
      </div>

      <ErrorText message={error} />

      {progress.total > 0 && (
        <div className="mt-4">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="font-mono text-[10px] text-[var(--vf-muted)]">{t("providerPanel.progress")}</span>
            <span className="font-mono text-[10px] text-[var(--vf-c2)]">
              {progress.done} / {progress.total} ({pct}%)
            </span>
          </div>
          <ProgressBar pct={pct} />
        </div>
      )}

      <TerminalCard
        title={t("providerPanel.liveOutputTitle", { label: providerLabel.toLowerCase() })}
        onClear={clearLog}
      >
        <LogConsole lines={logLines} />
      </TerminalCard>

      <div className="mt-6">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-mono text-[10px] uppercase tracking-[.12em] text-[var(--vf-muted)]">
            {t("providerPanel.generatedVideos")}
          </span>
          <div className="flex items-center gap-2">
            {progress.total > 0 && (
              <span className="font-mono text-[10px] text-[var(--vf-muted)]">
                {t("providerPanel.completedCount", { done: progress.done, total: progress.total })}
              </span>
            )}
            {allDone && videos.length > 0 && (
              <GhostButton
                onClick={handleDownloadAll}
                className="border-none text-white"
                style={{ background: "linear-gradient(135deg, var(--vf-c1), var(--vf-c2))" }}
              >
                {t("providerPanel.downloadAll")}
              </GhostButton>
            )}
            <GhostButton onClick={handleOpenFolder} disabled={!project}>
              {t("providerPanel.openFolder")}
            </GhostButton>
          </div>
        </div>
        <VideoGallery
          videos={videos}
          project={project}
          videoUrl={api.videoUrl}
          onRegenerate={supportsRegenerate ? handleRegenerate : undefined}
        />
      </div>

      <ConfirmModal
        visible={!!deleteSessionTarget}
        title={t("providerPanel.confirmDeleteSessionTitle")}
        message={deleteSessionTarget ? t("providerPanel.confirmDeleteSession", { account: deleteSessionTarget }) : ""}
        confirmLabel={t("providerPanel.deleteSessionButton")}
        cancelLabel={t("providerPanel.cancel")}
        onConfirm={performDeleteSession}
        onCancel={() => setDeleteSessionTarget(null)}
      />
    </div>
  );
}
