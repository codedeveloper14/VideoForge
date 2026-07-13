import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
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

const RESOLUCIONES = ["1920x1080", "1280x720", "1080x1920"];
const TRANSICIONES = [
  { value: "none", label: "Corte directo" },
  { value: "xfade", label: "Crossfade" },
  { value: "fade", label: "Fade a negro" },
];

const TIPO_OPTIONS = [
  "normal",
  "intro_dinamica",
  "texto_enfasis",
  "lower_third",
  "nombre_persona",
  "texto_lateral",
  "ref_persona",
  "ref_lugar",
  "ref_doble",
  "google_fullscreen",
  "broll",
  "quote_animado",
  "titulo_capitulo",
];

const OVERLAY_POS_OPTIONS = [
  { value: "bottom_center", label: "Abajo centro" },
  { value: "top_center", label: "Arriba centro" },
  { value: "center", label: "Centro" },
  { value: "bottom_left", label: "Abajo izquierda" },
  { value: "top_left", label: "Arriba izquierda" },
  { value: "right_center", label: "Derecha centro" },
];

export default function EditorPage() {
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
      setError("Selecciona un proyecto primero.");
      return;
    }
    if (!escenas.length) {
      setError("El proyecto no tiene escenas para analizar.");
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
      setNotice(`Análisis completo — ${enriched.length} escenas clasificadas.`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleTranscribir() {
    if (!project) {
      setError("Selecciona un proyecto primero.");
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
      setNotice(`Transcripción lista (${segs.length} segmentos, fuente: ${data.source || "?"}).`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setTranscribing(false);
    }
  }

  async function handleGuardarPlan() {
    if (!project || !escenas.length) {
      setError("Sin escenas para guardar.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await guardarPlan({ project_name: project, escenas });
      setNotice("Plan guardado.");
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
        setNotice("No hay un plan guardado para este proyecto.");
        return;
      }
      setEscenas(data.escenas || []);
      setNotice(`Plan cargado (${(data.escenas || []).length} escenas).`);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  function handleToggleEnabled(idx: number) {
    setEscenas((prev) =>
      prev.map((e, i) => (i === idx ? { ...e, habilitado: e.habilitado === false } : e)),
    );
  }

  function handleUpdateScene(idx: number, patch: Partial<EditorScene>) {
    setEscenas((prev) => prev.map((e, i) => (i === idx ? { ...e, ...patch } : e)));
  }

  function handlePickImage(idx: number, { url, b64 }: ImageSearchPick) {
    setEscenas((prev) =>
      prev.map((e, i) => (i === idx ? { ...e, imagen_url: b64 || url, ref_image_url: url } : e)),
    );
    setSearchModalIdx(-1);
  }

  async function handleRenderizar() {
    if (!project || !escenas.length) {
      setError("Sin escenas para renderizar.");
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
      if (!result.job_id) throw new Error(result.error || "No se recibió job_id del render.");
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
  timestamps.forEach((t) => {
    tsLookup[(t.escena || 1) - 1] = t;
  });

  return (
    <div>
      {/* Project selector */}
      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] px-4 py-3">
        <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
          Proyecto
        </span>
        <Select
          value={project}
          onChange={(v) => handleSelectProject(v)}
          className="min-w-[220px] rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-3 py-1.5 font-mono text-xs text-[var(--vf-text)] outline-none"
        >
          <SelectOption value="">— Sin proyecto seleccionado —</SelectOption>
          {projects.map((p) => (
            <SelectOption key={p.nombre} value={p.nombre}>
              {p.nombre}
            </SelectOption>
          ))}
        </Select>
        {loading && <span className="font-mono text-xs text-[var(--vf-muted)]">Cargando…</span>}
        {audioUrl && <audio controls src={audioUrl} className="ml-auto h-8 max-w-[260px]" />}
      </div>

      <div className="mb-4">
        <h1 className="text-2xl font-bold text-[var(--vf-text)]">
          Editor <span className="text-[var(--vf-c5)]">visual</span>
        </h1>
        <p className="mt-1 font-mono text-xs text-[var(--vf-muted)]">
          Analiza escenas con IA, reemplaza imágenes, transcribe el audio y genera el render
          enriquecido con overlays y Ken Burns.
        </p>
      </div>

      {/* Toolbar */}
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-4">
        <div>
          <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
            Resolución
          </label>
          <Select
            value={resolucion}
            onChange={(v) => setResolucion(v)}
            className="rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] px-2.5 py-2 font-mono text-xs text-[var(--vf-text)] outline-none"
          >
            {RESOLUCIONES.map((r) => (
              <SelectOption key={r} value={r}>
                {r}
              </SelectOption>
            ))}
          </Select>
        </div>
        <div>
          <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
            Transición
          </label>
          <Select
            value={transicion}
            onChange={(v) => setTransicion(v)}
            className="rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] px-2.5 py-2 font-mono text-xs text-[var(--vf-text)] outline-none"
          >
            {TRANSICIONES.map((t) => (
              <SelectOption key={t.value} value={t.value}>
                {t.label}
              </SelectOption>
            ))}
          </Select>
        </div>
        <div className="w-[90px]">
          <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
            Dur. trans (s)
          </label>
          <input
            type="number"
            step="0.1"
            min="0"
            value={transDur}
            onChange={(e) => setTransDur(parseFloat(e.target.value) || 0)}
            className="w-full rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] px-2.5 py-2 text-center font-mono text-xs text-[var(--vf-text)] outline-none"
          />
        </div>

        <div className="ml-auto flex flex-wrap gap-2">
          <button
            onClick={handleTranscribir}
            disabled={transcribing || !project}
            className="rounded-lg border border-[var(--vf-b2)] bg-transparent px-3.5 py-2 font-mono text-xs text-[var(--vf-muted)] hover:text-[var(--vf-text)] disabled:opacity-40"
          >
            {transcribing ? "Transcribiendo…" : "Transcribir audio"}
          </button>
          <button
            onClick={handleAnalizar}
            disabled={analyzing || !project}
            className="rounded-lg border-none px-4 py-2 font-mono text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: "linear-gradient(135deg, var(--vf-c5), var(--vf-c1))" }}
          >
            {analyzing ? "Analizando…" : "Analizar con IA"}
          </button>
        </div>
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
        <div className="rounded-xl border border-dashed border-[var(--vf-border)] p-14 text-center font-mono text-xs text-[var(--vf-muted)]">
          Selecciona un proyecto para empezar a editar.
        </div>
      ) : escenas.length === 0 && !loading ? (
        <div className="rounded-xl border border-dashed border-[var(--vf-border)] p-14 text-center font-mono text-xs text-[var(--vf-muted)]">
          Este proyecto no tiene escenas todavía. Genera guion e imágenes primero, o carga un
          plan guardado.
        </div>
      ) : (
        <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[1fr_340px]">
          {/* Scene list */}
          <div className="overflow-hidden rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)]">
            <div className="flex items-center justify-between border-b border-[var(--vf-border)] px-4 py-3">
              <span className="font-mono text-[11px] uppercase tracking-wider text-[var(--vf-c2)]">
                Escenas
              </span>
              <span className="rounded-full border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-2.5 py-0.5 font-mono text-[10px] text-[var(--vf-muted)]">
                {escenas.length} escenas
              </span>
            </div>
            <div className="max-h-[640px] overflow-y-auto p-2">
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

          {/* Props panel */}
          <div className="sticky top-4 rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-4">
            {!selectedScene ? (
              <p className="py-10 text-center font-mono text-xs text-[var(--vf-muted)]">
                Selecciona una escena para ver sus detalles.
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                <div className="font-mono text-[11px] uppercase tracking-wider text-[var(--vf-c2)]">
                  Escena {selectedIdx + 1}
                </div>
                <div className="rounded-lg border border-[var(--vf-border)] bg-black/20 p-2.5 font-mono text-[11px] italic leading-relaxed text-[var(--vf-muted)]">
                  {selectedScene.texto}
                </div>
                {selectedScene.imagen_url && (
                  <img
                    src={selectedScene.imagen_url}
                    alt=""
                    className="aspect-video w-full rounded-lg object-cover"
                  />
                )}
                <div className="flex flex-col gap-2.5">
                  <div>
                    <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-m2)]">
                      Tipo
                    </label>
                    <Select
                      value={selectedScene.tipo || "normal"}
                      onChange={(v) => handleUpdateScene(selectedIdx, { tipo: v })}
                      className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2.5 py-1.5 font-mono text-[10.5px] text-[var(--vf-text)] outline-none"
                    >
                      {TIPO_OPTIONS.map((t) => (
                        <SelectOption key={t} value={t}>
                          {t.replace(/_/g, " ")}
                        </SelectOption>
                      ))}
                    </Select>
                  </div>

                  <div>
                    <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-m2)]">
                      Texto overlay
                    </label>
                    <input
                      type="text"
                      value={selectedScene.texto_overlay || ""}
                      onChange={(e) => handleUpdateScene(selectedIdx, { texto_overlay: e.target.value })}
                      className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2.5 py-1.5 font-mono text-[10.5px] text-[var(--vf-text)] outline-none"
                    />
                  </div>

                  {selectedScene.texto_overlay && (
                    <div>
                      <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-m2)]">
                        Posición overlay
                      </label>
                      <Select
                        value={selectedScene.texto_overlay_pos || "bottom_center"}
                        onChange={(v) => handleUpdateScene(selectedIdx, { texto_overlay_pos: v })}
                        className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2.5 py-1.5 font-mono text-[10.5px] text-[var(--vf-text)] outline-none"
                      >
                        {OVERLAY_POS_OPTIONS.map((o) => (
                          <SelectOption key={o.value} value={o.value}>
                            {o.label}
                          </SelectOption>
                        ))}
                      </Select>
                    </div>
                  )}

                  <div>
                    <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-m2)]">
                      Texto secundario
                    </label>
                    <input
                      type="text"
                      value={selectedScene.texto_secundario || ""}
                      onChange={(e) => handleUpdateScene(selectedIdx, { texto_secundario: e.target.value })}
                      className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2.5 py-1.5 font-mono text-[10.5px] text-[var(--vf-text)] outline-none"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-m2)]">
                        Color acento
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={`#${(selectedScene.color_accent || "ffffff").replace(/^#/, "")}`}
                          onChange={(e) =>
                            handleUpdateScene(selectedIdx, { color_accent: e.target.value.replace(/^#/, "") })
                          }
                          className="h-[30px] w-[36px] flex-shrink-0 cursor-pointer rounded-md border border-[var(--vf-b2)] bg-transparent p-0.5"
                        />
                        <input
                          type="text"
                          value={selectedScene.color_accent || "ffffff"}
                          onChange={(e) =>
                            handleUpdateScene(selectedIdx, { color_accent: e.target.value.replace(/^#/, "") })
                          }
                          className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2.5 py-1.5 font-mono text-[10.5px] text-[var(--vf-text)] outline-none"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-m2)]">
                        N° capítulo
                      </label>
                      <input
                        type="number"
                        value={selectedScene.numero_capitulo ?? ""}
                        onChange={(e) => handleUpdateScene(selectedIdx, { numero_capitulo: e.target.value })}
                        className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2.5 py-1.5 font-mono text-[10.5px] text-[var(--vf-text)] outline-none"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-m2)]">
                        Split label 1
                      </label>
                      <input
                        type="text"
                        value={selectedScene.split_label_1 || ""}
                        onChange={(e) => handleUpdateScene(selectedIdx, { split_label_1: e.target.value })}
                        className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2.5 py-1.5 font-mono text-[10.5px] text-[var(--vf-text)] outline-none"
                      />
                    </div>
                    <div>
                      <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-m2)]">
                        Split label 2
                      </label>
                      <input
                        type="text"
                        value={selectedScene.split_label_2 || ""}
                        onChange={(e) => handleUpdateScene(selectedIdx, { split_label_2: e.target.value })}
                        className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2.5 py-1.5 font-mono text-[10.5px] text-[var(--vf-text)] outline-none"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-m2)]">
                      Ref label
                    </label>
                    <input
                      type="text"
                      value={selectedScene.ref_label || ""}
                      onChange={(e) => handleUpdateScene(selectedIdx, { ref_label: e.target.value })}
                      className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2.5 py-1.5 font-mono text-[10.5px] text-[var(--vf-text)] outline-none"
                    />
                  </div>

                  {selectedScene.google_query && (
                    <div className="truncate font-mono text-[10px] text-[var(--vf-muted)]">
                      <span className="text-[var(--vf-m2)]">Query: </span>
                      {selectedScene.google_query}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => setSearchModalIdx(selectedIdx)}
                  className="rounded-lg border border-[var(--vf-b2)] px-3 py-2 font-mono text-xs text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
                >
                  Buscar / reemplazar imagen
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Footer actions */}
      {project && escenas.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-4">
          <div className="flex gap-2">
            <button
              onClick={handleGuardarPlan}
              disabled={saving}
              className="rounded-lg border border-[var(--vf-b2)] px-4 py-2 font-mono text-xs text-[var(--vf-muted)] hover:text-[var(--vf-text)] disabled:opacity-50"
            >
              {saving ? "Guardando…" : "Guardar plan"}
            </button>
            <button
              onClick={handleCargarPlan}
              className="rounded-lg border border-[var(--vf-b2)] px-4 py-2 font-mono text-xs text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
            >
              Cargar plan guardado
            </button>
          </div>
          <button
            onClick={handleRenderizar}
            disabled={!!renderJobId && renderJob?.estado === "procesando"}
            className="rounded-lg border-none px-6 py-2.5 font-mono text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: "linear-gradient(135deg, var(--vf-c5), var(--vf-c1))" }}
          >
            Renderizar (enriquecido)
          </button>
        </div>
      )}

      {/* Render progress */}
      {renderJobId && renderJob && (
        <div className="mt-4 rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-mono text-xs text-[var(--vf-c2)]">
              {renderJob.mensaje || "Procesando…"}
            </span>
            <span className="font-mono text-[10px] text-[var(--vf-muted)]">
              {renderJob.estado}
            </span>
          </div>
          <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-[rgba(var(--vf-fg-rgb),0.05)]">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${Math.min(100, Math.max(0, renderJob.progreso || 0))}%`,
                background: "linear-gradient(90deg, var(--vf-c5), var(--vf-c1))",
              }}
            />
          </div>
          {renderJob.estado === "completado" && renderJob.video_url && (
            <a
              href={renderJob.video_url}
              download
              className="mt-2 inline-block rounded-lg px-4 py-2 font-mono text-xs font-bold text-black"
              style={{ background: "var(--vf-c5)" }}
            >
              Descargar video enriquecido
            </a>
          )}
          {renderJob.estado === "error" && (
            <p className="text-xs text-[var(--vf-danger)]">
              {renderJob.error || "El render falló."}
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
