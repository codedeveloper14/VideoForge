import { useTranslation } from "react-i18next";
import * as qwenApi from "../../api/qwen";
import { Select, SelectOption } from "../../components/Select";
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

// El aspect ratio real lo determina "size" (asi lo interpreta la API de Qwen
// via QWEN_SIZE_MAP en el backend) -- se muestra aqui solo para que la
// etiqueta sea honesta, no como un selector independiente que no hiciera nada.
const SIZE_OPTIONS = [
  { value: "1280x720", labelKey: "qwenPanel.sizeHorizontal", aspect: "16:9" },
  { value: "1920x1080", labelKey: "qwenPanel.sizeHorizontalHd", aspect: "16:9" },
  { value: "960x960", labelKey: "qwenPanel.sizeSquare", aspect: "1:1" },
  { value: "720x1280", labelKey: "qwenPanel.sizeVertical", aspect: "9:16" },
  { value: "1080x1920", labelKey: "qwenPanel.sizeVerticalHd", aspect: "9:16" },
];

export interface QwenPanelProps {
  project: string;
}

export default function QwenPanel({ project }: QwenPanelProps) {
  const { t } = useTranslation();
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
            {t("providerPanel.videoParams")}
          </label>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-[.1em] text-[var(--vf-m)]">
                {t("qwenPanel.sizeAspectRatio")}
              </label>
              <Select
                value={options.size as string}
                onChange={(value) => {
                  setOption("size", value);
                  const match = SIZE_OPTIONS.find((s) => s.value === value);
                  if (match) setOption("aspect_ratio", match.aspect);
                }}
                className="w-full rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.04)] px-2.5 py-2 font-mono text-[10.5px] text-[var(--vf-text)] outline-none transition-colors focus:border-[color-mix(in_srgb,var(--vf-c1)_40%,transparent)]"
              >
                {SIZE_OPTIONS.map((s) => (
                  <SelectOption key={s.value} value={s.value}>
                    {t(s.labelKey, { size: s.value })}
                  </SelectOption>
                ))}
              </Select>
            </div>
            <div>
              <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-[.1em] text-[var(--vf-m)]">
                {t("providerPanel.timeoutLabel")}
              </label>
              <input
                type="number"
                value={options.timeout as number}
                onChange={(e) => setOption("timeout", Number(e.target.value))}
                className="w-full rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.04)] px-2.5 py-2 font-mono text-[10.5px] text-[var(--vf-text)] outline-none transition-colors focus:border-[color-mix(in_srgb,var(--vf-c1)_40%,transparent)]"
              />
            </div>
          </div>
        </div>
      )}
    />
  );
}
