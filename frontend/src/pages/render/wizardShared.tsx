// Shared pieces for the Render wizard (Archivos -> Efectos -> Render),
// styled after the legacy reference (.pg-render / .card / .opt-btn / .drop-zone idiom).
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

// label/sub quedan como *Key -- estos son consts a nivel de modulo (fuera de
// cualquier componente), asi que no pueden llamar useTranslation() aca. Cada
// Step*.tsx los resuelve con t() al consumirlos.
export const RESOLUCIONES = [
  { value: "1920x1080", labelKey: "projectRenderPanel.resYoutube" },
  { value: "1080x1920", labelKey: "projectRenderPanel.resReels" },
  { value: "1080x1080", labelKey: "projectRenderPanel.resInstagram" },
  { value: "1280x720", labelKey: "projectRenderPanel.resHd" },
];

export const MODELOS = [
  { value: "tiny", labelKey: "projectRenderPanel.modelTiny" },
  { value: "base", labelKey: "projectRenderPanel.modelBase" },
  { value: "small", labelKey: "projectRenderPanel.modelSmall" },
  { value: "medium", labelKey: "projectRenderPanel.modelMedium" },
];

export const WHISPER_BACKENDS = [
  { value: "whisperx", labelKey: "projectRenderPanel.whisperXApi" },
  { value: "api", labelKey: "projectRenderPanel.whisperApi" },
  { value: "faster", labelKey: "projectRenderPanel.whisperFaster" },
  { value: "local", labelKey: "projectRenderPanel.whisperLocal" },
];

export const RENDER_MODES = [
  { value: "images", labelKey: "projectRenderPanel.modeImagesOnly", icon: "🖼️", descKey: "" },
  { value: "smart", labelKey: "projectRenderPanel.modeSmartMix", icon: "🧠", descKey: "projectRenderPanel.modeSmartMixDesc" },
  { value: "videos", labelKey: "projectRenderPanel.modeVideosOnly", icon: "🎬", descKey: "" },
];

export const MOTIONS = [
  { value: "none", labelKey: "projectRenderPanel.motionNone", subKey: "projectRenderPanel.motionNoneSub", icon: "⬜" },
  { value: "ken_burns", labelKey: "projectRenderPanel.motionKenBurns", subKey: "projectRenderPanel.motionKenBurnsSub", icon: "🎬" },
  { value: "zoom_in", labelKey: "projectRenderPanel.motionZoomIn", subKey: "projectRenderPanel.motionZoomInSub", icon: "🔍" },
  { value: "zoom_out", labelKey: "projectRenderPanel.motionZoomOut", subKey: "projectRenderPanel.motionZoomOutSub", icon: "🔭" },
  { value: "pan_left", labelKey: "projectRenderPanel.motionPanLeft", subKey: "projectRenderPanel.motionPanLeftSub", icon: "⬅️" },
  { value: "pan_right", labelKey: "projectRenderPanel.motionPanRight", subKey: "projectRenderPanel.motionPanRightSub", icon: "➡️" },
];

export const TRANSITIONS = [
  { value: "none", labelKey: "projectRenderPanel.transitionNone", subKey: "projectRenderPanel.transitionNoneSub", icon: "✂️" },
  { value: "dissolve", labelKey: "projectRenderPanel.transitionDissolve", subKey: "projectRenderPanel.transitionDissolveSub", icon: "✦" },
  { value: "slide_left", labelKey: "projectRenderPanel.transitionSlideLeft", subKey: "projectRenderPanel.transitionSlideLeftSub", icon: "◀️" },
  { value: "slide_right", labelKey: "projectRenderPanel.transitionSlideRight", subKey: "projectRenderPanel.transitionSlideRightSub", icon: "▶️" },
  { value: "zoom", labelKey: "projectRenderPanel.transitionZoom", subKey: "projectRenderPanel.transitionZoomSub", icon: "🔮" },
  { value: "fade", labelKey: "projectRenderPanel.transitionFade", subKey: "projectRenderPanel.transitionFadeSub", icon: "⬛" },
];

export function formatSize(bytes: number) {
  return bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
}

export function formatDur(s: number) {
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

interface WizardProgressProps {
  step: 1 | 2 | 3;
}

const STEPS: { id: 1 | 2 | 3; labelKey: string; dot: string }[] = [
  { id: 1, labelKey: "projectRenderPanel.stepFiles", dot: "1" },
  { id: 2, labelKey: "projectRenderPanel.stepEffects", dot: "2" },
  { id: 3, labelKey: "projectRenderPanel.stepRender", dot: "🎬" },
];

export function WizardProgress({ step }: WizardProgressProps) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto mb-8 flex max-w-[560px] items-center gap-0">
      {STEPS.map((s, i) => {
        const state = s.id < step ? "done" : s.id === step ? "active" : "pending";
        return (
          <div key={s.id} className="relative flex flex-1 flex-col items-center">
            {i < STEPS.length - 1 && (
              <div
                className="absolute left-[calc(50%+20px)] top-[18px] h-0.5 z-0"
                style={{
                  width: "calc(100% - 40px)",
                  background:
                    state === "done"
                      ? "var(--vf-success)"
                      : state === "active"
                        ? "linear-gradient(90deg, var(--vf-accent), var(--vf-b2))"
                        : "var(--vf-b2)",
                }}
              />
            )}
            <div
              className="relative z-[1] flex h-9 w-9 items-center justify-center rounded-full border-2 font-mono text-xs font-bold transition-all"
              style={
                state === "active"
                  ? {
                      borderColor: "var(--vf-accent)",
                      background: "var(--vf-accent)",
                      color: "#fff",
                      boxShadow: "0 0 16px rgba(124,106,255,.4)",
                    }
                  : state === "done"
                    ? { borderColor: "var(--vf-success)", background: "var(--vf-success)", color: "#000" }
                    : { borderColor: "var(--vf-b2)", background: "var(--vf-p)", color: "var(--vf-muted)" }
              }
            >
              {s.dot}
            </div>
            <div
              className="mt-2 text-center font-mono text-[11px] tracking-wide"
              style={{
                color:
                  state === "active"
                    ? "var(--vf-c2)"
                    : state === "done"
                      ? "var(--vf-success)"
                      : "var(--vf-muted)",
              }}
            >
              {t(s.labelKey)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

interface PageHeaderProps {
  title: string;
  sub: string;
}

export function WizardPageHeader({ title, sub }: PageHeaderProps) {
  return (
    <div className="px-0 pb-8 pt-2 text-center">
      <h2
        className="mb-2 text-[clamp(24px,4vw,38px)] font-extrabold leading-tight tracking-tight"
        style={{
          background: "linear-gradient(135deg, #fff 30%, var(--vf-c2) 70%, var(--vf-c1))",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent",
          backgroundClip: "text",
        }}
      >
        {title}
      </h2>
      <p className="font-mono text-sm text-[var(--vf-muted)]">{sub}</p>
    </div>
  );
}

interface CardProps {
  icon: string;
  iconBg?: string;
  title: string;
  sub: string;
  full?: boolean;
  children: ReactNode;
}

export function Card({ icon, iconBg, title, sub, full, children }: CardProps) {
  return (
    <div
      className={`rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5 transition-colors hover:border-[var(--vf-b2)] ${full ? "sm:col-span-2" : ""}`}
    >
      <div className="mb-3.5 flex items-center gap-2.5">
        <div
          className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-lg text-[15px]"
          style={{ background: iconBg || "rgba(124,106,255,.15)" }}
        >
          {icon}
        </div>
        <div>
          <div className="text-sm font-bold text-[var(--vf-text)]">{title}</div>
          <div className="font-mono text-[11px] text-[var(--vf-muted)]">{sub}</div>
        </div>
      </div>
      {children}
    </div>
  );
}

interface DropZoneProps {
  icon: string;
  label: ReactNode;
  hint: string;
  accept: string;
  multiple?: boolean;
  onFiles: (files: File[]) => void;
}

export function DropZone({ icon, label, hint, accept, multiple, onFiles }: DropZoneProps) {
  return (
    <label className="relative block cursor-pointer rounded-xl border-2 border-dashed border-[var(--vf-b2)] px-4 py-7 text-center transition-colors hover:border-[var(--vf-accent)] hover:bg-[var(--vf-accent)]/[0.04]">
      <input
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={(e) => {
          const files = Array.from(e.target.files || []);
          if (files.length) onFiles(files);
          e.target.value = "";
        }}
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
      />
      <div className="mb-1.5 text-[26px]">{icon}</div>
      <div className="text-[13px] text-[var(--vf-muted)]">{label}</div>
      <div className="mt-1 font-mono text-[11px] text-[var(--vf-m2)]">{hint}</div>
    </label>
  );
}

interface OptionGridProps<T extends string> {
  options: { value: T; label: string; sub: string; icon: string }[];
  value: T;
  onChange: (value: T) => void;
  cols?: 2 | 3;
}

export function OptionGrid<T extends string>({ options, value, onChange, cols = 2 }: OptionGridProps<T>) {
  return (
    <div className={`grid gap-2 ${cols === 2 ? "grid-cols-2" : "grid-cols-3"}`}>
      {options.map((opt) => (
        <button
          type="button"
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`select-none rounded-[10px] border-[1.5px] px-2 py-2.5 text-center transition-all ${
            value === opt.value
              ? "border-[var(--vf-accent)] bg-[var(--vf-accent)]/[0.12]"
              : "border-[var(--vf-b2)] bg-[var(--vf-p)] hover:border-[var(--vf-c2)] hover:bg-[var(--vf-accent)]/[0.06]"
          }`}
        >
          <div className="mb-1 text-[20px]">{opt.icon}</div>
          <span
            className={`block text-[11px] font-semibold ${value === opt.value ? "text-[var(--vf-c2)]" : "text-[var(--vf-text)]"}`}
          >
            {opt.label}
          </span>
          <span className="mt-0.5 block font-mono text-[10px] text-[var(--vf-muted)]">{opt.sub}</span>
        </button>
      ))}
    </div>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="mb-2.5 mt-4 font-mono text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
      {children}
    </div>
  );
}
