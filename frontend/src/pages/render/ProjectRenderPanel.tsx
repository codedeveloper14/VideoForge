import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getRenderDownloadUrl, getRenderStatus, startRender } from "../../api/render";
import type { RenderStatus } from "../../api/render";
import { loadScript } from "../../api/script";
import { Select, SelectOption } from "../../components/Select";

interface ProjectRenderPanelProps {
  project: string;
}

const RESOLUCIONES = [
  { value: "1920x1080", labelKey: "projectRenderPanel.resYoutube" },
  { value: "1080x1920", labelKey: "projectRenderPanel.resReels" },
  { value: "1080x1080", labelKey: "projectRenderPanel.resInstagram" },
  { value: "1280x720", labelKey: "projectRenderPanel.resHd" },
];

const MODELOS = [
  { value: "tiny", labelKey: "projectRenderPanel.modelTiny" },
  { value: "base", labelKey: "projectRenderPanel.modelBase" },
  { value: "small", labelKey: "projectRenderPanel.modelSmall" },
  { value: "medium", labelKey: "projectRenderPanel.modelMedium" },
];

const WHISPER_BACKENDS = [
  { value: "whisperx", labelKey: "projectRenderPanel.whisperXApi" },
  { value: "api", labelKey: "projectRenderPanel.whisperApi" },
  { value: "faster", labelKey: "projectRenderPanel.whisperFaster" },
  { value: "local", labelKey: "projectRenderPanel.whisperLocal" },
];

const RENDER_MODES = [
  { value: "smart", labelKey: "projectRenderPanel.modeSmart", descKey: "projectRenderPanel.modeSmartDesc" },
  { value: "images", labelKey: "projectRenderPanel.modeImages", descKey: "projectRenderPanel.modeImagesDesc" },
  { value: "videos", labelKey: "projectRenderPanel.modeVideos", descKey: "projectRenderPanel.modeVideosDesc" },
];

const MOTIONS = [
  { value: "none", labelKey: "projectRenderPanel.motionNone" },
  { value: "ken_burns", labelKey: "projectRenderPanel.motionKenBurns" },
  { value: "zoom_in", labelKey: "projectRenderPanel.motionZoomIn" },
  { value: "zoom_out", labelKey: "projectRenderPanel.motionZoomOut" },
  { value: "pan_left", labelKey: "projectRenderPanel.motionPanLeft" },
  { value: "pan_right", labelKey: "projectRenderPanel.motionPanRight" },
];

const TRANSITIONS = [
  { value: "none", labelKey: "projectRenderPanel.transitionNone" },
  { value: "dissolve", labelKey: "projectRenderPanel.transitionDissolve" },
  { value: "slide_left", labelKey: "projectRenderPanel.transitionSlideLeft" },
  { value: "slide_right", labelKey: "projectRenderPanel.transitionSlideRight" },
  { value: "zoom", labelKey: "projectRenderPanel.transitionZoom" },
  { value: "fade", labelKey: "projectRenderPanel.transitionFade" },
];

export default function ProjectRenderPanel({ project }: ProjectRenderPanelProps) {
  const { t } = useTranslation();
  const [renderMode, setRenderMode] = useState("smart");
  const [guion, setGuion] = useState("");
  const [useProjectScript, setUseProjectScript] = useState(true);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [useProjectAudio, setUseProjectAudio] = useState(true);

  const [resolucion, setResolucion] = useState("1920x1080");
  const [modelo, setModelo] = useState("base");
  const [whisperBackend, setWhisperBackend] = useState("whisperx");
  const [transicion, setTransicion] = useState("none");
  const [transDur, setTransDur] = useState(0.8);
  const [movimiento, setMovimiento] = useState("none");
  const [shake, setShake] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [limitInfo, setLimitInfo] = useState<string | null>(null);
  const [job, setJob] = useState<RenderStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load project's saved script for preview / reuse
  useEffect(() => {
    if (!project) return;
    loadScript(project)
      .then((data) => {
        if (data?.existe) setGuion(data.texto || "");
      })
      .catch(() => {});
  }, [project]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function startPolling(jobId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const data = await getRenderStatus(jobId);
        setJob(data);
        if (data.estado === "completado" || data.estado === "error") {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch (err) {
        setError((err as Error).message);
        if (pollRef.current) clearInterval(pollRef.current);
      }
    }, 2000);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!project) {
      setError(t("projectRenderPanel.selectProjectFirst"));
      return;
    }
    if (!useProjectAudio && !audioFile) {
      setError(t("projectRenderPanel.uploadAudioOrMarkUseProject"));
      return;
    }
    setError("");
    setLimitInfo(null);
    setJob(null);
    setLoading(true);
    try {
      const data = await startRender({
        project_name: project,
        render_mode: renderMode,
        guion,
        resolucion,
        modelo,
        whisper_backend: whisperBackend,
        transicion,
        trans_dur: transDur,
        movimiento,
        shake,
        audioFile: useProjectAudio ? null : audioFile,
      });
      setJob({ id: data.job_id, estado: "procesando", progreso: 0, mensaje: t("projectRenderPanel.startingJob") });
      startPolling(data.job_id);
    } catch (err) {
      const error = err as Error & { limit_reached?: boolean };
      if (error.limit_reached || /l[ií]mite/i.test(error.message || "")) {
        setLimitInfo(error.message);
      } else {
        setError(error.message);
      }
    } finally {
      setLoading(false);
    }
  }

  const isRendering = job && job.estado !== "completado" && job.estado !== "error";

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        {!project && (
          <p className="rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.05)] p-3 text-sm text-[var(--vf-muted)]">
            {t("projectRenderPanel.selectProjectAbove")}
          </p>
        )}

        {/* Render mode */}
        <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
          <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            {t("projectRenderPanel.renderModeTitle")}
          </h3>
          <div className="flex flex-wrap gap-2">
            {RENDER_MODES.map((m) => (
              <label
                key={m.value}
                className={`flex cursor-pointer flex-col gap-0.5 rounded-lg border px-3 py-2 text-sm transition ${
                  renderMode === m.value
                    ? "border-[var(--vf-accent)] bg-[var(--vf-accent)]/10"
                    : "border-[var(--vf-border)] bg-black/10"
                }`}
              >
                <span className="flex items-center gap-2 font-medium">
                  <input
                    type="radio"
                    name="renderMode"
                    value={m.value}
                    checked={renderMode === m.value}
                    onChange={() => setRenderMode(m.value)}
                    className="accent-[var(--vf-accent)]"
                  />
                  {t(m.labelKey)}
                </span>
                <span className="pl-5 text-[11px] text-[var(--vf-muted)]">{t(m.descKey)}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Audio + Script */}
        <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
          <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            {t("projectRenderPanel.audioTitle")}
          </h3>
          <label className="mb-2 flex items-center gap-2 text-sm text-[var(--vf-muted)]">
            <input
              type="checkbox"
              checked={useProjectAudio}
              onChange={(e) => setUseProjectAudio(e.target.checked)}
              className="accent-[var(--vf-accent)]"
            />
            {t("projectRenderPanel.useProjectAudio")}
          </label>
          {!useProjectAudio && (
            <input
              type="file"
              accept=".mp3,.wav,.m4a,.ogg,.aac"
              onChange={(e) => setAudioFile(e.target.files?.[0] || null)}
              className="block w-full text-sm text-[var(--vf-muted)]"
            />
          )}

          <h3 className="mb-3 mt-5 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            {t("projectRenderPanel.scriptTitle")}
          </h3>
          <label className="mb-2 flex items-center gap-2 text-sm text-[var(--vf-muted)]">
            <input
              type="checkbox"
              checked={useProjectScript}
              onChange={(e) => setUseProjectScript(e.target.checked)}
              className="accent-[var(--vf-accent)]"
            />
            {t("projectRenderPanel.useProjectScript")}
          </label>
          {!useProjectScript && (
            <textarea
              value={guion}
              onChange={(e) => setGuion(e.target.value)}
              rows={6}
              placeholder={t("projectRenderPanel.scriptPlaceholder") || ""}
              className="w-full rounded-lg border border-[var(--vf-border)] bg-black/20 p-3 text-sm text-[var(--vf-text)] outline-none focus:border-[var(--vf-accent)]"
            />
          )}
        </div>

        {/* Effects */}
        <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
          <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            {t("projectRenderPanel.cameraMotionTitle")}
          </h3>
          <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {MOTIONS.map((m) => (
              <button
                type="button"
                key={m.value}
                onClick={() => setMovimiento(m.value)}
                className={`rounded-lg border px-3 py-2 text-xs transition ${
                  movimiento === m.value
                    ? "border-[var(--vf-accent)] bg-[var(--vf-accent)]/10 text-[var(--vf-text)]"
                    : "border-[var(--vf-border)] text-[var(--vf-muted)]"
                }`}
              >
                {t(m.labelKey)}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm text-[var(--vf-muted)]">
            <input
              type="checkbox"
              checked={shake}
              onChange={(e) => setShake(e.target.checked)}
              className="accent-[var(--vf-accent)]"
            />
            {t("projectRenderPanel.enableShake")}
          </label>

          <h3 className="mb-3 mt-5 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            {t("projectRenderPanel.transitionTitle")}
          </h3>
          <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {TRANSITIONS.map((trans) => (
              <button
                type="button"
                key={trans.value}
                onClick={() => setTransicion(trans.value)}
                className={`rounded-lg border px-3 py-2 text-xs transition ${
                  transicion === trans.value
                    ? "border-[var(--vf-accent)] bg-[var(--vf-accent)]/10 text-[var(--vf-text)]"
                    : "border-[var(--vf-border)] text-[var(--vf-muted)]"
                }`}
              >
                {t(trans.labelKey)}
              </button>
            ))}
          </div>
          {transicion !== "none" && (
            <div className="flex items-center gap-3">
              <label className="text-xs text-[var(--vf-muted)]">{t("projectRenderPanel.duration")}</label>
              <input
                type="range"
                min="0.3"
                max="2"
                step="0.1"
                value={transDur}
                onChange={(e) => setTransDur(parseFloat(e.target.value))}
                className="flex-1 accent-[var(--vf-accent)]"
              />
              <span className="font-mono text-xs text-[var(--vf-muted)]">{transDur}s</span>
            </div>
          )}
        </div>

        {/* Output config */}
        <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
          <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            {t("projectRenderPanel.outputConfigTitle")}
          </h3>
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-[11px] text-[var(--vf-muted)]">{t("projectRenderPanel.resolution")}</label>
              <Select
                value={resolucion}
                onChange={(v) => setResolucion(v)}
                className="w-full rounded-lg border border-[var(--vf-border)] bg-black/20 p-2 text-sm text-[var(--vf-text)]"
              >
                {RESOLUCIONES.map((r) => (
                  <SelectOption key={r.value} value={r.value}>
                    {t(r.labelKey)}
                  </SelectOption>
                ))}
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-[var(--vf-muted)]">{t("projectRenderPanel.whisperModel")}</label>
              <Select
                value={modelo}
                onChange={(v) => setModelo(v)}
                className="w-full rounded-lg border border-[var(--vf-border)] bg-black/20 p-2 text-sm text-[var(--vf-text)]"
              >
                {MODELOS.map((m) => (
                  <SelectOption key={m.value} value={m.value}>
                    {t(m.labelKey)}
                  </SelectOption>
                ))}
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-[var(--vf-muted)]">{t("projectRenderPanel.whisperEngine")}</label>
              <Select
                value={whisperBackend}
                onChange={(v) => setWhisperBackend(v)}
                className="w-full rounded-lg border border-[var(--vf-border)] bg-black/20 p-2 text-sm text-[var(--vf-text)]"
              >
                {WHISPER_BACKENDS.map((w) => (
                  <SelectOption key={w.value} value={w.value}>
                    {t(w.labelKey)}
                  </SelectOption>
                ))}
              </Select>
            </div>
          </div>
        </div>

        {limitInfo && (
          <div className="rounded-lg border border-[var(--vf-c4)]/40 bg-[var(--vf-c4)]/10 p-4 text-sm">
            <p className="mb-2 text-[var(--vf-c4)]">{limitInfo}</p>
            <Link to="/app/planes" className="text-[var(--vf-accent)] hover:underline">
              {t("projectRenderPanel.upgradePlan")}
            </Link>
          </div>
        )}
        {error && <p className="text-sm text-[var(--vf-danger)]">{error}</p>}

        <button
          type="submit"
          disabled={loading || !project || !!isRendering}
          className="rounded-lg bg-[var(--vf-accent)] px-5 py-3 font-medium text-white transition hover:bg-[var(--vf-accent-hover)] disabled:opacity-50"
        >
          {loading ? t("projectRenderPanel.sending") : isRendering ? t("projectRenderPanel.rendering") : t("projectRenderPanel.generateVideo")}
        </button>
      </form>

      {/* Progress / result */}
      <div className="flex flex-col gap-4">
        {job && (
          <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
            <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
              {job.estado === "completado" ? t("projectRenderPanel.videoReady") : t("projectRenderPanel.renderProgress")}
            </h3>
            <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-[rgba(var(--vf-fg-rgb),0.05)]">
              <div
                className={`h-full rounded-full transition-all ${
                  job.estado === "error" ? "bg-[var(--vf-danger)]" : "bg-[var(--vf-accent)]"
                }`}
                style={{ width: `${Math.min(100, Math.max(0, job.progreso || 0))}%` }}
              />
            </div>
            <p className="mb-1 font-mono text-xs text-[var(--vf-muted)]">
              {job.progreso || 0}% · {job.estado}
            </p>
            {job.mensaje && <p className="text-sm text-[var(--vf-muted)]">{job.mensaje}</p>}
            {Array.isArray(job.logs) && job.logs.length > 0 && (
              <div className="mt-3 max-h-40 overflow-y-auto rounded-lg bg-black/30 p-2 font-mono text-[10px] text-[var(--vf-muted)]">
                {job.logs.map((line, i) => (
                  <div key={i}>{line}</div>
                ))}
              </div>
            )}
            {job.estado === "completado" && (
              <a
                href={job.video_url || getRenderDownloadUrl(job.id || job.job_id || "")}
                download
                className="mt-4 block rounded-lg bg-[var(--vf-success)] px-4 py-2.5 text-center font-medium text-black"
              >
                {t("projectRenderPanel.downloadVideo")}
              </a>
            )}
            {job.estado === "error" && !!job.limit_reached && (
              <div className="mt-2 rounded-lg border border-[var(--vf-c4)]/40 bg-[var(--vf-c4)]/10 p-4 text-sm">
                <p className="mb-2 text-[var(--vf-c4)]">{job.error}</p>
                <Link to="/app/planes" className="text-[var(--vf-accent)] hover:underline">
                  {t("projectRenderPanel.upgradePlan")}
                </Link>
              </div>
            )}
            {job.estado === "error" && !job.limit_reached && (
              <p className="mt-2 text-sm text-[var(--vf-danger)]">
                {job.error || t("projectRenderPanel.renderErrorGeneric")}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
