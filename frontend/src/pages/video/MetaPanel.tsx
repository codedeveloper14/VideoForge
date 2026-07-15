import { useEffect, useState } from "react";
import * as metaApi from "../../api/meta";
import { Select, SelectOption } from "../../components/Select";
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
  const [accounts, setAccounts] = useState<metaApi.MetaAccount[]>([]);
  const [account, setAccount] = useState("");

  useEffect(() => {
    metaApi
      .metaSesiones()
      .then((data) => {
        const list = data.accounts || [];
        setAccounts(list);
        if (list.length > 0) setAccount(list[0].name);
      })
      .catch(() => {});
  }, []);

  async function launchChrome() {
    if (!account) {
      setMsg("Sin cuentas disponibles.");
      return;
    }
    setMsg("Abriendo Chrome...");
    try {
      const d = await metaApi.metaLaunchChrome({ account, slots: 3 });
      setMsg(d.message || "Chrome lanzado.");
    } catch (err) {
      setMsg(`Error: ${(err as Error).message}`);
    }
  }

  async function openDevmode() {
    if (!account) {
      setMsg("Sin cuentas disponibles.");
      return;
    }
    setMsg("Abriendo página de extensiones...");
    try {
      const d = await metaApi.metaOpenDevmode({ account });
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
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={account}
          onChange={setAccount}
          className="min-w-[140px] rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-2 py-1.5 font-mono text-[10px] text-[var(--vf-text)] outline-none"
        >
          {accounts.length === 0 ? (
            <SelectOption value="">Sin cuentas</SelectOption>
          ) : (
            accounts.map((a) => (
              <SelectOption key={a.name} value={a.name}>
                {a.name}
              </SelectOption>
            ))
          )}
        </Select>
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
              <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-[.1em] text-[var(--vf-m)]">
                Modo
              </label>
              <Select
                value={options.mode as string}
                onChange={(value) => setOption("mode", value)}
                className="w-full rounded-[9px] border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.04)] px-2.5 py-2 font-mono text-[10.5px] text-[var(--vf-text)] outline-none transition-colors focus:border-[color-mix(in_srgb,var(--vf-c1)_40%,transparent)]"
              >
                {MODE_OPTIONS.map((o) => (
                  <SelectOption key={o.value} value={o.value}>
                    {o.label}
                  </SelectOption>
                ))}
              </Select>
            </div>
            <div>
              <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-[.1em] text-[var(--vf-m)]">
                Timeout (s)
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
      extraActions={() => <AdvancedActions />}
    />
  );
}
