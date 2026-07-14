import { useTranslation } from "react-i18next";
import type { EditorScene, TimestampEntry } from "../../api/editor";

const TIPO_STYLES: Record<string, string> = {
  normal: "bg-[rgba(var(--vf-fg-rgb),0.1)] text-[var(--vf-muted)]",
  intro_dinamica: "bg-[var(--vf-c3)]/20 text-[var(--vf-c3)]",
  texto_enfasis: "bg-[var(--vf-c4)]/20 text-[var(--vf-c4)]",
  lower_third: "bg-[var(--vf-c6)]/20 text-[var(--vf-c6)]",
  nombre_persona: "bg-[var(--vf-c6)]/20 text-[var(--vf-c6)]",
  texto_lateral: "bg-[var(--vf-c1)]/20 text-[var(--vf-c2)]",
  ref_persona: "bg-[var(--vf-c6)]/20 text-[var(--vf-c6)]",
  ref_lugar: "bg-[var(--vf-c4)]/20 text-[var(--vf-c4)]",
  ref_doble: "bg-[var(--vf-c3)]/20 text-[var(--vf-c3)]",
  google_fullscreen: "bg-[var(--vf-c5)]/20 text-[var(--vf-c5)]",
  broll: "bg-[var(--vf-c5)]/20 text-[var(--vf-c5)]",
  quote_animado: "bg-[var(--vf-c2)]/20 text-[var(--vf-c2)]",
  titulo_capitulo: "bg-[var(--vf-c3)]/20 text-[var(--vf-c3)]",
};

function TipoPill({ tipo }: { tipo?: string }) {
  if (!tipo) return null;
  const cls = TIPO_STYLES[tipo] || TIPO_STYLES.normal;
  return (
    <span
      className={`rounded-full px-2 py-0.5 font-mono text-[8.5px] font-bold uppercase tracking-wide ${cls}`}
    >
      {tipo.replace(/_/g, " ")}
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
  const { t } = useTranslation();
  const disabled = scene.habilitado === false;

  return (
    <div
      onClick={() => onSelect(index)}
      className={
        "mb-1.5 grid cursor-pointer grid-cols-[28px_88px_1fr_auto] items-center gap-2.5 rounded-xl border p-2.5 transition-colors " +
        (selected
          ? "border-[var(--vf-c5)]/40 bg-[var(--vf-c5)]/10"
          : "border-transparent bg-[rgba(var(--vf-fg-rgb),0.025)] hover:border-[rgba(var(--vf-fg-rgb),0.1)] hover:bg-[rgba(var(--vf-fg-rgb),0.045)]") +
        (disabled ? " opacity-40" : "")
      }
    >
      <div className="text-center font-mono text-[10px] font-bold text-[var(--vf-muted)]">
        {index + 1}
      </div>

      <div className="relative h-12 w-[88px] shrink-0 overflow-hidden rounded-lg bg-[rgba(var(--vf-fg-rgb),0.05)]">
        {scene.imagen_url ? (
          <img
            src={scene.imagen_url}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center border border-dashed border-[var(--vf-border)] font-mono text-[8px] text-[var(--vf-muted)]">
            {t("editorTool.noImage")}
          </div>
        )}
      </div>

      <div className="min-w-0">
        <p
          className="overflow-hidden text-[11.5px] leading-snug text-[var(--vf-text)]"
          style={{
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
          }}
        >
          {scene.texto || t("editorTool.noText")}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <TipoPill tipo={scene.tipo} />
          {scene.texto_overlay && (
            <span className="font-mono text-[9px] text-[var(--vf-c2)]">
              "{scene.texto_overlay}"
            </span>
          )}
          {timestamp && (
            <span className="font-mono text-[9px] text-[var(--vf-muted)]">
              {timestamp.inicio?.toFixed(1)}s–{timestamp.fin?.toFixed(1)}s
            </span>
          )}
        </div>
      </div>

      <div className="flex shrink-0 flex-col gap-1">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onSearchImage(index);
          }}
          className="rounded-md border border-[var(--vf-border)] px-2 py-1 font-mono text-[9px] text-[var(--vf-muted)] hover:border-[var(--vf-c5)] hover:text-[var(--vf-c5)]"
        >
          {t("editorTool.searchImage")}
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleEnabled(index);
          }}
          className="rounded-md border border-[var(--vf-border)] px-2 py-1 font-mono text-[9px] text-[var(--vf-muted)] hover:border-[var(--vf-danger)] hover:text-[var(--vf-danger)]"
        >
          {disabled ? t("editorTool.enable") : t("editorTool.disable")}
        </button>
      </div>
    </div>
  );
}
