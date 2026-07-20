import { useState } from "react";
import type { ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import * as vibesApi from "../../api/vibes";
import { Select, SelectOption } from "../../components/Select";
import ProviderPanel from "./ProviderPanel";
import type { ProviderApi, ProviderIniciarParams } from "./ProviderPanel";
import { GhostButton } from "./shared";

const api: ProviderApi = {
  sesiones: vibesApi.vibesSesiones,
  loginCuenta: vibesApi.vibesLoginCuenta,
  borrarSesion: vibesApi.vibesBorrarSesion,
  iniciar: (params: ProviderIniciarParams) =>
    vibesApi.vibesIniciar({
      project_name: params.project_name,
      prompt: params.prompt || "",
      slots: params.slots,
      aspect_ratio: params.aspect_ratio as string | undefined,
      resolution: params.resolution as string | undefined,
      batch_variation: params.batch_variation as boolean | undefined,
      timeout: params.timeout as number | undefined,
      reference_image: (params.reference_image as string | undefined) || undefined,
    }),
  // Vibes has no /regenerar endpoint.
  detener: vibesApi.vibesDetener,
  log: vibesApi.vibesLog,
  videos: vibesApi.vibesVideos,
  videoUrl: vibesApi.vibesVideoUrl,
  descargarTodasUrl: vibesApi.vibesDescargarTodasUrl,
  abrirCarpeta: vibesApi.vibesAbrirCarpeta,
};

const ASPECT_OPTIONS = [
  { value: "9:16", labelKey: "vibesPanel.aspectVertical" },
  { value: "16:9", labelKey: "vibesPanel.aspectHorizontal" },
  { value: "1:1", labelKey: "vibesPanel.aspectSquare" },
];

const RESOLUTION_OPTIONS = ["480p", "720p"];

function AdvancedActions() {
  const { t } = useTranslation();
  const [msg, setMsg] = useState("");

  async function launchChrome() {
    setMsg(t("metaPanel.openingChrome"));
    try {
      const d = await vibesApi.vibesLaunchChrome();
      setMsg(d.message || t("metaPanel.chromeLaunched"));
    } catch (err) {
      setMsg(t("providerPanel.errorPrefix", { message: (err as Error).message }));
    }
  }

  return (
    <div>
      <label className="mb-2 block font-mono text-[9.5px] uppercase tracking-wider text-[var(--vf-muted)]">
        {t("vibesPanel.bridgeSetup")}
      </label>
      <p className="mb-2 font-mono text-[10px] leading-relaxed text-[var(--vf-m2)]">
        {t("vibesPanel.bridgeSetupHint")}
      </p>
      <GhostButton onClick={launchChrome}>{t("metaPanel.launchChrome")}</GhostButton>
      {msg && <div className="mt-1.5 font-mono text-[10px] text-[var(--vf-m2)]">{msg}</div>}
    </div>
  );
}

export interface VibesPanelProps {
  project: string;
}

export default function VibesPanel({ project }: VibesPanelProps) {
  const { t } = useTranslation();
  return (
    <ProviderPanel
      project={project}
      providerLabel="Vibes"
      api={api}
      defaultSlots={1}
      maxSlots={4}
      showImages={false}
      supportsRegenerate={false}
      initialOptions={{
        aspect_ratio: "9:16",
        resolution: "480p",
        batch_variation: true,
        timeout: 300,
      }}
      extraOptions={({ options, setOption }) => {
        const refImage = options.reference_image as string | undefined;

        function handleRefImageChange(e: ChangeEvent<HTMLInputElement>) {
          const file = e.target.files?.[0];
          if (!file) return;
          const reader = new FileReader();
          reader.onload = () => setOption("reference_image", reader.result as string);
          reader.readAsDataURL(file);
        }

        return (
        <div>
          <label className="mb-2 block font-mono text-[9.5px] uppercase tracking-wider text-[var(--vf-muted)]">
            {t("vibesPanel.referenceImage")}
          </label>
          <p className="mb-2 font-mono text-[10px] leading-relaxed text-[var(--vf-m2)]">
            {t("vibesPanel.referenceImageHint")}
          </p>
          <div className="mb-4 flex items-center gap-3">
            <label className="flex cursor-pointer items-center gap-2 rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.04)] px-3 py-2 font-mono text-[10.5px] text-[var(--vf-text)] transition-colors hover:border-[color-mix(in_srgb,var(--vf-c1)_40%,transparent)]">
              {t("vibesPanel.chooseImage")}
              <input type="file" accept="image/*" className="hidden" onChange={handleRefImageChange} />
            </label>
            {refImage && (
              <div className="flex items-center gap-2">
                <img
                  src={refImage}
                  alt="reference"
                  className="h-10 w-10 rounded-md border border-[var(--vf-b)] object-cover"
                />
                <button
                  type="button"
                  onClick={() => setOption("reference_image", undefined)}
                  className="font-mono text-[10px] text-[var(--vf-m2)] hover:text-[var(--vf-text)]"
                >
                  {t("flowPanel.remove")}
                </button>
              </div>
            )}
          </div>

          <label className="mb-2 block font-mono text-[9.5px] uppercase tracking-wider text-[var(--vf-muted)]">
            {t("providerPanel.videoParams")}
          </label>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-[.1em] text-[var(--vf-m)]">
                {t("vibesPanel.aspectRatio")}
              </label>
              <Select
                value={options.aspect_ratio as string}
                onChange={(value) => setOption("aspect_ratio", value)}
                className="w-full rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.04)] px-2.5 py-2 font-mono text-[10.5px] text-[var(--vf-text)] outline-none transition-colors focus:border-[color-mix(in_srgb,var(--vf-c1)_40%,transparent)]"
              >
                {ASPECT_OPTIONS.map((o) => (
                  <SelectOption key={o.value} value={o.value}>
                    {t(o.labelKey)}
                  </SelectOption>
                ))}
              </Select>
            </div>
            <div>
              <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-[.1em] text-[var(--vf-m)]">
                {t("vibesPanel.resolution")}
              </label>
              <Select
                value={options.resolution as string}
                onChange={(value) => setOption("resolution", value)}
                className="w-full rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.04)] px-2.5 py-2 font-mono text-[10.5px] text-[var(--vf-text)] outline-none transition-colors focus:border-[color-mix(in_srgb,var(--vf-c1)_40%,transparent)]"
              >
                {RESOLUTION_OPTIONS.map((r) => (
                  <SelectOption key={r} value={r}>
                    {r}
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
            <div className="flex items-end">
              <label className="flex cursor-pointer items-center gap-2 font-mono text-[10px] text-[var(--vf-m)]">
                <input
                  type="checkbox"
                  checked={options.batch_variation as boolean}
                  onChange={(e) => setOption("batch_variation", e.target.checked)}
                  className="h-3.5 w-3.5 accent-[var(--vf-accent)]"
                />
                {t("vibesPanel.batchVariation")}
              </label>
            </div>
          </div>
        </div>
        );
      }}
      extraActions={() => <AdvancedActions />}
    />
  );
}
