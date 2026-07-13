import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getProjectContent } from "../api/projects";
import { PipelineStepper } from "../components/PipelineStepper";
import FlowPanel from "./imagen/FlowPanel";
import GentubePanel from "./imagen/GentubePanel";

const TABS = [
  { id: "flow", label: "Flow" },
  {
    id: "gentube",
    label: "GenTube",
    badge: { text: "Chromium", color: "#22c55e", bg: "rgba(34,197,94,.15)", border: "rgba(34,197,94,.3)" },
  },
];

export default function ImagenPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [project, setProject] = useState(searchParams.get("project") || "");
  const [tab, setTab] = useState(searchParams.get("tab") || "flow");

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

  // The project is now selected exclusively via the workspace tabs/sidebar in
  // AppLayout, which navigate with a new ?project= value — keep local state
  // in sync when that happens.
  useEffect(() => {
    const fromUrl = searchParams.get("project") || "";
    setProject((prev) => (fromUrl && fromUrl !== prev ? fromUrl : prev));
  }, [searchParams]);

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
      {project && <PipelineStepper project={project} current="imagen" />}

      <div className="mb-2 inline-flex items-center gap-0.5 rounded-full border border-[var(--vf-border)] bg-[var(--vf-surface)] p-1 font-mono text-xs">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={
              "flex items-center gap-1.5 rounded-full px-4 py-1.5 transition-colors " +
              (tab === t.id
                ? "bg-[var(--vf-c1)] text-white"
                : "text-[var(--vf-muted)] hover:text-[var(--vf-text)]")
            }
          >
            {t.label}
            {t.badge && (
              <span
                className="rounded-full border px-1.5 py-[1px] font-mono text-[8px] font-semibold uppercase tracking-wider"
                style={{
                  background: t.badge.bg,
                  color: t.badge.color,
                  borderColor: t.badge.border,
                }}
              >
                {t.badge.text}
              </span>
            )}
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
