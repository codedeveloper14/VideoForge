import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getPayments, getProfile } from "../api/user";
import { useTheme } from "../context/ThemeContext";
import type { Payment, UserProfile } from "../types";

const PLAN_BADGE_STYLES: Record<string, { background: string; color: string; border: string }> = {
  free: { background: "rgba(148,163,184,.12)", color: "#94a3b8", border: "1px solid rgba(148,163,184,.25)" },
  basico: { background: "rgba(34,211,160,.12)", color: "#22d3a0", border: "1px solid rgba(34,211,160,.25)" },
  pro: { background: "rgba(124,106,255,.15)", color: "#a78bfa", border: "1px solid rgba(167,139,250,.3)" },
  ultra: { background: "rgba(251,191,36,.12)", color: "#fbbf24", border: "1px solid rgba(251,191,36,.25)" },
  unlimited: { background: "rgba(192,132,252,.15)", color: "#c084fc", border: "1px solid rgba(192,132,252,.3)" },
};

function planBadgeStyle(plan: string) {
  return PLAN_BADGE_STYLES[plan] ?? PLAN_BADGE_STYLES.basico;
}

function usagePct(used: number, limit: number | null) {
  if (limit == null || limit <= 0) return 100;
  return Math.min(100, Math.round((used / limit) * 100));
}

function ThemeCard() {
  const { theme, setTheme } = useTheme();

  return (
    <div
      className="mb-6 flex items-center justify-between rounded-[20px] p-6"
      style={{ background: "var(--vf-surface)", border: "1px solid var(--vf-border)" }}
    >
      <div>
        <div
          className="mb-1 font-mono text-[9px] uppercase"
          style={{ color: "var(--vf-m)", letterSpacing: ".14em" }}
        >
          Apariencia
        </div>
        <div className="text-sm font-semibold" style={{ color: "var(--vf-text)" }}>
          Tema {theme === "dark" ? "oscuro" : "claro"}
        </div>
        <p className="mt-1 text-xs" style={{ color: "var(--vf-m)" }}>
          Se guarda en tu cuenta — la próxima vez que inicies sesión, aquí o en otro dispositivo, se aplica igual.
        </p>
      </div>

      <div className="flex flex-shrink-0 gap-1 rounded-full p-1" style={{ background: "var(--vf-p)", border: "1px solid var(--vf-border)" }}>
        <button
          type="button"
          onClick={() => setTheme("dark")}
          className="flex items-center gap-1.5 rounded-full px-3.5 py-2 text-xs font-semibold transition-colors"
          style={
            theme === "dark"
              ? { background: "linear-gradient(135deg,#6c56ff,#a855f7)", color: "#fff" }
              : { color: "var(--vf-m)" }
          }
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          </svg>
          Oscuro
        </button>
        <button
          type="button"
          onClick={() => setTheme("light")}
          className="flex items-center gap-1.5 rounded-full px-3.5 py-2 text-xs font-semibold transition-colors"
          style={
            theme === "light"
              ? { background: "linear-gradient(135deg,#6c56ff,#a855f7)", color: "#fff" }
              : { color: "var(--vf-m)" }
          }
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="4" />
            <line x1="12" y1="2" x2="12" y2="4" />
            <line x1="12" y1="20" x2="12" y2="22" />
            <line x1="4.93" y1="4.93" x2="6.34" y2="6.34" />
            <line x1="17.66" y1="17.66" x2="19.07" y2="19.07" />
            <line x1="2" y1="12" x2="4" y2="12" />
            <line x1="20" y1="12" x2="22" y2="12" />
            <line x1="4.93" y1="19.07" x2="6.34" y2="17.66" />
            <line x1="17.66" y1="6.34" x2="19.07" y2="4.93" />
          </svg>
          Claro
        </button>
      </div>
    </div>
  );
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getProfile(), getPayments()])
      .then(([profileData, paymentsData]) => {
        setProfile(profileData);
        setPayments(paymentsData);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-[var(--vf-muted)]">Cargando perfil…</p>;
  if (error) return <p className="text-sm text-[var(--vf-danger)]">{error}</p>;
  if (!profile) return null;

  const badge = planBadgeStyle(profile.plan);
  const initial = (profile.username || "?").charAt(0).toUpperCase();
  const ttsLimitHours =
    profile.limits.tts_chars_per_month != null
      ? Math.round((profile.limits.tts_chars_per_month / 10000) * 10) / 10
      : null;
  const ttsUsedHours = Math.round((profile.usage.tts_chars / 10000) * 10) / 10;

  return (
    <div className="mx-auto max-w-5xl">
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
        Configuración
      </h1>
      <p
        className="mb-8 font-mono text-[11.5px]"
        style={{ color: "rgba(var(--vf-fg-rgb),.32)", letterSpacing: ".01em" }}
      >
        Tu cuenta, uso y suscripción
      </p>

      {/* Profile card */}
      <div
        className="mb-6 flex items-center gap-5 rounded-[20px] p-7"
        style={{ background: "rgba(var(--vf-fg-rgb),.03)", border: "1px solid rgba(var(--vf-fg-rgb),.07)" }}
      >
        <div
          className="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-full text-[26px] font-extrabold text-white"
          style={{
            letterSpacing: "-.5px",
            background: "linear-gradient(135deg,#6c56ff,#a855f7)",
            boxShadow: "0 0 0 3px rgba(124,106,255,.3),0 6px 24px rgba(0,0,0,.5)",
          }}
        >
          {initial}
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-[3px] text-xl font-extrabold" style={{ letterSpacing: "-.4px", color: "var(--vf-text)" }}>
            {profile.username}
          </div>
          <div
            className="mb-2.5 truncate font-mono text-[11px]"
            style={{ color: "rgba(var(--vf-fg-rgb),.35)" }}
          >
            {profile.email}
          </div>
          <span
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-[5px] font-mono text-[10px] font-bold uppercase"
            style={{ letterSpacing: ".08em", ...badge }}
          >
            {profile.plan_name}
          </span>
        </div>
      </div>

      {/* Appearance card */}
      <ThemeCard />

      {/* Usage card */}
      <div
        className="mb-6 rounded-[20px] p-6"
        style={{ background: "rgba(var(--vf-fg-rgb),.03)", border: "1px solid rgba(var(--vf-fg-rgb),.07)" }}
      >
        <div
          className="mb-[18px] font-mono text-[9px] uppercase"
          style={{ color: "rgba(var(--vf-fg-rgb),.3)", letterSpacing: ".14em" }}
        >
          Uso este mes
        </div>

        <div className="mb-4">
          <div className="mb-[7px] flex justify-between font-mono text-[11px]">
            <span style={{ color: "rgba(var(--vf-fg-rgb),.65)" }}>Videos generados</span>
            <span style={{ color: "rgba(var(--vf-fg-rgb),.3)" }}>
              {profile.usage.videos} / {profile.limits.videos_per_month ?? "—"}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-lg" style={{ background: "rgba(var(--vf-fg-rgb),.06)" }}>
            <div
              className="h-full rounded-lg transition-[width]"
              style={{
                width: `${usagePct(profile.usage.videos, profile.limits.videos_per_month)}%`,
                background: "linear-gradient(90deg,#7c6aff,#a855f7)",
              }}
            />
          </div>
        </div>

        <div className="mb-4">
          <div className="mb-[7px] flex justify-between font-mono text-[11px]">
            <span style={{ color: "rgba(var(--vf-fg-rgb),.65)" }}>Shorts generados</span>
            <span style={{ color: "rgba(var(--vf-fg-rgb),.3)" }}>
              {profile.usage.shorts} / {profile.limits.shorts_per_month ?? "—"}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-lg" style={{ background: "rgba(var(--vf-fg-rgb),.06)" }}>
            <div
              className="h-full rounded-lg transition-[width]"
              style={{
                width: `${usagePct(profile.usage.shorts, profile.limits.shorts_per_month)}%`,
                background: "linear-gradient(90deg,#fbbf24,#f59e0b)",
              }}
            />
          </div>
        </div>

        <div>
          <div className="mb-[7px] flex justify-between font-mono text-[11px]">
            <span style={{ color: "rgba(var(--vf-fg-rgb),.65)" }}>Generación de voz</span>
            <span style={{ color: "rgba(var(--vf-fg-rgb),.3)" }}>
              {ttsUsedHours} / {ttsLimitHours ?? "—"} h
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-lg" style={{ background: "rgba(var(--vf-fg-rgb),.06)" }}>
            <div
              className="h-full rounded-lg transition-[width]"
              style={{
                width: `${usagePct(ttsUsedHours, ttsLimitHours)}%`,
                background: "linear-gradient(90deg,#22d3a0,#7c6aff)",
              }}
            />
          </div>
        </div>
      </div>

      {/* Subscription card */}
      <div
        className="mb-6 rounded-[20px] px-6 py-5"
        style={{ background: "rgba(var(--vf-fg-rgb),.02)", border: "1px solid rgba(var(--vf-fg-rgb),.07)" }}
      >
        <div
          className="mb-3.5 font-mono text-[9px] uppercase"
          style={{ color: "rgba(var(--vf-fg-rgb),.3)", letterSpacing: ".14em" }}
        >
          💳  Suscripción
        </div>
        {profile.subscription_date && (
          <div
            className="flex items-center justify-between py-[9px]"
            style={{ borderBottom: "1px solid rgba(var(--vf-fg-rgb),.05)" }}
          >
            <span className="font-mono text-[10.5px]" style={{ color: "rgba(var(--vf-fg-rgb),.42)" }}>
              Fecha de suscripción
            </span>
            <span className="font-mono text-[10.5px] font-semibold" style={{ color: "rgba(var(--vf-fg-rgb),.82)" }}>
              {profile.subscription_date}
            </span>
          </div>
        )}
        <div
          className="flex items-center justify-between py-[9px]"
          style={{ borderBottom: "1px solid rgba(var(--vf-fg-rgb),.05)" }}
        >
          <span className="font-mono text-[10.5px]" style={{ color: "rgba(var(--vf-fg-rgb),.42)" }}>
            Plan activado
          </span>
          <span className="font-mono text-[10.5px] font-semibold" style={{ color: "rgba(var(--vf-fg-rgb),.82)" }}>
            {profile.payment.activated_at || "—"}
          </span>
        </div>
        <div className="flex items-center justify-between py-[9px] last:pb-0" style={{ borderBottom: "none" }}>
          <span className="font-mono text-[10.5px]" style={{ color: "rgba(var(--vf-fg-rgb),.42)" }}>
            Próxima renovación
          </span>
          <span className="font-mono text-[10.5px] font-semibold" style={{ color: "rgba(var(--vf-fg-rgb),.82)" }}>
            {profile.payment.expires_at || "—"}
          </span>
        </div>
      </div>

      {/* Payment history card */}
      {payments.length > 0 && (
        <div
          className="mb-6 rounded-[20px] px-6 py-5"
          style={{ background: "rgba(var(--vf-fg-rgb),.02)", border: "1px solid rgba(var(--vf-fg-rgb),.07)" }}
        >
          <div
            className="mb-3.5 font-mono text-[9px] uppercase"
            style={{ color: "rgba(var(--vf-fg-rgb),.3)", letterSpacing: ".14em" }}
          >
            📈  Historial de pagos
          </div>
          <div className="flex flex-col gap-1.5">
            {payments.map((p, i) => (
              <div
                key={i}
                className="flex items-center justify-between py-[9px]"
                style={{
                  borderBottom:
                    i === payments.length - 1 ? "none" : "1px solid rgba(var(--vf-fg-rgb),.05)",
                }}
              >
                <span className="font-mono text-[10.5px]" style={{ color: "rgba(var(--vf-fg-rgb),.42)" }}>
                  {p.plan}
                </span>
                <span className="font-mono text-[10.5px] font-semibold" style={{ color: "rgba(var(--vf-fg-rgb),.82)" }}>
                  ${p.amount_usd} · {p.paid_at}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <Link
        to="/app/planes"
        className="block w-full rounded-2xl py-3.5 text-center font-mono text-xs font-bold uppercase text-white no-underline"
        style={{
          letterSpacing: ".06em",
          background: "linear-gradient(135deg,#6c56ff 0%,#a855f7 100%)",
        }}
      >
        ↗ Ver planes y hacer upgrade
      </Link>
    </div>
  );
}
