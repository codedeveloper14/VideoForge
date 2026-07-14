import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { listProjects } from "../api/projects";
import type { Project } from "../types";
import { Select, SelectOption } from "../components/Select";
import GrokPanel from "./video/GrokPanel";
import QwenPanel from "./video/QwenPanel";
import MetaPanel from "./video/MetaPanel";

const TABS = [
  { id: "grok", label: "Grok" },
  { id: "qwen", label: "Qwen" },
  { id: "meta", label: "Meta" },
];

export default function VideoPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState(searchParams.get("project") || "");
  const [error, setError] = useState("");
  const [tab, setTab] = useState(searchParams.get("tab") || "grok");

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
      next.set("tab", tab);
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project, tab]);

  return (
    <div>
      <div className="mb-5">
        <div className="mb-1 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-[var(--vf-m2)]">
          <span
            className="h-[5px] w-[5px] rounded-full"
            style={{ background: "var(--vf-c5)", boxShadow: "0 0 6px var(--vf-c5)" }}
          />
          {t("videoTool.moduleLabel")}
        </div>
        <h1 className="text-3xl font-bold tracking-tight text-[var(--vf-text)] md:text-4xl">
          {t("videoTool.titlePart1")}{" "}
          <span
            style={{
              background:
                "linear-gradient(110deg, var(--vf-c2) 0%, var(--vf-c1) 40%, var(--vf-c3) 85%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            {t("videoTool.titlePart2")}
          </span>
        </h1>
        <p className="mt-2 max-w-xl font-mono text-xs leading-relaxed text-[var(--vf-muted)]">
          {t("videoTool.subtitle")}
        </p>
      </div>

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

      <div className="mb-4 inline-flex rounded-full border border-[var(--vf-border)] bg-[var(--vf-surface)] p-1 font-mono text-xs">
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
        {tab === "grok" && <GrokPanel project={project} />}
        {tab === "qwen" && <QwenPanel project={project} />}
        {tab === "meta" && <MetaPanel project={project} />}
      </div>
    </div>
  );
}
