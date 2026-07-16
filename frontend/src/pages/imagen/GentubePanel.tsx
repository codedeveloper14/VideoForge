import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
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
import ConfirmModal from "../../components/ConfirmModal";
import { loadScript } from "../../api/script";

const POLL_MS = 2000;

interface GentubePanelProps {
  project: string;
  outputDir: string;
  resolvingDir: boolean;
}

export default function GentubePanel({ project, outputDir, resolvingDir }: GentubePanelProps) {
  const { t } = useTranslation();
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
  const [confirmResetOpen, setConfirmResetOpen] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
        if (!data.running && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
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
      setError(t("flowPanel.writeAtLeastOnePrompt"));
      return;
    }
    if (!outputDir) {
      setError(t("flowPanel.selectActiveProject"));
      return;
    }
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
      pollStatus();
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
    setConfirmResetOpen(false);
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
        {t("gentubePanel.moduleLabel")}
        <span
          className="rounded-full border px-1.5 py-[1px] font-mono text-[8px] font-semibold normal-case tracking-wider"
          style={{
            background: "rgba(34,197,94,.15)",
            color: "#22c55e",
            borderColor: "rgba(34,197,94,.3)",
          }}
        >
          {t("gentubePanel.chromiumTag")}
        </span>
      </div>
      <h1 className="mb-3 text-3xl font-extrabold tracking-tight sm:text-4xl">
        {t("gentubePanel.titlePart1")}{" "}
        <span
          className="bg-clip-text text-transparent"
          style={{
            backgroundImage:
              "linear-gradient(110deg, var(--vf-c2) 0%, var(--vf-c1) 40%, var(--vf-c3) 85%)",
          }}
        >
          {t("gentubePanel.titlePart2")}
        </span>{" "}
        {t("gentubePanel.titleSuffix")}
      </h1>
      <p className="mb-6 max-w-xl font-mono text-xs leading-relaxed text-[var(--vf-muted)]">
        {t("gentubePanel.headerSubtitle")}
      </p>

      <div className="mb-4 grid grid-cols-[260px_1fr] gap-4 max-lg:grid-cols-1">
        <div className="flex flex-col gap-3">
          <SectionCard
            title={t("gentubePanel.accountsTitle")}
            right={
              <button
                onClick={loadAccounts}
                className="font-mono text-[9px] text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
              >
                {t("flowPanel.refresh")}
              </button>
            }
          >
            <div className="flex flex-col gap-1.5">
              {accounts.length === 0 ? (
                <div className="font-mono text-[10px] text-[var(--vf-m2)]">{t("flowPanel.noDataYet")}</div>
              ) : (
                accounts.map((a, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-md border border-[var(--vf-border)] bg-[var(--vf-p)] px-2 py-1"
                  >
                    <span className="font-mono text-[10px] text-[var(--vf-muted)]">
                      {a.name || t("flowPanel.accountFallback", { n: i })}
                    </span>
                    <div className="flex items-center gap-2">
                      <span
                        className="font-mono text-[9px]"
                        style={{ color: a.logged_in ? "var(--vf-c5)" : "var(--vf-m2)" }}
                      >
                        {a.logged_in ? t("flowPanel.connected") : t("flowPanel.disconnected")}
                      </span>
                      <button
                        onClick={() => handleLogin(i)}
                        disabled={loggingIn === i}
                        className="font-mono text-[9px] text-[var(--vf-c2)] underline disabled:opacity-50"
                      >
                        {loggingIn === i ? t("gentubePanel.openingEllipsis") : t("flowPanel.login")}
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
                {t("gentubePanel.simultaneousSlots")}
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

          <SectionCard title={t("gentubePanel.formatTitle")}>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                  {t("gentubePanel.ratio")}
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
                  {t("gentubePanel.quality")}
                </label>
                <Select
                  value={quality}
                  onChange={(v) => setQuality(v)}
                  className="w-full rounded-md border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] px-2 py-1.5 font-mono text-xs text-[var(--vf-text)] outline-none"
                >
                  <SelectOption value="standard">{t("gentubePanel.qualityStandard")}</SelectOption>
                  <SelectOption value="high">{t("gentubePanel.qualityHigh")}</SelectOption>
                </Select>
              </div>
            </div>
          </SectionCard>
        </div>

        <div className="flex flex-col gap-3">
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

          <SectionCard
            title={t("gentubePanel.promptsTitleShort")}
            right={
              <div className="flex items-center gap-2.5">
                <button
                  type="button"
                  onClick={handleLoadFromScript}
                  className="font-mono text-[9px] text-[var(--vf-c2)] underline"
                >
                  {t("flowPanel.loadFromScript")}
                </button>
                <span className="font-mono text-[9px] text-[var(--vf-m2)]">
                  {t("gentubePanel.promptsCount", { count: countPrompts(prompts) })}
                </span>
              </div>
            }
          >
            <textarea
              value={prompts}
              onChange={(e) => setPrompts(e.target.value)}
              placeholder={t("gentubePanel.promptPlaceholderShort") || ""}
              className="min-h-[140px] w-full resize-y rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] p-2.5 font-mono text-[11px] leading-relaxed text-[var(--vf-text)] outline-none"
            />
            <div className="mt-2 grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                  {t("gentubePanel.repetitions")}
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
                  {t("gentubePanel.estimatedTotal")}
                </label>
                <div className="py-1 font-mono text-lg font-bold text-[var(--vf-c2)]">
                  {countPrompts(prompts) * (Number(repeat) || 1)}
                </div>
              </div>
            </div>
          </SectionCard>

          <div className="flex gap-2.5">
            <PrimaryButton onClick={handleStart} disabled={running}>
              {t("flowPanel.startGeneration")}
            </PrimaryButton>
            <StopButton onClick={handleStop} disabled={!running}>
              {t("flowPanel.stop")}
            </StopButton>
            <GhostButton onClick={handleClearImages}>🗑</GhostButton>
            <GhostButton onClick={() => setConfirmResetOpen(true)}>{t("gentubePanel.resetButton")}</GhostButton>
          </div>
          <ErrorText message={error} />
        </div>
      </div>

      <div className="mb-4 rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-3.5">
        <div className="mb-3 grid grid-cols-4 gap-2">
          <StatBox value={processed} label={t("gentubePanel.processed")} />
          <StatBox value={savedImages} label={t("gentubePanel.images")} color="var(--vf-c5)" />
          <StatBox value={total} label={t("gentubePanel.total")} />
          <StatBox value={rate} label={t("gentubePanel.imgPerMin")} color="var(--vf-c2)" />
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
            {t("gentubePanel.terminal")}
          </button>
          <button
            onClick={() => setTab("gal")}
            className={
              "border-b-2 px-3 py-2.5 font-mono text-[10px] " +
              (tab === "gal" ? "border-[var(--vf-c1)] text-[var(--vf-text)]" : "border-transparent text-[var(--vf-muted)]")
            }
          >
            {t("gentubePanel.galleryCount", { count: images.length })}
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

      <ConfirmModal
        visible={confirmResetOpen}
        title={t("gentubePanel.confirmResetTitle")}
        message={t("gentubePanel.confirmReset")}
        confirmLabel={t("gentubePanel.resetButton")}
        cancelLabel={t("gentubePanel.cancel")}
        onConfirm={handleReset}
        onCancel={() => setConfirmResetOpen(false)}
      />
    </div>
  );
}
