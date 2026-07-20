import { useEffect, useRef, useState } from "react";
import { useGenerationStatus } from "../context/GenerationStatusContext";
import type { GenerationEntry } from "../context/GenerationStatusContext";

const DOT_COLOR: Record<GenerationEntry["status"], string> = {
  running: "var(--vf-c1)",
  done: "var(--vf-success)",
  error: "var(--vf-danger)",
};

// Colorea cada linea del log igual que LogConsole (pages/video/shared.tsx,
// pages/imagen/shared.tsx) para que la terminal de la pastilla se vea consistente
// con las demas terminales de la app -- mismo criterio (regex), sin importarla
// directamente porque esas viven dentro de pages/ y esto es un componente global.
function logLineColor(line: string): string | undefined {
  if (/❌|\[ERROR\]/.test(line)) return "#ff5566";
  if (/\[WARNING\]/.test(line)) return "#fbbf24";
  if (/✅|✓|completado/i.test(line)) return "var(--vf-c5)";
  return undefined;
}

// Historial tipo terminal que se ve al expandir la pastilla -- equivalente al
// "vf-proc-log" de la UI vieja (ui_embedded.py). Auto-scrollea al fondo cada vez
// que llega una linea nueva mientras el panel esta expandido.
function GenerationLog({ lines }: { lines: string[] }) {
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [lines]);

  return (
    <div
      ref={boxRef}
      className="max-h-[140px] overflow-y-auto rounded-lg bg-[#0a0a0f] px-2.5 py-2 font-mono text-[10px] leading-[1.6]"
    >
      {lines.map((line, i) => (
        <div key={i} style={{ color: logLineColor(line) || "rgba(160,232,176,.85)" }}>
          {line}
        </div>
      ))}
    </div>
  );
}

function Chip({ entry }: { entry: GenerationEntry }) {
  const { dismiss } = useGenerationStatus();
  const [expanded, setExpanded] = useState(false);
  const dotColor = DOT_COLOR[entry.status];
  const indeterminate = entry.pct == null;
  const barPct = indeterminate ? 38 : Math.min(100, Math.max(0, entry.pct as number));

  return (
    <div
      className="w-[280px] overflow-hidden rounded-2xl border transition-all"
      style={{
        borderColor: "rgba(124,106,255,.25)",
        background: "linear-gradient(160deg, var(--vf-s), var(--vf-p))",
        boxShadow: "0 12px 34px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.04)",
      }}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left"
      >
        <span
          className="h-[7px] w-[7px] flex-shrink-0 rounded-full"
          style={{
            background: dotColor,
            boxShadow: `0 0 6px ${dotColor}`,
            animation: entry.status === "running" ? "vfChipPulse 1.4s ease-in-out infinite" : undefined,
          }}
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-mono text-[9px] uppercase tracking-[.12em] text-[var(--vf-muted)]">
            {entry.label}
          </span>
          <span className="mt-0.5 block truncate font-mono text-[11px] text-[var(--vf-text)]">
            {entry.message}
          </span>
        </span>
        <span className="flex-shrink-0 font-mono text-[11px] font-bold text-[var(--vf-c2)]">
          {entry.pct != null ? `${Math.round(entry.pct)}%` : "–"}
        </span>
        <span
          className="flex-shrink-0 text-[9px] text-[var(--vf-m2)] transition-transform"
          style={{ transform: expanded ? "rotate(180deg)" : undefined }}
        >
          &#9650;
        </span>
      </button>

      {expanded && (
        <div className="flex flex-col gap-2 border-t border-[rgba(var(--vf-fg-rgb),.06)] px-3.5 py-2.5">
          <GenerationLog lines={entry.log} />
          {entry.status !== "running" && (
            <button
              onClick={() => dismiss(entry.id)}
              className="self-start font-mono text-[10px] uppercase tracking-wide text-[var(--vf-m2)] hover:text-[var(--vf-text)]"
            >
              Cerrar
            </button>
          )}
        </div>
      )}

      <div className="h-[3px] w-full overflow-hidden bg-[rgba(var(--vf-fg-rgb),.06)]">
        <div
          className="h-full rounded-full transition-[width] duration-500"
          style={{
            width: `${barPct}%`,
            background: "linear-gradient(90deg,#6366f1,#a855f7,#f472b6)",
            animation: indeterminate ? "vfChipIndeterminate 1.1s ease-in-out infinite alternate" : undefined,
          }}
        />
      </div>
    </div>
  );
}

// Pila flotante de "pastillas" de progreso, una por cada generacion activa (video,
// imagen, voz, guion, render...), sin importar en que pagina este el usuario. Cada
// panel que inicia una generacion llama a useGenerationStatus().start(...) y este
// componente (montado una sola vez en AppLayout) se encarga de mostrarlas.
export default function FloatingGenerationChips() {
  const { entries } = useGenerationStatus();

  if (entries.length === 0) return null;

  return (
    <>
      <style>{`
        @keyframes vfChipPulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .45; transform: scale(.72); } }
        @keyframes vfChipIndeterminate { from { margin-left: 0%; } to { margin-left: 62%; } }
      `}</style>
      <div className="fixed bottom-4 right-4 z-[9400] flex flex-col-reverse gap-2.5">
        {entries.map((entry) => (
          <Chip key={entry.id} entry={entry} />
        ))}
      </div>
    </>
  );
}
