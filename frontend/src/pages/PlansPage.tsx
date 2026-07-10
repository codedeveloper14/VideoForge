import { useEffect, useState } from "react";
import { listPlans } from "../api/plans";
import { startCheckout } from "../api/stripe";
import { getProfile } from "../api/user";
import type { Plan } from "../types";

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
      <h1 className="mb-6 text-2xl font-semibold">Planes</h1>
      {error && <p className="mb-4 text-sm text-[var(--vf-danger)]">{error}</p>}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {plans.map((plan) => {
          const isCurrent = plan.id === currentPlan;
          return (
            <div
              key={plan.id}
              className={`flex flex-col rounded-2xl border p-6 ${
                plan.highlight
                  ? "border-[var(--vf-accent)] bg-[var(--vf-surface-2)]"
                  : "border-[var(--vf-border)] bg-[var(--vf-surface)]"
              }`}
            >
              <div className="mb-2 text-2xl">{plan.emoji}</div>
              <h2 className="text-lg font-semibold">{plan.name}</h2>
              <p className="mt-1 text-2xl font-bold">
                ${plan.price_usd}
                <span className="text-sm font-normal text-[var(--vf-muted)]">/mes</span>
              </p>
              <ul className="mt-4 flex-1 space-y-1 text-sm text-[var(--vf-muted)]">
                {plan.videos_per_month != null && (
                  <li>{plan.videos_per_month} videos/mes</li>
                )}
                {plan.videos_per_day != null && <li>{plan.videos_per_day} videos/día</li>}
                {plan.shorts_per_month != null && (
                  <li>{plan.shorts_per_month} shorts/mes</li>
                )}
                {plan.audio_hours_per_month != null && (
                  <li>{plan.audio_hours_per_month}h de audio/mes</li>
                )}
                {plan.max_video_minutes != null && (
                  <li>hasta {plan.max_video_minutes} min por video</li>
                )}
              </ul>
              <button
                onClick={() => handleSubscribe(plan.id)}
                disabled={isCurrent || checkingOut === plan.id}
                className="mt-6 rounded-lg bg-[var(--vf-accent)] py-2 text-sm font-medium text-white hover:bg-[var(--vf-accent-hover)] disabled:cursor-not-allowed disabled:bg-[var(--vf-surface-2)] disabled:text-[var(--vf-muted)]"
              >
                {isCurrent
                  ? "Plan actual"
                  : checkingOut === plan.id
                    ? "Redirigiendo…"
                    : "Suscribirse"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
