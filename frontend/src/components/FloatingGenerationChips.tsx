import { useEffect, useRef, useState } from "react";
import { useGenerationStatus } from "../context/GenerationStatusContext";
import type { GenerationEntry } from "../context/GenerationStatusContext";

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

// "IMAGENES · FLOW" -> "IMAGENES" -- igual que _LB en ui_embedded.py, la pastilla
// colapsada muestra la categoria (Video/Imagenes/Voz/Guion), no el proveedor exacto.
function shortCategory(label: string): string {
  return label.split(/[·:]/)[0].trim().toUpperCase();
}

function GenerationLog({ lines }: { lines: string[] }) {
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [lines]);

  return (
    <div
      ref={boxRef}
      className="mt-3 max-h-[148px] overflow-y-auto rounded-[11px] px-3.5 py-2.5 font-mono text-[11px] leading-[1.55]"
      style={{ background: "rgba(0,0,0,.28)", border: "1px solid rgba(124,106,255,.11)" }}
    >
      {lines.map((line, i) => (
        <div key={i} style={{ color: logLineColor(line) || "#64748b" }}>
          {line}
        </div>
      ))}
    </div>
  );
}

// Tarjeta expandida (equivalente a .vf-proc-card de ui_embedded.py) -- aparece
// arriba del chip colapsado al hacer click en el.
function ExpandedCard({ entry }: { entry: GenerationEntry }) {
  const { dismiss } = useGenerationStatus();
  const indeterminate = entry.pct == null;
  const barPct = indeterminate ? 38 : Math.min(100, Math.max(0, entry.pct as number));
  const isDone = entry.status !== "running";
  const isError = entry.status === "error";

  return (
    <div
      className="mb-2 w-[min(420px,92vw)] rounded-[18px] px-[22px] pb-4 pt-[22px]"
      style={{
        border: `1px solid ${isError ? "rgba(248,113,113,.35)" : "rgba(124,106,255,.30)"}`,
        background: "linear-gradient(160deg, rgba(13,15,25,.98), rgba(7,8,16,.99))",
        boxShadow: "0 24px 70px rgba(0,0,0,.65), inset 0 1px 0 rgba(255,255,255,.05)",
      }}
    >
      {!isDone ? (
        <>
          <div
            className="font-mono text-[10px] uppercase tracking-[.18em]"
            style={{ color: "rgba(167,139,250,.65)" }}
          >
            En curso
          </div>
          <div className="mt-[9px] text-[18px] font-bold leading-[1.22]" style={{ color: "#f1f0ff" }}>
            {entry.label}
          </div>
          <div className="mt-1.5 text-[12.5px] leading-relaxed" style={{ color: "#64748b" }}>
            {entry.message}
          </div>
          <GenerationLog lines={entry.log} />
          <div
            className="mt-4 h-[5px] overflow-hidden rounded-full"
            style={{ background: "rgba(255,255,255,.06)" }}
          >
            <div
              className="h-full rounded-full transition-[width] duration-[420ms]"
              style={{
                width: `${barPct}%`,
                background: "linear-gradient(90deg,#6366f1,#a855f7,#f472b6)",
                boxShadow: "0 0 12px rgba(168,85,247,.4)",
                animation: indeterminate ? "vfProcInd 1.1s ease-in-out infinite alternate" : undefined,
              }}
            />
          </div>
          {entry.onStop && (
            <div className="mt-4 flex justify-end">
              <button
                onClick={entry.onStop}
                className="rounded-[9px] px-3.5 py-2 font-mono text-[10.5px]"
                style={{
                  border: "1px solid rgba(239,68,68,.28)",
                  background: "rgba(239,68,68,.08)",
                  color: "#fca5a5",
                }}
              >
                Detener
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="py-1.5 text-center">
          <div
            className="mx-auto mb-2.5 flex h-14 w-14 items-center justify-center rounded-full text-[26px]"
            style={
              isError
                ? { background: "rgba(248,113,113,.18)", border: "1px solid rgba(248,113,113,.5)", color: "#fecaca" }
                : {
                    background: "linear-gradient(135deg, rgba(52,211,153,.35), rgba(16,185,129,.12))",
                    border: "1px solid rgba(52,211,153,.45)",
                    color: "#6ee7b7",
                  }
            }
          >
            {isError ? "✕" : "✓"}
          </div>
          <div
            className="font-mono text-[10px] uppercase tracking-[.18em]"
            style={{ color: "rgba(167,139,250,.65)" }}
          >
            {isError ? "Error" : "Listo"}
          </div>
          <div className="mt-1.5 text-[15px]" style={{ color: "#f1f0ff" }}>
            {entry.message}
          </div>
          <div className="mt-3.5 flex justify-center gap-2">
            <button
              onClick={() => dismiss(entry.id)}
              className="rounded-[9px] px-3.5 py-2 font-mono text-[10.5px]"
              style={{ background: "transparent", border: "1px solid rgba(124,106,255,.2)", color: "#a78bfa" }}
            >
              Cerrar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// Chip colapsado (equivalente a .vf-proc-chip) -- siempre visible, es el "resumen"
// de la generacion; al hacer click alterna la tarjeta expandida arriba.
function CollapsedChip({
  entry,
  expanded,
  onToggle,
}: {
  entry: GenerationEntry;
  expanded: boolean;
  onToggle: () => void;
}) {
  const dotColor = entry.status === "running" ? "#a78bfa" : entry.status === "error" ? "#f87171" : "#34d399";
  const indeterminate = entry.pct == null && entry.status === "running";
  const barPct = entry.status !== "running" ? 100 : entry.pct != null ? Math.min(100, Math.max(0, entry.pct)) : 38;

  return (
    <button
      onClick={onToggle}
      className="relative flex w-[min(420px,92vw)] items-center gap-2.5 overflow-hidden rounded-full py-2.5 pl-3 pr-3.5 text-left"
      style={{
        border: "1px solid rgba(124,106,255,.22)",
        background: "linear-gradient(135deg, rgba(13,15,25,.97), rgba(9,10,19,.98))",
        boxShadow: "0 4px 18px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.04)",
      }}
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
        <span
          className="block truncate font-mono text-[9px] uppercase tracking-[.14em]"
          style={{ color: "rgba(167,139,250,.6)" }}
        >
          {shortCategory(entry.label)} - STUDIO IVR
        </span>
        <span className="mt-0.5 block truncate font-mono text-[11px] font-medium" style={{ color: "rgba(238,238,245,.82)" }}>
          {entry.message}
        </span>
      </span>
      <span className="flex-shrink-0 font-mono text-[12px] font-bold" style={{ color: "#c4b5fd" }}>
        {entry.pct != null ? `${Math.round(entry.pct)}%` : "-"}
      </span>
      <span
        className="flex-shrink-0 text-[10px] font-bold transition-transform"
        style={{ color: "rgba(124,106,255,.55)", transform: expanded ? "rotate(180deg)" : undefined }}
      >
        &#9650;
      </span>
      <span
        className="absolute bottom-0 left-0 right-0 h-[3px] overflow-hidden rounded-b-full"
        style={{ background: "rgba(255,255,255,.06)", opacity: expanded ? 0 : 1 }}
      >
        <span
          className="block h-full rounded-full transition-[width] duration-[420ms]"
          style={{
            width: `${barPct}%`,
            background: "linear-gradient(90deg,#6366f1,#a855f7,#f472b6)",
            animation: indeterminate ? "vfChipInd 1.1s ease-in-out infinite alternate" : undefined,
          }}
        />
      </span>
    </button>
  );
}

function ProcOverlay({ entry }: { entry: GenerationEntry }) {
  const [expanded, setExpanded] = useState(false);

  // Al terminar (bien o mal) se auto-expande para que el usuario vea el resultado sin
  // tener que hacer click -- igual que `_done()` en ui_embedded.py.
  useEffect(() => {
    if (entry.status !== "running") setExpanded(true);
  }, [entry.status]);

  return (
    <div className="flex flex-col items-end">
      {expanded && <ExpandedCard entry={entry} />}
      <CollapsedChip entry={entry} expanded={expanded} onToggle={() => setExpanded((v) => !v)} />
    </div>
  );
}

// Pila flotante de "pastillas" de progreso (id vf-proc-stack, igual que en la UI vieja
// embebida de PyWebView -- ui_embedded.py/launcher.py) -- una por cada generacion
// activa (video, imagen, voz, guion...), sin importar en que pagina este el usuario.
// Cada panel que inicia una generacion llama a useGenerationStatus().start(...) y este
// componente (montado una sola vez en AppLayout) se encarga de mostrarlas.
export default function FloatingGenerationChips() {
  const { entries } = useGenerationStatus();

  if (entries.length === 0) return null;

  return (
    <>
      <style>{`
        @keyframes vfChipPulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .45; transform: scale(.72); } }
        @keyframes vfChipInd { from { margin-left: 0%; } to { margin-left: 62%; } }
        @keyframes vfProcInd { from { margin-left: 0%; } to { margin-left: 62%; } }
      `}</style>
      <div
        id="vf-proc-stack"
        className="fixed bottom-5 right-5 z-[9400] flex max-h-screen flex-col-reverse items-end justify-end gap-2"
      >
        {entries.map((entry) => (
          <ProcOverlay key={entry.id} entry={entry} />
        ))}
      </div>
    </>
  );
}
