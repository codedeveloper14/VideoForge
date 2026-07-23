import { api } from "./client";

// ── Escenas / plan ────────────────────────────────────────────────────
export interface EditorScene {
  indice?: number;
  texto: string;
  imagen_file?: string;
  imagen_url?: string | null;
  ref_image_url?: string;
  tipo?: string;
  habilitado?: boolean;
  texto_overlay?: string;
  texto_overlay_pos?: string;
  texto_secundario?: string;
  color_accent?: string;
  split_label_1?: string;
  split_label_2?: string;
  numero_capitulo?: number | string;
  ref_label?: string;
  google_query?: string;
  [key: string]: unknown;
}

export interface TimestampEntry {
  escena: number;
  inicio: number;
  fin: number;
  texto: string;
}

export interface ProjectData {
  audio_url?: string | null;
  timestamps?: TimestampEntry[];
  escenas?: EditorScene[];
  guion?: string;
  images?: string[];
  [key: string]: unknown;
}

// ── Proyecto (carga principal del editor) ───────────────────────────
export function getProjectData(projectName: string) {
  return api
    .get<ProjectData>(`/editor/proyecto/${encodeURIComponent(projectName)}`)
    .then((r) => r.data);
}

export function editorImageUrl(projectName: string, filename: string): string {
  return `/api/editor/imagen/${encodeURIComponent(projectName)}/${encodeURIComponent(filename)}`;
}

export function editorAudioUrl(projectName: string, filename: string): string {
  return `/api/editor/audio/${encodeURIComponent(projectName)}/${encodeURIComponent(filename)}`;
}

// ── Analisis IA ──────────────────────────────────────────────────────
export interface AnalizarEscenasParams {
  escenas: Array<{ texto: string; imagen_file?: string }>;
  project_name: string;
}

export interface AnalizarEscenasResult {
  escenas?: EditorScene[];
  [key: string]: unknown;
}

export function analizarEscenas({ escenas, project_name }: AnalizarEscenasParams) {
  return api
    .post<AnalizarEscenasResult>("/editor/analizar", { escenas, project_name })
    .then((r) => r.data);
}

// ── Busqueda / proxy de imagenes ─────────────────────────────────────
export interface BuscarImagenParams {
  query: string;
  n?: number;
  serper_key?: string;
  pexels_key?: string;
}

export interface BuscarImagenResult {
  urls?: string[];
  [key: string]: unknown;
}

export function buscarImagen({ query, n = 4, serper_key = "", pexels_key = "" }: BuscarImagenParams) {
  return api
    .post<BuscarImagenResult>("/editor/buscar_imagen", { query, n, serper_key, pexels_key })
    .then((r) => r.data);
}

export interface ProxyImagenResult {
  b64?: string;
  error?: string;
  [key: string]: unknown;
}

export function proxyImagen(url: string) {
  return api.post<ProxyImagenResult>("/editor/proxy_imagen", { url }).then((r) => r.data);
}

// ── Plan de edicion ───────────────────────────────────────────────────
export interface GuardarPlanParams {
  project_name: string;
  escenas: EditorScene[];
}

export interface GuardarPlanResult {
  ok?: boolean;
  [key: string]: unknown;
}

export function guardarPlan({ project_name, escenas }: GuardarPlanParams) {
  return api
    .post<GuardarPlanResult>("/editor/guardar_plan", { project_name, escenas })
    .then((r) => r.data);
}

export interface CargarPlanResult {
  existe: boolean;
  escenas?: EditorScene[];
  [key: string]: unknown;
}

export function cargarPlan(project: string) {
  return api
    .get<CargarPlanResult>("/editor/cargar_plan", { params: { project } })
    .then((r) => r.data);
}

// ── Transcripcion ─────────────────────────────────────────────────────
export interface TranscribirSegment {
  seg_idx: number;
  start: number;
  end: number;
  text: string;
}

export interface TranscribirResult {
  segments?: TranscribirSegment[];
  source?: string;
  [key: string]: unknown;
}

export function transcribirProyecto(projectName: string) {
  return api
    .get<TranscribirResult>(`/editor/transcribir/${encodeURIComponent(projectName)}`)
    .then((r) => r.data);
}

// ── Render enriquecido ────────────────────────────────────────────────
export interface RenderEnriquecidoParams {
  project_name: string;
  escenas: EditorScene[];
  resolucion?: string;
  transicion?: string;
  trans_dur?: number;
  pexels_key?: string;
  unsplash_key?: string;
}

export interface RenderEnriquecidoResult {
  job_id?: string;
  error?: string;
  [key: string]: unknown;
}

export function renderEnriquecido({
  project_name,
  escenas,
  resolucion = "1920x1080",
  transicion = "xfade",
  trans_dur = 0.6,
  pexels_key = "",
  unsplash_key = "",
}: RenderEnriquecidoParams) {
  return api
    .post<RenderEnriquecidoResult>("/editor/render_enriquecido", {
      project_name,
      escenas,
      resolucion,
      transicion,
      trans_dur,
      pexels_key,
      unsplash_key,
    })
    .then((r) => r.data);
}

export interface EditorJobStatus {
  estado: string;
  mensaje?: string;
  progreso?: number;
  video_url?: string;
  error?: string;
  [key: string]: unknown;
}

export function getEditorJobStatus(jobId: string) {
  return api
    .get<EditorJobStatus>(`/editor/estado/${encodeURIComponent(jobId)}`)
    .then((r) => r.data);
}

export function getEditorDownloadUrl(jobId: string): string {
  return `/api/descargar_render/${jobId}`;
}
