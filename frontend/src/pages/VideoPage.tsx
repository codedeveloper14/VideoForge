import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PipelineStepper } from "../components/PipelineStepper";
import { HeaderArt } from "../components/HeaderArt";
import GrokPanel from "./video/GrokPanel";
import QwenPanel from "./video/QwenPanel";
import VibesPanel from "./video/VibesPanel";
import MetaPanel from "./video/MetaPanel";

const TABS = [
  { id: "grok", label: "Grok" },
  { id: "qwen", label: "Qwen" },
  { id: "vibes", label: "Vibes" },
  { id: "meta", label: "Meta" },
];

export default function VideoPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [project, setProject] = useState(searchParams.get("project") || "");
  const [tab, setTab] = useState(searchParams.get("tab") || "grok");

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

  return (
    <div>
      {project && <PipelineStepper project={project} current="video" />}

      <div
        className="relative mb-9 overflow-hidden rounded-2xl border border-[rgba(124,106,255,.15)] p-5"
        style={{ background: "var(--vf-surface)" }}
      >
        <div className="flex items-center gap-5">
          <div className="min-w-0 max-w-2xl flex-1">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),.03)] px-3 py-1 font-mono text-[9.5px] uppercase tracking-widest text-[var(--vf-muted)]">
              <span
                className="h-[5px] w-[5px] rounded-full"
                style={{ background: "var(--vf-c5)", boxShadow: "0 0 6px var(--vf-c5)" }}
              />
              {t("videoTool.moduleLabel")}
            </div>
            <h1 className="mb-3 text-3xl font-extrabold tracking-tight sm:text-4xl">
              {t("videoTool.titlePart1")}{" "}
              <span
                className="bg-clip-text text-transparent"
                style={{
                  backgroundImage:
                    "linear-gradient(110deg, var(--vf-c2) 0%, var(--vf-c1) 40%, var(--vf-c3) 85%)",
                }}
              >
                {t("videoTool.titlePart2")}
              </span>
            </h1>
            <p className="font-mono text-[12.5px] leading-relaxed text-[var(--vf-muted)]">
              {t("videoTool.subtitle")}
            </p>
          </div>
          <HeaderArt />
        </div>
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
        {tab === "vibes" && <VibesPanel project={project} />}
        {tab === "meta" && <MetaPanel project={project} />}
      </div>
    </div>
  );
}
