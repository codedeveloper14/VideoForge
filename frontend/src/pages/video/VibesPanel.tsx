import { useState } from "react";
import { useTranslation } from "react-i18next";
import * as vibesApi from "../../api/vibes";
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
      timeout: params.timeout as number | undefined,
      images: params.images,
    }),
  // Vibes has no /regenerar endpoint.
  detener: vibesApi.vibesDetener,
  log: vibesApi.vibesLog,
  videos: vibesApi.vibesVideos,
  videoUrl: vibesApi.vibesVideoUrl,
  descargarTodasUrl: vibesApi.vibesDescargarTodasUrl,
  abrirCarpeta: vibesApi.vibesAbrirCarpeta,
};

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
      showImages
      requiresImages={false}
      supportsRegenerate={false}
      initialOptions={{
        timeout: 300,
      }}
      extraOptions={({ options, setOption }) => (
        <div>
          <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-[.1em] text-[var(--vf-m)]">
            {t("providerPanel.timeoutLabel")}
          </label>
          <input
            type="number"
            value={options.timeout as number}
            onChange={(e) => setOption("timeout", Number(e.target.value))}
            className="w-full max-w-[160px] rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.04)] px-2.5 py-2 font-mono text-[10.5px] text-[var(--vf-text)] outline-none transition-colors focus:border-[color-mix(in_srgb,var(--vf-c1)_40%,transparent)]"
          />
        </div>
      )}
      extraActions={() => <AdvancedActions />}
    />
  );
}
