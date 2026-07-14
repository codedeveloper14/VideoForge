import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getProjectContent, listProjects } from "../api/projects";
import type { Project } from "../types";
import { Select, SelectOption } from "../components/Select";
import FlowPanel from "./imagen/FlowPanel";
import GentubePanel from "./imagen/GentubePanel";

const TABS = [
  { id: "flow", label: "Flow" },
  { id: "gentube", label: "Gentube" },
];

export default function ImagenPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState(searchParams.get("project") || "");
  const [error, setError] = useState("");
  const [tab, setTab] = useState(searchParams.get("tab") || "flow");

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((err: unknown) => setError((err as Error).message));
  }, []);

  useEffect(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (project) next.set("project", project);
      else next.delete("project");
      next.set("tab", tab);
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project, tab]);

  // output_dir es la carpeta real "imagen/" del proyecto en disco -- la resuelve
  // el backend (project_service.get_project_content -> debug.img_dir), igual que
  // hacia el launcher.py original (flowResolveOutputDir / gtStart / mntGenerar).
  // Nunca se adivina como string ni la escribe el usuario.
  const [resolvedOutputDir, setResolvedOutputDir] = useState("");
  const [resolvingDir, setResolvingDir] = useState(false);

  useEffect(() => {
    if (!project) {
      setResolvedOutputDir("");
      return;
    }
    setResolvingDir(true);
    getProjectContent(project)
      .then((data) => setResolvedOutputDir(data.debug?.img_dir || ""))
      .catch(() => setResolvedOutputDir(""))
      .finally(() => setResolvingDir(false));
  }, [project]);

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] px-4 py-3">
        <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
          {t("tools.project")}
        </span>
        <Select
          value={project}
          onChange={(v) => setProject(v)}
          className="min-w-[200px] rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-3 py-1.5 font-mono text-xs text-[var(--vf-text)] outline-none"
        >
          <SelectOption value="">{t("tools.noProjectSelected")}</SelectOption>
          {projects.map((p) => (
            <SelectOption key={p.nombre} value={p.nombre}>
              {p.nombre}
            </SelectOption>
          ))}
        </Select>
        {error && <span className="text-xs text-[var(--vf-danger)]">{error}</span>}
      </div>

      <div className="mb-2 inline-flex rounded-full border border-[var(--vf-border)] bg-[var(--vf-surface)] p-1 font-mono text-xs">
        {TABS.map((tabItem) => (
          <button
            key={tabItem.id}
            onClick={() => setTab(tabItem.id)}
            className={
              "rounded-full px-4 py-1.5 transition-colors " +
              (tab === tabItem.id
                ? "bg-[var(--vf-c1)] text-white"
                : "text-[var(--vf-muted)] hover:text-[var(--vf-text)]")
            }
          >
            {tabItem.label}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {tab === "flow" && (
          <FlowPanel project={project} outputDir={resolvedOutputDir} resolvingDir={resolvingDir} />
        )}
        {tab === "gentube" && (
          <GentubePanel project={project} outputDir={resolvedOutputDir} resolvingDir={resolvingDir} />
        )}
      </div>
    </div>
  );
}
