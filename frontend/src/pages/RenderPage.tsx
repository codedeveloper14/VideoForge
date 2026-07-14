import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { listProjects } from "../api/projects";
import type { Project } from "../types";
import { Select, SelectOption } from "../components/Select";
import JobsPanel from "./render/JobsPanel";
import ProjectRenderPanel from "./render/ProjectRenderPanel";
import QuickRenderPanel from "./render/QuickRenderPanel";

type RenderMode = "project" | "quick";

export default function RenderPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState(searchParams.get("project") || "");
  const [mode, setMode] = useState<RenderMode>("project");
  const [error, setError] = useState("");

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((err) => setError((err as Error).message));
  }, []);

  useEffect(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (project) next.set("project", project);
      else next.delete("project");
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  return (
    <div>
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="tool-h1 text-2xl font-semibold">{t("renderTool.title")}</h1>
          <p className="mt-1 text-sm text-[var(--vf-muted)]">
            {t("renderTool.subtitle")}
          </p>
        </div>
      </div>

      <div className="mb-6 flex gap-2 rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-1 w-fit">
        <button
          type="button"
          onClick={() => setMode("project")}
          className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
            mode === "project"
              ? "bg-[var(--vf-accent)] text-white"
              : "text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
          }`}
        >
          {t("renderTool.projectRender")}
        </button>
        <button
          type="button"
          onClick={() => setMode("quick")}
          className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
            mode === "quick"
              ? "bg-[var(--vf-accent)] text-white"
              : "text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
          }`}
        >
          {t("renderTool.quickMode")}
        </button>
      </div>

      {mode === "project" && (
        <div className="proj-topbar mb-6 flex items-center gap-3 rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-3">
          <span className="font-mono text-xs uppercase tracking-wider text-[var(--vf-muted)]">
            {t("tools.project")}
          </span>
          <Select
            value={project}
            onChange={(v) => setProject(v)}
            className="proj-select flex-1 rounded-lg border border-[var(--vf-border)] bg-black/20 p-2 text-sm text-[var(--vf-text)]"
          >
            <SelectOption value="">{t("tools.noProjectSelected")}</SelectOption>
            {projects.map((p) => (
              <SelectOption key={p.nombre} value={p.nombre}>
                {p.nombre}
              </SelectOption>
            ))}
          </Select>
        </div>
      )}

      {error && <p className="mb-4 text-sm text-[var(--vf-danger)]">{error}</p>}

      <div className="grid gap-6 xl:grid-cols-[1fr_320px] xl:items-start">
        <div>
          {mode === "project" ? (
            <ProjectRenderPanel project={project} />
          ) : (
            <QuickRenderPanel />
          )}
        </div>
        <div className="xl:sticky xl:top-6">
          <JobsPanel />
        </div>
      </div>
    </div>
  );
}
