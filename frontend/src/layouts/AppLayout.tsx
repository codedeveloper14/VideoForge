import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function IconHome() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <polyline points="9,22 9,12 15,12 15,22" />
    </svg>
  );
}
function IconProjects() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="7" width="20" height="14" rx="2" />
      <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
    </svg>
  );
}
function IconIdea() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a7 7 0 0 1 7 7c0 2.66-1.49 4.98-3.69 6.22L15 18H9l-.31-2.78C6.49 13.98 5 11.66 5 9a7 7 0 0 1 7-7z" />
      <line x1="9" y1="21" x2="15" y2="21" />
      <line x1="9" y1="18" x2="15" y2="18" />
    </svg>
  );
}
function IconTasks() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 11 12 14 22 4" />
      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
    </svg>
  );
}
function IconSettings() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.07 4.93l-1.41 1.41M4.93 4.93l1.41 1.41M12 2v2M12 20v2M20 12h2M2 12h2M17.66 17.66l-1.41-1.41M6.34 17.66l1.41-1.41" />
    </svg>
  );
}
function IconDocs() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}
function IconHelp() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}
function IconUpgrade() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13,2 3,14 12,14 11,22 21,10 12,10" />
    </svg>
  );
}

function xiClass({ isActive }: { isActive: boolean }) {
  return (
    "flex w-full items-center gap-2.5 overflow-hidden text-ellipsis whitespace-nowrap rounded-lg px-2.5 py-2 text-left text-[13px] font-medium transition-colors " +
    (isActive ? "text-[#eeeef5]" : "text-[#5a5a75] hover:bg-white/[0.045] hover:text-[rgba(238,238,245,0.82)]")
  );
}

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const initial = (user || "?").charAt(0).toUpperCase();

  return (
    <div className="flex min-h-screen" style={{ background: "#06060c", color: "#eeeef5" }}>
      <aside
        className="fixed left-0 top-0 bottom-0 z-[920] flex w-[220px] flex-col overflow-y-auto"
        style={{ background: "#0a0a14", borderRight: "1px solid rgba(255,255,255,.06)" }}
      >
        <NavLink
          to="/app/home"
          className="flex flex-shrink-0 items-center gap-[11px] px-[15px] pb-[15px] pt-[18px]"
          style={{ borderBottom: "1px solid rgba(255,255,255,.05)" }}
        >
          <div
            className="flex h-[38px] w-[38px] flex-shrink-0 items-center justify-center rounded-[10px]"
            style={{
              background: "linear-gradient(145deg,#6c56ff 0%,#a855f7 55%,#c084fc 100%)",
              boxShadow: "0 0 0 1px rgba(168,85,247,.18), 0 4px 14px rgba(124,106,255,.42)",
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <rect x="2" y="3" width="5" height="18" rx="1" fill="rgba(255,255,255,.22)" />
              <rect x="2.8" y="5.5" width="3.2" height="2" rx=".4" fill="rgba(255,255,255,.85)" />
              <rect x="2.8" y="11" width="3.2" height="2" rx=".4" fill="rgba(255,255,255,.85)" />
              <rect x="2.8" y="16.5" width="3.2" height="2" rx=".4" fill="rgba(255,255,255,.85)" />
              <path d="M10 7.5L21 12 10 16.5V7.5Z" fill="white" />
            </svg>
          </div>
          <div>
            <b className="block text-[14.5px] font-extrabold leading-[1.2] tracking-[-0.025em] text-[#eeeef5]">Studio IVR</b>
            <span className="mt-px block text-[8.5px] font-semibold uppercase tracking-[0.14em] text-[#38384e]">
              AI Pipeline
            </span>
          </div>
        </NavLink>

        <nav className="flex flex-1 flex-col gap-px px-2 pt-2.5">
          <NavLink to="/app/home" end className={xiClass}>
            <span className="flex h-[15px] w-[15px] flex-shrink-0 items-center justify-center opacity-70">
              <IconHome />
            </span>
            Inicio
          </NavLink>

          <span className="block px-[9px] pb-1 pt-[15px] text-[9px] font-bold uppercase tracking-[0.14em] text-[#38384e]">
            General
          </span>

          <NavLink to="/app/home" className={xiClass}>
            <span className="flex h-[15px] w-[15px] flex-shrink-0 items-center justify-center opacity-70">
              <IconProjects />
            </span>
            Proyectos
          </NavLink>

          <button
            onClick={() => navigate("/app/idea2video")}
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium text-[#5a5a75] transition-colors hover:bg-white/[0.04] hover:text-[rgba(238,238,245,0.72)]"
          >
            <span className="flex-shrink-0 opacity-35">
              <IconIdea />
            </span>
            Idea &rarr; Video
          </button>

          <button
            onClick={() => navigate("/app/tareas")}
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium text-[#5a5a75] transition-colors hover:bg-white/[0.04] hover:text-[rgba(238,238,245,0.72)]"
          >
            <span className="flex-shrink-0 opacity-35">
              <IconTasks />
            </span>
            Tareas
          </button>

          <NavLink to="/app/ajustes" className={xiClass}>
            <span className="flex h-[15px] w-[15px] flex-shrink-0 items-center justify-center opacity-70">
              <IconSettings />
            </span>
            Ajustes
          </NavLink>
        </nav>

        <div
          className="mx-2 mb-1.5 mt-3 flex-shrink-0 rounded-xl px-[13px] pb-[11px] pt-[13px]"
          style={{ background: "rgba(124,106,255,.08)", border: "1px solid rgba(124,106,255,.18)" }}
        >
          <div className="mb-1.5 flex items-center gap-2.5">
            <div className="flex h-[26px] w-[26px] flex-shrink-0 items-center justify-center rounded-[7px]" style={{ background: "rgba(124,106,255,.2)" }}>
              <IconUpgrade />
            </div>
            <span className="text-[13px] font-bold text-[#a78bfa]">Upgrade</span>
          </div>
          <p className="mb-[9px] text-[11px] leading-[1.5] text-[#5a5a75]">
            Más créditos, renders y funciones premium.
          </p>
          <button
            onClick={() => navigate("/app/planes")}
            className="flex items-center gap-1 text-xs font-semibold transition-colors hover:text-[#a78bfa]"
            style={{ color: "#7c6aff" }}
          >
            Ver planes
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>

        <div className="flex flex-shrink-0 flex-col gap-px px-2 pb-1 pt-[5px]">
          <button
            onClick={() => navigate("/app/documentacion")}
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium text-[#5a5a75] transition-colors hover:bg-white/[0.04] hover:text-[rgba(238,238,245,0.72)]"
          >
            <span className="flex-shrink-0 opacity-35">
              <IconDocs />
            </span>
            Documentación
          </button>
          <button
            onClick={() => navigate("/app/ayuda")}
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium text-[#5a5a75] transition-colors hover:bg-white/[0.04] hover:text-[rgba(238,238,245,0.72)]"
          >
            <span className="flex-shrink-0 opacity-35">
              <IconHelp />
            </span>
            Centro de ayuda
          </button>
        </div>

        <div className="relative flex-shrink-0">
          <div
            onClick={() => setDropdownOpen((v) => !v)}
            className="flex cursor-pointer items-center gap-2.5 px-[13px] py-3 transition-colors hover:bg-white/[0.04]"
            style={{ borderTop: "1px solid rgba(255,255,255,.05)" }}
          >
            <div
              className="flex h-[30px] w-[30px] flex-shrink-0 items-center justify-center rounded-[8px] text-xs font-bold text-white"
              style={{ background: "linear-gradient(145deg,#6c56ff,#a855f7)", boxShadow: "0 2px 8px rgba(124,106,255,.35)" }}
            >
              {initial}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12.5px] font-semibold text-[#eeeef5]">{user}</div>
              <div className="truncate text-[10.5px] text-[#5a5a75]">Studio IVR</div>
            </div>
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="flex-shrink-0 opacity-25"
              style={{ transform: dropdownOpen ? "rotate(180deg)" : undefined }}
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </div>

          {dropdownOpen && (
            <div
              className="absolute bottom-[64px] left-2 right-2 z-10 overflow-hidden rounded-xl"
              style={{ background: "#12121f", border: "1px solid rgba(255,255,255,.08)", boxShadow: "0 12px 36px rgba(0,0,0,.6)" }}
            >
              <button
                onClick={() => {
                  setDropdownOpen(false);
                  navigate("/app/ajustes");
                }}
                className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13px] text-[#c8c8d8] hover:bg-white/[0.05]"
              >
                <IconSettings /> Configuración
              </button>
              <button
                onClick={() => {
                  setDropdownOpen(false);
                  navigate("/app/planes");
                }}
                className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13px] text-[#a78bfa] hover:bg-white/[0.05]"
              >
                <IconUpgrade /> Upgrade
              </button>
              <div style={{ borderTop: "1px solid rgba(255,255,255,.06)" }} />
              <button
                onClick={logout}
                className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13px] text-[#f47286] hover:bg-white/[0.05]"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                  <polyline points="16 17 21 12 16 7" />
                  <line x1="21" y1="12" x2="9" y2="12" />
                </svg>
                Cerrar sesión
              </button>
            </div>
          )}
        </div>
      </aside>

      <main className="ml-[220px] flex-1 overflow-y-auto p-8" style={{ background: "#06060c" }}>
        <Outlet />
      </main>
    </div>
  );
}
