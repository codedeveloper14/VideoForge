import { api } from "./client";

export interface StartQuickRenderOptions {
  guion?: string;
  resolucion?: string;
  fade?: number;
  modelo?: string;
  whisper_backend?: string;
  transicion?: string;
  movimiento?: string;
  trans_dur?: number;
  shake?: boolean;
  audioFile?: File | null;
  imageFiles?: File[];
}

export interface StartQuickRenderResult {
  job_id: string;
  [key: string]: unknown;
}

export interface MultitaskJob {
  id: string;
  tipo?: string;
  proyecto?: string;
  estado?: string;
  progreso?: number;
  mensaje?: string;
  inicio?: number;
  video_url?: string;
  [key: string]: unknown;
}

// Start a "quick render" (no project) — direct upload of script + audio + ordered images.
// `opts`: guion, resolucion, fade, modelo, whisper_backend, transicion, movimiento,
// trans_dur, shake, audioFile (File), imageFiles (ordered array of File).
export function startQuickRender(opts: StartQuickRenderOptions) {
  const fd = new FormData();
  fd.append("guion", opts.guion || "");
  fd.append("resolucion", opts.resolucion || "1920x1080");
  fd.append("fade", String(opts.fade ?? 0));
  fd.append("modelo", opts.modelo || "base");
  fd.append("whisper_backend", opts.whisper_backend || "whisperx");
  fd.append("transicion", opts.transicion || "none");
  fd.append("movimiento", opts.movimiento || "none");
  fd.append("trans_dur", String(opts.trans_dur ?? 0.8));
  fd.append("shake", opts.shake ? "true" : "false");
  if (opts.audioFile) {
    fd.append("audio", opts.audioFile);
  }
  (opts.imageFiles || []).forEach((file, i) => {
    fd.append(`imagen_${i}`, file);
  });
  return api.post<StartQuickRenderResult>("/generar", fd).then((r) => r.data);
}

export function getQuickRenderDownloadUrl(jobId: string) {
  return `/api/descargar/${jobId}`;
}

export function listJobs() {
  return api.get<MultitaskJob[]>("/multitask/jobs").then((r) => r.data);
}
