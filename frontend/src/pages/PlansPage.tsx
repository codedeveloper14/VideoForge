import { useEffect, useState } from "react";
import { listPlans } from "../api/plans";
import { startCheckout } from "../api/stripe";
import { getProfile } from "../api/user";
import type { Plan } from "../types";

function IconFree() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="7.5" />
    </svg>
  );
}
function IconSprout() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 20V11" />
      <path d="M12 11c0-3.5-2.5-6-6.5-6C5.5 9 8 11.5 12 11.5" />
      <path d="M12 11c0-3 2-5.5 5.5-5.5C17.8 9 15.5 11 12 11" />
    </svg>
  );
}
function IconGrowthBars() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <line x1="6" y1="20" x2="6" y2="14" />
      <line x1="12" y1="20" x2="12" y2="9" />
      <line x1="18" y1="20" x2="18" y2="4" />
    </svg>
  );
}
function IconGem() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 3h12l3 5-9 13L3 8z" />
      <path d="M3 8h18M9 3l3 5 3-5M12 8l-3 13M12 8l3 13" />
    </svg>
  );
}
function IconInfinity() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18.178 8c5.096 0 5.096 8 0 8-5.095 0-7.133-8-12.739-8-4.585 0-4.585 8 0 8 5.606 0 7.644-8 12.739-8z" />
    </svg>
  );
}

const PLAN_ICONS = {
  free: IconFree,
  basico: IconSprout,
  pro: IconGrowthBars,
  ultra: IconGem,
  unlimited: IconInfinity,
} as Record<string, () => React.ReactElement>;

type PlanTheme = {
  accent: string;
  iconBg: string;
  iconColor: string;
  iconBorder: string;
  nameColor: string;
  checkBg: string;
  btnClass: string;
  cardStyle?: React.CSSProperties;
  ribbon?: string;
};

const THEMES: Record<string, PlanTheme> = {
  free: {
    accent: "linear-gradient(90deg,#475569,#64748b)",
    iconBg: "rgba(100,116,139,.12)",
    iconColor: "#94a3b8",
    iconBorder: "1px solid rgba(100,116,139,.2)",
    nameColor: "#94a3b8",
    checkBg: "#64748b20",
    btnClass: "free-btn",
  },
  basico: {
    accent: "linear-gradient(90deg,#22d3a0,#0ea5e9)",
    iconBg: "rgba(34,211,160,.12)",
    iconColor: "#22d3a0",
    iconBorder: "1px solid rgba(34,211,160,.2)",
    nameColor: "#22d3a0",
    checkBg: "#22d3a020",
    btnClass: "starter-btn",
  },
  pro: {
    accent: "linear-gradient(90deg,#6c56ff,#a855f7,#ec4899)",
    iconBg: "rgba(124,106,255,.15)",
    iconColor: "#a78bfa",
    iconBorder: "1px solid rgba(167,139,250,.22)",
    nameColor: "#a78bfa",
    checkBg: "#7c6aff20",
    btnClass: "pro-btn",
    ribbon: "Más popular",
  },
  ultra: {
    accent: "linear-gradient(90deg,#fbbf24,#f97316)",
    iconBg: "rgba(251,191,36,.12)",
    iconColor: "#fbbf24",
    iconBorder: "1px solid rgba(251,191,36,.2)",
    nameColor: "#fbbf24",
    checkBg: "#fbbf2420",
    btnClass: "ultra-btn",
  },
  unlimited: {
    accent: "linear-gradient(90deg,#9333ea,#c084fc,#e879f9)",
    iconBg: "rgba(192,132,252,.15)",
    iconColor: "#c084fc",
    iconBorder: "1px solid rgba(192,132,252,.25)",
    nameColor: "#c084fc",
    checkBg: "#c084fc20",
    btnClass: "unlimited-btn",
    cardStyle: {
      background: "linear-gradient(160deg,rgba(147,51,234,.1) 0%,rgba(192,132,252,.04) 100%)",
      borderColor: "rgba(192,132,252,.25)",
    },
    ribbon: "⬡ Enterprise",
  },
};

const DEFAULT_THEME: PlanTheme = THEMES.basico;

function themeFor(planId: string): PlanTheme {
  return THEMES[planId] ?? DEFAULT_THEME;
}

function planFeatures(plan: Plan): string[] {
  const feats: string[] = [];
  if (plan.videos_per_month != null) feats.push(`${plan.videos_per_month} videos al mes`);
  if (plan.videos_per_day != null) feats.push(`${plan.videos_per_day} videos al día`);
  if (plan.shorts_per_month != null) feats.push(`${plan.shorts_per_month} shorts al mes`);
  if (plan.audio_hours_per_month != null) feats.push(`${plan.audio_hours_per_month} h audio al mes`);
  if (plan.tts_mins_per_day != null) feats.push(`${plan.tts_mins_per_day} min de voz al día`);
  if (plan.max_video_minutes != null) feats.push(`hasta ${plan.max_video_minutes} min por video`);
  return feats;
}

export default function PlansPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [currentPlan, setCurrentPlan] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [checkingOut, setCheckingOut] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listPlans(), getProfile()])
      .then(([plansData, profile]) => {
        setPlans(plansData);
        setCurrentPlan(profile.plan);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleSubscribe(planId: string) {
    setCheckingOut(planId);
    setError("");
    try {
      const { url } = await startCheckout(planId);
      if (url) {
        window.location.href = url;
      } else {
        setError("No se pudo iniciar el pago para este plan.");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCheckingOut(null);
    }
  }

  if (loading) return <p className="text-[var(--vf-muted)]">Cargando planes…</p>;

  return (
    <div>
      <h1
        className="mb-2 text-[34px] font-extrabold"
        style={{
          letterSpacing: "-.8px",
          background: "linear-gradient(90deg,var(--vf-text) 30%,var(--vf-c2))",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent",
          backgroundClip: "text",
        }}
      >
        Elige tu plan
      </h1>
      <p
        className="mb-9 max-w-xl font-mono text-[11.5px]"
        style={{ color: "rgba(var(--vf-fg-rgb),.32)", letterSpacing: ".01em" }}
      >
        Escala tu producción. Cancela cuando quieras.
      </p>

      {error && <p className="mb-4 text-sm text-[var(--vf-danger)]">{error}</p>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {plans.map((plan) => {
          const isCurrent = plan.id === currentPlan;
          const isFree = plan.id === "free";
          const theme = themeFor(plan.id);
          const isHighlight = plan.highlight && !isCurrent;
          const feats = planFeatures(plan);

          return (
            <div
              key={plan.id}
              className={`relative flex flex-col overflow-hidden rounded-[22px] ${
                isFree ? "opacity-75" : ""
              }`}
              style={{
                background: "rgba(var(--vf-fg-rgb),.038)",
                border: isCurrent
                  ? "1px solid rgba(34,211,160,.42)"
                  : "1px solid rgba(var(--vf-fg-rgb),.09)",
                boxShadow: isCurrent
                  ? "0 0 0 1px rgba(34,211,160,.14),0 8px 32px rgba(34,211,160,.07)"
                  : isHighlight
                    ? "0 0 0 1px rgba(108,86,255,.22),0 24px 70px rgba(108,86,255,.22),0 8px 24px rgba(0,0,0,.45)"
                    : undefined,
                transform: isHighlight ? "translateY(-10px)" : undefined,
                ...theme.cardStyle,
              }}
            >
              <div className="h-1 w-full flex-shrink-0" style={{ background: theme.accent }} />
              <div className="flex flex-1 flex-col px-[22px] pb-[22px] pt-[26px]">
                {isCurrent && (
                  <div
                    className="mb-4 inline-flex w-fit items-center gap-1.5 rounded-full px-3 py-1 font-mono text-[9px] font-bold uppercase text-[#22d3a0]"
                    style={{
                      letterSpacing: ".1em",
                      background: "rgba(34,211,160,.12)",
                      border: "1px solid rgba(34,211,160,.3)",
                    }}
                  >
                    ✓ Tu plan actual
                  </div>
                )}
                {!isCurrent && theme.ribbon && (
                  <div
                    className="mb-4 inline-flex w-fit items-center gap-1.5 rounded-full px-[13px] py-[5px] font-mono text-[9px] font-bold uppercase text-white"
                    style={{
                      letterSpacing: ".1em",
                      background:
                        plan.id === "unlimited"
                          ? "linear-gradient(135deg,#9333ea,#c084fc)"
                          : "linear-gradient(135deg,#6c56ff,#a855f7)",
                      boxShadow: "0 3px 14px rgba(108,86,255,.45)",
                    }}
                  >
                    {theme.ribbon}
                  </div>
                )}

                <div className="mb-1 flex items-center gap-3">
                  <span
                    className="flex h-[42px] w-[42px] flex-shrink-0 items-center justify-center rounded-[13px]"
                    style={{ background: theme.iconBg, color: theme.iconColor, border: theme.iconBorder }}
                  >
                    {(PLAN_ICONS[plan.id] ?? IconFree)()}
                  </span>
                  <span className="text-[22px] font-extrabold" style={{ letterSpacing: "-.5px", color: theme.nameColor }}>
                    {plan.name}
                  </span>
                </div>

                <div className="mb-5 flex items-end gap-[5px]" style={{ lineHeight: 1 }}>
                  <span className="text-[46px] font-extrabold" style={{ letterSpacing: "-2.5px", lineHeight: 0.88, color: theme.nameColor }}>
                    ${plan.price_usd}
                  </span>
                  <span className="mb-[5px] text-xs" style={{ color: "rgba(var(--vf-fg-rgb),.28)" }}>
                    /mes
                  </span>
                </div>

                <div className="mb-5 h-px" style={{ background: "rgba(var(--vf-fg-rgb),.07)" }} />

                <ul className="mb-6 flex flex-1 flex-col gap-[11px]" style={{ listStyle: "none", padding: 0, margin: 0 }}>
                  {feats.map((f, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2.5 text-[12.5px]"
                      style={{ color: "rgba(var(--vf-fg-rgb),.68)", lineHeight: 1.4 }}
                    >
                      <span
                        className="mt-[1px] flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full text-[11px] font-extrabold"
                        style={{ background: theme.checkBg, color: theme.iconColor }}
                      >
                        ✓
                      </span>
                      {f}
                    </li>
                  ))}
                </ul>

                <button
                  onClick={() => handleSubscribe(plan.id)}
                  disabled={isCurrent || isFree || checkingOut === plan.id}
                  className={`w-full rounded-[13px] py-3.5 font-mono text-[11px] font-bold uppercase transition-transform ${
                    isCurrent || isFree ? "cursor-default" : "cursor-pointer hover:-translate-y-0.5"
                  }`}
                  style={{
                    letterSpacing: ".06em",
                    ...(isCurrent
                      ? {
                          background: "rgba(var(--vf-fg-rgb),.05)",
                          border: "1.5px solid rgba(var(--vf-fg-rgb),.1)",
                          color: "rgba(var(--vf-fg-rgb),.3)",
                        }
                      : isFree
                        ? {
                            background: "rgba(var(--vf-fg-rgb),.04)",
                            border: "1px solid rgba(var(--vf-fg-rgb),.07)",
                            color: "rgba(var(--vf-fg-rgb),.35)",
                          }
                        : theme.btnClass === "starter-btn"
                          ? {
                              color: "#052e1c",
                              background: "linear-gradient(135deg,#22d3a0,#10b981)",
                              boxShadow: "0 4px 18px rgba(34,211,160,.32)",
                              border: "none",
                            }
                          : theme.btnClass === "pro-btn"
                            ? {
                                color: "#fff",
                                background: "linear-gradient(135deg,#6c56ff,#a855f7)",
                                boxShadow: "0 4px 22px rgba(108,86,255,.45)",
                                border: "none",
                              }
                            : theme.btnClass === "ultra-btn"
                              ? {
                                  color: "#2d1a00",
                                  background: "linear-gradient(135deg,#fbbf24,#f59e0b)",
                                  boxShadow: "0 4px 18px rgba(251,191,36,.32)",
                                  border: "none",
                                }
                              : theme.btnClass === "unlimited-btn"
                                ? {
                                    color: "#fff",
                                    background: "linear-gradient(135deg,#9333ea,#c084fc,#e879f9)",
                                    boxShadow: "0 4px 22px rgba(192,132,252,.45)",
                                    border: "none",
                                  }
                                : {}),
                  }}
                >
                  {isCurrent
                    ? "Plan actual"
                    : isFree
                      ? "Plan gratuito"
                      : checkingOut === plan.id
                        ? "Redirigiendo…"
                        : `↗ Elegir ${plan.name}`}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
