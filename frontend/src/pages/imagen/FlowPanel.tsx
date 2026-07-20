import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { Select, SelectOption } from "../../components/Select";
import {
  flowAbrirCarpeta,
  flowAccounts,
  flowBridgeStatus,
  flowImages,
  flowImageUrl,
  flowLogin,
  flowOpenAll,
  flowResetChromium,
  flowResetLock,
  flowRetry,
  flowRunPrompts,
  flowStatus,
  flowStop,
} from "../../api/flow";
import type { FlowAccount, FlowBridgeAccount, FlowBrowserMode } from "../../api/flow";
import type { ApiError } from "../../api/client";
import { ErrorText, LogConsole, countPrompts } from "./shared";
import type { GalleryImage } from "./shared";
import { HeaderArt } from "../../components/HeaderArt";
import ConfirmModal from "../../components/ConfirmModal";
import { loadScript } from "../../api/script";

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

export default function FlowPanel({ project, outputDir, resolvingDir }: FlowPanelProps) {
  const { t } = useTranslation();
  const [prompts, setPrompts] = useState("");
  const [slots, setSlots] = useState(2);
  const [aspect, setAspect] = useState("IMAGE_ASPECT_RATIO_LANDSCAPE");
  const [model, setModel] = useState("NANO_BANANA_2");
  const [maxRetries, setMaxRetries] = useState(2);
  const [referenceImage, setReferenceImage] = useState("");
  const [referenceImageName, setReferenceImageName] = useState("");
  const [browserMode, setBrowserMode] = useState<FlowBrowserMode>("auto");

  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<Progress>({ done: 0, total: 0, label: t("flowPanel.readyToGenerate") });
  const [logLines, setLogLines] = useState<string[]>([]);
  const [images, setImages] = useState<GalleryImage[]>([]);
  const [error, setError] = useState("");
  const [lockConflict, setLockConflict] = useState(false);

  const [accounts, setAccounts] = useState<FlowAccount[]>([]);
  const [noBrowserConnected, setNoBrowserConnected] = useState(false);
  const [confirmResetOpen, setConfirmResetOpen] = useState(false);

  // Estado del Puente B (extension <-> bridge WS/HTTP 5556/5557) — se consulta
  // siempre, no solo mientras corre una generacion, para que el indicador de la UI
  // se ponga verde solo con abrir Google Flow en Chrome, sin que el usuario toque
  // nada. bridgeChecked evita que el aviso "sin cuentas" parpadee antes del primer poll.
  const [bridgeAccounts, setBridgeAccounts] = useState<FlowBridgeAccount[]>([]);
  const [bridgeChecked, setBridgeChecked] = useState(false);

  const sinceRef = useRef(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // El backend acepta el job y arranca el hilo de fondo al instante (siempre
  // "responde bien"), pero _pick_account() se queda esperando en silencio si
  // ningun navegador con la extension esta conectado al bridge -- sin este
  // aviso, el usuario solo ve la barra de progreso quieta sin saber por que.
  const disconnectedSinceRef = useRef<number | null>(null);
  const NO_BROWSER_WARNING_MS = 15000;
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
      setError(t("flowPanel.chooseImageFile"));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setReferenceImage(reader.result as string);
      setReferenceImageName(file.name);
    };
    reader.onerror = () => setError(t("flowPanel.couldNotReadRefImage"));
    reader.readAsDataURL(file);
  }

  function loadAccounts() {
    flowAccounts()
      .then((d) => setAccounts(d.accounts || []))
      .catch(() => {});
  }

  // "ok" (sesion valida, via bridge WS/HTTP o cookie en disco) y "open" (hay un
  // Chromium de Playwright abierto para ese perfil) son senales independientes --
  // una cuenta conectada por el Chrome real del usuario nunca tiene "open" en true,
  // y por eso antes convivian dos listas que parecian contradecirse (conectado arriba,
  // inactivo abajo). Un solo estado combinado por cuenta evita esa lectura confusa.
  function accountStatus(a: FlowAccount): { label: string; color: string } {
    if (a.ok && a.open) return { label: t("flowPanel.connectedPlaywright"), color: "var(--vf-c5)" };
    if (a.ok) return { label: t("flowPanel.connected"), color: "var(--vf-c5)" };
    if (a.open) return { label: t("flowPanel.openingProfile"), color: "var(--vf-c2)" };
    return { label: t("flowPanel.disconnected"), color: "var(--vf-m2)" };
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
            label: d.label || (d.running ? t("flowPanel.generating") : t("flowPanel.completed")),
          });
        }
        setRunning(!!d.running);
        if (!d.running && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          disconnectedSinceRef.current = null;
          setNoBrowserConnected(false);
        }
        refreshImages();
      })
      .catch(() => {});
  }

  // Poll continuo del Puente B, siempre activo (no solo mientras corre un batch):
  // es lo que hace que "Conectado como <email>" aparezca solo con abrir Flow en
  // Chrome con la extension puesta, sin ninguna accion del usuario en esta app.
  useEffect(() => {
    // loadAccounts() (tarjetas "Perfiles Chromium") corre en el mismo poll que
    // flowBridgeStatus() (el aviso de arriba) -- antes se cargaba una sola vez al
    // montar y de nuevo al apretar "Login", pero ANTES de que el usuario terminara
    // de loguearse en la ventana de Playwright que se acababa de abrir. La tarjeta
    // quedaba pegada en "abriendo..." para siempre aunque el login ya hubiera
    // terminado y el aviso de arriba (que si refrescaba) mostrara la cuenta
    // conectada y habilitara generar.
    function pollBridge() {
      flowBridgeStatus()
        .then((d) => {
          const accs = d.accounts || [];
          setBridgeAccounts(accs);
          setBridgeChecked(true);
          const connected = accs.some((a) => a.connected);
          if (connected) {
            disconnectedSinceRef.current = null;
            setNoBrowserConnected(false);
            return;
          }
          if (disconnectedSinceRef.current === null) disconnectedSinceRef.current = Date.now();
          setNoBrowserConnected(Date.now() - disconnectedSinceRef.current > NO_BROWSER_WARNING_MS);
        })
        .catch(() => setBridgeChecked(true));
      loadAccounts();
    }
    pollBridge();
    // Sync inicial de "running" contra el backend real -- sin esto, si el batch
    // sigue corriendo (o el lock quedo colgado) de una sesion anterior, el
    // frontend arranca creyendo running=false: el poll de progreso nunca arranca,
    // el boton "Detener" queda deshabilitado, y el usuario se queda sin forma de
    // ver ni liberar el estado hasta que reintenta "Generar" y ve el 409.
    pollOnce();
    const id = setInterval(pollBridge, 2500);
    return () => {
      clearInterval(id);
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
    setLockConflict(false);
    const list = prompts
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    if (!list.length) {
      setError(t("flowPanel.writeAtLeastOnePrompt"));
      return;
    }
    if (!outputDir) {
      setError(t("flowPanel.selectActiveProject"));
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
        auto_open: true,
        browser_mode: browserMode,
      });
      setRunning(true);
      pollOnce();
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr.status === 409) {
        setError(t("flowPanel.lockConflictError"));
        setLockConflict(true);
        // El 409 significa que el backend YA tiene un batch activo -- puede ser de
        // esta misma sesion o de otra que quedo colgada; en ambos casos hay que
        // reflejarlo en el estado local para que el boton "Detener" deje de estar
        // deshabilitado (sin esto el usuario no tiene forma de intervenir).
        setRunning(true);
        pollOnce();
      } else {
        setError(apiErr.message);
      }
    }
  }

  async function handleForceResetLock() {
    try {
      await flowResetLock();
      setLockConflict(false);
      setError("");
      setRunning(false);
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleStop() {
    try {
      await flowStop();
      setRunning(false);
      setLockConflict(false);
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleLoadFromScript() {
    setError("");
    if (!project) {
      setError(t("flowPanel.selectActiveProject"));
      return;
    }
    try {
      const data = await loadScript(project);
      const loaded = typeof data.prompts === "string" ? data.prompts.trim() : "";
      if (!loaded) {
        setError(t("flowPanel.noPromptsInScript"));
        return;
      }
      setPrompts(loaded);
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
    setConfirmResetOpen(false);
    try {
      await flowResetChromium();
      loadAccounts();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const pct = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;
  const hasLiveAccount = bridgeAccounts.some((a) => a.connected);
  const showNoAccountsWarning = bridgeChecked && !hasLiveAccount;

  return (
    <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-4 px-2">
      <div
        className="relative mb-0.5 overflow-hidden rounded-2xl border border-[rgba(124,106,255,.15)] p-5"
        style={{ background: "var(--vf-surface)" }}
      >
        <div className="flex flex-shrink-0 gap-1.5 sm:absolute sm:right-5 sm:top-5">
          <span className="rounded-md border border-[rgba(124,106,255,.22)] bg-[rgba(124,106,255,.1)] px-2 py-1 text-[9px] font-bold uppercase tracking-[0.1em] text-[var(--vf-c2)]">
            {t("flowPanel.module03")}
          </span>
          <span className="rounded-md border border-[rgba(var(--vf-fg-rgb),.08)] bg-[rgba(var(--vf-fg-rgb),.04)] px-2 py-1 text-[9px] font-semibold tracking-[0.06em] text-[var(--vf-m2)]">
            {t("flowPanel.labsTag")}
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
                <div className="text-[10px] font-bold tracking-[0.18em] text-[rgba(124,106,255,.6)]">{t("flowPanel.moduleLabelFull")}</div>
                <h1 className="m-0 text-[26px] font-bold leading-[1.1] tracking-[-0.025em] text-[var(--vf-text)]">
                  {t("flowPanel.titlePart1")}{" "}
                  <span
                    className="bg-clip-text text-transparent"
                    style={{ backgroundImage: "linear-gradient(90deg,var(--vf-c2),var(--vf-c3))" }}
                  >
                    {t("flowPanel.titlePart2")}
                  </span>
                </h1>
              </div>
            </div>
            <p className="mb-3.5 max-w-[560px] text-[13.5px] leading-[1.55] text-[var(--vf-m)]">
              {t("flowPanel.subtitle")}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {[t("flowPanel.chipBatches"), t("flowPanel.chipMultiAccount"), t("flowPanel.chipVisualRef"), t("flowPanel.chipGoogleLabs")].map((chip, i) => (
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
          {t("flowPanel.destination")}
        </span>
        <span className="flex-1 truncate font-mono text-[11px] text-[var(--vf-c5)]">
          {resolvingDir
            ? t("flowPanel.resolvingProjectFolder")
            : outputDir || t("flowPanel.selectProjectAbove")}
        </span>
      </div>

      <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(320px,460px)] items-start gap-x-6 gap-y-4 max-[1040px]:grid-cols-1">
        <div className="flex w-full flex-col gap-3.5">
          <section className="flow-card">
            <div className="mb-3 flex items-center justify-between gap-2.5">
              <span className="font-mono text-[9px] uppercase tracking-[.14em] text-[var(--vf-m2)]">
                {t("flowPanel.promptsTitle", { count: countPrompts(prompts) })}
              </span>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleLoadFromScript}
                  className="flow-btn flow-btn--ghost"
                >
                  {t("flowPanel.loadFromScript")}
                </button>
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
              placeholder={t("flowPanel.promptPlaceholder") || ""}
              className="flow-textarea"
            />
          </section>

          <section className="flow-card">
            <div className="mb-3 flex items-center justify-between gap-2.5">
              <span className="font-mono text-[9px] uppercase tracking-[.14em] text-[var(--vf-m2)]">
                {t("flowPanel.visualReference")}
              </span>
              <span className="font-mono text-[9px] text-[var(--vf-muted)] opacity-75">
                {t("flowPanel.optionalStyleGuide")}
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
                      {t("flowPanel.attachedImageLabel")}
                    </div>
                    <div className="font-mono text-[9px] leading-relaxed text-[var(--vf-m2)] opacity-90">
                      {t("flowPanel.clickOrDragToReplace")}
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
                      aria-label={t("flowPanel.remove") || ""}
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
                        {t("flowPanel.attachImage")}
                      </div>
                      <span className="block font-mono text-[10px] leading-relaxed text-[var(--vf-m2)]">
                        {t("flowPanel.dragOrClickFormats")}
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
                {t("flowPanel.parameters")}
              </span>
              <span className="font-mono text-[9px] text-[var(--vf-muted)] opacity-75">
                Slots · ratio · {t("flowPanel.model").toLowerCase()}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 max-[400px]:grid-cols-1">
              <div className="col-span-2 flex flex-col gap-2 max-[400px]:col-span-1">
                <label className="font-mono text-[10px] tracking-wide text-[var(--vf-m)]">
                  {t("flowPanel.parallelSlots")} <span className="font-semibold text-[var(--vf-c2)]">{slots}</span>
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
                  {t("flowPanel.aspectRatio")}
                </label>
                <Select
                  value={aspect}
                  onChange={(value) => setAspect(value)}
                  className="flow-select"
                >
                  <SelectOption value="IMAGE_ASPECT_RATIO_LANDSCAPE">{t("flowPanel.aspectLandscape")}</SelectOption>
                  <SelectOption value="IMAGE_ASPECT_RATIO_PORTRAIT">{t("flowPanel.aspectPortrait")}</SelectOption>
                  <SelectOption value="IMAGE_ASPECT_RATIO_SQUARE">{t("flowPanel.aspectSquare")}</SelectOption>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <label className="font-mono text-[10px] tracking-wide text-[var(--vf-m)]">
                  {t("flowPanel.model")}
                </label>
                <Select value={model} onChange={setModel} className="flow-select">
                  <SelectOption value="NANO_BANANA_2">{t("flowPanel.modelQuality")}</SelectOption>
                  <SelectOption value="IMAGE_GENERATION_001_IMAGEN4">{t("flowPanel.modelSpeed")}</SelectOption>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <label className="font-mono text-[10px] tracking-wide text-[var(--vf-m)]">
                  {t("flowPanel.retries")}
                </label>
                <Select
                  value={maxRetries}
                  onChange={(value) => setMaxRetries(Number(value))}
                  className="flow-select"
                >
                  <SelectOption value={1}>1</SelectOption>
                  <SelectOption value={2}>{t("flowPanel.retriesBalanced")}</SelectOption>
                  <SelectOption value={3}>{t("flowPanel.retriesMaxTolerance")}</SelectOption>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <label className="font-mono text-[10px] tracking-wide text-[var(--vf-m)]">
                  {t("flowPanel.browserMode")}
                </label>
                <Select
                  value={browserMode}
                  onChange={(value) => setBrowserMode(value as FlowBrowserMode)}
                  className="flow-select"
                >
                  <SelectOption value="auto">{t("flowPanel.browserModeAuto")}</SelectOption>
                  <SelectOption value="chrome">{t("flowPanel.browserModeChrome")}</SelectOption>
                  <SelectOption value="chromium">{t("flowPanel.browserModeChromium")}</SelectOption>
                </Select>
              </div>
            </div>
          </section>

          <section className="flow-card" style={{ padding: "14px 16px" }}>
            <div className="mb-2.5 flex items-center gap-2">
              <span className="font-mono text-[11px] font-semibold text-[var(--vf-text)]">
                {t("flowPanel.bridgeStatusTitle")}
              </span>
            </div>
            {!bridgeChecked || bridgeAccounts.length === 0 ? (
              <div
                className="flex items-center gap-2 rounded-[10px] border px-3 py-2 font-mono text-[10.5px]"
                style={{
                  borderColor: "rgba(245,158,11,.35)",
                  background: "rgba(245,158,11,.08)",
                  color: "#f5a623",
                }}
              >
                <span>{t("flowPanel.bridgeConnecting")}</span>
              </div>
            ) : (
              <div className="flex flex-col gap-1.5">
                {bridgeAccounts.map((a) => (
                  <div
                    key={a.account_hash}
                    className="flex items-center gap-2 rounded-[10px] border px-3 py-2 font-mono text-[10.5px]"
                    style={
                      a.connected
                        ? { borderColor: "rgba(34,197,94,.35)", background: "rgba(34,197,94,.08)", color: "#22c55e" }
                        : { borderColor: "rgba(245,158,11,.35)", background: "rgba(245,158,11,.08)", color: "#f5a623" }
                    }
                  >
                    <span>
                      {a.connected
                        ? t("flowPanel.bridgeConnectedAs", { email: a.email || a.account_hash })
                        : t("flowPanel.bridgeReconnecting", { email: a.email || a.account_hash })}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="flow-card" style={{ padding: "14px 16px" }}>
            <div className="mb-2.5 flex items-center justify-between">
              <span className="font-mono text-[11px] text-[var(--vf-m)]">{progress.label}</span>
              <span className="font-mono text-[11px] font-semibold text-[var(--vf-c2)]">{pct}%</span>
            </div>
            <div className="flow-progress-track mb-3.5">
              <div className="flow-progress-fill" style={{ width: `${pct}%` }} />
            </div>
            {showNoAccountsWarning && (
              <div
                className="mb-3 rounded-[10px] border px-3 py-2 font-mono text-[10.5px]"
                style={{
                  borderColor: "rgba(248,113,113,.4)",
                  background: "rgba(248,113,113,.1)",
                  color: "#f87171",
                }}
              >
                {t("flowPanel.noActiveAccountsWarning")}
              </div>
            )}
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={handleStart}
                disabled={running || showNoAccountsWarning}
                className="flow-btn flow-btn--primary"
              >
                {t("flowPanel.startGeneration")}
              </button>
              <button
                type="button"
                onClick={handleStop}
                disabled={!running}
                className="flow-btn flow-btn--danger"
              >
                {t("flowPanel.stop")}
              </button>
            </div>
            <ErrorText message={error} />
            {lockConflict && (
              <button
                type="button"
                onClick={handleForceResetLock}
                className="mt-1.5 font-mono text-[10.5px] text-[var(--vf-c2)] underline"
              >
                {t("flowPanel.forceResetLock")}
              </button>
            )}
            {running && noBrowserConnected && (
              <div
                className="mt-2.5 rounded-[10px] border px-3 py-2 font-mono text-[10.5px]"
                style={{
                  borderColor: "rgba(245,158,11,.35)",
                  background: "rgba(245,158,11,.1)",
                  color: "#f5a623",
                }}
              >
                {t("flowPanel.noBrowserConnected")}
              </div>
            )}

            <details className="mt-2.5 overflow-hidden rounded-[10px] border border-[var(--vf-border)] bg-[var(--vf-s)]">
              <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2 font-mono text-[9px] uppercase tracking-[.1em] text-[var(--vf-m)]">
                <span>{t("flowPanel.perfilesChromiumTitle")}</span>
                <span className="text-[8px] text-[var(--vf-m2)]">{t("flowPanel.perfilQuotaNote")}</span>
              </summary>
              <div className="flex flex-col gap-1.5 px-2.5 pb-2.5">
                {accounts.length === 0 ? (
                  <div className="font-mono text-[10px] text-[var(--vf-m2)]">{t("flowPanel.noDataYet")}</div>
                ) : (
                  accounts.map((a, i) => {
                    const status = accountStatus(a);
                    return (
                      <div
                        key={i}
                        className="flex items-center justify-between rounded-md border border-[var(--vf-border)] px-2 py-1"
                      >
                        <span className="font-mono text-[10px] text-[var(--vf-muted)]">
                          {a.email || t("flowPanel.accountFallback", { n: i + 1 })}
                        </span>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[9px]" style={{ color: status.color }}>
                            {status.label}
                          </span>
                          <button
                            onClick={() => handleLogin(i)}
                            className="font-mono text-[9px] text-[var(--vf-c2)] underline"
                          >
                            {t("flowPanel.login")}
                          </button>
                        </div>
                      </div>
                    );
                  })
                )}
                <p className="px-0.5 font-mono text-[9px] text-[var(--vf-m2)]">
                  {t("flowPanel.openProfileHint")}
                </p>
                <div className="mt-1 flex gap-2">
                  <button
                    type="button"
                    onClick={() => flowOpenAll().catch(() => {})}
                    className="flow-btn flow-btn--ghost flow-btn--xs flex-1"
                  >
                    {t("flowPanel.openAll")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmResetOpen(true)}
                    className="flow-btn flow-btn--ghost flow-btn--xs flex-1"
                  >
                    {t("flowPanel.reset")}
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
            {t("flowPanel.gallery")}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={refreshImages}
              className="flow-btn flow-btn--ghost flow-btn--xs"
            >
              {t("flowPanel.refresh")}
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
          <div className="flow-gallery-empty">{t("flowPanel.noImagesYet")}</div>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-2.5">
            {images.map((img, i) => (
              <div key={img.key || i} className="flow-img-wrap aspect-square">
                <img src={img.src} alt={img.name || ""} loading="lazy" />
                <div className="flow-img-overlay">
                  <button
                    onClick={() => handleRetry(img, i)}
                    className="flow-retry-btn"
                    title={t("flowPanel.retryTitle") || ""}
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
          {t("flowPanel.viewFullLog")}
        </summary>
        <div className="mt-2">
          <LogConsole lines={logLines} />
        </div>
      </details>

      <ConfirmModal
        visible={confirmResetOpen}
        title={t("flowPanel.confirmResetTitle")}
        message={t("flowPanel.confirmResetChromium")}
        confirmLabel={t("flowPanel.reset")}
        cancelLabel={t("flowPanel.cancel")}
        onConfirm={handleResetChromium}
        onCancel={() => setConfirmResetOpen(false)}
      />
    </div>
  );
}
