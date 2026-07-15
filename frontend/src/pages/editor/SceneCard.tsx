import type { EditorScene, TimestampEntry } from "../../api/editor";

const TIPO_PILL: Record<string, { bg: string; color: string; letter: string }> = {
  normal: { bg: "rgba(var(--vf-fg-rgb),.08)", color: "var(--vf-m2)", letter: "N" },
  texto_enfasis: { bg: "rgba(255,195,0,.18)", color: "#FFD700", letter: "T" },
  split_screen: { bg: "rgba(124,106,255,.22)", color: "#a78bfa", letter: "S" },
  broll: { bg: "rgba(34,211,160,.18)", color: "var(--vf-c5)", letter: "B" },
  ref_persona: { bg: "rgba(59,130,246,.22)", color: "#60a5fa", letter: "P" },
  ref_lugar: { bg: "rgba(245,158,11,.18)", color: "#fbbf24", letter: "L" },
  ref_doble: { bg: "rgba(236,72,153,.18)", color: "#f472b6", letter: "D" },
  intro_dinamica: { bg: "rgba(239,68,68,.18)", color: "#f87171", letter: "I" },
};

function TipoPill({ tipo }: { tipo?: string }) {
  const key = tipo || "normal";
  const style = TIPO_PILL[key] || TIPO_PILL.normal;
  return (
    <span
      className="rounded-full px-[7px] py-[2px] font-mono text-[8.5px] font-bold uppercase tracking-wide"
      style={{ background: style.bg, color: style.color }}
    >
      {key.replace(/_/g, " ")}
    </span>
  );
}

export interface SceneCardProps {
  scene: EditorScene;
  index: number;
  selected: boolean;
  timestamp?: TimestampEntry;
  onSelect: (index: number) => void;
  onToggleEnabled: (index: number) => void;
  onSearchImage: (index: number) => void;
}

export default function SceneCard({
  scene,
  index,
  selected,
  timestamp,
  onSelect,
  onToggleEnabled,
  onSearchImage,
}: SceneCardProps) {
  const disabled = scene.habilitado === false;

  return (
    <div
      onClick={() => onSelect(index)}
      className={
        "mb-1.5 grid cursor-pointer grid-cols-[36px_80px_1fr_auto] items-center gap-2.5 rounded-xl border p-2.5 transition-colors " +
        (selected
          ? "border-[var(--vf-c5)]/30 bg-[var(--vf-c5)]/[0.07]"
          : "border-transparent bg-[rgba(var(--vf-fg-rgb),.025)] hover:border-[rgba(var(--vf-fg-rgb),.08)] hover:bg-[rgba(var(--vf-fg-rgb),.045)]") +
        (disabled ? " opacity-[0.38]" : "")
      }
    >
      <div className="text-center font-mono text-[10px] font-bold text-[var(--vf-m2)]">
        {index + 1}
      </div>

      <div className="relative h-12 w-20 shrink-0 overflow-hidden rounded-[7px] bg-[rgba(var(--vf-fg-rgb),.06)]">
        {scene.imagen_url ? (
          <img
            src={scene.imagen_url}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center rounded-[7px] border border-dashed border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),.05)] font-mono text-[8px] text-[var(--vf-m2)]">
            sin img
          </div>
        )}
      </div>

      <div className="min-w-0">
        <p
          className="overflow-hidden text-[11.5px] leading-[1.38] text-[var(--vf-text)]"
          style={{
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
          }}
        >
          {scene.texto || "(sin texto)"}
        </p>
        <div className="mt-[5px] flex flex-wrap items-center gap-1.5">
          <TipoPill tipo={scene.tipo} />
          {scene.texto_overlay && (
            <span className="font-mono text-[9px] text-[var(--vf-c2)]">
              "{scene.texto_overlay}"
            </span>
          )}
          {timestamp && (
            <span className="font-mono text-[9px] text-[var(--vf-m2)]">
              {timestamp.inicio?.toFixed(1)}s–{timestamp.fin?.toFixed(1)}s
            </span>
          )}
          {scene.ref_image_url && (
            <span
              className="ml-0.5 inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ background: "var(--vf-c5)" }}
              title="Tiene imagen de referencia"
            />
          )}
        </div>
      </div>

      <div className="flex shrink-0 flex-col gap-1">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onSearchImage(index);
          }}
          className="rounded-md border border-[var(--vf-b)] px-2 py-1 font-mono text-[9px] text-[var(--vf-m2)] transition-colors hover:border-[var(--vf-c5)] hover:text-[var(--vf-c5)]"
        >
          Buscar img
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleEnabled(index);
          }}
          className="rounded-md border border-[var(--vf-b)] px-2 py-1 font-mono text-[9px] text-[var(--vf-m2)] transition-colors hover:border-[var(--vf-danger)] hover:text-[var(--vf-danger)]"
        >
          {disabled ? "Activar" : "Desactivar"}
        </button>
      </div>
    </div>
  );
}
