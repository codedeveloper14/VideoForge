import { useEffect, useState } from "react";
import { getPayments, getProfile } from "../api/user";
import type { Payment, UserProfile } from "../types";

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

  return (
    <div className="max-w-2xl">
      <h1 className="mb-6 text-2xl font-semibold">Perfil</h1>

      <div className="mb-6 rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-6">
        <p className="text-lg font-semibold">{profile.username}</p>
        <p className="text-sm text-[var(--vf-muted)]">{profile.email}</p>
        <p className="mt-2 text-sm">
          Plan: <span className="font-medium">{profile.plan_name}</span>
        </p>
        {profile.subscription_date && (
          <p className="text-sm text-[var(--vf-muted)]">
            Suscrito desde {profile.subscription_date}
          </p>
        )}
      </div>

      <div className="mb-6 rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-6">
        <h2 className="mb-3 text-sm font-semibold text-[var(--vf-muted)]">Uso este mes</h2>
        <dl className="grid grid-cols-3 gap-4 text-center">
          <div>
            <dt className="text-xs text-[var(--vf-muted)]">Videos</dt>
            <dd className="text-lg font-semibold">
              {profile.usage.videos}
              {profile.limits.videos_per_month != null && (
                <span className="text-sm text-[var(--vf-muted)]"> / {profile.limits.videos_per_month}</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--vf-muted)]">Shorts</dt>
            <dd className="text-lg font-semibold">
              {profile.usage.shorts}
              {profile.limits.shorts_per_month != null && (
                <span className="text-sm text-[var(--vf-muted)]"> / {profile.limits.shorts_per_month}</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--vf-muted)]">Caracteres TTS</dt>
            <dd className="text-lg font-semibold">{profile.usage.tts_chars}</dd>
          </div>
        </dl>
      </div>

      <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-6">
        <h2 className="mb-3 text-sm font-semibold text-[var(--vf-muted)]">Historial de pagos</h2>
        {payments.length === 0 ? (
          <p className="text-sm text-[var(--vf-muted)]">Sin pagos registrados.</p>
        ) : (
          <ul className="space-y-2">
            {payments.map((p, i) => (
              <li key={i} className="flex justify-between text-sm">
                <span>{p.plan}</span>
                <span className="text-[var(--vf-muted)]">
                  ${p.amount_usd} · {p.paid_at}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
