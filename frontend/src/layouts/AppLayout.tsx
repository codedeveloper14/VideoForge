import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { getProfile } from "../api/user";
import type { UserProfile } from "../types";

type IconKey = "home" | "proyectos" | "idea2video" | "tareas" | "ajustes" | "docs" | "ayuda";

const ICONS: Record<IconKey, React.ReactNode> = {
  home: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <polyline points="9,22 9,12 15,12 15,22" />
    </svg>
  ),
  proyectos: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="7" width="20" height="14" rx="2" />
      <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
    </svg>
  ),
  idea2video: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a7 7 0 0 1 7 7c0 2.66-1.49 4.98-3.69 6.22L15 18H9l-.31-2.78C6.49 13.98 5 11.66 5 9a7 7 0 0 1 7-7z" />
      <line x1="9" y1="21" x2="15" y2="21" />
      <line x1="9" y1="18" x2="15" y2="18" />
    </svg>
  ),
  tareas: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 11 12 14 22 4" />
      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
    </svg>
  ),
  ajustes: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.07 4.93l-1.41 1.41M4.93 4.93l1.41 1.41M12 2v2M12 20v2M20 12h2M2 12h2M17.66 17.66l-1.41-1.41M6.34 17.66l1.41-1.41" />
    </svg>
  ),
  docs: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  ),
  ayuda: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  ),
};

interface NavItemDef {
  to: string;
  label: string;
  icon: IconKey;
}

const NAV_ITEMS: NavItemDef[] = [
  { to: "/app/home", label: "Inicio", icon: "home" },
  { to: "/app/proyectos", label: "Proyectos", icon: "proyectos" },
  { to: "/app/idea2video", label: "Idea a Video", icon: "idea2video" },
  { to: "/app/tareas", label: "Tareas", icon: "tareas" },
  { to: "/app/perfil", label: "Ajustes", icon: "ajustes" },
];

const FOOT_LINKS: NavItemDef[] = [
  { to: "/app/ayuda", label: "Documentación", icon: "docs" },
  { to: "/app/ayuda", label: "Centro de ayuda", icon: "ayuda" },
];

function NavItem({ to, label, icon }: NavItemDef) {
  return (
    <NavLink
      to={to}
      end={to === "/app/home"}
      className={({ isActive }) =>
        `group relative flex items-center gap-2.5 rounded-[9px] px-2.5 py-2 text-[12px] tracking-[0.01em] transition-colors ${
          isActive
            ? "bg-gradient-to-r from-[rgba(124,106,255,0.14)] to-[rgba(124,106,255,0.06)] font-medium text-[var(--vf-text)]"
            : "text-[var(--vf-m)] hover:bg-white/[0.045] hover:text-[rgba(238,238,245,0.8)]"
        }`
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <span
              className="absolute left-0 top-1/2 h-[55%] w-[2.5px] -translate-y-1/2 rounded-r-[2px]"
              style={{ background: "linear-gradient(180deg, var(--vf-c2), var(--vf-c1))" }}
            />
          )}
          <span
            className={`flex h-[17px] w-[17px] flex-shrink-0 items-center justify-center [&>svg]:h-[15px] [&>svg]:w-[15px] ${
              isActive ? "text-[var(--vf-c2)] opacity-100" : "text-[var(--vf-m)] opacity-70 group-hover:opacity-100"
            }`}
          >
            {ICONS[icon]}
          </span>
          {label}
        </>
      )}
    </NavLink>
  );
}

const PLAN_NAMES: Record<string, string> = {
  free: "Free",
  basico: "Básico",
  pro: "Pro",
  ultra: "Ultra",
  unlimited: "Ilimitado",
};

function AccountMenu({ profile }: { profile: UserProfile | null }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const name = profile?.username || user || "Usuario";
  const email = profile?.email || "";
  const initial = name[0]?.toUpperCase() || "?";
  const planLabel = profile ? PLAN_NAMES[profile.plan] || profile.plan_name : "";

  return (
    <div className="relative" ref={ref}>
      {open && (
        <div
          className="absolute bottom-full left-0 mb-2 w-full min-w-[210px] overflow-hidden rounded-[13px] border border-white/[0.11] bg-[#0f0f1e] shadow-[0_-8px_40px_rgba(0,0,0,.8)]"
        >
          <div className="flex items-center gap-2.5 border-b border-white/[0.06] px-3.5 py-3">
            <div
              className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-[9px] text-[13px] font-bold text-white"
              style={{ background: "linear-gradient(145deg,#6c56ff,#a855f7)" }}
            >
              {initial}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12px] font-bold text-[var(--vf-text)]">{name}</div>
              <div className="truncate text-[10px] text-[var(--vf-m)]">{email}</div>
            </div>
            {planLabel && (
              <span
                className="flex-shrink-0 rounded-[5px] border px-[7px] py-0.5 text-[8px] font-bold uppercase tracking-[0.1em]"
                style={{ borderColor: "rgba(124,106,255,.25)", background: "rgba(124,106,255,.14)", color: "#a78bfa" }}
              >
                {planLabel}
              </span>
            )}
          </div>
          <button
            onClick={() => {
              setOpen(false);
              navigate("/app/perfil");
            }}
            className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[12.5px] font-medium text-[#7a7a9a] transition-colors hover:bg-white/[0.05] hover:text-[#d4d4f0]"
          >
            <span className="[&>svg]:h-3.5 [&>svg]:w-3.5">{ICONS.ajustes}</span>
            Configuración
          </button>
          <button
            onClick={() => {
              setOpen(false);
              navigate("/app/planes");
            }}
            className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[12.5px] font-medium text-[#a78bfa] transition-colors hover:bg-[rgba(124,106,255,.1)] hover:text-[#c4b5fd]"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="17 11 12 6 7 11" />
              <line x1="12" y1="6" x2="12" y2="18" />
            </svg>
            Upgrade
          </button>
          <div className="h-px bg-white/[0.06]" />
          <button
            onClick={() => void logout()}
            className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[12.5px] font-medium text-[rgba(248,113,113,.75)] transition-colors hover:bg-[rgba(239,68,68,.07)] hover:text-[#f87171]"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            Cerrar sesión
          </button>
        </div>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2.5 rounded-[10px] px-2 py-2 text-left transition-colors hover:bg-white/[0.04]"
      >
        <div
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-[9px] text-[13px] font-bold text-white"
          style={{ background: "linear-gradient(145deg,#6c56ff,#a855f7)" }}
        >
          {initial}
        </div>
        <div className="min-w-0 flex-1 overflow-hidden">
          <div className="truncate text-[11.5px] font-semibold text-[var(--vf-text)]">{name}</div>
          <div className="truncate text-[9.5px] text-[var(--vf-m2)]">{email || "Cargando…"}</div>
        </div>
        <svg
          viewBox="0 0 24 24"
          width="13"
          height="13"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`flex-shrink-0 text-[var(--vf-m)] transition-transform ${open ? "rotate-180" : ""}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
    </div>
  );
}

export default function AppLayout() {
  const [profile, setProfile] = useState<UserProfile | null>(null);

  useEffect(() => {
    getProfile()
      .then(setProfile)
      .catch(() => {});
  }, []);

  return (
    <div className="flex min-h-screen bg-[var(--vf-bg)] text-[var(--vf-text)]">
      <aside
        className="fixed left-0 top-0 flex h-screen w-[228px] flex-shrink-0 flex-col overflow-y-auto border-r border-[rgba(124,106,255,0.1)]"
        style={{ background: "linear-gradient(180deg, #0b0b16 0%, #09090f 100%)" }}
      >
        <div
          className="flex flex-shrink-0 items-center gap-[11px] border-b border-white/[0.04] px-4 py-5"
          style={{ background: "rgba(124,106,255,.03)" }}
        >
          <div
            className="relative flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center overflow-hidden rounded-[10px]"
            style={{
              background: "linear-gradient(145deg,#5b45e8 0%,#8b5cf6 50%,#a855f7 100%)",
              boxShadow: "0 0 0 1px rgba(168,85,247,.2), 0 4px 18px rgba(124,106,255,.5)",
            }}
          >
            <svg viewBox="0 0 24 24" width="14" height="14" className="relative z-10">
              <rect x="2" y="4" width="4" height="16" rx="1" fill="rgba(255,255,255,.22)" />
              <rect x="2.5" y="6" width="3" height="2" rx=".5" fill="rgba(255,255,255,.6)" />
              <rect x="2.5" y="11" width="3" height="2" rx=".5" fill="rgba(255,255,255,.6)" />
              <rect x="2.5" y="16" width="3" height="2" rx=".5" fill="rgba(255,255,255,.6)" />
              <path d="M9 8.5L18.5 12 9 15.5V8.5Z" fill="white" />
            </svg>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-[15px] font-extrabold leading-none tracking-[-0.5px]">Studio IVR</span>
            <span
              className="text-[8.5px] uppercase tracking-[0.12em] text-[var(--vf-m)]"
              style={{ fontFamily: "var(--vf-mono)" }}
            >
              AI Pipeline
            </span>
          </div>
        </div>

        <nav className="flex min-h-0 flex-1 flex-col gap-[1px] px-2.5 pb-2 pt-3">
          {NAV_ITEMS.map((item) => (
            <NavItem key={item.label} {...item} />
          ))}
        </nav>

        {/* Upgrade card */}
        <div className="mx-2.5 mb-2 rounded-xl border border-[rgba(124,106,255,.18)] bg-[rgba(124,106,255,.06)] p-3">
          <div className="mb-1 flex items-center gap-1.5">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="#a78bfa" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="13,2 3,14 12,14 11,22 21,10 12,10" />
            </svg>
            <span className="text-[11.5px] font-bold text-[var(--vf-text)]">Upgrade</span>
          </div>
          <p className="mb-2 text-[10px] leading-snug text-[var(--vf-m)]">
            Más créditos, renders y funciones premium.
          </p>
          <NavLink
            to="/app/planes"
            className="flex items-center gap-1 text-[10.5px] font-semibold text-[#a78bfa] hover:text-[#c4b5fd]"
          >
            Ver planes
            <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </NavLink>
        </div>

        <div className="flex flex-shrink-0 flex-col gap-[1px] border-t border-white/[0.04] px-2.5 py-2">
          {FOOT_LINKS.map((item) => (
            <NavLink
              key={item.label}
              to={item.to}
              className="flex items-center gap-2.5 rounded-[9px] px-2.5 py-2 text-[11.5px] text-[var(--vf-m)] transition-colors hover:bg-white/[0.045] hover:text-[rgba(238,238,245,0.8)]"
            >
              <span className="flex h-[15px] w-[15px] flex-shrink-0 items-center justify-center opacity-70 [&>svg]:h-[14px] [&>svg]:w-[14px]">
                {ICONS[item.icon]}
              </span>
              {item.label}
            </NavLink>
          ))}
        </div>

        <div className="flex-shrink-0 border-t border-white/[0.04] bg-black/20 p-2.5">
          <AccountMenu profile={profile} />
        </div>
      </aside>
      <main className="ml-[228px] flex-1 overflow-y-auto bg-[var(--vf-bg)] p-8">
        <Outlet />
      </main>
    </div>
  );
}
