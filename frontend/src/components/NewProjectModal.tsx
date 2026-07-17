import { useState, type FormEvent, type JSX } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { createProject } from "../api/projects";
import ComingSoonToast from "./ComingSoonToast";

type PipelineType = "sketch" | "youtube" | "idea";
type VideoFormat = "largo" | "short";

const ACCENT: Record<PipelineType, string> = {
  sketch: "var(--vf-c1)",
  youtube: "var(--vf-c3)",
  idea: "var(--vf-c5)",
};

function IconClose() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}
function IconCheck() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="1.5,5 4,7.5 8.5,2.5" />
    </svg>
  );
}
function IconSketch() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
    </svg>
  );
}
function IconYoutube() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="4" width="15" height="14" rx="2" />
      <polygon points="23,8 16,11.5 23,15" fill="currentColor" stroke="none" />
    </svg>
  );
}
function IconIdea() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13,2 3,14 12,14 11,22 21,10 12,10" />
    </svg>
  );
}
function IconWide() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <rect x="2" y="5" width="20" height="14" rx="2" />
    </svg>
  );
}
function IconTall() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <rect x="7" y="2" width="10" height="20" rx="2" />
    </svg>
  );
}
function IconStepScript() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
    </svg>
  );
}
function IconStepVoice() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="2" y1="10" x2="2" y2="14" />
      <line x1="6" y1="6" x2="6" y2="18" />
      <line x1="10" y1="8" x2="10" y2="16" />
      <line x1="14" y1="4" x2="14" y2="20" />
      <line x1="18" y1="8" x2="18" y2="16" />
      <line x1="22" y1="10" x2="22" y2="14" />
    </svg>
  );
}
function IconStepImages() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="21,15 16,10 5,21" />
    </svg>
  );
}
function IconStepVideo() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 3l14 9-14 9V3z" />
    </svg>
  );
}
function IconStepRender() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17,8 12,3 7,8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  );
}
function IconStepYoutube() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="4" width="14" height="13" rx="2" />
      <polygon points="22,7 16,10.5 22,14" fill="currentColor" stroke="none" />
    </svg>
  );
}
function IconStepIdea() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13,2 3,14 12,14 11,22 21,10 12,10" />
    </svg>
  );
}
function IconLock() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

const CARDS: { type: PipelineType; Icon: () => JSX.Element; titleKey: string; descKey: string }[] = [
  { type: "sketch", Icon: IconSketch, titleKey: "newProjectModal.cardScriptTitle", descKey: "newProjectModal.cardScriptDesc" },
  { type: "youtube", Icon: IconYoutube, titleKey: "newProjectModal.cardYoutubeTitle", descKey: "newProjectModal.cardYoutubeDesc" },
  { type: "idea", Icon: IconIdea, titleKey: "newProjectModal.cardIdeaTitle", descKey: "newProjectModal.cardIdeaDesc" },
];

const PIPELINE_STEPS: Record<PipelineType, { Icon: () => JSX.Element; labelKey: string }[]> = {
  sketch: [
    { Icon: IconStepScript, labelKey: "newProjectModal.stepScript" },
    { Icon: IconStepVoice, labelKey: "newProjectModal.stepVoice" },
    { Icon: IconStepImages, labelKey: "newProjectModal.stepImages" },
    { Icon: IconStepVideo, labelKey: "newProjectModal.stepVideo" },
    { Icon: IconStepRender, labelKey: "newProjectModal.stepRender" },
  ],
  youtube: [
    { Icon: IconStepYoutube, labelKey: "newProjectModal.stepYoutube" },
    { Icon: IconStepImages, labelKey: "newProjectModal.stepImages" },
    { Icon: IconStepVideo, labelKey: "newProjectModal.stepVideo" },
    { Icon: IconStepRender, labelKey: "newProjectModal.stepRender" },
  ],
  idea: [
    { Icon: IconStepIdea, labelKey: "newProjectModal.stepIdea" },
    { Icon: IconStepScript, labelKey: "newProjectModal.stepScript" },
    { Icon: IconStepVoice, labelKey: "newProjectModal.stepVoice" },
    { Icon: IconStepImages, labelKey: "newProjectModal.stepImages" },
    { Icon: IconStepRender, labelKey: "newProjectModal.stepRender" },
  ],
};

export default function NewProjectModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const { t } = useTranslation();
  const [pipelineType, setPipelineType] = useState<PipelineType>("sketch");
  const [format, setFormat] = useState<VideoFormat>("largo");
  const [nombre, setNombre] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [soonToast, setSoonToast] = useState(false);

  function pickCard(type: PipelineType) {
    if (type !== "sketch") {
      setSoonToast(true);
      return;
    }
    setPipelineType(type);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!nombre.trim()) return;
    setCreating(true);
    setError("");
    try {
      await createProject(nombre.trim());
      onCreated(nombre.trim());
    } catch (err) {
      setError((err as Error).message);
      setCreating(false);
    }
  }

  const accent = ACCENT[pipelineType];

  return createPortal(
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-md" onClick={onClose}>
      <form
        onSubmit={handleSubmit}
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-[560px] rounded-[20px] border p-8 pb-6 shadow-[0_28px_80px_rgba(0,0,0,.5)]"
        style={{ background: "var(--vf-s)", borderColor: "rgba(var(--vf-fg-rgb),.1)" }}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-5 top-5 flex h-7 w-7 items-center justify-center rounded-lg text-[var(--vf-m)] hover:bg-[rgba(var(--vf-fg-rgb),.07)] hover:text-[var(--vf-text)]"
        >
          <IconClose />
        </button>

        <div className="mb-6">
          <div
            className="mb-2 text-[9px] font-bold uppercase tracking-[0.2em]"
            style={{ fontFamily: "var(--vf-mono)", color: "rgba(167,139,250,.65)" }}
          >
            {t("newProjectModal.eyebrow")}
          </div>
          <h2 className="mb-2 text-[26px] font-extrabold leading-[1.15] tracking-[-0.04em] text-[var(--vf-text)]">
            {t("newProjectModal.title")}
          </h2>
          <p className="text-[13px] leading-relaxed text-[var(--vf-m)]">{t("newProjectModal.subtitle")}</p>
        </div>

        <div className="mb-5 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
          {CARDS.map(({ type, Icon, titleKey, descKey }) => {
            const selected = pipelineType === type;
            const cardAccent = ACCENT[type];
            return (
              <button
                type="button"
                key={type}
                onClick={() => pickCard(type)}
                className="flex min-h-[150px] flex-col rounded-2xl border p-4 text-left transition-all hover:-translate-y-0.5"
                style={{
                  borderColor: selected ? cardAccent : "rgba(var(--vf-fg-rgb),.08)",
                  background: selected ? `color-mix(in srgb, ${cardAccent} 10%, transparent)` : "rgba(var(--vf-fg-rgb),.025)",
                  boxShadow: selected ? `0 0 0 4px color-mix(in srgb, ${cardAccent} 12%, transparent)` : "none",
                }}
              >
                <div className="mb-auto flex items-start justify-between pb-3.5">
                  <div
                    className="flex h-11 w-11 items-center justify-center rounded-xl border transition-all"
                    style={{
                      borderColor: selected ? cardAccent : "rgba(var(--vf-fg-rgb),.1)",
                      background: selected
                        ? `color-mix(in srgb, ${cardAccent} 20%, transparent)`
                        : "rgba(var(--vf-fg-rgb),.07)",
                      color: selected ? cardAccent : "var(--vf-m)",
                    }}
                  >
                    <Icon />
                  </div>
                  <div
                    className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full border-[1.5px] transition-all"
                    style={
                      selected
                        ? { background: cardAccent, borderColor: cardAccent }
                        : { borderColor: "rgba(var(--vf-fg-rgb),.18)" }
                    }
                  >
                    {selected && <IconCheck />}
                  </div>
                </div>
                <div className="mt-auto">
                  <div className="mb-1 text-[15px] font-bold tracking-[-0.02em] text-[var(--vf-text)]">{t(titleKey)}</div>
                  <div className="text-[11px] leading-snug text-[var(--vf-m)]">{t(descKey)}</div>
                </div>
              </button>
            );
          })}
        </div>

        <div className="mb-2.5 font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-[var(--vf-m)]">
          {t("newProjectModal.formatLabel")}
        </div>
        <div className="mb-[18px] grid grid-cols-2 gap-2.5">
          <button
            type="button"
            onClick={() => setFormat("largo")}
            className="flex items-center gap-2.5 rounded-xl border px-4 py-3 text-left transition-all"
            style={
              format === "largo"
                ? { borderColor: "rgba(124,106,255,.55)", background: "rgba(124,106,255,.1)", boxShadow: "0 0 0 3px rgba(124,106,255,.1)" }
                : { borderColor: "rgba(var(--vf-fg-rgb),.08)", background: "rgba(var(--vf-fg-rgb),.03)" }
            }
          >
            <span style={{ color: format === "largo" ? "#a78bfa" : "var(--vf-m)" }}>
              <IconWide />
            </span>
            <span className="flex-1 text-[13px] font-semibold" style={{ color: format === "largo" ? "var(--vf-text)" : "var(--vf-m)" }}>
              {t("newProjectModal.formatLong")}
            </span>
            <span className="font-mono text-[10px] text-[var(--vf-m2)]">16:9</span>
          </button>
          <button
            type="button"
            onClick={() => setFormat("short")}
            className="flex items-center gap-2.5 rounded-xl border px-4 py-3 text-left transition-all"
            style={
              format === "short"
                ? { borderColor: "rgba(124,106,255,.55)", background: "rgba(124,106,255,.1)", boxShadow: "0 0 0 3px rgba(124,106,255,.1)" }
                : { borderColor: "rgba(var(--vf-fg-rgb),.08)", background: "rgba(var(--vf-fg-rgb),.03)" }
            }
          >
            <span style={{ color: format === "short" ? "#a78bfa" : "var(--vf-m)" }}>
              <IconTall />
            </span>
            <span className="flex-1 text-[13px] font-semibold" style={{ color: format === "short" ? "var(--vf-text)" : "var(--vf-m)" }}>
              {t("newProjectModal.formatShort")}
            </span>
            <span className="font-mono text-[10px] text-[var(--vf-m2)]">9:16</span>
          </button>
        </div>

        <div className="mb-2.5 font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-[var(--vf-m)]">
          {t("newProjectModal.pipelineLabel")}
        </div>
        <div
          className="mb-[18px] rounded-xl border p-3.5 transition-colors"
          style={{ background: "rgba(var(--vf-fg-rgb),.02)", borderColor: `color-mix(in srgb, ${accent} 20%, transparent)` }}
        >
          <div className="flex flex-wrap items-center gap-1">
            {PIPELINE_STEPS[pipelineType].map((step, i) => (
              <span key={step.labelKey} className="flex items-center gap-1">
                {i > 0 && <span className="px-0.5 text-[10px] text-[var(--vf-m2)]">&#8250;</span>}
                <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-[11px] font-medium text-[var(--vf-m)]">
                  <span className="opacity-60">
                    <step.Icon />
                  </span>
                  {t(step.labelKey)}
                </span>
              </span>
            ))}
          </div>
        </div>

        <div className="mb-2.5 font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-[var(--vf-m)]">
          {t("newProjectModal.titleLabel")}
        </div>
        <input
          autoFocus
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          placeholder={t("newProjectModal.titlePlaceholder") || ""}
          maxLength={60}
          className="mb-1.5 w-full rounded-xl border px-4 py-3 text-[13px] text-[var(--vf-text)] outline-none transition-all placeholder:text-[var(--vf-m2)]"
          style={{ background: "rgba(var(--vf-fg-rgb),.04)", borderColor: "rgba(var(--vf-fg-rgb),.09)" }}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = "rgba(124,106,255,.5)";
            e.currentTarget.style.boxShadow = "0 0 0 3px rgba(124,106,255,.1)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = "rgba(var(--vf-fg-rgb),.09)";
            e.currentTarget.style.boxShadow = "none";
          }}
        />
        {error && <p className="mb-1.5 text-xs text-[var(--vf-danger)]">{error}</p>}

        <div className="mt-5 flex gap-2.5">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-xl border px-4 py-2.5 text-[13px] font-semibold transition-colors"
            style={{ background: "rgba(var(--vf-fg-rgb),.04)", borderColor: "rgba(var(--vf-fg-rgb),.09)", color: "var(--vf-m)" }}
          >
            {t("topbar.cancel")}
          </button>
          <button
            type="submit"
            disabled={creating}
            className="flex-1 rounded-xl px-4 py-2.5 text-[13px] font-bold text-white transition-all hover:-translate-y-px disabled:opacity-50"
            style={{ background: `linear-gradient(135deg, ${accent}, #8b5cf6)`, boxShadow: `0 4px 16px color-mix(in srgb, ${accent} 45%, transparent)` }}
          >
            {creating ? t("topbar.creating") : t("topbar.createProjectArrow")}
          </button>
        </div>

        <div className="mt-3 flex items-center justify-center gap-1.5 text-[11px] text-[var(--vf-m2)]">
          <IconLock />
          {t("newProjectModal.privacyHint")}
        </div>
      </form>

      <ComingSoonToast visible={soonToast} onClose={() => setSoonToast(false)} />
    </div>,
    document.body,
  );
}
