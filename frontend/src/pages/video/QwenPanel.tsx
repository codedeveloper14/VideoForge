import * as qwenApi from "../../api/qwen";
import ProviderPanel from "./ProviderPanel";
import type { ProviderApi, ProviderIniciarParams, ProviderRegenerarParams } from "./ProviderPanel";

const api: ProviderApi = {
  sesiones: qwenApi.qwenSesiones,
  loginCuenta: qwenApi.qwenLoginCuenta,
  borrarSesion: qwenApi.qwenBorrarSesion,
  iniciar: (params: ProviderIniciarParams) =>
    qwenApi.qwenIniciar({
      project_name: params.project_name,
      prompt: params.prompt,
      slots: params.slots,
      images: params.images,
      size: params.size as string | undefined,
      timeout: params.timeout as number | undefined,
      aspect_ratio: params.aspect_ratio as string | undefined,
    }),
  regenerar: (params: ProviderRegenerarParams) =>
    qwenApi.qwenRegenerar({
      project_name: params.project_name,
      video_name: params.video_name,
      prompt: params.prompt,
      size: params.size as string | undefined,
    }),
  detener: qwenApi.qwenDetener,
  log: qwenApi.qwenLog,
  videos: qwenApi.qwenVideos,
  videoUrl: qwenApi.qwenVideoUrl,
  descargarTodasUrl: qwenApi.qwenDescargarTodasUrl,
  abrirCarpeta: qwenApi.qwenAbrirCarpeta,
};

const ASPECT_OPTIONS = [
  { value: "16:9", label: "16:9 — Horizontal" },
  { value: "9:16", label: "9:16 — Reels" },
  { value: "1:1", label: "1:1 — Cuadrado" },
  { value: "4:3", label: "4:3" },
  { value: "3:2", label: "3:2" },
];
const SIZE_OPTIONS = ["1280x720", "1920x1080", "720x1280", "1080x1920"];

export interface QwenPanelProps {
  project: string;
}

export default function QwenPanel({ project }: QwenPanelProps) {
  return (
    <ProviderPanel
      project={project}
      providerLabel="Qwen"
      api={api}
      defaultSlots={2}
      supportsRegenerate
      initialOptions={{
        size: "1280x720",
        timeout: 900,
        aspect_ratio: "16:9",
      }}
      extraOptions={({ options, setOption }) => (
        <div>
          <label className="mb-2 block font-mono text-[9.5px] uppercase tracking-wider text-[var(--vf-muted)]">
            Parámetros de video
          </label>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="mb-1 block font-mono text-[9px] text-[var(--vf-m2)]">
                Aspect Ratio
              </label>
              <select
                value={options.aspect_ratio as string}
                onChange={(e) => setOption("aspect_ratio", e.target.value)}
                className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2 py-1.5 font-mono text-[10px] text-[var(--vf-text)] outline-none"
              >
                {ASPECT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block font-mono text-[9px] text-[var(--vf-m2)]">
                Tamaño
              </label>
              <select
                value={options.size as string}
                onChange={(e) => setOption("size", e.target.value)}
                className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2 py-1.5 font-mono text-[10px] text-[var(--vf-text)] outline-none"
              >
                {SIZE_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block font-mono text-[9px] text-[var(--vf-m2)]">
                Timeout (s)
              </label>
              <input
                type="number"
                value={options.timeout as number}
                onChange={(e) => setOption("timeout", Number(e.target.value))}
                className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2 py-1.5 font-mono text-[10px] text-[var(--vf-text)] outline-none"
              />
            </div>
          </div>
        </div>
      )}
    />
  );
}
