import { api } from "./client";

export interface SaveScriptResult {
  ok: boolean;
  [key: string]: unknown;
}

export interface LoadScriptResult {
  existe: boolean;
  texto?: string;
  [key: string]: unknown;
}

export interface AnalyzeImageResult {
  [key: string]: unknown;
}

export interface N8nProxyParams {
  guion: string;
  outputMode?: string;
  promptMode?: string;
  promptStyle?: string;
  descripcionEstilo?: string;
  descripcionReferencia?: string;
  estilo?: string;
}

export interface N8nProxyResult {
  prompts?: string[] | string;
  prompts_texto?: string;
  output?: string;
  resultado?: string;
  texto_prompts?: string;
  guion?: string;
  guion_con_saltos?: string;
  guion_texto?: string;
  texto?: string;
  escenas?: number;
  total_escenas?: number;
  fragmentos?: number;
  [key: string]: unknown;
}

export interface LoadAudioResult {
  existe: boolean;
  archivos?: string[];
  principal?: string;
  [key: string]: unknown;
}

export function saveScript(projectName: string, texto: string, prompts = "") {
  return api
    .post<SaveScriptResult>("/guion/guardar", { project_name: projectName, texto, prompts })
    .then((r) => r.data);
}

export function loadScript(project: string) {
  return api
    .get<LoadScriptResult>("/guion/cargar", { params: { project } })
    .then((r) => r.data);
}

export function analyzeImage(imageBase64: string, mimeType = "image/png") {
  return api
    .post<AnalyzeImageResult>("/guion/analyze_image", {
      image_base64: imageBase64,
      mime_type: mimeType,
    })
    .then((r) => r.data);
}

export function n8nProxy({
  guion,
  outputMode = "con_prompts",
  promptMode = "general",
  promptStyle = "default",
  descripcionEstilo = "",
  descripcionReferencia = "",
  estilo = "",
}: N8nProxyParams) {
  return api
    .post<N8nProxyResult>("/guion/n8n_proxy", {
      guion,
      output_mode: outputMode,
      prompt_mode: promptMode,
      prompt_style: promptStyle,
      descripcion_estilo: descripcionEstilo,
      descripcion_referencia: descripcionReferencia,
      estilo,
    })
    .then((r) => r.data);
}

export function loadAudio(project: string) {
  return api
    .get<LoadAudioResult>("/audio/cargar", { params: { project } })
    .then((r) => r.data);
}

export function audioFileUrl(project: string, file: string) {
  return `/api/audio/archivo?project=${encodeURIComponent(project)}&file=${encodeURIComponent(file)}`;
}
