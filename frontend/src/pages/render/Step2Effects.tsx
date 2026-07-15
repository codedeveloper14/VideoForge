import { useTranslation } from "react-i18next";
import {
  Card,
  MODELOS,
  MOTIONS,
  OptionGrid,
  RESOLUCIONES,
  SectionLabel,
  TRANSITIONS,
  WHISPER_BACKENDS,
  WizardPageHeader,
} from "./wizardShared";

interface Step2EffectsProps {
  movimiento: string;
  onMovimientoChange: (v: string) => void;
  shake: boolean;
  onShakeChange: (v: boolean) => void;

  transicion: string;
  onTransicionChange: (v: string) => void;
  transDur: number;
  onTransDurChange: (v: number) => void;

  resolucion: string;
  onResolucionChange: (v: string) => void;
  modelo: string;
  onModeloChange: (v: string) => void;
  whisperBackend: string;
  onWhisperBackendChange: (v: string) => void;

  onBack: () => void;
  onSubmit: () => void;
  submitting: boolean;
}

export default function Step2Effects({
  movimiento,
  onMovimientoChange,
  shake,
  onShakeChange,
  transicion,
  onTransicionChange,
  transDur,
  onTransDurChange,
  resolucion,
  onResolucionChange,
  modelo,
  onModeloChange,
  whisperBackend,
  onWhisperBackendChange,
  onBack,
  onSubmit,
  submitting,
}: Step2EffectsProps) {
  const { t } = useTranslation();
  const motionOptions = MOTIONS.map((m) => ({ value: m.value, label: t(m.labelKey), sub: t(m.subKey), icon: m.icon }));
  const transitionOptions = TRANSITIONS.map((tr) => ({ value: tr.value, label: t(tr.labelKey), sub: t(tr.subKey), icon: tr.icon }));

  return (
    <div>
      <WizardPageHeader title={t("projectRenderPanel.wizardStep2Title")} sub={t("projectRenderPanel.wizardStep2Sub")} />

      <div className="grid gap-4 sm:grid-cols-2">
        <Card icon="🎥" iconBg="rgba(56,189,248,.12)" title={t("projectRenderPanel.cameraMotionTitle")} sub={t("projectRenderPanel.cameraMotionSub")}>
          <OptionGrid options={motionOptions} value={movimiento} onChange={onMovimientoChange} cols={2} />
          <div className="mt-4 flex items-center gap-2.5 border-t border-dashed border-[var(--vf-b2)] pt-3">
            <input
              type="checkbox"
              id="chkShake"
              checked={shake}
              onChange={(e) => onShakeChange(e.target.checked)}
              className="h-4 w-4 cursor-pointer accent-[var(--vf-accent)]"
            />
            <label htmlFor="chkShake" className="cursor-pointer select-none text-xs text-[var(--vf-text)]">
              {t("projectRenderPanel.enableShakeFull")}
            </label>
          </div>
        </Card>

        <Card icon="✨" iconBg="rgba(251,146,60,.12)" title={t("projectRenderPanel.transitionTitle")} sub={t("projectRenderPanel.transitionSub")}>
          <OptionGrid options={transitionOptions} value={transicion} onChange={onTransicionChange} cols={3} />
          {transicion !== "none" && (
            <>
              <SectionLabel>{t("projectRenderPanel.transitionDurationLabel")}</SectionLabel>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="0.3"
                  max="2"
                  step="0.1"
                  value={transDur}
                  onChange={(e) => onTransDurChange(parseFloat(e.target.value))}
                  className="flex-1 accent-[var(--vf-accent)]"
                />
                <span className="min-w-9 text-right font-mono text-[13px] text-[var(--vf-c2)]">{transDur}s</span>
              </div>
            </>
          )}
        </Card>

        <Card icon="⚙️" iconBg="rgba(244,114,182,.12)" title={t("projectRenderPanel.configurationTitle")} sub={t("projectRenderPanel.configurationSub")} full>
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="mb-1.5 block font-mono text-[11px] tracking-wide text-[var(--vf-muted)]">
                {t("projectRenderPanel.resolutionUpper")}
              </label>
              <select
                value={resolucion}
                onChange={(e) => onResolucionChange(e.target.value)}
                className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-p)] p-2 font-mono text-xs text-[var(--vf-text)]"
              >
                {RESOLUCIONES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {t(r.labelKey)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block font-mono text-[11px] tracking-wide text-[var(--vf-muted)]">
                {t("projectRenderPanel.whisperModelUpper")}
              </label>
              <select
                value={modelo}
                onChange={(e) => onModeloChange(e.target.value)}
                className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-p)] p-2 font-mono text-xs text-[var(--vf-text)]"
              >
                {MODELOS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {t(m.labelKey)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block font-mono text-[11px] tracking-wide text-[var(--vf-muted)]">
                {t("projectRenderPanel.whisperEngineUpper")}
              </label>
              <select
                value={whisperBackend}
                onChange={(e) => onWhisperBackendChange(e.target.value)}
                className="w-full rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-p)] p-2 font-mono text-xs text-[var(--vf-text)]"
              >
                {WHISPER_BACKENDS.map((w) => (
                  <option key={w.value} value={w.value}>
                    {t(w.labelKey)}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </Card>
      </div>

      <div className="mt-6 flex gap-3">
        <button
          type="button"
          onClick={onBack}
          className="rounded-xl border-[1.5px] border-[var(--vf-b2)] bg-transparent px-7 py-3.5 text-sm font-semibold text-[var(--vf-muted)] transition-colors hover:border-[var(--vf-c2)] hover:text-[var(--vf-text)]"
        >
          {t("projectRenderPanel.backArrow")}
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={onSubmit}
          className="flex-1 rounded-xl px-4 py-3.5 text-base font-bold text-white shadow-[0_4px_20px_rgba(124,106,255,.3)] transition-all hover:-translate-y-px hover:shadow-[0_8px_30px_rgba(124,106,255,.45)] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 disabled:hover:shadow-none"
          style={{ background: "linear-gradient(135deg, var(--vf-accent), #9f7aea)" }}
        >
          {submitting ? t("projectRenderPanel.sending") : t("projectRenderPanel.generateVideoButton")}
        </button>
      </div>
    </div>
  );
}
