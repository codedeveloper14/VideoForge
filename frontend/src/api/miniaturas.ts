import { api } from "./client";

export interface GenerarMiniaturasParams {
  prompts: string[];
  ratio?: string;
  width?: number;
  height?: number;
  output_dir?: string;
}

export interface GenerarMiniaturasResult {
  images?: string[];
  [key: string]: unknown;
}

// Generates thumbnail images via the Pollination pipeline (reuses the general
// image-generation endpoint with thumbnail-oriented prompts — no dedicated
// backend blueprint exists for "miniaturas").
export function generarMiniaturas({
  prompts,
  ratio = "16:9",
  width = 1920,
  height = 1097,
  output_dir = "",
}: GenerarMiniaturasParams) {
  return api
    .post<GenerarMiniaturasResult>("/pollination/generate", {
      prompts,
      ratio,
      width,
      height,
      output_dir,
    })
    .then((r) => r.data);
}

// Pollination saves files server-side and tracks the last output_dir in
// memory; images generated there are served back via the Whisk image route
// (same mechanism the Imagen/Pollination panel uses).
export function miniaturaImageUrl(filename: string): string {
  return `/api/whisk/image/${encodeURIComponent(filename)}`;
}
