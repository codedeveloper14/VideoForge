import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

type IconKey =
  | "home"
  | "idea2video"
  | "guion"
  | "voz"
  | "imagen"
  | "video"
  | "render"
  | "editor"
  | "proyectos"
  | "planes"
  | "perfil"
  | "ayuda";

const ICONS: Record<IconKey, React.ReactNode> = {
  home: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <polyline points="9,22 9,12 15,12 15,22" />
    </svg>
  ),
  idea2video: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a7 7 0 0 0-4 12.7V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.3A7 7 0 0 0 12 2z" />
      <line x1="9.5" y1="21" x2="14.5" y2="21" />
    </svg>
  ),
  guion: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14,2 14,8 20,8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  ),
  voz: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
    </svg>
  ),
  imagen: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2.5" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="21,15 16,10 5,21" />
    </svg>
  ),
  video: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="23,7 16,12 23,17 23,7" />
      <rect x="1" y="5" width="15" height="14" rx="2" />
    </svg>
  ),
  render: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="2" width="20" height="20" rx="2.5" />
      <path d="M7 2v20M17 2v20M2 12h20M2 7h5M2 17h5M17 7h5M17 17h5" />
    </svg>
  ),
  editor: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8M12 17v4" />
      <path d="M7 8h5M7 11h3" />
    </svg>
  ),
  proyectos: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </svg>
  ),
  planes: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
    </svg>
  ),
  perfil: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  ),
  ayuda: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 2-3 4" />
      <line x1="12" y1="17" x2="12" y2="17.01" />
    </svg>
  ),
};

interface NavItemDef {
  to: string;
  label: string;
  icon: IconKey;
}

const PIPELINE_ITEMS: NavItemDef[] = [
  { to: "/app/home", label: "Home", icon: "home" },
  { to: "/app/idea2video", label: "Idea a Video", icon: "idea2video" },
  { to: "/app/guion", label: "Guion", icon: "guion" },
  { to: "/app/voz", label: "Voz", icon: "voz" },
  { to: "/app/imagen", label: "Imagen", icon: "imagen" },
  { to: "/app/video", label: "Video", icon: "video" },
  { to: "/app/render", label: "Render", icon: "render" },
  { to: "/app/editor", label: "Editor", icon: "editor" },
];

const ACCOUNT_ITEMS: NavItemDef[] = [
  { to: "/app/proyectos", label: "Proyectos", icon: "proyectos" },
  { to: "/app/planes", label: "Planes", icon: "planes" },
  { to: "/app/perfil", label: "Perfil", icon: "perfil" },
  { to: "/app/ayuda", label: "Ayuda", icon: "ayuda" },
];

function NavItem({ to, label, icon }: NavItemDef) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `group relative flex items-center gap-2.5 rounded-[9px] px-2.5 py-2 font-[var(--vf-mono)] text-[11px] tracking-[0.01em] transition-colors ${
          isActive
            ? "bg-gradient-to-r from-[rgba(124,106,255,0.14)] to-[rgba(124,106,255,0.06)] font-medium text-[var(--vf-text)]"
            : "text-[var(--vf-m)] hover:bg-white/[0.045] hover:text-[rgba(238,238,245,0.8)]"
        }`
      }
      style={{ fontFamily: "var(--vf-mono)" }}
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
            className={`flex h-[17px] w-[17px] flex-shrink-0 items-center justify-center [&>svg]:h-[14px] [&>svg]:w-[14px] ${
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

export default function AppLayout() {
  const { user, logout } = useAuth();

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

        <nav className="flex min-h-0 flex-1 flex-col gap-[1px] px-2.5 pb-4 pt-2">
          <span
            className="px-2 pb-[5px] pt-4 text-[8.5px] font-medium uppercase tracking-[0.18em] text-[var(--vf-m2)]"
            style={{ fontFamily: "var(--vf-mono)" }}
          >
            Pipeline
          </span>
          {PIPELINE_ITEMS.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}

          <div className="my-2 mx-2.5 h-px bg-white/[0.04]" />

          <span
            className="px-2 pb-[5px] pt-2 text-[8.5px] font-medium uppercase tracking-[0.18em] text-[var(--vf-m2)]"
            style={{ fontFamily: "var(--vf-mono)" }}
          >
            Cuenta
          </span>
          {ACCOUNT_ITEMS.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </nav>

        <div className="flex flex-shrink-0 flex-col gap-2 border-t border-white/[0.04] bg-black/20 px-4 py-3">
          <div className="flex items-center gap-2">
            <span
              className="h-[6px] w-[6px] flex-shrink-0 rounded-full"
              style={{ background: "var(--vf-c5)", boxShadow: "0 0 6px var(--vf-c5)" }}
            />
            <p
              className="truncate text-[10px] tracking-[0.06em] text-[var(--vf-m2)]"
              style={{ fontFamily: "var(--vf-mono)" }}
            >
              {user}
            </p>
          </div>
          <button
            onClick={logout}
            className="w-full rounded-[9px] px-2.5 py-2 text-left text-[11px] text-[var(--vf-m)] transition-colors hover:bg-white/[0.045] hover:text-[var(--vf-danger)]"
            style={{ fontFamily: "var(--vf-mono)" }}
          >
            Cerrar sesión
          </button>
        </div>
      </aside>
      <main className="ml-[228px] flex-1 overflow-y-auto bg-[var(--vf-bg)] p-8">
        <Outlet />
      </main>
    </div>
  );
}
