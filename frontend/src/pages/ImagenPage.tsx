import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { listProjects } from "../api/projects";
import type { Project } from "../types";
import WhiskPanel from "./imagen/WhiskPanel";
import PollinationPanel from "./imagen/PollinationPanel";
import FlowPanel from "./imagen/FlowPanel";
import GentubePanel from "./imagen/GentubePanel";

const TABS = [
  { id: "whisk", label: "Whisk" },
  { id: "pollination", label: "Pollination" },
  { id: "flow", label: "Flow" },
  { id: "gentube", label: "Gentube" },
];

export default function ImagenPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState(searchParams.get("project") || "");
  const [error, setError] = useState("");
  const [tab, setTab] = useState(searchParams.get("tab") || "whisk");

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

  // Default output_dir suggestion: project-scoped "imagen" subfolder.
  const defaultOutputDir = project ? `${project}/imagen` : "";

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] px-4 py-3">
        <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
          Proyecto
        </span>
        <select
          value={project}
          onChange={(e) => setProject(e.target.value)}
          className="min-w-[200px] rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-s)] px-3 py-1.5 font-mono text-xs text-[var(--vf-text)] outline-none"
        >
          <option value="">— Sin proyecto seleccionado —</option>
          {projects.map((p) => (
            <option key={p.nombre} value={p.nombre}>
              {p.nombre}
            </option>
          ))}
        </select>
        {error && <span className="text-xs text-[var(--vf-danger)]">{error}</span>}
      </div>

      <div className="mb-2 inline-flex rounded-full border border-[var(--vf-border)] bg-[var(--vf-surface)] p-1 font-mono text-xs">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={
              "rounded-full px-4 py-1.5 transition-colors " +
              (tab === t.id
                ? "bg-[var(--vf-c1)] text-white"
                : "text-[var(--vf-muted)] hover:text-[var(--vf-text)]")
            }
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {tab === "whisk" && (
          <WhiskPanel project={project} defaultOutputDir={defaultOutputDir} />
        )}
        {tab === "pollination" && (
          <PollinationPanel project={project} defaultOutputDir={defaultOutputDir} />
        )}
        {tab === "flow" && <FlowPanel project={project} defaultOutputDir={defaultOutputDir} />}
        {tab === "gentube" && (
          <GentubePanel project={project} defaultOutputDir={defaultOutputDir} />
        )}
      </div>
    </div>
  );
}
