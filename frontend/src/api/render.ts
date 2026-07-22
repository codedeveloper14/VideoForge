import { api } from "./client";

export interface StartRenderOptions {
  project_name: string;
  render_mode?: string;
  guion?: string;
  resolucion?: string;
  modelo?: string;
  whisper_backend?: string;
  transicion?: string;
  trans_dur?: number;
  movimiento?: string;
  shake?: boolean;
  audioFile?: File | null;
  /** Nombre del audio del proyecto elegido explicitamente (ignora si audioFile viene). */
  audioFilename?: string | null;
  /** Nombres de imagen seleccionados en el panel de assets -- si se omite, el backend usa todas. */
  imageFilenames?: string[] | null;
  /** Nombres de video seleccionados en el panel de assets -- si se omite, el backend usa todos. */
  videoFilenames?: string[] | null;
}

export interface StartRenderResult {
  job_id: string;
  [key: string]: unknown;
}

export interface RenderStatus {
  id?: string;
  job_id?: string;
  estado: string;
  progreso?: number;
  mensaje?: string;
  logs?: string[];
  video_url?: string;
  error?: string;
  [key: string]: unknown;
}

// Start a project-based render ("render inteligente"). `opts` may include:
// project_name, render_mode, guion, resolucion, modelo, whisper_backend,
// transicion, trans_dur, movimiento, shake, audioFile (optional File).
export function startRender(opts: StartRenderOptions) {
  const fd = new FormData();
  fd.append("project_name", opts.project_name || "");
  fd.append("render_mode", opts.render_mode || "smart");
  fd.append("guion", opts.guion || "");
  fd.append("resolucion", opts.resolucion || "1920x1080");
  fd.append("modelo", opts.modelo || "base");
  fd.append("whisper_backend", opts.whisper_backend || "whisperx");
  fd.append("transicion", opts.transicion || "none");
  fd.append("trans_dur", String(opts.trans_dur ?? 0.8));
  fd.append("movimiento", opts.movimiento || "none");
  fd.append("shake", opts.shake ? "true" : "false");
  if (opts.audioFile) {
    fd.append("audio", opts.audioFile);
  } else if (opts.audioFilename) {
    fd.append("audio_filename", opts.audioFilename);
  }
  if (opts.imageFilenames) {
    fd.append("image_filenames", JSON.stringify(opts.imageFilenames));
  }
  if (opts.videoFilenames) {
    fd.append("video_filenames", JSON.stringify(opts.videoFilenames));
  }
  return api.post<StartRenderResult>("/render_inteligente", fd).then((r) => r.data);
}

export function getRenderStatus(jobId: string) {
  return api.get<RenderStatus>(`/estado/${jobId}`).then((r) => r.data);
}

export function getRenderDownloadUrl(jobId: string) {
  return `/api/descargar_render/${jobId}`;
}
