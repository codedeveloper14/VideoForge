import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { listProjects } from "../api/projects";
import type { Project } from "../types";
import { Select, SelectOption } from "../components/Select";
import {
  analizarEscenas,
  cargarPlan,
  getEditorJobStatus,
  getProjectData,
  guardarPlan,
  renderEnriquecido,
  transcribirProyecto,
} from "../api/editor";
import type { EditorJobStatus, EditorScene, TimestampEntry } from "../api/editor";
import SceneCard from "./editor/SceneCard";
import ImageSearchModal from "./editor/ImageSearchModal";
import type { ImageSearchPick } from "./editor/ImageSearchModal";

const RESOLUCIONES = [
  { value: "1920x1080", labelKey: "editorTool.resolutionFhd" },
  { value: "1280x720", labelKey: "editorTool.resolutionHd" },
  { value: "1080x1920", labelKey: "editorTool.resolutionVertical" },
];
const TRANSICIONES = [
  { value: "none", labelKey: "editorTool.transNoneDirect" },
  { value: "xfade", labelKey: "editorTool.transXfade" },
  { value: "fade", labelKey: "editorTool.transFadeBlack" },
];

const TIPO_OPTIONS: { value: string; iconKey: string; labelKey: string }[] = [
  { value: "normal", iconKey: "editorTool.tipoIconNormal", labelKey: "editorTool.typeNormal" },
  { value: "texto_enfasis", iconKey: "editorTool.tipoIconEmphasis", labelKey: "editorTool.typeEmphasis" },
  { value: "split_screen", iconKey: "editorTool.tipoIconSplit", labelKey: "editorTool.typeSplit" },
  { value: "broll", iconKey: "editorTool.tipoIconBroll", labelKey: "editorTool.typeBroll" },
  { value: "intro_dinamica", iconKey: "editorTool.tipoIconIntro", labelKey: "editorTool.typeIntro" },
];

const OVERLAY_POS_OPTIONS = [
  { value: "bottom_center", labelKey: "editorTool.posBottomCenter" },
  { value: "top_center", labelKey: "editorTool.posTopCenter" },
  { value: "center", labelKey: "editorTool.posCenter" },
  { value: "bottom_left", labelKey: "editorTool.posBottomLeft" },
];

export default function EditorPage() {
  const { t } = useTranslation();
  const { proyecto: routeProject } = useParams<{ proyecto?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryProject = searchParams.get("project") || "";
  const initialProject = routeProject || queryProject || "";

  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState(initialProject);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [escenas, setEscenas] = useState<EditorScene[]>([]);
  const [timestamps, setTimestamps] = useState<TimestampEntry[]>([]);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [selectedIdx, setSelectedIdx] = useState(-1);
  const [searchModalIdx, setSearchModalIdx] = useState(-1);

  const [analyzing, setAnalyzing] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [saving, setSaving] = useState(false);

  const [resolucion, setResolucion] = useState("1920x1080");
  const [transicion, setTransicion] = useState("xfade");
  const [transDur, setTransDur] = useState(0.6);

  const [renderJobId, setRenderJobId] = useState<string | null>(null);
  const [renderJob, setRenderJob] = useState<EditorJobStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Keep the URL in sync with the selected project (route param takes priority).
  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (routeProject && routeProject !== project) setProject(routeProject);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeProject]);

  const loadProject = useCallback(async (name: string) => {
    if (!name) return;
    setLoading(true);
    setError("");
    setNotice("");
    setSelectedIdx(-1);
    try {
      const data = await getProjectData(name);
      setAudioUrl(data.audio_url || null);
      setTimestamps(data.timestamps || []);

      let scenes = data.escenas || [];
      // If no plan exists yet, seed a minimal scene list from the guion lines
      // so the editor has something to show/analyze even before "Analizar con IA".
      if (!scenes.length && data.guion) {
        const lines = data.guion
          .split("\n")
          .map((l) => l.trim())
          .filter(Boolean);
        scenes = lines.map((texto, i) => ({
          indice: i,
          texto,
          imagen_file: "",
          imagen_url: data.images?.[i] || null,
          tipo: "normal",
          habilitado: true,
        }));
      }
      setEscenas(scenes);
    } catch (err) {
      setError((err as Error).message);
      setEscenas([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (project) loadProject(project);
  }, [project, loadProject]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function handleSelectProject(name: string) {
    setProject(name);
    if (routeProject) {
      navigate(`/app/editor/${encodeURIComponent(name)}`);
    }
  }

  async function handleAnalizar() {
    if (!project) {
      setError(t("editorTool.selectProjectFirst"));
      return;
    }
    if (!escenas.length) {
      setError(t("editorTool.noScenesToAnalyze"));
      return;
    }
    setAnalyzing(true);
    setError("");
    setNotice("");
    try {
      const payload = escenas.map((e) => ({ texto: e.texto, imagen_file: e.imagen_file || "" }));
      const data = await analizarEscenas({ escenas: payload, project_name: project });
      const enriched = (data.escenas || []).map((e, i) => ({
        ...e,
        imagen_url: escenas[i]?.imagen_url ?? null,
      }));
      setEscenas(enriched);
      setNotice(t("editorTool.analysisComplete", { count: enriched.length }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleTranscribir() {
    if (!project) {
      setError(t("editorTool.selectProjectFirst"));
      return;
    }
    setTranscribing(true);
    setError("");
    setNotice("");
    try {
      const data = await transcribirProyecto(project);
      const segs = data.segments || [];
      setTimestamps(
        segs.map((s) => ({ escena: s.seg_idx + 1, inicio: s.start, fin: s.end, texto: s.text })),
      );
      setNotice(t("editorTool.transcriptionReady", { count: segs.length, source: data.source || "?" }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setTranscribing(false);
    }
  }

  async function handleGuardarPlan() {
    if (!project || !escenas.length) {
      setError(t("editorTool.noScenesToSave"));
      return;
    }
    setSaving(true);
    setError("");
    try {
      await guardarPlan({ project_name: project, escenas });
      setNotice(t("editorTool.planSaved"));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function handleCargarPlan() {
    if (!project) return;
    setError("");
    try {
      const data = await cargarPlan(project);
      if (!data.existe) {
        setNotice(t("editorTool.noSavedPlan"));
        return;
      }
      setEscenas(data.escenas || []);
      setNotice(t("editorTool.planLoaded", { count: (data.escenas || []).length }));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  function handleToggleEnabled(idx: number) {
    setEscenas((prev) =>
      prev.map((e, i) => (i === idx ? { ...e, habilitado: e.habilitado === false } : e)),
    );
  }

  function handlePickImage(idx: number, { url, b64 }: ImageSearchPick) {
    setEscenas((prev) =>
      prev.map((e, i) => (i === idx ? { ...e, imagen_url: b64 || url, ref_image_url: url } : e)),
    );
    setSearchModalIdx(-1);
  }

  function updateScene(idx: number, patch: Partial<EditorScene>) {
    setEscenas((prev) => prev.map((e, i) => (i === idx ? { ...e, ...patch } : e)));
  }

  function handleQuitarRef(idx: number) {
    setEscenas((prev) =>
      prev.map((e, i) => (i === idx ? { ...e, imagen_url: null, ref_image_url: undefined } : e)),
    );
  }

  async function handleRenderizar() {
    if (!project || !escenas.length) {
      setError(t("editorTool.noScenesToRender"));
      return;
    }
    setError("");
    setNotice("");
    setRenderJob(null);
    try {
      // Autosave the plan before rendering, mirroring the reference editor's behavior.
      await guardarPlan({ project_name: project, escenas });
      const result = await renderEnriquecido({
        project_name: project,
        escenas,
        resolucion,
        transicion,
        trans_dur: transDur,
      });
      if (!result.job_id) throw new Error(result.error || t("editorTool.noJobId"));
      setRenderJobId(result.job_id);
      startPolling(result.job_id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  function startPolling(jobId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const job = await getEditorJobStatus(jobId);
        setRenderJob(job);
        if (job.estado === "completado" || job.estado === "error") {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch (err) {
        if (pollRef.current) clearInterval(pollRef.current);
        setError((err as Error).message);
      }
    }, 2000);
  }

  const selectedScene = selectedIdx >= 0 ? escenas[selectedIdx] : null;
  const tsLookup: Record<number, TimestampEntry> = {};
  timestamps.forEach((ts) => {
    tsLookup[(ts.escena || 1) - 1] = ts;
  });
  const analyzed = escenas.some((e) => e.tipo || e.texto_overlay);
  const rendering = !!renderJobId && renderJob?.estado === "procesando";

  return (
    <div className="mx-auto max-w-[1280px] px-0 pb-14">
      {/* HERO */}
      <div
        className="mb-6 flex flex-col gap-4 rounded-[20px] border p-7"
        style={{
          background:
            "linear-gradient(135deg, rgba(34,211,160,.12), rgba(124,106,255,.10))",
          borderColor: "rgba(34,211,160,.22)",
          boxShadow: "0 20px 50px rgba(0,0,0,.3)",
        }}
      >
        <div>
          <p className="mb-2 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[.18em] text-[var(--vf-c5)]">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--vf-c5)]" />
            {t("editorTool.heroLabel")}
          </p>
          <h1 className="m-0 text-[clamp(1.4rem,2.8vw,1.9rem)] font-bold text-[var(--vf-text)]">
            {t("editorTool.heroTitlePart1")}{" "}
            <em
              className="not-italic bg-clip-text text-transparent"
              style={{ backgroundImage: "linear-gradient(90deg, var(--vf-c5), var(--vf-c1))" }}
            >
              {t("editorTool.heroTitlePart2")}
            </em>
          </h1>
          <p className="mt-2.5 max-w-[62ch] text-[13.5px] leading-relaxed text-[var(--vf-m)]">
            {t("editorTool.heroDescription")}
          </p>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2.5">
          <div
            className="flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 font-mono text-[10.5px]"
            style={{
              borderColor: "rgba(124,106,255,.35)",
              color: "var(--vf-c1)",
              background: "rgba(124,106,255,.06)",
            }}
          >
            <span
              className="flex h-[18px] w-[18px] items-center justify-center rounded-full text-[9px] font-bold"
              style={{ background: "rgba(124,106,255,.25)", color: "var(--vf-c1)" }}
            >
              1
            </span>
            {t("editorTool.stepScriptImages")}
          </div>
          <div className="font-mono text-[13px] text-[var(--vf-m2)]">→</div>
          <div
            className="flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 font-mono text-[10.5px]"
            style={{
              borderColor: "var(--vf-c5)",
              color: "var(--vf-c5)",
              background: "rgba(34,211,160,.08)",
            }}
          >
            <span
              className="flex h-[18px] w-[18px] items-center justify-center rounded-full text-[9px] font-bold"
              style={{ background: "var(--vf-c5)", color: "#06130f" }}
            >
              2
            </span>
            {t("editorTool.stepEditorAI")}
          </div>
          <div className="font-mono text-[13px] text-[var(--vf-m2)]">→</div>
          <div className="flex items-center gap-1.5 rounded-full border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.03)] px-3.5 py-1.5 font-mono text-[10.5px] text-[var(--vf-m2)]">
            <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-[rgba(var(--vf-fg-rgb),.08)] text-[9px] font-bold">
              3
            </span>
            {t("editorTool.renderEnrichedButton")}
          </div>
        </div>
      </div>

      {/* PROJECT SELECTOR */}
      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-[var(--vf-b)] bg-[var(--vf-s)] px-4 py-3">
        <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-m2)]">
          {t("tools.project")}
        </span>
        <Select
          value={project}
          onChange={(value) => handleSelectProject(value)}
          className="min-w-[220px] rounded-lg border border-[var(--vf-b2)] bg-[rgba(var(--vf-fg-rgb),.05)] px-3 py-1.5 font-mono text-xs text-[var(--vf-text)] outline-none"
        >
          <SelectOption value="">{t("tools.noProjectSelected")}</SelectOption>
          {projects.map((p) => (
            <SelectOption key={p.nombre} value={p.nombre}>
              {p.nombre}
            </SelectOption>
          ))}
        </Select>
        {loading && <span className="font-mono text-xs text-[var(--vf-m2)]">{t("editorTool.loading")}</span>}
        <button
          onClick={handleTranscribir}
          disabled={transcribing || !project}
          className="rounded-lg border border-[var(--vf-b2)] bg-[rgba(var(--vf-fg-rgb),.04)] px-3.5 py-2 font-mono text-xs text-[var(--vf-m2)] transition-colors hover:border-[var(--vf-c5)] hover:text-[var(--vf-c5)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {transcribing ? t("editorTool.transcribing") : t("editorTool.transcribeAudio")}
        </button>
        {audioUrl && <audio controls src={audioUrl} className="ml-auto h-8 max-w-[260px]" />}
      </div>

      {/* CONTROLES SUPERIORES */}
      <div className="mb-5 flex flex-wrap items-end gap-4 rounded-[14px] border border-[var(--vf-b)] bg-[var(--vf-s)] px-5 py-4">
        <div className="flex flex-col gap-1">
          <label className="font-mono text-[9px] uppercase tracking-[.08em] text-[var(--vf-m2)]">
            {t("editorTool.resolution")}
          </label>
          <Select
            value={resolucion}
            onChange={(value) => setResolucion(value)}
            className="w-[150px] rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.05)] px-3 py-2 text-[12.5px] text-[var(--vf-text)] outline-none focus:border-[var(--vf-c5)]/50"
          >
            {RESOLUCIONES.map((r) => (
              <SelectOption key={r.value} value={r.value}>
                {t(r.labelKey)}
              </SelectOption>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="font-mono text-[9px] uppercase tracking-[.08em] text-[var(--vf-m2)]">
            {t("editorTool.transition")}
          </label>
          <Select
            value={transicion}
            onChange={(value) => setTransicion(value)}
            className="w-[130px] rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.05)] px-3 py-2 text-[12.5px] text-[var(--vf-text)] outline-none focus:border-[var(--vf-c5)]/50"
          >
            {TRANSICIONES.map((trans) => (
              <SelectOption key={trans.value} value={trans.value}>
                {t(trans.labelKey)}
              </SelectOption>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="font-mono text-[9px] uppercase tracking-[.08em] text-[var(--vf-m2)]">
            {t("editorTool.transDurLabel")}
          </label>
          <input
            type="number"
            step="0.1"
            min="0"
            value={transDur}
            onChange={(e) => setTransDur(parseFloat(e.target.value) || 0)}
            className="w-[90px] rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.05)] px-3 py-2 text-center text-[12.5px] text-[var(--vf-text)] outline-none focus:border-[var(--vf-c5)]/50"
          />
        </div>
        <button
          onClick={handleAnalizar}
          disabled={analyzing || !project}
          className="ml-auto flex items-center gap-1.5 whitespace-nowrap rounded-[11px] border-none px-5 py-2.5 text-[12.5px] font-bold text-white transition-all disabled:transform-none disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none"
          style={{
            background: "linear-gradient(135deg, var(--vf-c5), var(--vf-c1))",
            boxShadow: "0 6px 22px rgba(34,211,160,.3)",
          }}
        >
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4l3 3" />
          </svg>
          {analyzing ? t("editorTool.analyzing") : t("editorTool.analyzeWithAI")}
        </button>
      </div>

      {error && (
        <p className="mb-3 rounded-lg border border-[var(--vf-danger)]/30 bg-[var(--vf-danger)]/10 px-3 py-2 text-xs text-[var(--vf-danger)]">
          {error}
        </p>
      )}
      {notice && !error && (
        <p className="mb-3 rounded-lg border border-[var(--vf-c5)]/30 bg-[var(--vf-c5)]/10 px-3 py-2 text-xs text-[var(--vf-c5)]">
          {notice}
        </p>
      )}

      {!project ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl px-6 py-[52px] text-center text-[13px] leading-relaxed text-[var(--vf-m2)]">
          <svg width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1" viewBox="0 0 24 24" opacity="0.3">
            <path d="M15 10l4.553-2.069A1 1 0 0 1 21 8.82v6.36a1 1 0 0 1-1.447.894L15 14M3 8a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8z" />
          </svg>
          <p>
            {t("editorTool.emptyNoProjectLine1")}
            <br />{t("editorTool.emptyNoProjectLine2")} <strong className="text-[var(--vf-m)]">{t("editorTool.analyzeWithAI")}</strong>
          </p>
        </div>
      ) : escenas.length === 0 && !loading ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl px-6 py-[52px] text-center text-[13px] leading-relaxed text-[var(--vf-m2)]">
          <svg width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1" viewBox="0 0 24 24" opacity="0.3">
            <path d="M15 10l4.553-2.069A1 1 0 0 1 21 8.82v6.36a1 1 0 0 1-1.447.894L15 14M3 8a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8z" />
          </svg>
          <p>{t("editorTool.noScenesYet")}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[1fr_360px]">
          {/* TIMELINE DE ESCENAS */}
          <div className="overflow-hidden rounded-2xl border border-[var(--vf-b)] bg-[var(--vf-s)]">
            <div className="flex items-center justify-between border-b border-[var(--vf-b)] px-[18px] py-3.5">
              <span className="font-mono text-[11px] font-semibold uppercase tracking-[.09em] text-[var(--vf-c2)]">
                {t("editorTool.timelineTitle")}
              </span>
              <span className="rounded-full border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.05)] px-2.5 py-0.5 font-mono text-[10px] text-[var(--vf-m2)]">
                {t("editorTool.scenesCount", { count: escenas.length })}
              </span>
            </div>

            {analyzed && (
              <div className="flex flex-wrap gap-3 border-b border-white/[0.04] px-[18px] py-2.5">
                <span className="flex items-center gap-1.5 font-mono text-[9.5px] text-[var(--vf-m2)]">
                  <span className="rounded-full bg-[rgba(var(--vf-fg-rgb),.08)] px-[7px] py-[2px] font-mono text-[8.5px] font-bold uppercase tracking-wide text-[var(--vf-m2)]">
                    N
                  </span>
                  {t("editorTool.typeNormal")}
                </span>
                <span className="flex items-center gap-1.5 font-mono text-[9.5px] text-[var(--vf-m2)]">
                  <span
                    className="rounded-full px-[7px] py-[2px] font-mono text-[8.5px] font-bold uppercase tracking-wide"
                    style={{ background: "rgba(255,195,0,.18)", color: "#FFD700" }}
                  >
                    T
                  </span>
                  {t("editorTool.typeEmphasis")}
                </span>
                <span className="flex items-center gap-1.5 font-mono text-[9.5px] text-[var(--vf-m2)]">
                  <span
                    className="rounded-full px-[7px] py-[2px] font-mono text-[8.5px] font-bold uppercase tracking-wide"
                    style={{ background: "rgba(124,106,255,.22)", color: "#a78bfa" }}
                  >
                    S
                  </span>
                  {t("editorTool.typeSplit")}
                </span>
                <span className="flex items-center gap-1.5 font-mono text-[9.5px] text-[var(--vf-m2)]">
                  <span
                    className="rounded-full px-[7px] py-[2px] font-mono text-[8.5px] font-bold uppercase tracking-wide"
                    style={{ background: "rgba(34,211,160,.18)", color: "var(--vf-c5)" }}
                  >
                    B
                  </span>
                  {t("editorTool.typeBroll")}
                </span>
                <span className="flex items-center gap-1.5 font-mono text-[9.5px] text-[var(--vf-m2)]">
                  <span
                    className="rounded-full px-[7px] py-[2px] font-mono text-[8.5px] font-bold uppercase tracking-wide"
                    style={{ background: "rgba(239,68,68,.18)", color: "#f87171" }}
                  >
                    I
                  </span>
                  {t("editorTool.typeIntro")}
                </span>
              </div>
            )}

            <div className="max-h-[620px] overflow-y-auto p-2">
              {escenas.map((scene, i) => (
                <SceneCard
                  key={i}
                  scene={scene}
                  index={i}
                  selected={selectedIdx === i}
                  timestamp={tsLookup[i]}
                  onSelect={setSelectedIdx}
                  onToggleEnabled={handleToggleEnabled}
                  onSearchImage={setSearchModalIdx}
                />
              ))}
            </div>
          </div>

          {/* PANEL DE PROPIEDADES */}
          <div className="sticky top-5 overflow-hidden rounded-2xl border border-[var(--vf-b)] bg-[var(--vf-s)]">
            {!selectedScene ? (
              <div className="flex flex-col items-center gap-3 px-6 py-10 text-center text-[13px] leading-relaxed text-[var(--vf-m2)]">
                <svg width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                  <rect x="3" y="3" width="18" height="18" rx="3" />
                  <path d="M3 9h18M9 21V9" />
                </svg>
                <p>{t("editorTool.selectSceneToEdit")}</p>
              </div>
            ) : (
              <div className="p-[18px]">
                <div className="mb-3.5 flex items-center justify-between">
                  <span className="font-mono text-[11px] font-semibold uppercase tracking-[.09em] text-[var(--vf-c2)]">
                    {t("editorTool.sceneNumber", { n: selectedIdx + 1 })}
                  </span>
                  <button
                    title={selectedScene.habilitado === false ? t("editorTool.enableScene") : t("editorTool.disableScene")}
                    onClick={() => handleToggleEnabled(selectedIdx)}
                    className="rounded-md p-1 text-[var(--vf-m2)] transition-colors hover:text-[var(--vf-text)]"
                  >
                    <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <polyline points="9 11 12 14 22 4" />
                      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                    </svg>
                  </button>
                </div>

                {/* Texto narración */}
                <div className="mb-4">
                  <label className="mb-1.5 block font-mono text-[9.5px] font-semibold uppercase tracking-[.07em] text-[var(--vf-m2)]">
                    {t("editorTool.narrationText")}
                  </label>
                  <div className="min-h-[40px] rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.03)] px-3 py-2.5 text-[12.5px] italic leading-relaxed text-[var(--vf-m)]">
                    {selectedScene.texto}
                  </div>
                </div>

                {/* Tipo de plano */}
                <div className="mb-4">
                  <label className="mb-1.5 block font-mono text-[9.5px] font-semibold uppercase tracking-[.07em] text-[var(--vf-m2)]">
                    {t("editorTool.shotType")}
                  </label>
                  <div className="grid grid-cols-5 gap-[5px]">
                    {TIPO_OPTIONS.map((opt) => {
                      const active = (selectedScene.tipo || "normal") === opt.value;
                      return (
                        <button
                          key={opt.value}
                          onClick={() => updateScene(selectedIdx, { tipo: opt.value })}
                          className={
                            "flex flex-col items-center gap-1 rounded-[10px] border px-1 py-2 font-mono text-[9px] transition-all " +
                            (active
                              ? "border-[var(--vf-c5)] bg-[var(--vf-c5)]/10 text-[var(--vf-c5)]"
                              : "border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.03)] text-[var(--vf-m)] hover:border-[var(--vf-c5)]/40 hover:text-[var(--vf-c5)]")
                          }
                        >
                          <span className="text-base leading-none">{t(opt.iconKey)}</span>
                          <span>{t(opt.labelKey)}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Texto overlay */}
                <div className="mb-4">
                  <label className="mb-1.5 block font-mono text-[9.5px] font-semibold uppercase tracking-[.07em] text-[var(--vf-m2)]">
                    {t("editorTool.onScreenText")}{" "}
                    <span className="font-mono text-[9px] font-normal normal-case text-[var(--vf-m2)] opacity-70">
                      {t("editorTool.maxSixWords")}
                    </span>
                  </label>
                  <input
                    type="text"
                    maxLength={50}
                    value={selectedScene.texto_overlay || ""}
                    onChange={(e) => updateScene(selectedIdx, { texto_overlay: e.target.value })}
                    placeholder={t("editorTool.overlayTextPlaceholder") || ""}
                    className="w-full rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.05)] px-3 py-2.5 text-[12.5px] text-[var(--vf-text)] outline-none focus:border-[var(--vf-c5)]/50"
                  />
                  <div className="mt-2 flex flex-wrap gap-2">
                    <select
                      value={(selectedScene.texto_overlay_pos as string) || "bottom_center"}
                      onChange={(e) => updateScene(selectedIdx, { texto_overlay_pos: e.target.value })}
                      className="flex-1 min-w-[120px] rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.05)] px-3 py-2.5 text-[12.5px] text-[var(--vf-text)] outline-none focus:border-[var(--vf-c5)]/50"
                    >
                      {OVERLAY_POS_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {t(o.labelKey)}
                        </option>
                      ))}
                    </select>
                    <input
                      type="color"
                      title={t("editorTool.textColorTitle") || ""}
                      value={(selectedScene.color_accent as string) || "#ffffff"}
                      onChange={(e) => updateScene(selectedIdx, { color_accent: e.target.value })}
                      className="h-9 w-11 cursor-pointer rounded-lg border-none bg-transparent"
                    />
                  </div>
                </div>

                {/* Texto secundario / N° capítulo */}
                <div className="mb-4 grid grid-cols-2 gap-2">
                  <div>
                    <label className="mb-1.5 block font-mono text-[9.5px] font-semibold uppercase tracking-[.07em] text-[var(--vf-m2)]">
                      {t("editorTool.secondaryText")}
                    </label>
                    <input
                      type="text"
                      value={selectedScene.texto_secundario || ""}
                      onChange={(e) => updateScene(selectedIdx, { texto_secundario: e.target.value })}
                      className="w-full rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.05)] px-3 py-2.5 text-[12.5px] text-[var(--vf-text)] outline-none focus:border-[var(--vf-c5)]/50"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block font-mono text-[9.5px] font-semibold uppercase tracking-[.07em] text-[var(--vf-m2)]">
                      {t("editorTool.chapterNumberLabel")}
                    </label>
                    <input
                      type="number"
                      value={selectedScene.numero_capitulo ?? ""}
                      onChange={(e) => updateScene(selectedIdx, { numero_capitulo: e.target.value })}
                      className="w-full rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.05)] px-3 py-2.5 text-[12.5px] text-[var(--vf-text)] outline-none focus:border-[var(--vf-c5)]/50"
                    />
                  </div>
                </div>

                {/* Imagen de referencia */}
                <div className="mb-4">
                  <label className="mb-1.5 block font-mono text-[9.5px] font-semibold uppercase tracking-[.07em] text-[var(--vf-m2)]">
                    {t("editorTool.refImageLabel2")}
                  </label>
                  <input
                    type="text"
                    value={selectedScene.ref_label || ""}
                    onChange={(e) => updateScene(selectedIdx, { ref_label: e.target.value })}
                    placeholder={t("editorTool.refLabelPlaceholder") || ""}
                    className="mb-2 w-full rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.05)] px-3 py-2 text-[11.5px] text-[var(--vf-text)] outline-none focus:border-[var(--vf-c5)]/50"
                  />
                  <div className="relative flex h-[110px] items-center justify-center overflow-hidden rounded-[10px] border border-dashed border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.04)]">
                    {selectedScene.imagen_url ? (
                      <img
                        src={selectedScene.imagen_url}
                        alt=""
                        className="h-full w-full rounded-[10px] object-cover"
                      />
                    ) : (
                      <div className="flex flex-col items-center gap-1.5 font-mono text-[11px] text-[var(--vf-m2)]">
                        <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                          <rect x="3" y="3" width="18" height="18" rx="2" />
                          <circle cx="8.5" cy="8.5" r="1.5" />
                          <polyline points="21 15 16 10 5 21" />
                        </svg>
                        <span>{t("editorTool.noRefImage")}</span>
                      </div>
                    )}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <button
                      onClick={() => setSearchModalIdx(selectedIdx)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--vf-b2)] bg-[rgba(var(--vf-fg-rgb),.04)] px-3 py-1.5 font-mono text-[11px] text-[var(--vf-text)] transition-colors hover:border-[var(--vf-c5)] hover:text-[var(--vf-c5)]"
                    >
                      <svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <circle cx="11" cy="11" r="8" />
                        <line x1="21" y1="21" x2="16.65" y2="16.65" />
                      </svg>
                      {t("editorTool.searchInGoogle")}
                    </button>
                    <button
                      onClick={() => handleQuitarRef(selectedIdx)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--vf-b2)] bg-[rgba(var(--vf-fg-rgb),.04)] px-3 py-1.5 font-mono text-[11px] text-[var(--vf-m2)] transition-colors hover:border-[var(--vf-c5)] hover:text-[var(--vf-c5)]"
                    >
                      {t("editorTool.removeLabel")}
                    </button>
                  </div>
                  <div className="mt-2 flex gap-1.5">
                    <input
                      type="text"
                      value={selectedScene.google_query || ""}
                      onChange={(e) => updateScene(selectedIdx, { google_query: e.target.value })}
                      placeholder={t("editorTool.searchQueryPlaceholder") || ""}
                      className="flex-1 rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.05)] px-3 py-2.5 text-[12.5px] text-[var(--vf-text)] outline-none focus:border-[var(--vf-c5)]/50"
                    />
                  </div>

                  {selectedScene.tipo === "split_screen" && (
                    <div className="mt-2">
                      <label className="mb-1 block font-mono text-[9.5px] font-semibold uppercase tracking-[.07em] text-[var(--vf-m2)]">
                        {t("editorTool.aiImageSide")}
                      </label>
                      <div className="flex gap-1.5">
                        <button
                          onClick={() => updateScene(selectedIdx, { lado_ia: "left" })}
                          className={
                            "flex-1 rounded-lg border px-2 py-1.5 font-mono text-[10.5px] transition-all " +
                            (selectedScene.lado_ia === "left"
                              ? "border-[var(--vf-c1)] bg-[var(--vf-c1)]/10 text-[var(--vf-c2)]"
                              : "border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.03)] text-[var(--vf-m)]")
                          }
                        >
                          {t("editorTool.leftArrow")}
                        </button>
                        <button
                          onClick={() => updateScene(selectedIdx, { lado_ia: "right" })}
                          className={
                            "flex-1 rounded-lg border px-2 py-1.5 font-mono text-[10.5px] transition-all " +
                            (selectedScene.lado_ia === "right"
                              ? "border-[var(--vf-c1)] bg-[var(--vf-c1)]/10 text-[var(--vf-c2)]"
                              : "border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.03)] text-[var(--vf-m)]")
                          }
                        >
                          {t("editorTool.rightArrow")}
                        </button>
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-1.5">
                        <input
                          type="text"
                          value={selectedScene.split_label_1 || ""}
                          onChange={(e) => updateScene(selectedIdx, { split_label_1: e.target.value })}
                          placeholder={t("editorTool.splitLabel1Placeholder") || ""}
                          className="w-full rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.05)] px-2.5 py-2 text-[11px] text-[var(--vf-text)] outline-none focus:border-[var(--vf-c5)]/50"
                        />
                        <input
                          type="text"
                          value={selectedScene.split_label_2 || ""}
                          onChange={(e) => updateScene(selectedIdx, { split_label_2: e.target.value })}
                          placeholder={t("editorTool.splitLabel2Placeholder") || ""}
                          className="w-full rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.05)] px-2.5 py-2 text-[11px] text-[var(--vf-text)] outline-none focus:border-[var(--vf-c5)]/50"
                        />
                      </div>
                    </div>
                  )}
                </div>

                {/* Duración extra */}
                <div className="mb-4">
                  <label className="mb-1.5 block font-mono text-[9.5px] font-semibold uppercase tracking-[.07em] text-[var(--vf-m2)]">
                    {t("editorTool.extraDuration")}{" "}
                    <span className="font-mono text-[9px] font-normal normal-case text-[var(--vf-m2)] opacity-70">
                      +{(selectedScene.duracion_extra as number) || 0}s
                    </span>
                  </label>
                  <input
                    type="range"
                    min={0}
                    max={3}
                    step={0.5}
                    value={(selectedScene.duracion_extra as number) || 0}
                    onChange={(e) =>
                      updateScene(selectedIdx, { duracion_extra: parseFloat(e.target.value) })
                    }
                    className="mt-1 w-full accent-[var(--vf-c5)]"
                  />
                </div>

                {/* Imagen IA generada */}
                <div>
                  <label className="mb-1.5 block font-mono text-[9.5px] font-semibold uppercase tracking-[.07em] text-[var(--vf-m2)]">
                    {t("editorTool.aiGeneratedImage")}
                  </label>
                  <div className="flex h-[90px] items-center justify-center overflow-hidden rounded-[10px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.04)]">
                    {selectedScene.imagen_ia_url ? (
                      <img
                        src={selectedScene.imagen_ia_url as string}
                        alt=""
                        className="w-full rounded-lg"
                      />
                    ) : (
                      <div className="flex flex-col items-center gap-1.5 font-mono text-[11px] text-[var(--vf-m2)]">
                        <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                          <rect x="3" y="3" width="18" height="18" rx="2" />
                          <circle cx="8.5" cy="8.5" r="1.5" />
                          <polyline points="21 15 16 10 5 21" />
                        </svg>
                        <span>{t("editorTool.noAiImage")}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* FOOTER ACCIONES */}
      {project && escenas.length > 0 && (
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-[14px] border border-[var(--vf-b)] bg-[var(--vf-s)] px-5 py-4">
          <div className="flex flex-wrap items-center gap-2.5">
            <button
              onClick={handleGuardarPlan}
              disabled={saving}
              className="rounded-[10px] border border-[var(--vf-b2)] bg-[rgba(var(--vf-fg-rgb),.03)] px-4 py-2.5 font-mono text-xs text-[var(--vf-m)] transition-colors hover:border-[rgba(var(--vf-fg-rgb),.2)] hover:text-[var(--vf-text)] disabled:opacity-50"
            >
              💾 {saving ? t("editorTool.saving") : t("editorTool.savePlan")}
            </button>
            <button
              onClick={handleCargarPlan}
              className="rounded-[10px] border border-[var(--vf-b2)] bg-[rgba(var(--vf-fg-rgb),.03)] px-4 py-2.5 font-mono text-xs text-[var(--vf-m)] transition-colors hover:border-[rgba(var(--vf-fg-rgb),.2)] hover:text-[var(--vf-text)]"
            >
              📂 {t("editorTool.loadSavedPlan")}
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            {renderJob && (
              <div className="font-mono text-[10px] text-[var(--vf-m2)]">{renderJob.estado}</div>
            )}
            <button
              onClick={handleRenderizar}
              disabled={rendering}
              className="flex items-center gap-2 rounded-xl border-none px-6 py-3 text-[13px] font-bold text-white transition-all disabled:transform-none disabled:cursor-not-allowed disabled:opacity-45"
              style={{
                background: "linear-gradient(135deg, var(--vf-c5), var(--vf-c1))",
                boxShadow: "0 8px 28px rgba(34,211,160,.3)",
              }}
            >
              <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              {t("editorTool.renderEnrichedButton")}
            </button>
          </div>
        </div>
      )}

      {/* LOG DE RENDER */}
      {renderJobId && renderJob && (
        <div className="mt-5 rounded-2xl border border-[var(--vf-b)] bg-[var(--vf-s)] p-5">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[11px] font-semibold uppercase tracking-[.09em] text-[var(--vf-c2)]">
              {t("editorTool.renderProgress")}
            </span>
          </div>
          <div className="my-3 h-1.5 overflow-hidden rounded-full bg-[var(--vf-b)]">
            <div
              className="h-full rounded-full transition-all duration-400"
              style={{
                width: `${Math.min(100, Math.max(0, renderJob.progreso || 0))}%`,
                background: "linear-gradient(90deg, var(--vf-c5), var(--vf-c1))",
              }}
            />
          </div>
          <p className="mb-2 font-mono text-[11px] text-[var(--vf-c5)]">
            {renderJob.mensaje || t("editorTool.startingEllipsis")}
          </p>
          {renderJob.estado === "completado" && renderJob.video_url && (
            <a
              href={renderJob.video_url}
              download
              className="mt-3.5 flex items-center justify-center rounded-xl px-4 py-3.5 font-mono text-[12.5px] font-bold text-[#06130f] transition-all hover:-translate-y-px"
              style={{ background: "var(--vf-c5)" }}
            >
              ⬇️ {t("editorTool.downloadEnrichedVideo")}
            </a>
          )}
          {renderJob.estado === "error" && (
            <p className="text-xs text-[var(--vf-danger)]">
              {renderJob.error || t("editorTool.renderFailed")}
            </p>
          )}
        </div>
      )}

      {searchModalIdx >= 0 && (
        <ImageSearchModal
          sceneIndex={searchModalIdx}
          initialQuery={escenas[searchModalIdx]?.google_query || escenas[searchModalIdx]?.texto || ""}
          onClose={() => setSearchModalIdx(-1)}
          onPick={handlePickImage}
        />
      )}
    </div>
  );
}
