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
      className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-[13px] leading-none text-[rgba(var(--vf-fg-rgb),0.3)] transition-colors hover:text-[rgba(var(--vf-fg-rgb),0.6)]"
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

function strengthOf(pwd: string): number {
  let s = 0;
  if (pwd.length >= 8) s++;
  if (/[A-Z]/.test(pwd)) s++;
  if (/[0-9]/.test(pwd)) s++;
  if (/[^A-Za-z0-9]/.test(pwd)) s++;
  return s;
}

const STRENGTH_PCT = ["0%", "25%", "50%", "75%", "100%"];
const STRENGTH_LABEL = ["", "Débil", "Aceptable", "Buena", "Fuerte"];
const STRENGTH_COLOR = ["#ff5544", "#ff7733", "#fbbf24", "#22d3a0"];

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const strength = strengthOf(password);
  const matches = confirmPassword.length > 0 ? password === confirmPassword : null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (password.length < 8) {
      setError("La contraseña debe tener al menos 8 caracteres.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Las contraseñas no coinciden.");
      return;
    }

    setSubmitting(true);
    try {
      await register(username, email, password, "basico");
      navigate("/app/planes");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-[var(--vf-bg)] text-[var(--vf-text)]">
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
          className="w-full max-w-[440px] rounded-[28px] border border-[rgba(var(--vf-fg-rgb),0.065)] p-9 pb-8"
          style={{
            background: "var(--vf-s)",
            backdropFilter: "blur(32px)",
            boxShadow:
              "0 0 0 1px rgba(124,106,255,.06), 0 40px 100px rgba(0,0,0,.75), 0 0 160px rgba(124,106,255,.04), inset 0 1px 0 rgba(var(--vf-fg-rgb),.04)",
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
                <rect x="2" y="4" width="4" height="16" rx="1" fill="rgba(var(--vf-fg-rgb),.22)" />
                <rect x="2.5" y="6" width="3" height="2" rx=".5" fill="rgba(var(--vf-fg-rgb),.6)" />
                <rect x="2.5" y="11" width="3" height="2" rx=".5" fill="rgba(var(--vf-fg-rgb),.6)" />
                <rect x="2.5" y="16" width="3" height="2" rx=".5" fill="rgba(var(--vf-fg-rgb),.6)" />
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
          <div className="mb-6 flex gap-0.5 rounded-xl border border-[rgba(var(--vf-fg-rgb),0.05)] bg-[rgba(var(--vf-fg-rgb),0.04)] p-[3px]">
            <Link
              to="/login"
              className="flex flex-1 items-center justify-center rounded-[9px] border border-transparent px-3 py-2.5 text-center text-[11px] font-medium tracking-[0.04em] text-[rgba(var(--vf-fg-rgb),0.4)] transition-colors hover:bg-[rgba(var(--vf-fg-rgb),0.04)] hover:text-[rgba(var(--vf-fg-rgb),0.6)]"
              style={{ fontFamily: "var(--vf-mono)" }}
            >
              Iniciar sesión
            </Link>
            <button
              type="button"
              className="flex-1 rounded-[9px] border border-[rgba(124,106,255,0.2)] bg-[rgba(124,106,255,0.18)] px-3 py-2.5 text-[11px] font-medium tracking-[0.04em] text-white"
              style={{ fontFamily: "var(--vf-mono)" }}
            >
              Crear cuenta
            </button>
          </div>

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
                className="mb-1.5 flex items-center gap-1.5 text-[9.5px] uppercase tracking-[0.1em] text-[rgba(var(--vf-fg-rgb),0.4)]"
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
                Nombre de usuario
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="mi_usuario"
                autoComplete="username"
                autoCapitalize="off"
                spellCheck="false"
                minLength={3}
                maxLength={20}
                pattern="[a-zA-Z0-9_]+"
                title="3-20 caracteres: letras, números y guion bajo"
                autoFocus
                required
                className="w-full rounded-xl border border-[rgba(var(--vf-fg-rgb),0.07)] bg-[rgba(var(--vf-fg-rgb),0.035)] px-[15px] py-3 text-sm font-medium tracking-[-0.2px] text-[var(--vf-text)] outline-none transition-colors focus:border-[rgba(124,106,255,0.45)] focus:bg-[rgba(124,106,255,0.04)]"
              />
            </div>

            <div className="mb-3.5">
              <label
                className="mb-1.5 flex items-center gap-1.5 text-[9.5px] uppercase tracking-[0.1em] text-[rgba(var(--vf-fg-rgb),0.4)]"
                style={{ fontFamily: "var(--vf-mono)" }}
              >
                <FieldIcon
                  d={
                    <>
                      <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                      <polyline points="22,6 12,13 2,6" />
                    </>
                  }
                />
                Correo electrónico
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="correo@ejemplo.com"
                autoComplete="email"
                required
                className="w-full rounded-xl border border-[rgba(var(--vf-fg-rgb),0.07)] bg-[rgba(var(--vf-fg-rgb),0.035)] px-[15px] py-3 text-sm font-medium tracking-[-0.2px] text-[var(--vf-text)] outline-none transition-colors focus:border-[rgba(124,106,255,0.45)] focus:bg-[rgba(124,106,255,0.04)]"
              />
            </div>

            <div className="mb-3.5">
              <label
                className="mb-1.5 flex items-center gap-1.5 text-[9.5px] uppercase tracking-[0.1em] text-[rgba(var(--vf-fg-rgb),0.4)]"
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
                  placeholder="Mínimo 8 caracteres"
                  autoComplete="new-password"
                  minLength={8}
                  required
                  className="w-full rounded-xl border border-[rgba(var(--vf-fg-rgb),0.07)] bg-[rgba(var(--vf-fg-rgb),0.035)] px-[15px] py-3 pr-[42px] text-sm font-medium tracking-[-0.2px] text-[var(--vf-text)] outline-none transition-colors focus:border-[rgba(124,106,255,0.45)] focus:bg-[rgba(124,106,255,0.04)]"
                />
                <EyeToggle shown={showPassword} onClick={() => setShowPassword((v) => !v)} />
              </div>
              <div className="mt-[7px] flex flex-col gap-[5px]">
                <div className="h-[3px] overflow-hidden rounded-[2px] bg-[rgba(var(--vf-fg-rgb),0.06)]">
                  <div
                    className="h-full rounded-[2px] transition-all duration-300"
                    style={{
                      width: STRENGTH_PCT[strength],
                      background: strength > 0 ? STRENGTH_COLOR[strength - 1] : "transparent",
                    }}
                  />
                </div>
                {password && (
                  <span
                    className="text-[9px]"
                    style={{
                      fontFamily: "var(--vf-mono)",
                      color: strength > 0 ? STRENGTH_COLOR[strength - 1] : "rgba(var(--vf-fg-rgb),.28)",
                    }}
                  >
                    {STRENGTH_LABEL[strength]}
                  </span>
                )}
              </div>
            </div>

            <div className="mb-3.5">
              <label
                className="mb-1.5 flex items-center gap-1.5 text-[9.5px] uppercase tracking-[0.1em] text-[rgba(var(--vf-fg-rgb),0.4)]"
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
                Confirmar contraseña
              </label>
              <div className="relative">
                <input
                  type={showConfirmPassword ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repite la contraseña"
                  autoComplete="new-password"
                  required
                  className="w-full rounded-xl border border-[rgba(var(--vf-fg-rgb),0.07)] bg-[rgba(var(--vf-fg-rgb),0.035)] px-[15px] py-3 pr-[42px] text-sm font-medium tracking-[-0.2px] text-[var(--vf-text)] outline-none transition-colors focus:border-[rgba(124,106,255,0.45)] focus:bg-[rgba(124,106,255,0.04)]"
                />
                <EyeToggle shown={showConfirmPassword} onClick={() => setShowConfirmPassword((v) => !v)} />
              </div>
              {matches !== null && (
                <div
                  className="mt-[5px] ml-px text-[9.5px] transition-colors"
                  style={{
                    fontFamily: "var(--vf-mono)",
                    color: matches ? "var(--vf-success)" : "var(--vf-danger)",
                  }}
                >
                  {matches ? "✓ Las contraseñas coinciden" : "✗ No coinciden"}
                </div>
              )}
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
              {submitting ? "Creando cuenta…" : "Crear cuenta →"}
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-[var(--vf-muted)]">
            Empiezas en el plan Básico — puedes cambiarlo luego en Planes.
          </p>
          <p className="mt-2 text-center text-sm text-[var(--vf-muted)]">
            ¿Ya tienes cuenta?{" "}
            <Link to="/login" className="text-[var(--vf-accent)] hover:underline">
              Inicia sesión
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
