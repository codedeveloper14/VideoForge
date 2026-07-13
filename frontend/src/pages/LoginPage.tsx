import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function EyeToggle({ shown, onClick }: { shown: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="absolute right-[11px] top-1/2 -translate-y-1/2 p-1 text-[13px] leading-none text-[rgba(var(--vf-fg-rgb),0.25)] transition-colors hover:text-[rgba(var(--vf-fg-rgb),0.6)]"
    >
      {shown ? "🙈" : "👁"}
    </button>
  );
}

const FEATURES = [
  {
    icon: "#fbbf24",
    bg: "rgba(251,191,36,.12)",
    path: <polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />,
    title: "Pipeline inteligente",
    desc: "Automatiza cada etapa de tu producción.",
  },
  {
    icon: "#a78bfa",
    bg: "rgba(124,106,255,.12)",
    path: (
      <>
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
      </>
    ),
    title: "Colaboración en equipo",
    desc: "Trabaja junto a tu equipo en tiempo real.",
  },
  {
    icon: "#22d3a0",
    bg: "rgba(34,211,160,.1)",
    path: (
      <>
        <rect x="3" y="11" width="18" height="11" rx="2" />
        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
      </>
    ),
    title: "Seguro y confiable",
    desc: "Tus proyectos están siempre protegidos.",
  },
];

export default function LoginPage() {
  const { login, changePassword } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [mustChange, setMustChange] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!username.trim() || !password) {
      setError("Completa usuario y contraseña.");
      return;
    }
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

  async function handleChangePassword(e: FormEvent) {
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
  const canSubmitChange = reqLen && reqNum && reqUp;

  return (
    <div
      className="relative flex min-h-screen items-center justify-center overflow-hidden p-5"
      style={{ background: "var(--vf-bg)", color: "var(--vf-text)", fontFamily: "'Syne',sans-serif" }}
    >
      <div
        className="pointer-events-none fixed inset-0 z-0"
        style={{
          background:
            "radial-gradient(ellipse 55% 55% at 15% 15%, rgba(99,80,255,.18) 0%, transparent 55%)," +
            "radial-gradient(ellipse 45% 45% at 85% 80%, rgba(124,106,255,.12) 0%, transparent 50%)," +
            "radial-gradient(ellipse 35% 35% at 75% 8%, rgba(167,139,250,.08) 0%, transparent 45%)," +
            "radial-gradient(ellipse 30% 30% at 5% 90%, rgba(80,60,200,.07) 0%, transparent 45%)",
        }}
      />

      <div
        className="relative z-10 flex w-full overflow-hidden rounded-[18px] border border-[rgba(var(--vf-fg-rgb),0.09)]"
        style={{
          width: "min(1080px, 96vw)",
          height: "min(660px, 88vh)",
          boxShadow: "0 40px 120px rgba(88,70,230,.5), 0 0 90px rgba(124,106,255,.25)",
        }}
      >
        {/* LEFT PANEL */}
        <div
          className="relative flex flex-1 flex-col overflow-hidden p-10 max-md:hidden"
          style={{ background: "var(--vf-s)" }}
        >
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(ellipse 90% 70% at -10% -10%, rgba(124,106,255,.13) 0%, transparent 55%)," +
                "radial-gradient(ellipse 60% 40% at 110% 110%, rgba(99,80,255,.07) 0%, transparent 50%)",
            }}
          />

          <div className="relative z-10 flex items-center gap-3">
            <div
              className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[10px]"
              style={{
                background: "linear-gradient(135deg,#6f5eff 0%,#9b68ff 100%)",
                boxShadow: "0 0 22px rgba(124,106,255,.38)",
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 8.5L18.5 12 9 15.5V8.5Z" fill="#fff" />
              </svg>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[15px] font-extrabold tracking-[-0.3px]">Studio IVR</span>
              <span
                className="text-[7.5px] uppercase tracking-[0.2em]"
                style={{ fontFamily: "var(--vf-mono)", color: "rgba(167,139,250,.5)" }}
              >
                AI Pipeline
              </span>
            </div>
          </div>

          <div className="relative z-10 flex flex-1 flex-col justify-center">
            <h1
              className="mb-4 font-extrabold leading-[1.06] tracking-[-1.8px] text-[var(--vf-text)]"
              style={{ fontSize: "clamp(32px,3.5vw,50px)" }}
            >
              Crea. Automatiza.
              <br />
              <span style={{ color: "var(--vf-c1)" }}>Produce.</span>
            </h1>
            <p className="max-w-[360px] text-[13px] leading-[1.7] text-[rgba(var(--vf-fg-rgb),0.38)]" style={{ fontFamily: "var(--vf-mono)" }}>
              La plataforma completa para producción audiovisual con IA. Guión, voz, video y renderizado en un solo
              flujo.
            </p>
          </div>

          <div className="relative z-10 flex flex-col gap-4">
            {FEATURES.map((f) => (
              <div key={f.title} className="flex items-start gap-3.5">
                <div
                  className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-[9px]"
                  style={{ background: f.bg }}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={f.icon} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    {f.path}
                  </svg>
                </div>
                <div>
                  <div className="mb-0.5 text-[13px] font-bold text-[rgba(var(--vf-fg-rgb),0.8)]">{f.title}</div>
                  <div className="text-[11.5px] leading-[1.4] text-[rgba(var(--vf-fg-rgb),0.3)]" style={{ fontFamily: "var(--vf-mono)" }}>
                    {f.desc}
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="relative z-10 mt-6 text-[8.5px] text-[rgba(var(--vf-fg-rgb),0.18)]" style={{ fontFamily: "var(--vf-mono)" }}>
            © 2026 Studio IVR. Todos los derechos reservados.
          </div>
        </div>

        {/* RIGHT PANEL */}
        <div
          className="flex w-full flex-shrink-0 items-center justify-center p-11 md:w-[400px]"
          style={{ background: "var(--vf-s)", borderLeft: "1px solid rgba(var(--vf-fg-rgb),.06)" }}
        >
          <div className="w-full max-w-[320px]">
            {!mustChange ? (
              <form onSubmit={handleSubmit}>
                <div className="mb-1.5 whitespace-nowrap text-xl font-extrabold tracking-[-0.4px]">
                  Bienvenido de nuevo
                </div>
                <div className="mb-6 text-[12.5px] leading-[1.55] text-[rgba(var(--vf-fg-rgb),0.38)]">
                  Inicia sesión para continuar con tus proyectos.
                </div>

                {error && (
                  <div
                    className="mb-3 rounded-[9px] px-3 py-2.5 text-[10.5px] leading-[1.5]"
                    style={{ fontFamily: "var(--vf-mono)", background: "rgba(255,60,80,.06)", border: "1px solid rgba(255,60,80,.15)", color: "#ff6677" }}
                  >
                    ⚠ {error}
                  </div>
                )}

                <div className="mb-3">
                  <div className="mb-1.5 flex items-center justify-between">
                    <span className="text-xs font-semibold text-[rgba(var(--vf-fg-rgb),0.62)]">Correo electrónico o usuario</span>
                  </div>
                  <div className="relative">
                    <svg className="pointer-events-none absolute left-[13px] top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[rgba(var(--vf-fg-rgb),0.22)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                      <circle cx="12" cy="7" r="4" />
                    </svg>
                    <input
                      type="text"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder="tu_usuario"
                      autoComplete="username"
                      autoCapitalize="off"
                      spellCheck="false"
                      autoFocus
                      className="w-full rounded-[10px] py-3 pl-[38px] pr-[40px] text-[13.5px] font-medium text-[var(--vf-text)] outline-none transition-colors"
                      style={{ background: "rgba(var(--vf-fg-rgb),.035)", border: "1px solid rgba(var(--vf-fg-rgb),.08)" }}
                    />
                  </div>
                </div>

                <div className="mb-3">
                  <div className="mb-1.5 flex items-center justify-between">
                    <span className="text-xs font-semibold text-[rgba(var(--vf-fg-rgb),0.62)]">Contraseña</span>
                    <span className="pointer-events-none text-[11px] opacity-38" style={{ fontFamily: "var(--vf-mono)", color: "var(--vf-c1)" }}>
                      ¿Olvidaste tu contraseña?
                    </span>
                  </div>
                  <div className="relative">
                    <svg className="pointer-events-none absolute left-[13px] top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[rgba(var(--vf-fg-rgb),0.22)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="11" width="18" height="11" rx="2" />
                      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </svg>
                    <input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••"
                      autoComplete="current-password"
                      className="w-full rounded-[10px] py-3 pl-[38px] pr-[40px] text-[13.5px] font-medium text-[var(--vf-text)] outline-none transition-colors"
                      style={{ background: "rgba(var(--vf-fg-rgb),.035)", border: "1px solid rgba(var(--vf-fg-rgb),.08)" }}
                    />
                    <EyeToggle shown={showPassword} onClick={() => setShowPassword((v) => !v)} />
                  </div>
                </div>

                <div className="mb-[18px] mt-3 flex items-center justify-between">
                  <label className="flex cursor-pointer select-none items-center gap-2 text-xs text-[rgba(var(--vf-fg-rgb),0.45)]">
                    <input
                      type="checkbox"
                      checked={remember}
                      onChange={(e) => setRemember(e.target.checked)}
                      className="hidden"
                    />
                    <span
                      className="flex h-[15px] w-[15px] flex-shrink-0 items-center justify-center rounded-[4px] transition-colors"
                      style={{
                        border: `1.5px solid ${remember ? "var(--vf-c1)" : "rgba(var(--vf-fg-rgb),.18)"}`,
                        background: remember ? "var(--vf-c1)" : "rgba(var(--vf-fg-rgb),.03)",
                      }}
                    >
                      {remember && (
                        <svg width="8" height="6" viewBox="0 0 8 6" fill="none">
                          <path d="M1 3L3 5L7 1" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </span>
                    Recordarme
                  </label>
                </div>

                <button
                  type="submit"
                  disabled={submitting}
                  className="mb-[18px] w-full rounded-[10px] py-[13.5px] text-[14.5px] font-bold tracking-[-0.1px] text-white transition-transform hover:-translate-y-[1.5px] disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:translate-y-0"
                  style={{
                    background: "linear-gradient(135deg,#6f5eff 0%,#9b68ff 100%)",
                    boxShadow: "0 4px 18px rgba(112,90,255,.3)",
                  }}
                >
                  {submitting ? "Ingresando…" : "Iniciar sesión →"}
                </button>

                <div
                  className="mb-3.5 flex items-center gap-2.5 text-[11px]"
                  style={{ fontFamily: "var(--vf-mono)", color: "rgba(var(--vf-fg-rgb),.18)" }}
                >
                  <span className="h-px flex-1" style={{ background: "rgba(var(--vf-fg-rgb),.07)" }} />
                  O continúa con
                  <span className="h-px flex-1" style={{ background: "rgba(var(--vf-fg-rgb),.07)" }} />
                </div>

                <div className="mb-4 grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => alert("Próximamente.")}
                    className="flex items-center justify-center gap-1.5 whitespace-nowrap rounded-[9px] py-2.5 text-xs font-semibold text-[rgba(var(--vf-fg-rgb),0.65)] transition-colors hover:bg-[rgba(var(--vf-fg-rgb),0.055)] hover:text-white"
                    style={{ border: "1px solid rgba(var(--vf-fg-rgb),.09)", background: "rgba(var(--vf-fg-rgb),.03)" }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24">
                      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                    </svg>
                    Continuar con Google
                  </button>
                  <button
                    type="button"
                    onClick={() => alert("Próximamente.")}
                    className="flex items-center justify-center gap-1.5 whitespace-nowrap rounded-[9px] py-2.5 text-xs font-semibold text-[rgba(var(--vf-fg-rgb),0.65)] transition-colors hover:bg-[rgba(var(--vf-fg-rgb),0.055)] hover:text-white"
                    style={{ border: "1px solid rgba(var(--vf-fg-rgb),.09)", background: "rgba(var(--vf-fg-rgb),.03)" }}
                  >
                    <svg width="12" height="14" viewBox="0 0 814 1000" fill="currentColor">
                      <path d="M788.1 340.9c-5.8 4.5-108.2 62.2-108.2 190.5 0 148.4 130.3 200.9 134.2 202.2-.6 3.2-20.7 71.9-68.7 141.9-42.8 61.6-87.5 123.1-155.5 123.1s-85.5-39.5-164-39.5c-76.5 0-103.7 40.8-165.9 40.8s-105-36.8-162.8-106.3C180.9 742.2 139 649 139 603c0-188.1 130.9-314.3 260.2-314.3 73.9 0 135.4 48.4 179.9 48.4 42.6 0 113.5-50.7 196.7-50.7z" />
                      <path d="M555.5 0c-58.1 0-115.8 38.4-153.1 97.8-33.1 53.2-60.3 131.2-60.3 209.5 0 4.7.5 9.4.5 14.1 3.7.2 7.5.3 11.2.3 55.1 0 113.9-37.1 149.7-95.7 37.7-62.4 62.3-140.6 62.3-218.8 0-2.6-.1-5.2-.2-7.8z" />
                    </svg>
                    Continuar con Apple
                  </button>
                </div>

                <div className="text-center text-xs" style={{ fontFamily: "var(--vf-mono)", color: "rgba(var(--vf-fg-rgb),.28)" }}>
                  ¿No tienes cuenta?
                  <Link to="/register" className="ml-1 font-bold" style={{ color: "var(--vf-c2)" }}>
                    Registrarse
                  </Link>
                </div>
              </form>
            ) : (
              <form onSubmit={handleChangePassword} className="text-center">
                <div
                  className="mx-auto mb-4 flex h-[50px] w-[50px] items-center justify-center rounded-[13px] text-xl"
                  style={{ background: "rgba(251,191,36,.07)", border: "1px solid rgba(251,191,36,.16)" }}
                >
                  🔐
                </div>
                <div className="mb-1 text-lg font-extrabold tracking-[-0.35px]">Cambia tu contraseña</div>
                <p className="mb-4.5 text-[10px] leading-[1.6] text-[rgba(var(--vf-fg-rgb),0.28)]" style={{ fontFamily: "var(--vf-mono)" }}>
                  Es tu primer acceso. Por seguridad
                  <br />
                  debes establecer una nueva contraseña.
                </p>

                {error && (
                  <div
                    className="mb-3 rounded-[9px] px-3 py-2.5 text-left text-[10.5px] leading-[1.5]"
                    style={{ fontFamily: "var(--vf-mono)", background: "rgba(255,60,80,.06)", border: "1px solid rgba(255,60,80,.15)", color: "#ff6677" }}
                  >
                    ⚠ {error}
                  </div>
                )}

                <div
                  className="mb-3 flex flex-col gap-1.5 rounded-[9px] p-2.5 text-left"
                  style={{ background: "rgba(var(--vf-fg-rgb),.02)", border: "1px solid rgba(var(--vf-fg-rgb),.05)" }}
                >
                  {[
                    { ok: reqLen, label: "Mínimo 8 caracteres" },
                    { ok: reqNum, label: "Al menos un número" },
                    { ok: reqUp, label: "Al menos una mayúscula" },
                  ].map((r) => (
                    <div
                      key={r.label}
                      className="flex items-center gap-1.5 text-[9.5px] transition-colors"
                      style={{ fontFamily: "var(--vf-mono)", color: r.ok ? "var(--vf-c5)" : "rgba(var(--vf-fg-rgb),.26)" }}
                    >
                      <span className="w-3 text-center text-[10px]">{r.ok ? "✓" : "○"}</span>
                      {r.label}
                    </div>
                  ))}
                </div>

                <div className="mb-3 text-left">
                  <div className="mb-1.5 text-xs font-semibold text-[rgba(var(--vf-fg-rgb),0.62)]">Nueva contraseña</div>
                  <div className="relative">
                    <input
                      type={showNewPassword ? "text" : "password"}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="Nueva contraseña"
                      autoComplete="new-password"
                      autoFocus
                      className="w-full rounded-[10px] py-3 pl-[14px] pr-[40px] text-[13.5px] font-medium text-[var(--vf-text)] outline-none"
                      style={{ background: "rgba(var(--vf-fg-rgb),.035)", border: "1px solid rgba(var(--vf-fg-rgb),.08)" }}
                    />
                    <EyeToggle shown={showNewPassword} onClick={() => setShowNewPassword((v) => !v)} />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={submitting || !canSubmitChange}
                  className="mt-1 w-full rounded-[9px] py-3 text-[11.5px] font-bold uppercase tracking-[0.05em] text-black transition-transform hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:translate-y-0"
                  style={{ fontFamily: "var(--vf-mono)", background: "#fbbf24" }}
                >
                  {submitting ? "Guardando…" : "Guardar contraseña →"}
                </button>
              </form>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
