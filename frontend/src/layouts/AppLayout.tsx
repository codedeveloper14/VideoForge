import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { NavLink, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import { WorkspaceProvider, useWorkspace, type PipelinePage } from "../context/WorkspaceContext";
import { listProjects } from "../api/projects";
import type { Project } from "../types";
import ActiveJobsPopup from "../components/ActiveJobsPopup";
import UpdateNotice from "../components/UpdateNotice";
import NewProjectModal from "../components/NewProjectModal";

const NO_SIDEBAR_ROUTES = [
  "/app/idea2video",
  "/app/tareas",
  "/app/ajustes",
  "/app/planes",
  "/app/documentacion",
  "/app/ayuda",
];

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
function IconSearch() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}
function IconBell() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}
function IconPlus() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function IconBack() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="15,18 9,12 15,6" />
    </svg>
  );
}

function IconMenu() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  );
}

function xiClass({ isActive }: { isActive: boolean }) {
  return (
    "flex w-full items-center gap-2.5 overflow-hidden text-ellipsis whitespace-nowrap rounded-lg px-2.5 py-2 text-left text-[13px] font-medium transition-colors " +
    (isActive ? "text-[var(--vf-text)]" : "text-[var(--vf-m)] hover:bg-[rgba(var(--vf-fg-rgb),0.045)] hover:text-[rgba(var(--vf-fg-rgb),0.82)]")
  );
}

const PIPELINE_STEPS: { page: PipelinePage; labelKey: string }[] = [
  { page: "guion", labelKey: "sidebar.pipelineScript" },
  { page: "imagen", labelKey: "sidebar.pipelineImages" },
  { page: "voz", labelKey: "sidebar.pipelineVoice" },
  { page: "video", labelKey: "sidebar.pipelineVideo" },
  { page: "render", labelKey: "sidebar.pipelineRender" },
];

function ProjectSearch({ onClose, onPick }: { onClose: () => void; onPick: (name: string) => void }) {
  const { t } = useTranslation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    listProjects().then(setProjects).catch(() => {});
  }, []);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  const filtered = projects.filter((p) => p.nombre.toLowerCase().includes(query.toLowerCase()));

  return (
    <div
      ref={ref}
      className="absolute left-0 top-[52px] z-[960] w-[300px] rounded-xl border border-[rgba(var(--vf-fg-rgb),.1)] bg-[var(--vf-p)] p-2 shadow-[0_16px_44px_rgba(0,0,0,.6)]"
    >
      <input
        autoFocus
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t("topbar.searchProjects") || ""}
        className="mb-1.5 w-full rounded-lg border border-[rgba(var(--vf-fg-rgb),.08)] bg-[rgba(var(--vf-fg-rgb),.04)] px-3 py-2 text-sm text-[var(--vf-text)] outline-none"
      />
      <div className="max-h-[260px] overflow-y-auto">
        {filtered.length === 0 && (
          <p className="px-2 py-3 text-center text-xs text-[var(--vf-m)]">{t("topbar.noProjects")}</p>
        )}
        {filtered.map((p) => (
          <button
            key={p.nombre}
            onClick={() => onPick(p.nombre)}
            className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] text-[var(--vf-text)] hover:bg-[rgba(var(--vf-fg-rgb),.06)]"
          >
            {p.nombre}
          </button>
        ))}
      </div>
    </div>
  );
}

function TopBar({ leftOffset }: { leftOffset: number }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { tabs, openProject, closeTab } = useWorkspace();
  const [showCreate, setShowCreate] = useState(false);
  const [showSearch, setShowSearch] = useState(false);

  const activeProject = searchParams.get("project") || "";
  const onHome = location.pathname === "/app/home" || location.pathname === "/app";

  return (
    <header
      className="fixed right-0 top-0 z-[910] flex h-12 items-center gap-2.5 border-b border-[rgba(var(--vf-fg-rgb),.06)] bg-[rgba(var(--vf-bg-rgb),.92)] px-4 backdrop-blur-[16px] transition-[left] duration-200"
      style={{ left: leftOffset }}
    >
      <button
        onClick={() => navigate("/app/home")}
        title={t("topbar.home") || ""}
        className={
          "flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center rounded-lg border transition-colors " +
          (onHome
            ? "border-[rgba(124,106,255,.35)] bg-[rgba(124,106,255,.15)] text-[#a78bfa]"
            : "border-[rgba(var(--vf-fg-rgb),.1)] bg-[rgba(var(--vf-fg-rgb),.06)] text-[var(--vf-m)] hover:border-[rgba(124,106,255,.35)] hover:bg-[rgba(124,106,255,.15)] hover:text-[#a78bfa]")
        }
      >
        <IconHome />
      </button>

      <div className="flex items-end gap-[3px]">
        {tabs.map((name) => {
          const isActive = name === activeProject;
          return (
            <button
              key={name}
              onClick={() => openProject(name)}
              title={name}
              className={
                "flex h-9 min-w-[80px] max-w-[180px] items-center gap-1.5 overflow-hidden rounded-t-lg border border-b-0 px-2.5 text-[12px] font-medium transition-colors " +
                (isActive
                  ? "border-[rgba(124,106,255,.35)] bg-[rgba(124,106,255,.15)] text-[var(--vf-text)]"
                  : "border-[rgba(var(--vf-fg-rgb),.09)] bg-[rgba(var(--vf-fg-rgb),.04)] text-[var(--vf-m)] hover:bg-[rgba(var(--vf-fg-rgb),.08)] hover:text-[var(--vf-text)]")
              }
              style={isActive ? { borderTopColor: "#7c6aff" } : undefined}
            >
              <span className="truncate">{name}</span>
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  closeTab(name);
                  if (isActive) navigate("/app/home");
                }}
                className="flex h-[15px] w-[15px] flex-shrink-0 items-center justify-center rounded text-[9.5px] text-[rgba(var(--vf-fg-rgb),.35)] hover:bg-[rgba(var(--vf-fg-rgb),.1)] hover:text-[var(--vf-text)]"
              >
                ✕
              </span>
            </button>
          );
        })}
        <button
          onClick={() => setShowCreate(true)}
          title={t("topbar.newTab") || ""}
          className="mb-[3px] flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md border border-dashed border-[rgba(var(--vf-fg-rgb),.22)] bg-[rgba(var(--vf-fg-rgb),.05)] text-[var(--vf-m)] hover:border-[rgba(124,106,255,.55)] hover:bg-[rgba(124,106,255,.15)] hover:text-[#a78bfa]"
        >
          +
        </button>
      </div>

      <div className="flex-1" />

      <div className="relative">
        <button
          onClick={() => setShowSearch((v) => !v)}
          className="flex min-w-[200px] items-center gap-2 rounded-lg border border-[rgba(var(--vf-fg-rgb),.08)] bg-[rgba(var(--vf-fg-rgb),.05)] px-3 py-1.5 text-[var(--vf-m)] hover:border-[rgba(124,106,255,.25)] hover:bg-[rgba(var(--vf-fg-rgb),.08)]"
        >
          <IconSearch />
          <span className="flex-1 text-left text-[11.5px]">{t("topbar.searchProjects")}</span>
          <kbd className="rounded border border-[rgba(var(--vf-fg-rgb),.08)] bg-[rgba(var(--vf-fg-rgb),.06)] px-1 py-0.5 text-[9px] text-[var(--vf-m2)]">⌘K</kbd>
        </button>
        {showSearch && (
          <ProjectSearch
            onClose={() => setShowSearch(false)}
            onPick={(name) => {
              setShowSearch(false);
              openProject(name);
            }}
          />
        )}
      </div>

      <button
        onClick={() => setShowCreate(true)}
        className="flex flex-shrink-0 items-center gap-1.5 rounded-lg px-[15px] py-1.5 text-[12.5px] font-semibold text-white shadow-[0_4px_14px_rgba(124,106,255,.38)] transition-all hover:-translate-y-px hover:opacity-90"
        style={{ background: "linear-gradient(135deg,#7c6aff,#a855f7)" }}
      >
        <IconPlus /> {t("topbar.newProjectPlain")}
      </button>

      <ActiveJobsPopup />

      <button
        className="flex h-[30px] w-[30px] flex-shrink-0 items-center justify-center rounded-lg text-[var(--vf-m)] hover:bg-[rgba(var(--vf-fg-rgb),.07)] hover:text-[var(--vf-text)]"
        title={t("topbar.notifications") || ""}
      >
        <IconBell />
      </button>

      {showCreate && (
        <NewProjectModal
          onClose={() => setShowCreate(false)}
          onCreated={(name) => {
            setShowCreate(false);
            openProject(name);
          }}
        />
      )}
    </header>
  );
}

function AppLayoutInner() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [dropdownRect, setDropdownRect] = useState<{ bottom: number; left: number } | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const accountTriggerRef = useRef<HTMLDivElement>(null);
  const accountPopupRef = useRef<HTMLDivElement>(null);

  const initial = (user || "?").charAt(0).toUpperCase();
  const hideSidebar = NO_SIDEBAR_ROUTES.some((r) => location.pathname.startsWith(r));
  // On the mobile drawer, always show full labels regardless of the desktop collapse toggle.
  const effectiveCollapsed = collapsed && !mobileNavOpen;

  const activeProject = searchParams.get("project") || "";
  const currentPage = PIPELINE_STEPS.find((s) => location.pathname === `/app/${s.page}`)?.page;
  const showPipeline = !!activeProject && !!currentPage;

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!dropdownOpen || !accountTriggerRef.current) return;
    const r = accountTriggerRef.current.getBoundingClientRect();
    setDropdownRect({
      bottom: window.innerHeight - r.top + 6,
      left: effectiveCollapsed ? r.right + 8 : r.left + 8,
    });
  }, [dropdownOpen, effectiveCollapsed]);

  useEffect(() => {
    if (!dropdownOpen) return;
    function handleClick(e: MouseEvent) {
      const target = e.target as Node;
      if (accountTriggerRef.current?.contains(target)) return;
      if (accountPopupRef.current?.contains(target)) return;
      setDropdownOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [dropdownOpen]);

  return (
    <div className="flex min-h-screen" style={{ background: "var(--vf-bg)", color: "var(--vf-text)" }}>
      {!hideSidebar && (
      <>
      <button
        onClick={() => setMobileNavOpen(true)}
        title={t("sidebar.openMenu")}
        className="fixed left-3 top-3 z-[905] flex h-9 w-9 items-center justify-center rounded-lg md:hidden"
        style={{ background: "var(--vf-s)", border: "1px solid rgba(var(--vf-fg-rgb),.1)", color: "var(--vf-m)" }}
      >
        <IconMenu />
      </button>
      {mobileNavOpen && (
        <div
          onClick={() => setMobileNavOpen(false)}
          className="fixed inset-0 z-[915] bg-black/50 md:hidden"
        />
      )}
      <aside
        className={`fixed left-0 top-0 bottom-0 z-[920] flex w-[220px] flex-col overflow-y-auto overflow-x-hidden transition-transform duration-200 md:transition-[width] ${
          mobileNavOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        } ${collapsed ? "md:w-[64px]" : "md:w-[220px]"}`}
        style={{ background: "var(--vf-s)", borderRight: "1px solid rgba(var(--vf-fg-rgb),.06)" }}
      >
        <div
          className={`flex flex-shrink-0 items-center gap-[11px] pb-[15px] pt-[18px] ${
            effectiveCollapsed ? "justify-center px-2" : "px-[15px]"
          }`}
          style={{ borderBottom: "1px solid rgba(var(--vf-fg-rgb),.05)" }}
        >
          <NavLink to="/app/home" className="flex flex-shrink-0 items-center gap-[11px]" title={effectiveCollapsed ? t("sidebar.appName") : undefined}>
            <img src="/logo.png" alt="" className="h-[38px] w-[38px] flex-shrink-0 object-contain" />
            {!effectiveCollapsed && (
              <div>
                <b className="block whitespace-nowrap text-[14.5px] font-extrabold leading-[1.2] tracking-[-0.025em] text-[var(--vf-text)]">{t("sidebar.appName")}</b>
                <span className="mt-px block whitespace-nowrap text-[8.5px] font-semibold uppercase tracking-[0.14em] text-[var(--vf-m2)]">
                  {t("sidebar.tagline")}
                </span>
              </div>
            )}
          </NavLink>
          {!effectiveCollapsed && (
            <button
              onClick={() => setCollapsed(true)}
              title={t("sidebar.collapseMenu")}
              className="ml-auto flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg text-[var(--vf-m)] transition-colors hover:bg-[rgba(var(--vf-fg-rgb),0.06)] hover:text-[var(--vf-text)]"
            >
              <IconMenu />
            </button>
          )}
        </div>

        {effectiveCollapsed && (
          <div className="flex flex-shrink-0 justify-center px-2 pt-2">
            <button
              onClick={() => setCollapsed(false)}
              title={t("sidebar.expandMenu")}
              className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg text-[var(--vf-m)] transition-colors hover:bg-[rgba(var(--vf-fg-rgb),0.06)] hover:text-[var(--vf-text)]"
            >
              <IconMenu />
            </button>
          </div>
        )}

        <nav className="flex flex-shrink-0 flex-col gap-px px-2 pt-2.5">
          <NavLink to="/app/home" end className={xiClass} title={effectiveCollapsed ? t("sidebar.home") : undefined}>
            <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center opacity-70">
              <IconHome />
            </span>
            {!effectiveCollapsed && t("sidebar.home")}
          </NavLink>

          {!effectiveCollapsed && (
            <span className="block px-[9px] pb-1 pt-[15px] text-[9px] font-bold uppercase tracking-[0.14em] text-[var(--vf-m2)]">
              {t("sidebar.general")}
            </span>
          )}

          <NavLink to="/app/home" className={xiClass} title={effectiveCollapsed ? t("sidebar.projects") : undefined}>
            <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center opacity-70">
              <IconProjects />
            </span>
            {!effectiveCollapsed && t("sidebar.projects")}
          </NavLink>

          <button
            onClick={() => navigate("/app/idea2video")}
            title={effectiveCollapsed ? t("sidebar.ideaToVideo") : undefined}
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium text-[var(--vf-m)] transition-colors hover:bg-[rgba(var(--vf-fg-rgb),0.04)] hover:text-[rgba(var(--vf-fg-rgb),0.72)]"
          >
            <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center opacity-35">
              <IconIdea />
            </span>
            {!effectiveCollapsed && t("sidebar.ideaToVideo")}
          </button>

          <button
            onClick={() => navigate("/app/tareas")}
            title={effectiveCollapsed ? t("sidebar.tasks") : undefined}
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium text-[var(--vf-m)] transition-colors hover:bg-[rgba(var(--vf-fg-rgb),0.04)] hover:text-[rgba(var(--vf-fg-rgb),0.72)]"
          >
            <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center opacity-35">
              <IconTasks />
            </span>
            {!effectiveCollapsed && t("sidebar.tasks")}
          </button>

          <NavLink to="/app/ajustes" className={xiClass} title={effectiveCollapsed ? t("sidebar.settings") : undefined}>
            <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center opacity-70">
              <IconSettings />
            </span>
            {!effectiveCollapsed && t("sidebar.settings")}
          </NavLink>
        </nav>

        {showPipeline && (
          <div className="mt-1 flex-shrink-0 border-t border-[rgba(var(--vf-fg-rgb),.06)] px-2.5 pb-2 pt-3">
            <span className="mb-2 block px-px text-[9.5px] font-bold uppercase tracking-[0.12em] text-[var(--vf-m2)]">
              {t("sidebar.pipelineLabel")}
            </span>
            {PIPELINE_STEPS.map((step, i) => {
              const isOn = step.page === currentPage;
              return (
                <button
                  key={step.page}
                  onClick={() => navigate(`/app/${step.page}?project=${encodeURIComponent(activeProject)}`)}
                  className={
                    "flex w-full items-center gap-2.5 rounded-lg px-2 py-[7px] text-left text-[13px] font-medium transition-colors " +
                    (isOn ? "bg-gradient-to-r from-[rgba(124,106,255,.18)] to-[rgba(124,106,255,.06)] text-[var(--vf-text)]" : "text-[var(--vf-m)] hover:bg-[rgba(var(--vf-fg-rgb),.05)] hover:text-[var(--vf-text)]")
                  }
                >
                  <span
                    className={
                      "flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-[6px] border text-[11px] font-bold " +
                      (isOn ? "border-[rgba(124,106,255,.4)] bg-[rgba(124,106,255,.3)] text-[#a78bfa]" : "border-[rgba(var(--vf-fg-rgb),.08)] bg-[rgba(var(--vf-fg-rgb),.07)] text-[var(--vf-m)]")
                    }
                  >
                    {i + 1}
                  </span>
                  {t(step.labelKey)}
                </button>
              );
            })}
          </div>
        )}

        <div className="flex-1" />

        {collapsed ? (
          <div className="mx-2 mb-1.5 mt-3 flex flex-shrink-0 justify-center">
            <button
              onClick={() => navigate("/app/planes")}
              title={`${t("sidebar.upgrade")} — ${t("sidebar.viewPlans")}`}
              className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-[9px]"
              style={{ background: "rgba(124,106,255,.15)", border: "1px solid rgba(124,106,255,.25)" }}
            >
              <IconUpgrade />
            </button>
          </div>
        ) : (
          <div
            className="mx-2 mb-1.5 mt-3 flex-shrink-0 rounded-xl px-[13px] pb-[11px] pt-[13px]"
            style={{ background: "rgba(124,106,255,.08)", border: "1px solid rgba(124,106,255,.18)" }}
          >
            <div className="mb-1.5 flex items-center gap-2.5">
              <div className="flex h-[26px] w-[26px] flex-shrink-0 items-center justify-center rounded-[7px]" style={{ background: "rgba(124,106,255,.2)" }}>
                <IconUpgrade />
              </div>
              <span className="text-[13px] font-bold text-[#a78bfa]">{t("sidebar.upgrade")}</span>
            </div>
            <p className="mb-[9px] text-[11px] leading-[1.5] text-[var(--vf-m)]">
              {t("sidebar.upgradeDesc")}
            </p>
            <button
              onClick={() => navigate("/app/planes")}
              className="flex items-center gap-1 text-xs font-semibold transition-colors hover:text-[#a78bfa]"
              style={{ color: "#7c6aff" }}
            >
              {t("sidebar.viewPlans")}
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
          </div>
        )}

        <div className="flex flex-shrink-0 flex-col gap-px px-2 pb-1 pt-[5px]">
          <button
            onClick={() => navigate("/app/documentacion")}
            title={effectiveCollapsed ? t("sidebar.docs") : undefined}
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium text-[var(--vf-m)] transition-colors hover:bg-[rgba(var(--vf-fg-rgb),0.04)] hover:text-[rgba(var(--vf-fg-rgb),0.72)]"
          >
            <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center opacity-35">
              <IconDocs />
            </span>
            {!effectiveCollapsed && t("sidebar.docs")}
          </button>
          <button
            onClick={() => navigate("/app/ayuda")}
            title={effectiveCollapsed ? t("sidebar.helpCenter") : undefined}
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium text-[var(--vf-m)] transition-colors hover:bg-[rgba(var(--vf-fg-rgb),0.04)] hover:text-[rgba(var(--vf-fg-rgb),0.72)]"
          >
            <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center opacity-35">
              <IconHelp />
            </span>
            {!effectiveCollapsed && t("sidebar.helpCenter")}
          </button>
        </div>

        <div className="relative flex-shrink-0">
          <div
            ref={accountTriggerRef}
            onClick={() => setDropdownOpen((v) => !v)}
            title={effectiveCollapsed ? user || undefined : undefined}
            className={`flex cursor-pointer items-center gap-2.5 py-3 transition-colors hover:bg-[rgba(var(--vf-fg-rgb),0.04)] ${effectiveCollapsed ? "justify-center px-2" : "px-[13px]"}`}
            style={{ borderTop: "1px solid rgba(var(--vf-fg-rgb),.05)" }}
          >
            <div
              className="flex h-[30px] w-[30px] flex-shrink-0 items-center justify-center rounded-[8px] text-xs font-bold text-white"
              style={{ background: "linear-gradient(145deg,#6c56ff,#a855f7)", boxShadow: "0 2px 8px rgba(124,106,255,.35)" }}
            >
              {initial}
            </div>
            {!effectiveCollapsed && (
              <>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12.5px] font-semibold text-[var(--vf-text)]">{user}</div>
                  <div className="truncate text-[10.5px] text-[var(--vf-m)]">Studio IVR</div>
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
              </>
            )}
          </div>

          {dropdownOpen &&
            dropdownRect &&
            createPortal(
              <div
                ref={accountPopupRef}
                className="fixed z-[930] w-[200px] overflow-hidden rounded-xl"
                style={{
                  bottom: dropdownRect.bottom,
                  left: dropdownRect.left,
                  background: "var(--vf-p)",
                  border: "1px solid rgba(var(--vf-fg-rgb),.08)",
                  boxShadow: "0 12px 36px rgba(0,0,0,.6)",
                }}
              >
              <button
                onClick={() => {
                  setDropdownOpen(false);
                  navigate("/app/ajustes");
                }}
                className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13px] text-[var(--vf-text)] hover:bg-[rgba(var(--vf-fg-rgb),0.05)]"
              >
                <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center">
                  <IconSettings />
                </span>
                {t("sidebar.configuration")}
              </button>
              <button
                onClick={() => {
                  setDropdownOpen(false);
                  navigate("/app/planes");
                }}
                className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13px] text-[#a78bfa] hover:bg-[rgba(var(--vf-fg-rgb),0.05)]"
              >
                <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center">
                  <IconUpgrade />
                </span>
                {t("sidebar.upgrade")}
              </button>
              <div style={{ borderTop: "1px solid rgba(var(--vf-fg-rgb),.06)" }} />
              <button
                onClick={logout}
                className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13px] text-[var(--vf-danger)] hover:bg-[rgba(var(--vf-fg-rgb),0.05)]"
              >
                <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                    <polyline points="16 17 21 12 16 7" />
                    <line x1="21" y1="12" x2="9" y2="12" />
                  </svg>
                </span>
                {t("sidebar.logout")}
              </button>
              </div>,
              document.body,
            )}
        </div>
      </aside>
      </>
      )}

      <TopBar leftOffset={hideSidebar ? 0 : collapsed ? 64 : 220} />

      <main
        className="mt-12 flex-1 overflow-y-auto p-8 transition-[margin] duration-200"
        style={{ background: "var(--vf-bg)", marginLeft: hideSidebar ? 0 : collapsed ? 64 : 220 }}
      >
        <UpdateNotice />
        {hideSidebar && (
          <button
            onClick={() => navigate("/app/home")}
            className="mb-4 flex items-center gap-1.5 text-sm text-[var(--vf-muted)] transition-colors hover:text-[var(--vf-text)]"
          >
            <IconBack />
            {t("sidebar.back")}
          </button>
        )}
        <Outlet />
      </main>
    </div>
  );
}

export default function AppLayout() {
  return (
    <WorkspaceProvider>
      <AppLayoutInner />
    </WorkspaceProvider>
  );
}
