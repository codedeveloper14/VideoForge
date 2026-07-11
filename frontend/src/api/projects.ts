import { api } from "./client";
import type { Project } from "../types";

export interface CreateProjectResult {
  ok: boolean;
  nombre: string;
  ruta: string;
}

export interface ProjectScene {
  index: string;
  image: string | null;
  video: string | null;
  has_video: boolean;
}

export interface ProjectContentDebug {
  img_dir: string;
  img_count: number;
  vid_count: number;
  img_dir_exists: boolean;
}

export interface ProjectContent {
  scenes: ProjectScene[];
  total: number;
  with_video: number;
  images_only: number;
  debug: ProjectContentDebug;
}

export function listProjects() {
  return api.get<Project[]>("/proyectos/listar").then((r) => r.data);
}

export function createProject(nombre: string) {
  return api
    .post<CreateProjectResult>("/proyectos/crear", { nombre })
    .then((r) => r.data);
}

export function deleteProject(nombre: string) {
  return api
    .post<{ ok: boolean; nombre: string; msg: string | null }>(
      "/proyectos/borrar",
      { nombre },
    )
    .then((r) => r.data);
}

export function getProjectContent(project: string) {
  return api
    .get<ProjectContent>("/proyectos/contenido", { params: { project } })
    .then((r) => r.data);
}

export function listFinalVideos(project: string) {
  return api
    .get<{ videos: string[] }>("/proyectos/videos_final", {
      params: { project },
    })
    .then((r) => r.data);
}
