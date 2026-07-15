// Shared in-page pipeline stepper shown at the top of each pipeline page's content
// once a project is active (ported from the legacy .vf-pg-nav / .vf-ptabs markup).
import { useNavigate } from "react-router-dom";
import type { PipelinePage } from "../context/WorkspaceContext";

const STEPS: { page: PipelinePage; label: string }[] = [
  { page: "guion", label: "Guión escrito" },
  { page: "imagen", label: "Generación de imágenes" },
  { page: "voz", label: "Generación de voz" },
  { page: "video", label: "Generación de video" },
  { page: "render", label: "Renderizado" },
];

interface PipelineStepperProps {
  project: string;
  current: PipelinePage;
}

export function PipelineStepper({ project, current }: PipelineStepperProps) {
  const navigate = useNavigate();
  const currentIndex = STEPS.findIndex((s) => s.page === current);

  return (
    <div
      className="-mx-8 sticky top-0 z-10 mb-9 flex items-center gap-0 px-4 py-2.5 backdrop-blur-[10px]"
      style={{ background: "rgba(var(--vf-bg-rgb),.6)", borderBottom: "1px solid rgba(124,106,255,.1)" }}
    >
      <div className="mr-4 flex-shrink-0 whitespace-nowrap font-mono text-[8.5px] uppercase tracking-[0.18em]" style={{ color: "rgba(124,106,255,.45)" }}>
        Paso {currentIndex + 1} de {STEPS.length}
      </div>
      <div className="flex min-w-0 flex-1 items-center overflow-x-auto" style={{ scrollbarWidth: "none" }}>
        {STEPS.map((step, i) => {
          const isActive = step.page === current;
          const isLast = i === STEPS.length - 1;
          return (
            <button
              key={step.page}
              type="button"
              onClick={() => navigate(`/app/${step.page}?project=${encodeURIComponent(project)}`)}
              className={
                "relative flex min-w-0 flex-1 items-center gap-1.5 whitespace-nowrap rounded-full py-[3px] pl-1 pr-2.5 text-[10.5px] font-medium transition-opacity " +
                (isActive ? "font-semibold text-[var(--vf-text)] opacity-100" : "text-[var(--vf-text)] opacity-35 hover:opacity-60")
              }
              style={
                isActive
                  ? {
                      background: "rgba(124,106,255,.12)",
                      boxShadow: "0 0 16px rgba(124,106,255,.2)",
                    }
                  : undefined
              }
            >
              {!isLast && (
                <span
                  className="pointer-events-none absolute right-0 top-1/2 h-px w-3.5 -translate-y-1/2"
                  style={{ background: "rgba(124,106,255,.18)" }}
                />
              )}
              <span
                className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full border font-mono text-[9px] font-bold transition-all"
                style={
                  isActive
                    ? {
                        background: "linear-gradient(135deg,#7c6aff,#a855f7)",
                        borderColor: "transparent",
                        color: "#fff",
                        boxShadow: "0 0 8px rgba(124,106,255,.4)",
                      }
                    : {
                        background: "rgba(var(--vf-fg-rgb),.06)",
                        borderColor: "rgba(var(--vf-fg-rgb),.09)",
                        color: "var(--vf-m2)",
                      }
                }
              >
                {i + 1}
              </span>
              {step.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
