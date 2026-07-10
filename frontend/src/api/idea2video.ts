import { api } from "./client";

export interface GenerateScriptParams {
  idea: string;
  dur?: number;
  style?: string;
  tone?: string;
  audience?: string;
}

export interface GenerateScriptResult {
  ok: boolean;
  error?: string;
  script?: string;
  title?: string;
  scenes?: number;
  words?: number;
  dur?: number;
}

export interface StartAutopilotParams {
  script: string;
  title?: string;
  voiceId?: string;
  refImage?: string | null;
  mode?: string;
}

export interface StartAutopilotResult {
  error?: string;
  job_id: string;
}

export interface AutopilotPhases {
  recursos?: string;
  fragmentar?: string;
  prompts?: string;
  voz?: string;
  imagenes?: string;
  ensamblar?: string;
  [key: string]: string | undefined;
}

export interface AutopilotStatus {
  status: string;
  phase?: string;
  phases: AutopilotPhases;
  images: string[];
  log: string[];
  title?: string;
  project_name?: string;
  current_detail?: string;
  scenes?: number;
  char_count?: number;
  started?: string;
  ref_image?: string | null;
  mode?: string;
  elapsed?: number;
  video_url?: string;
  video_dl?: string;
  error?: string;
}

export interface AbrirCarpetaResult {
  ok?: boolean;
  error?: string;
}

export function generateScript({
  idea,
  dur = 60,
  style = "cinematic",
  tone = "inspirador",
  audience = "general",
}: GenerateScriptParams) {
  return api
    .post<GenerateScriptResult>("/idea2video/script", { idea, dur, style, tone, audience })
    .then((r) => r.data);
}

export function startAutopilot({
  script,
  title = "",
  voiceId = "",
  refImage = null,
  mode = "rapido",
}: StartAutopilotParams) {
  return api
    .post<StartAutopilotResult>("/idea2video/autopilot", {
      script,
      title,
      voice_id: voiceId,
      ref_image: refImage,
      mode,
    })
    .then((r) => r.data);
}

export function getAutopilotStatus(jobId: string) {
  return api.get<AutopilotStatus>(`/idea2video/autopilot/${jobId}`).then((r) => r.data);
}

export function abrirCarpetaAutopilot(jobId: string) {
  return api
    .post<AbrirCarpetaResult>(`/idea2video/autopilot/${jobId}/abrir_carpeta`)
    .then((r) => r.data);
}

export function apImagenUrl(project: string, file: string) {
  return `/api/idea2video/ap_imagen?project=${encodeURIComponent(project)}&file=${encodeURIComponent(file)}`;
}
