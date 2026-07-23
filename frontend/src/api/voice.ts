import { api } from "./client";

export interface Voice {
  "ID Voz"?: string;
  "Nombre Voz"?: string;
  id?: string;
  voice_id?: string;
  name?: string;
  [key: string]: unknown;
}

export interface GenerateVoiceParams {
  projectName?: string;
  voiceId?: string;
  data: string;
}

export interface VoiceFragment {
  chunkText?: string;
  audio?: string;
  url?: string;
  audioUrl?: string;
  [key: string]: unknown;
}

export interface GenerateVoiceResult {
  error?: string;
  fragments?: VoiceFragment[];
  [key: string]: unknown;
}

export interface MergeAudioPayload {
  fragments: VoiceFragment[];
  [key: string]: unknown;
}

export interface MergeAudioResult {
  finalAudio?: string;
  [key: string]: unknown;
}

export interface CloneVoicePayload {
  name: string;
  audio_base64: string;
  mime_type: string;
  lang: string;
  text: string;
}

export interface CloneVoiceResult {
  error?: string;
  [key: string]: unknown;
}

export function listVoices() {
  return api.get<Voice[]>("/voz/voces").then((r) => r.data);
}

export function generateVoice({ projectName = "", voiceId = "", data }: GenerateVoiceParams) {
  return api
    .post<GenerateVoiceResult>("/voz/generar", {
      project_name: projectName,
      voice_id: voiceId,
      data,
    })
    .then((r) => r.data);
}

export function mergeAudio(projectName: string, payload: MergeAudioPayload) {
  return api
    .post<MergeAudioResult>("/voz/fusionar", { project_name: projectName, ...payload })
    .then((r) => r.data);
}

export function cloneVoice(payload: CloneVoicePayload) {
  return api.post<CloneVoiceResult>("/voz/clonar", payload).then((r) => r.data);
}
