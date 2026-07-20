import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { listProjects } from "../api/projects";
import type { Project } from "../types";
import {
  getRenderDownloadUrl,
  getRenderStatus,
  startRender,
} from "../api/render";
import { getQuickRenderDownloadUrl, startQuickRender } from "../api/quickRender";
import JobsPanel from "./render/JobsPanel";
import Step1Files from "./render/Step1Files";
import type { ImageEntry, RenderModeValue } from "./render/Step1Files";
import Step2Effects from "./render/Step2Effects";
import Step3Render from "./render/Step3Render";
import type { RenderJobState } from "./render/Step3Render";
import { WizardProgress } from "./render/wizardShared";
import { PipelineStepper } from "../components/PipelineStepper";
import { useGenerationStatus } from "../context/GenerationStatusContext";

type WizardStep = 1 | 2 | 3;

export default function RenderPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState(searchParams.get("project") || "");
  const [pageError, setError] = useState("");

  // Whether the page was opened with a project already selected via the
  // workspace tab (i.e. arrived from AppLayout's project tabs/sidebar). In
  // that case Step 1's own project picker is redundant and gets hidden —
  // but a manual/quick-render flow with no ?project= keeps its own picker.
  const arrivedWithProject = useRef(!!searchParams.get("project")).current;

  const [step, setStep] = useState<WizardStep>(1);

  // Step 1 state
  const [renderMode, setRenderMode] = useState<RenderModeValue>("smart");
  const [useProjectAudio, setUseProjectAudio] = useState(true);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [images, setImages] = useState<ImageEntry[]>([]);
  const [useProjectScript, setUseProjectScript] = useState(true);
  const [guion, setGuion] = useState("");
  const [step1Error, setStep1Error] = useState("");

  // Step 2 state
  const [movimiento, setMovimiento] = useState("none");
  const [shake, setShake] = useState(false);
  const [transicion, setTransicion] = useState("none");
  const [transDur, setTransDur] = useState(0.8);
  const [resolucion, setResolucion] = useState("1920x1080");
  const [modelo, setModelo] = useState("base");
  const [whisperBackend, setWhisperBackend] = useState("whisperx");
  const [submitting, setSubmitting] = useState(false);

  // Step 3 state
  const [job, setJob] = useState<RenderJobState | null>(null);
  const [downloadUrl, setDownloadUrl] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const genStatus = useGenerationStatus();
  const genIdRef = useRef("");

  const usesProjectFlow = renderMode !== "images";

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

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function startPolling(jobId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const data = await getRenderStatus(jobId);
        setJob((prev) => ({ ...prev, ...data }));
        genStatus.update(genIdRef.current, {
          pct: typeof data.progreso === "number" ? Math.round(data.progreso) : null,
          message: data.mensaje || "Renderizando...",
        });
        if (data.estado === "completado" || data.estado === "error") {
          if (pollRef.current) clearInterval(pollRef.current);
          genStatus.finish(genIdRef.current, data.estado === "completado", data.mensaje || data.error);
        }
      } catch (err) {
        setJob((prev) => (prev ? { ...prev, estado: "error", error: (err as Error).message } : prev));
        if (pollRef.current) clearInterval(pollRef.current);
        genStatus.finish(genIdRef.current, false, (err as Error).message);
      }
    }, 2000);
  }

  function goToStep1() {
    setStep1Error("");
    if (usesProjectFlow) {
      if (!project) {
        setStep1Error(t("renderTool.selectProjectTopbar"));
        return;
      }
    } else {
      if (!audioFile) {
        setStep1Error(t("renderTool.uploadAudioFile"));
        return;
      }
      if (!images.length) {
        setStep1Error(t("renderTool.uploadAtLeastOneImage"));
        return;
      }
      if (!guion.trim()) {
        setStep1Error(t("renderTool.writeScriptOneLinePerScene"));
        return;
      }
    }
    setStep(2);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function goBackToStep1() {
    setStep(1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function handleGenerate() {
    setSubmitting(true);
    setStep1Error("");
    genIdRef.current = "render:" + (project || "quick");
    genStatus.start(genIdRef.current, "Render", "Iniciando...");
    try {
      if (usesProjectFlow) {
        const data = await startRender({
          project_name: project,
          render_mode: renderMode,
          guion,
          resolucion,
          modelo,
          whisper_backend: whisperBackend,
          transicion,
          trans_dur: transDur,
          movimiento,
          shake,
          audioFile: useProjectAudio ? null : audioFile,
        });
        setDownloadUrl(getRenderDownloadUrl(data.job_id));
        setJob({ id: data.job_id, estado: "procesando", progreso: 0, mensaje: t("renderTool.startingJob") });
        setStep(3);
        window.scrollTo({ top: 0, behavior: "smooth" });
        startPolling(data.job_id);
      } else {
        const data = await startQuickRender({
          guion,
          resolucion,
          fade: 0,
          modelo,
          whisper_backend: whisperBackend,
          transicion,
          movimiento,
          trans_dur: transDur,
          shake,
          audioFile,
          imageFiles: images.map((i) => i.file),
        });
        setDownloadUrl(getQuickRenderDownloadUrl(data.job_id));
        setJob({ id: data.job_id, estado: "procesando", progreso: 0, mensaje: t("renderTool.startingJob") });
        setStep(3);
        window.scrollTo({ top: 0, behavior: "smooth" });
        startPolling(data.job_id);
      }
    } catch (err) {
      const error = err as Error & { limit_reached?: boolean };
      setStep1Error(error.message || t("renderTool.renderStartError"));
      genStatus.finish(genIdRef.current, false, error.message || t("renderTool.renderStartError"));
      setStep(2);
    } finally {
      setSubmitting(false);
    }
  }

  function resetWizard() {
    if (pollRef.current) clearInterval(pollRef.current);
    setJob(null);
    setDownloadUrl("");
    setAudioFile(null);
    setImages([]);
    setGuion("");
    setUseProjectAudio(true);
    setUseProjectScript(true);
    setMovimiento("none");
    setShake(false);
    setTransicion("none");
    setTransDur(0.8);
    setStep1Error("");
    setStep(1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const sceneCount = guion.split("\n").filter((l) => l.trim()).length;

  const motionLabels: Record<string, string> = {
    none: t("projectRenderPanel.motionNone"),
    ken_burns: t("projectRenderPanel.motionKenBurns"),
    zoom_in: t("projectRenderPanel.motionZoomIn"),
    zoom_out: t("projectRenderPanel.motionZoomOut"),
    pan_left: t("renderTool.motionPanLeftArrow"),
    pan_right: t("renderTool.motionPanRightArrow"),
  };
  const transLabels: Record<string, string> = {
    none: t("projectRenderPanel.transitionNone"),
    dissolve: t("renderTool.transitionDissolveShort"),
    slide_left: t("renderTool.transitionSlideLeftArrow"),
    slide_right: t("renderTool.transitionSlideRightArrow"),
    zoom: t("renderTool.transitionZoomShort"),
    fade: t("renderTool.transitionFadeShort"),
  };

  const summaryPills = [
    { label: t("renderTool.pillImages", { count: images.length || 0 }) },
    {
      label: audioFile
        ? `🎵 ${audioFile.name.split(".").pop()?.toUpperCase()}`
        : useProjectAudio
          ? t("renderTool.pillAudioProject")
          : t("renderTool.pillAudioUnknown"),
    },
    { label: t("renderTool.pillScenes", { count: sceneCount }) },
    { label: t("renderTool.pillResolution", { res: resolucion.replace("x", "×") }) },
    { label: t("renderTool.pillMotion", { motion: motionLabels[movimiento] || movimiento }) },
    { label: t("renderTool.pillTransition", { trans: transLabels[transicion] || transicion }) },
    { label: t("renderTool.pillWhisper", { model: modelo }) },
  ];

  return (
    <div>
      {project && <PipelineStepper project={project} current="render" />}

      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="tool-h1 text-2xl font-semibold">{t("renderTool.title")}</h1>
          <p className="mt-1 text-sm text-[var(--vf-muted)]">
            {t("renderTool.subtitle")}
          </p>
        </div>
      </div>

      {pageError && <p className="mb-4 text-sm text-[var(--vf-danger)]">{pageError}</p>}

      <div className="grid gap-6 xl:grid-cols-[1fr_320px] xl:items-start">
        <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-bg,transparent)] p-1">
          <WizardProgress step={step} />

          {step === 1 && (
            <Step1Files
              projects={projects}
              project={project}
              onProjectChange={setProject}
              hideProjectPicker={arrivedWithProject}
              renderMode={renderMode}
              onRenderModeChange={setRenderMode}
              useProjectAudio={useProjectAudio}
              onUseProjectAudioChange={setUseProjectAudio}
              audioFile={audioFile}
              onAudioFileChange={setAudioFile}
              images={images}
              onImagesChange={setImages}
              useProjectScript={useProjectScript}
              onUseProjectScriptChange={setUseProjectScript}
              guion={guion}
              onGuionChange={setGuion}
              error={step1Error}
              onContinue={goToStep1}
            />
          )}

          {step === 2 && (
            <Step2Effects
              movimiento={movimiento}
              onMovimientoChange={setMovimiento}
              shake={shake}
              onShakeChange={setShake}
              transicion={transicion}
              onTransicionChange={setTransicion}
              transDur={transDur}
              onTransDurChange={setTransDur}
              resolucion={resolucion}
              onResolucionChange={setResolucion}
              modelo={modelo}
              onModeloChange={setModelo}
              whisperBackend={whisperBackend}
              onWhisperBackendChange={setWhisperBackend}
              onBack={goBackToStep1}
              onSubmit={handleGenerate}
              submitting={submitting}
            />
          )}

          {step === 3 && (
            <Step3Render
              job={job}
              pills={summaryPills}
              sceneCount={sceneCount}
              downloadUrl={downloadUrl}
              onNewVideo={resetWizard}
            />
          )}

          {step1Error && step === 2 && (
            <p className="mt-4 text-center text-sm text-[var(--vf-danger)]">{step1Error}</p>
          )}
        </div>
        <div className="xl:sticky xl:top-6">
          <JobsPanel />
        </div>
      </div>
    </div>
  );
}
