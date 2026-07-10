import { useState } from "react";
import * as metaApi from "../../api/meta";
import ProviderPanel from "./ProviderPanel";
import type { ProviderApi, ProviderIniciarParams } from "./ProviderPanel";
import { GhostButton } from "./shared";

const api: ProviderApi = {
  sesiones: metaApi.metaSesiones,
  loginCuenta: metaApi.metaLoginCuenta,
  borrarSesion: metaApi.metaBorrarSesion,
  iniciar: (params: ProviderIniciarParams) =>
    metaApi.metaIniciar({
      project_name: params.project_name,
      prompt: params.prompt,
      slots: params.slots,
      images: params.images,
      mode: params.mode as string | undefined,
      timeout: params.timeout as number | undefined,
    }),
  // Meta has no /regenerar endpoint.
  detener: metaApi.metaDetener,
  log: metaApi.metaLog,
  videos: metaApi.metaVideos,
  videoUrl: metaApi.metaVideoUrl,
  descargarTodasUrl: metaApi.metaDescargarTodasUrl,
  abrirCarpeta: metaApi.metaAbrirCarpeta,
};

const MODE_OPTIONS = [
  { value: "ext", label: "ext — Extensión Chrome" },
  { value: "http", label: "http — Modo HTTP directo" },
];

function AdvancedActions() {
  const [msg, setMsg] = useState("");

  async function launchChrome() {
    setMsg("Abriendo Chrome...");
    try {
      const d = await metaApi.metaLaunchChrome({ account: "cuenta1", slots: 3 });
      setMsg(d.message || "Chrome lanzado.");
    } catch (err) {
      setMsg(`Error: ${(err as Error).message}`);
    }
  }

  async function openDevmode() {
    setMsg("Abriendo página de extensiones...");
    try {
      const d = await metaApi.metaOpenDevmode({ account: "cuenta1" });
      setMsg(d.message || "Página de dev-mode abierta.");
    } catch (err) {
      setMsg(`Error: ${(err as Error).message}`);
    }
  }

  return (
    <div>
      <label className="mb-2 block font-mono text-[9.5px] uppercase tracking-wider text-[var(--vf-muted)]">
        Avanzado (modo worker permanente)
      </label>
      <div className="flex flex-wrap gap-2">
        <GhostButton onClick={launchChrome}>🌐 Lanzar Chrome</GhostButton>
        <GhostButton onClick={openDevmode}>🧩 Abrir dev-mode</GhostButton>
      </div>
      {msg && <div className="mt-1.5 font-mono text-[10px] text-[var(--vf-m2)]">{msg}</div>}
    </div>
  );
}

export interface MetaPanelProps {
  project: string;
}

export default function MetaPanel({ project }: MetaPanelProps) {
  return (
    <ProviderPanel
      project={project}
      providerLabel="Meta"
      api={api}
      defaultSlots={1}
      supportsRegenerate={false}
      initialOptions={{
        mode: "ext",
        timeout: 900,
      }}
      extraOptions={({ options, setOption }) => (
        <div>
          <label className="mb-2 block font-mono text-[9.5px] uppercase tracking-wider text-[var(--vf-muted)]">
            Parámetros de video
          </label>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block font-mono text-[9px] text-[var(--vf-m2)]">
                Modo
              </label>
              <select
                value={options.mode as string}
                onChange={(e) => setOption("mode", e.target.value)}
                className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2 py-1.5 font-mono text-[10px] text-[var(--vf-text)] outline-none"
              >
                {MODE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
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
      extraActions={() => <AdvancedActions />}
    />
  );
}
