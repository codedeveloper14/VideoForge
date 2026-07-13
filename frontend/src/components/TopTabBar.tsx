import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { getProjectFromLocation, useTabs } from "../context/TabsContext";
import ProjectPickerModal from "./ProjectPickerModal";
import ActiveJobsPopup from "./ActiveJobsPopup";

function IconPlus() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}
function IconClose() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}
function IconSearch() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}
function IconBell() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

export default function TopTabBar() {
  const { tabs, openTab, closeTab } = useTabs();
  const location = useLocation();
  const navigate = useNavigate();
  const [pickerOpen, setPickerOpen] = useState(false);

  const activeProject = getProjectFromLocation(location.pathname, location.search);

  function goToProject(name: string) {
    navigate(`/app/proyectos/${encodeURIComponent(name)}`);
  }

  function handleSelectFromPicker(name: string) {
    openTab(name);
    setPickerOpen(false);
    goToProject(name);
  }

  function handleClose(e: React.MouseEvent, name: string) {
    e.stopPropagation();
    const wasActive = name === activeProject;
    const remaining = tabs.filter((t) => t.name !== name);
    closeTab(name);
    if (wasActive) {
      if (remaining.length > 0) {
        goToProject(remaining[remaining.length - 1].name);
      } else {
        navigate("/app/home");
      }
    }
  }

  return (
    <div className="mb-5 flex flex-wrap items-center gap-2.5">
      <div className="flex flex-1 flex-wrap items-center gap-1.5">
        {tabs.length === 0 ? (
          <button
            onClick={() => setPickerOpen(true)}
            className="flex items-center gap-1.5 rounded-lg border border-[rgba(var(--vf-fg-rgb),0.12)] bg-[rgba(var(--vf-fg-rgb),0.03)] px-3 py-1.5 text-xs font-semibold text-[var(--vf-muted)] transition-colors hover:text-[var(--vf-text)]"
          >
            <IconPlus />
            Abrir proyecto
          </button>
        ) : (
          <>
            {tabs.map((tab) => {
              const isActive = tab.name === activeProject;
              return (
                <button
                  key={tab.name}
                  onClick={() => goToProject(tab.name)}
                  title={tab.name}
                  className={`group flex max-w-[180px] items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
                    isActive
                      ? "border-[var(--vf-c1)]/45 bg-[var(--vf-c1)]/[0.14] text-[var(--vf-c1)]"
                      : "border-[rgba(var(--vf-fg-rgb),0.1)] bg-[rgba(var(--vf-fg-rgb),0.03)] text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
                  }`}
                >
                  <span className="truncate">{tab.name}</span>
                  <span
                    onClick={(e) => handleClose(e, tab.name)}
                    className="flex-shrink-0 rounded p-0.5 opacity-50 transition-opacity hover:opacity-100"
                  >
                    <IconClose />
                  </span>
                </button>
              );
            })}
            <button
              onClick={() => setPickerOpen(true)}
              title="Abrir otro proyecto"
              className="flex h-[30px] w-[30px] flex-shrink-0 items-center justify-center rounded-lg border border-[rgba(var(--vf-fg-rgb),0.1)] bg-[rgba(var(--vf-fg-rgb),0.03)] text-[var(--vf-muted)] transition-colors hover:text-[var(--vf-text)]"
            >
              <IconPlus />
            </button>
          </>
        )}
      </div>

      <button
        onClick={() => setPickerOpen(true)}
        className="flex min-w-[180px] items-center gap-2 rounded-lg border border-[rgba(var(--vf-fg-rgb),0.1)] bg-[rgba(var(--vf-fg-rgb),0.03)] px-3 py-1.5 text-xs text-[var(--vf-muted)] transition-colors hover:text-[var(--vf-text)]"
      >
        <IconSearch />
        Buscar proyectos...
      </button>
      <button
        onClick={() => setPickerOpen(true)}
        className="flex-shrink-0 rounded-lg bg-[var(--vf-accent)] px-3.5 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-[var(--vf-accent-hover)]"
      >
        + Nuevo Proyecto
      </button>
      <ActiveJobsPopup />
      <button
        title="Notificaciones"
        className="flex h-[30px] w-[30px] flex-shrink-0 items-center justify-center rounded-lg border border-[rgba(var(--vf-fg-rgb),0.1)] bg-[rgba(var(--vf-fg-rgb),0.03)] text-[var(--vf-muted)] transition-colors hover:text-[var(--vf-text)]"
      >
        <IconBell />
      </button>

      {pickerOpen && <ProjectPickerModal onClose={() => setPickerOpen(false)} onSelect={handleSelectFromPicker} />}
    </div>
  );
}
