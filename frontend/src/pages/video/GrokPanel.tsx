import { useTranslation } from "react-i18next";
import * as grokApi from "../../api/grok";
import { Select, SelectOption } from "../../components/Select";
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
  { value: "2:3", labelKey: "grokPanel.aspectVertical" },
  { value: "9:16", labelKey: "grokPanel.aspectReels" },
  { value: "1:1", labelKey: "grokPanel.aspectSquare" },
  { value: "16:9", labelKey: "grokPanel.aspectHorizontal" },
  { value: "4:3", labelKey: "" },
  { value: "3:4", labelKey: "" },
  { value: "3:2", labelKey: "" },
];
const DURATION_OPTIONS = [4, 6, 8, 10];
const RES_OPTIONS = ["480p", "720p", "1080p"];

export interface GrokPanelProps {
  project: string;
}

export default function GrokPanel({ project }: GrokPanelProps) {
  const { t } = useTranslation();
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
            {t("providerPanel.videoParams")}
          </label>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="mb-1 block font-mono text-[9px] text-[var(--vf-m2)]">
                {t("grokPanel.aspectRatio")}
              </label>
              <Select
                value={options.aspect_ratio as string}
                onChange={(v) => setOption("aspect_ratio", v)}
                className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2 py-1.5 font-mono text-[10px] text-[var(--vf-text)] outline-none"
              >
                {ASPECT_OPTIONS.map((o) => (
                  <SelectOption key={o.value} value={o.value}>
                    {o.labelKey ? t(o.labelKey) : o.value}
                  </SelectOption>
                ))}
              </Select>
            </div>
            <div>
              <label className="mb-1 block font-mono text-[9px] text-[var(--vf-m2)]">
                {t("grokPanel.duration")}
              </label>
              <Select
                value={options.video_length as number}
                onChange={(v) => setOption("video_length", Number(v))}
                className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2 py-1.5 font-mono text-[10px] text-[var(--vf-text)] outline-none"
              >
                {DURATION_OPTIONS.map((d) => (
                  <SelectOption key={d} value={d}>
                    {t("grokPanel.durationSeconds", { d })}
                  </SelectOption>
                ))}
              </Select>
            </div>
            <div>
              <label className="mb-1 block font-mono text-[9px] text-[var(--vf-m2)]">
                {t("grokPanel.resolution")}
              </label>
              <Select
                value={options.resolution as string}
                onChange={(v) => setOption("resolution", v)}
                className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2 py-1.5 font-mono text-[10px] text-[var(--vf-text)] outline-none"
              >
                {RES_OPTIONS.map((r) => (
                  <SelectOption key={r} value={r}>
                    {r}
                  </SelectOption>
                ))}
              </Select>
            </div>
          </div>
        </div>
      )}
    />
  );
}
