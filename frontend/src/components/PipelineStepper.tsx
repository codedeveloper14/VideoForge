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
    <div className="-mx-8 mb-9 bg-[#07070e] px-8 pt-2" style={{ borderBottom: "1px solid rgba(255,255,255,.05)" }}>
      <div className="mb-3.5 font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-[#4a4a63]">
        Paso {currentIndex + 1} de {STEPS.length}
      </div>
      <div
        className="flex items-center gap-1 overflow-x-auto"
        style={{ borderBottom: "1px solid rgba(255,255,255,.08)", scrollbarWidth: "none" }}
      >
        {STEPS.map((step, i) => {
          const isActive = step.page === current;
          return (
            <button
              key={step.page}
              type="button"
              onClick={() => navigate(`/app/${step.page}?project=${encodeURIComponent(project)}`)}
              className={
                "flex flex-shrink-0 items-center gap-2 whitespace-nowrap border-b-2 px-3.5 py-2.5 font-mono text-[11.5px] font-medium transition-colors " +
                (isActive
                  ? "border-[var(--vf-c1)] text-[var(--vf-text)]"
                  : "border-transparent text-[var(--vf-muted)] hover:text-[var(--vf-text)]")
              }
            >
              <span
                className={
                  "flex h-[18px] w-[18px] flex-shrink-0 items-center justify-center rounded-full border text-[10px] font-bold " +
                  (isActive
                    ? "border-[var(--vf-c1)]/40 bg-[var(--vf-c1)]/25 text-[var(--vf-c1)]"
                    : "border-[rgba(255,255,255,.1)] bg-white/[0.05] text-[var(--vf-muted)]")
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
