import { useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

interface EyeToggleProps {
  shown: boolean;
  onClick: () => void;
}

function EyeToggle({ shown, onClick }: EyeToggleProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-[13px] leading-none text-white/30 transition-colors hover:text-white/60"
    >
      {shown ? "🙈" : "👁"}
    </button>
  );
}

interface FieldIconProps {
  d: ReactNode;
}

function FieldIcon({ d }: FieldIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className="h-[11px] w-[11px] opacity-50"
    >
      {d}
    </svg>
  );
}

export default function LoginPage() {
  const { login, changePassword } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [mustChange, setMustChange] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const data = await login(username, password);
      if (data.must_change_password) {
        setMustChange(true);
        return;
      }
      navigate("/app/home");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await changePassword(username, newPassword);
      navigate("/app/home");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  const reqLen = newPassword.length >= 8;
  const reqNum = /[0-9]/.test(newPassword);
  const reqUp = /[A-Z]/.test(newPassword);

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#06060d] text-[var(--vf-text)]">
      {/* Decorative gradient orbs */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div
          className="absolute -left-[25%] -top-[40%] h-[1000px] w-[1000px] rounded-full opacity-90"
          style={{ background: "radial-gradient(circle, rgba(124,106,255,.15), transparent 60%)", filter: "blur(120px)" }}
        />
        <div
          className="absolute -right-[25%] -top-[15%] h-[800px] w-[800px] rounded-full"
          style={{ background: "radial-gradient(circle, rgba(244,114,182,.08), transparent 60%)", filter: "blur(120px)" }}
        />
        <div
          className="absolute bottom-[-35%] left-[20%] h-[700px] w-[700px] rounded-full"
          style={{ background: "radial-gradient(circle, rgba(34,211,160,.07), transparent 60%)", filter: "blur(120px)" }}
        />
      </div>

      <div className="relative z-10 flex min-h-screen items-center justify-center px-5 py-6">
        <div
          className="w-full max-w-[440px] rounded-[28px] border border-white/[0.065] p-9 pb-8"
          style={{
            background: "rgba(11,11,24,.9)",
            backdropFilter: "blur(32px)",
            boxShadow:
              "0 0 0 1px rgba(124,106,255,.06), 0 40px 100px rgba(0,0,0,.75), 0 0 160px rgba(124,106,255,.04), inset 0 1px 0 rgba(255,255,255,.04)",
          }}
        >
          {/* Logo */}
          <div className="mb-7 flex items-center justify-center gap-3.5">
            <div
              className="relative flex h-[46px] w-[46px] flex-shrink-0 items-center justify-center overflow-hidden rounded-2xl"
              style={{
                background: "linear-gradient(145deg,#4f35d6 0%,#7c6aff 45%,#a855f7 100%)",
                boxShadow: "0 0 0 1px rgba(168,85,247,.2), 0 8px 28px rgba(124,106,255,.55), 0 0 60px rgba(124,106,255,.12)",
              }}
            >
              <svg viewBox="0 0 24 24" width="19" height="19" className="relative z-10">
                <rect x="2" y="4" width="4" height="16" rx="1" fill="rgba(255,255,255,.22)" />
                <rect x="2.5" y="6" width="3" height="2" rx=".5" fill="rgba(255,255,255,.6)" />
                <rect x="2.5" y="11" width="3" height="2" rx=".5" fill="rgba(255,255,255,.6)" />
                <rect x="2.5" y="16" width="3" height="2" rx=".5" fill="rgba(255,255,255,.6)" />
                <path d="M9 8.5L18.5 12 9 15.5V8.5Z" fill="white" />
              </svg>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[21px] font-extrabold leading-none tracking-[-0.6px]">Studio IVR</span>
              <span
                className="text-[9px] uppercase tracking-[0.15em]"
                style={{ fontFamily: "var(--vf-mono)", color: "rgba(167,139,250,.65)" }}
              >
                AI Pipeline
              </span>
            </div>
          </div>

          {/* Tabs */}
          <div className="mb-6 flex gap-0.5 rounded-xl border border-white/5 bg-white/[0.04] p-[3px]">
            <button
              type="button"
              className="flex-1 rounded-[9px] border border-[rgba(124,106,255,0.2)] bg-[rgba(124,106,255,0.18)] px-3 py-2.5 text-[11px] font-medium tracking-[0.04em] text-white"
              style={{ fontFamily: "var(--vf-mono)" }}
            >
              Iniciar sesión
            </button>
            <Link
              to="/register"
              className="flex flex-1 items-center justify-center rounded-[9px] border border-transparent px-3 py-2.5 text-center text-[11px] font-medium tracking-[0.04em] text-white/40 transition-colors hover:bg-white/[0.04] hover:text-white/60"
              style={{ fontFamily: "var(--vf-mono)" }}
            >
              Crear cuenta
            </Link>
          </div>

          {!mustChange ? (
            <form onSubmit={handleSubmit}>
              {error && (
                <div
                  className="mb-3.5 rounded-[11px] border border-[rgba(255,60,80,0.18)] px-3.5 py-2.5 text-[11px] leading-[1.55]"
                  style={{ fontFamily: "var(--vf-mono)", background: "rgba(255,60,80,.07)", color: "#ff6677" }}
                >
                  ⚠ {error}
                </div>
              )}

              <div className="mb-3.5">
                <label
                  className="mb-1.5 flex items-center gap-1.5 text-[9.5px] uppercase tracking-[0.1em] text-white/40"
                  style={{ fontFamily: "var(--vf-mono)" }}
                >
                  <FieldIcon
                    d={
                      <>
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                        <circle cx="12" cy="7" r="4" />
                      </>
                    }
                  />
                  Usuario
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="tu_usuario"
                  autoComplete="username"
                  autoCapitalize="off"
                  spellCheck="false"
                  autoFocus
                  required
                  className="w-full rounded-xl border border-white/[0.07] bg-white/[0.035] px-[15px] py-3 text-sm font-medium tracking-[-0.2px] text-[var(--vf-text)] outline-none transition-colors focus:border-[rgba(124,106,255,0.45)] focus:bg-[rgba(124,106,255,0.04)]"
                />
              </div>

              <div className="mb-3.5">
                <label
                  className="mb-1.5 flex items-center gap-1.5 text-[9.5px] uppercase tracking-[0.1em] text-white/40"
                  style={{ fontFamily: "var(--vf-mono)" }}
                >
                  <FieldIcon
                    d={
                      <>
                        <rect x="3" y="11" width="18" height="11" rx="2" />
                        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                      </>
                    }
                  />
                  Contraseña
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    autoComplete="current-password"
                    required
                    className="w-full rounded-xl border border-white/[0.07] bg-white/[0.035] px-[15px] py-3 pr-[42px] text-sm font-medium tracking-[-0.2px] text-[var(--vf-text)] outline-none transition-colors focus:border-[rgba(124,106,255,0.45)] focus:bg-[rgba(124,106,255,0.04)]"
                  />
                  <EyeToggle shown={showPassword} onClick={() => setShowPassword((v) => !v)} />
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="mt-1 w-full rounded-[13px] py-3.5 text-xs font-semibold uppercase tracking-[0.07em] text-white transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0"
                style={{
                  fontFamily: "var(--vf-mono)",
                  background: "linear-gradient(135deg,#5d45f0 0%,#7c6aff 50%,#9f7aea 100%)",
                  boxShadow: "0 4px 24px rgba(124,106,255,.38), 0 0 60px rgba(124,106,255,.08)",
                }}
              >
                {submitting ? "Ingresando…" : "Ingresar →"}
              </button>

              <div
                className="mt-4.5 flex items-center justify-center gap-2 border-t border-white/[0.04] pt-3.5 text-[9px] text-white/20"
                style={{ fontFamily: "var(--vf-mono)" }}
              >
                <span
                  className="h-[5px] w-[5px] flex-shrink-0 rounded-full"
                  style={{ background: "var(--vf-c5)", boxShadow: "0 0 6px var(--vf-c5)" }}
                />
                Servidor activo · Conexión segura
              </div>
            </form>
          ) : (
            <form onSubmit={handleChangePassword}>
              <div className="mb-5 text-center">
                <div
                  className="mx-auto mb-4 flex h-[54px] w-[54px] items-center justify-center rounded-2xl border border-[rgba(251,191,36,0.2)] text-[22px]"
                  style={{ background: "linear-gradient(135deg, rgba(251,191,36,.14), rgba(251,191,36,.04))" }}
                >
                  🔐
                </div>
                <h2 className="mb-1.5 text-xl font-extrabold tracking-[-0.4px]">Cambia tu contraseña</h2>
                <p
                  className="text-[10.5px] leading-[1.65] text-white/30"
                  style={{ fontFamily: "var(--vf-mono)" }}
                >
                  Es tu primer acceso. Por seguridad debes establecer una nueva contraseña.
                </p>
              </div>

              {error && (
                <div
                  className="mb-3.5 rounded-[11px] border border-[rgba(255,60,80,0.18)] px-3.5 py-2.5 text-[11px] leading-[1.55]"
                  style={{ fontFamily: "var(--vf-mono)", background: "rgba(255,60,80,.07)", color: "#ff6677" }}
                >
                  ⚠ {error}
                </div>
              )}

              <div className="mb-3.5 flex flex-col gap-1.5 rounded-[11px] border border-white/5 bg-white/[0.02] p-3.5">
                <div
                  className={`flex items-center gap-1.5 text-[10px] transition-colors ${
                    reqLen ? "text-[var(--vf-success)]" : "text-white/28"
                  }`}
                  style={{ fontFamily: "var(--vf-mono)" }}
                >
                  <span className="w-3.5 text-center text-[11px]">{reqLen ? "✓" : "○"}</span>
                  Mínimo 8 caracteres
                </div>
                <div
                  className={`flex items-center gap-1.5 text-[10px] transition-colors ${
                    reqNum ? "text-[var(--vf-success)]" : "text-white/28"
                  }`}
                  style={{ fontFamily: "var(--vf-mono)" }}
                >
                  <span className="w-3.5 text-center text-[11px]">{reqNum ? "✓" : "○"}</span>
                  Al menos un número
                </div>
                <div
                  className={`flex items-center gap-1.5 text-[10px] transition-colors ${
                    reqUp ? "text-[var(--vf-success)]" : "text-white/28"
                  }`}
                  style={{ fontFamily: "var(--vf-mono)" }}
                >
                  <span className="w-3.5 text-center text-[11px]">{reqUp ? "✓" : "○"}</span>
                  Al menos una mayúscula
                </div>
              </div>

              <div className="mb-3.5">
                <label
                  className="mb-1.5 block text-[9.5px] uppercase tracking-[0.1em] text-white/40"
                  style={{ fontFamily: "var(--vf-mono)" }}
                >
                  Nueva contraseña
                </label>
                <div className="relative">
                  <input
                    type={showNewPassword ? "text" : "password"}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Nueva contraseña"
                    autoComplete="new-password"
                    required
                    minLength={8}
                    autoFocus
                    className="w-full rounded-xl border border-white/[0.07] bg-white/[0.035] px-[15px] py-3 pr-[42px] text-sm font-medium tracking-[-0.2px] text-[var(--vf-text)] outline-none transition-colors focus:border-[rgba(124,106,255,0.45)] focus:bg-[rgba(124,106,255,0.04)]"
                  />
                  <EyeToggle shown={showNewPassword} onClick={() => setShowNewPassword((v) => !v)} />
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="mt-1 w-full rounded-xl py-[13px] text-xs font-bold uppercase tracking-[0.07em] text-black transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0"
                style={{
                  fontFamily: "var(--vf-mono)",
                  background: "linear-gradient(135deg,#b8860b,#fbbf24,#f59e0b)",
                  boxShadow: "0 4px 22px rgba(251,191,36,.28)",
                }}
              >
                {submitting ? "Guardando…" : "Guardar contraseña →"}
              </button>
            </form>
          )}

          {!mustChange && (
            <p className="mt-5 text-center text-sm text-[var(--vf-muted)]">
              ¿No tienes cuenta?{" "}
              <Link to="/register" className="text-[var(--vf-accent)] hover:underline">
                Regístrate
              </Link>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
