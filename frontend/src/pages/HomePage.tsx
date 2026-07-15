import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { createProject, deleteProject, listProjects } from "../api/projects";
import { useWorkspace } from "../context/WorkspaceContext";
import type { Project } from "../types";

function IconClapper() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="10" width="16" height="10" rx="1.5" />
      <path d="M4 10l1.2-4.6a1 1 0 0 1 1.22-.72L19.8 7.9a1 1 0 0 1 .72 1.22L20 10z" />
      <path d="M8 10 9 5.3M13 10l1-4.7" strokeWidth="1.3" />
    </svg>
  );
}
function IconPlayCircle() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M10 8.3l6 3.7-6 3.7z" fill="currentColor" stroke="none" />
    </svg>
  );
}
function IconFilmStrip() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="3" y1="8" x2="7" y2="8" />
      <line x1="3" y1="12" x2="7" y2="12" />
      <line x1="3" y1="16" x2="7" y2="16" />
      <line x1="17" y1="8" x2="21" y2="8" />
      <line x1="17" y1="12" x2="21" y2="12" />
      <line x1="17" y1="16" x2="21" y2="16" />
    </svg>
  );
}
function IconCamera() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="7" width="12" height="10" rx="2" />
      <path d="M15 10.5 21 7v10l-6-3.5z" />
    </svg>
  );
}
function IconAperture() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <line x1="14.31" y1="8" x2="20.05" y2="17.94" />
      <line x1="9.69" y1="8" x2="21.17" y2="8" />
      <line x1="7.38" y1="12" x2="13.12" y2="2.06" />
      <line x1="9.69" y1="16" x2="3.95" y2="6.06" />
      <line x1="14.31" y1="16" x2="2.83" y2="16" />
      <line x1="16.62" y1="12" x2="10.88" y2="21.94" />
    </svg>
  );
}
function IconStar() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3.5l2.5 5.5 6 .7-4.4 4.1 1.2 6-5.3-3-5.3 3 1.2-6L3.5 9.7l6-.7z" />
    </svg>
  );
}

const PALETTE = [
  { color: "#7c6aff", Icon: IconClapper },
  { color: "#f472b6", Icon: IconPlayCircle },
  { color: "#22d3a0", Icon: IconFilmStrip },
  { color: "#fbbf24", Icon: IconCamera },
  { color: "#38bdf8", Icon: IconAperture },
  { color: "#a855f7", Icon: IconStar },
];

function pmStyle(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const idx = Math.abs(hash) % PALETTE.length;
  return PALETTE[idx];
}

function formatDate(creado: number, locale: string) {
  return new Date(creado * 1000).toLocaleDateString(locale === "en" ? "en-US" : "es-CO", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function HomePage() {
  const { t, i18n } = useTranslation();
  const { openProject } = useWorkspace();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [nombre, setNombre] = useState("");
  const [creating, setCreating] = useState(false);
  const [openMenu, setOpenMenu] = useState<string | null>(null);

  function load() {
    setLoading(true);
    listProjects()
      .then(setProjects)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!nombre.trim()) return;
    setCreating(true);
    setError("");
    try {
      await createProject(nombre.trim());
      setNombre("");
      setShowCreate(false);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(name: string) {
    setOpenMenu(null);
    if (!confirm(t("home.confirmDelete", { name }))) return;
    setError("");
    try {
      await deleteProject(name);
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="max-w-6xl" onClick={() => openMenu && setOpenMenu(null)}>
      <div className="mb-8">
        <div
          className="mb-4 inline-flex items-center gap-2 rounded-full border border-[var(--vf-b)] bg-[rgba(var(--vf-fg-rgb),0.03)] px-3 py-1 text-[9.5px] font-medium uppercase tracking-[0.18em] text-[var(--vf-m)]"
          style={{ fontFamily: "var(--vf-mono)" }}
        >
          <span
            className="h-[5px] w-[5px] rounded-full"
            style={{ background: "var(--vf-c5)", boxShadow: "0 0 6px var(--vf-c5)" }}
          />
          {t("home.eyebrow")}
        </div>
        <h1 className="mb-2 text-[clamp(28px,3vw,42px)] font-bold leading-[1.05] tracking-[-1px]">
          {t("home.myProjects")}{" "}
          <span
            className="bg-clip-text text-transparent"
            style={{ backgroundImage: "linear-gradient(110deg, var(--vf-c2), var(--vf-c1), var(--vf-c3))" }}
          >
            {t("home.projects")}
          </span>
        </h1>
        <p className="max-w-[380px] text-xs leading-relaxed text-[var(--vf-m)]" style={{ fontFamily: "var(--vf-mono)" }}>
          {t("home.subtitle")}
        </p>
      </div>

      {showCreate && (
        <form
          onSubmit={handleCreate}
          className="mb-8 flex flex-wrap gap-2 rounded-2xl border border-[var(--vf-b)] bg-[var(--vf-s)] p-4"
        >
          <input
            autoFocus
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder={t("home.newProjectNamePlaceholder")}
            className="min-w-[220px] flex-1 rounded-lg border border-[var(--vf-border)] bg-[var(--vf-p)] px-3 py-2 text-sm outline-none focus:border-[var(--vf-accent)]"
          />
          <button
            type="submit"
            disabled={creating}
            className="rounded-lg bg-[var(--vf-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--vf-accent-hover)] disabled:opacity-50"
          >
            {creating ? t("home.creating") : t("home.create")}
          </button>
          <button
            type="button"
            onClick={() => setShowCreate(false)}
            className="rounded-lg border border-[var(--vf-border)] px-4 py-2 text-sm hover:bg-[rgba(var(--vf-fg-rgb),0.04)]"
          >
            {t("home.cancel")}
          </button>
        </form>
      )}

      {error && <p className="mb-6 text-sm text-[var(--vf-danger)]">{error}</p>}

      {loading ? (
        <p className="text-[var(--vf-muted)]">{t("home.loading")}</p>
      ) : projects.length === 0 ? (
        <div
          className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-[var(--vf-b2)] bg-[rgba(var(--vf-fg-rgb),0.02)] p-[60px_40px] text-center"
        >
          <div className="text-[40px] opacity-40">🎬</div>
          <div className="text-lg font-bold tracking-[-0.4px] text-[var(--vf-text)] opacity-60">{t("home.noProjectsYet")}</div>
          <p className="max-w-[300px] text-[11px] leading-relaxed text-[var(--vf-m)]" style={{ fontFamily: "var(--vf-mono)" }}>
            {t("home.noProjectsDesc")}
          </p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-1 inline-flex items-center gap-2 rounded-[10px] border-none px-[22px] py-3 text-xs font-semibold tracking-[0.03em] text-white transition-all hover:-translate-y-0.5"
            style={{
              fontFamily: "var(--vf-mono)",
              background: "linear-gradient(135deg, var(--vf-c1), #9f7aea)",
              boxShadow: "0 4px 20px rgba(124,106,255,.38)",
            }}
          >
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            {t("home.createFirstProject")}
          </button>
        </div>
      ) : (
        <div
          className="grid gap-4"
          style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}
        >
          {projects.map((p) => {
            const { color, Icon } = pmStyle(p.nombre);
            return (
              <div
                key={p.nombre}
                onClick={() => openProject(p.nombre)}
                className="relative flex cursor-pointer flex-col gap-2.5 overflow-hidden rounded-2xl border border-[var(--vf-b)] bg-[var(--vf-s)] p-[24px_20px] transition-all hover:-translate-y-[3px] hover:border-[rgba(124,106,255,0.3)] hover:shadow-[0_16px_40px_rgba(0,0,0,.35)]"
              >
                <div className="flex items-start justify-between gap-2">
                  <div
                    className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[11px]"
                    style={{ background: `${color}22`, border: `1px solid ${color}33`, color }}
                  >
                    <Icon />
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setOpenMenu(openMenu === p.nombre ? null : p.nombre);
                    }}
                    title={t("home.options")}
                    className="rounded-[5px] border-none bg-transparent px-1.5 py-0.5 text-base text-[var(--vf-m)] transition-colors hover:bg-[rgba(var(--vf-fg-rgb),0.06)] hover:text-[var(--vf-text)]"
                  >
                    ⋯
                  </button>
                  {openMenu === p.nombre && (
                    <div
                      onClick={(e) => e.stopPropagation()}
                      className="absolute right-4 top-14 z-10 min-w-[150px] rounded-[10px] border border-[var(--vf-b2)] bg-[var(--vf-p)] p-1.5 shadow-[0_12px_36px_rgba(0,0,0,.5)]"
                    >
                      <button
                        onClick={() => handleDelete(p.nombre)}
                        className="flex w-full items-center gap-2 rounded-[7px] border-none bg-transparent px-3 py-2 text-left text-[11px] text-[var(--vf-danger)] transition-colors hover:bg-[rgba(255,85,102,0.1)]"
                        style={{ fontFamily: "var(--vf-mono)" }}
                      >
                        {t("home.delete")}
                      </button>
                    </div>
                  )}
                </div>
                <div className="truncate text-[15px] font-bold tracking-[-0.3px] text-[var(--vf-text)]">{p.nombre}</div>
                <div className="text-[10px] tracking-[0.04em] text-[var(--vf-m2)]" style={{ fontFamily: "var(--vf-mono)" }}>
                  {t("home.createdOn", { date: formatDate(p.creado, i18n.language) })}
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    openProject(p.nombre);
                  }}
                  className="mt-1 w-full rounded-lg border border-[rgba(124,106,255,0.2)] py-2 text-[11px] font-medium tracking-[0.04em] transition-all hover:border-[rgba(124,106,255,0.35)]"
                  style={{ fontFamily: "var(--vf-mono)", background: "rgba(124,106,255,.1)", color: "var(--vf-c2)" }}
                >
                  {t("home.openProject")}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
