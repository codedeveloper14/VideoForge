import * as grokApi from "../../api/grok";
import ProviderPanel from "./ProviderPanel";
import type { ProviderApi, ProviderIniciarParams, ProviderRegenerarParams } from "./ProviderPanel";

const api: ProviderApi = {
  sesiones: grokApi.grokSesiones,
  loginCuenta: grokApi.grokLoginCuenta,
  borrarSesion: grokApi.grokBorrarSesion,
  iniciar: (params: ProviderIniciarParams) =>
    grokApi.grokIniciar({
      project_name: params.project_name,
      prompt: params.prompt,
      slots: params.slots,
      images: params.images,
      aspect_ratio: params.aspect_ratio as string | undefined,
      video_length: params.video_length as number | undefined,
      resolution: params.resolution as string | undefined,
    }),
  regenerar: (params: ProviderRegenerarParams) => grokApi.grokRegenerar(params),
  detener: grokApi.grokDetener,
  log: grokApi.grokLog,
  videos: grokApi.grokVideos,
  videoUrl: grokApi.grokVideoUrl,
  descargarTodasUrl: grokApi.grokDescargarTodasUrl,
  abrirCarpeta: grokApi.grokAbrirCarpeta,
};

const ASPECT_OPTIONS = [
  { value: "2:3", label: "2:3 — Vertical" },
  { value: "9:16", label: "9:16 — Reels" },
  { value: "1:1", label: "1:1 — Cuadrado" },
  { value: "16:9", label: "16:9 — Horizontal" },
  { value: "4:3", label: "4:3" },
  { value: "3:2", label: "3:2" },
];
const DURATION_OPTIONS = [4, 6, 8, 10];
const RES_OPTIONS = ["480p", "720p", "1080p"];

export interface GrokPanelProps {
  project: string;
}

export default function GrokPanel({ project }: GrokPanelProps) {
  return (
    <ProviderPanel
      project={project}
      providerLabel="Grok"
      api={api}
      defaultSlots={3}
      supportsRegenerate
      initialOptions={{
        aspect_ratio: "2:3",
        video_length: 6,
        resolution: "480p",
      }}
      extraOptions={({ options, setOption }) => (
        <div>
          <label className="mb-2 block font-mono text-[9.5px] uppercase tracking-wider text-[var(--vf-muted)]">
            Parámetros de video
          </label>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-[.1em] text-[var(--vf-m)]">
                Aspect Ratio
              </label>
              <select
                value={options.aspect_ratio as string}
                onChange={(e) => setOption("aspect_ratio", e.target.value)}
                className="w-full rounded-[9px] border border-[var(--vf-b)] bg-white/[0.04] px-2.5 py-2 font-mono text-[10.5px] text-[var(--vf-text)] outline-none transition-colors focus:border-[color-mix(in_srgb,var(--vf-c1)_40%,transparent)]"
              >
                {ASPECT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-[.1em] text-[var(--vf-m)]">
                Duración
              </label>
              <select
                value={options.video_length as number}
                onChange={(e) => setOption("video_length", Number(e.target.value))}
                className="w-full rounded-[9px] border border-[var(--vf-b)] bg-white/[0.04] px-2.5 py-2 font-mono text-[10.5px] text-[var(--vf-text)] outline-none transition-colors focus:border-[color-mix(in_srgb,var(--vf-c1)_40%,transparent)]"
              >
                {DURATION_OPTIONS.map((d) => (
                  <option key={d} value={d}>
                    {d} seg
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-[.1em] text-[var(--vf-m)]">
                Resolución
              </label>
              <select
                value={options.resolution as string}
                onChange={(e) => setOption("resolution", e.target.value)}
                className="w-full rounded-[9px] border border-[var(--vf-b)] bg-white/[0.04] px-2.5 py-2 font-mono text-[10.5px] text-[var(--vf-text)] outline-none transition-colors focus:border-[color-mix(in_srgb,var(--vf-c1)_40%,transparent)]"
              >
                {RES_OPTIONS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      )}
    />
  );
}
