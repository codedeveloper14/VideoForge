import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Project } from "../../types";
import { loadScript, loadAudio, audioFileUrl } from "../../api/script";
import { uploadProjectImage, uploadProjectVideo } from "../../api/projects";
import { Select, SelectOption } from "../../components/Select";
import AssetGallery from "./AssetGallery";
import type { AssetSelection } from "./AssetGallery";
import { AssetUploadZone } from "./AssetUploadZone";
import { Card, DropZone, RENDER_MODES, WizardPageHeader, formatSize } from "./wizardShared";

export interface ImageEntry {
  file: File;
  url: string;
}

export type RenderModeValue = "images" | "smart" | "videos";

interface Step1FilesProps {
  projects: Project[];
  project: string;
  onProjectChange: (name: string) => void;
  /** Hide the inline project picker when a project was already selected via a workspace tab. */
  hideProjectPicker?: boolean;

  renderMode: RenderModeValue;
  onRenderModeChange: (mode: RenderModeValue) => void;

  useProjectAudio: boolean;
  onUseProjectAudioChange: (v: boolean) => void;
  audioFile: File | null;
  onAudioFileChange: (f: File | null) => void;
  /** Nombre del audio del proyecto elegido explicitamente (entre varios generados en Paso 3). */
  audioFilename: string;
  onAudioFilenameChange: (name: string) => void;

  images: ImageEntry[];
  onImagesChange: (images: ImageEntry[]) => void;

  /** Seleccion activa de imagenes/videos del proyecto para el render (panel de assets). */
  onAssetSelectionChange: (selection: AssetSelection) => void;

  useProjectScript: boolean;
  onUseProjectScriptChange: (v: boolean) => void;
  guion: string;
  onGuionChange: (v: string) => void;

  error: string;
  onContinue: () => void;
}

export default function Step1Files({
  projects,
  project,
  onProjectChange,
  hideProjectPicker,
  renderMode,
  onRenderModeChange,
  useProjectAudio,
  onUseProjectAudioChange,
  audioFile,
  onAudioFileChange,
  audioFilename,
  onAudioFilenameChange,
  images,
  onImagesChange,
  onAssetSelectionChange,
  useProjectScript,
  onUseProjectScriptChange,
  guion,
  onGuionChange,
  error,
  onContinue,
}: Step1FilesProps) {
  const { t } = useTranslation();
  const [scriptLoaded, setScriptLoaded] = useState(false);
  // "images" tambien opera sobre el proyecto activo cuando hay uno seleccionado
  // (arrastrado desde el stepper o elegido en el picker de abajo) -- solo cae al
  // flujo de quick-render (subida manual, sin proyecto) si de verdad no hay proyecto.
  const usesProject = renderMode !== "images" || !!project;

  const [uploadingImage, setUploadingImage] = useState(false);
  const [uploadingVideo, setUploadingVideo] = useState(false);
  const [imageUploadMsg, setImageUploadMsg] = useState<{ type: "ok" | "error"; text: string } | null>(null);
  const [videoUploadMsg, setVideoUploadMsg] = useState<{ type: "ok" | "error"; text: string } | null>(null);
  const [galleryRefresh, setGalleryRefresh] = useState(0);
  const [projectAudioFiles, setProjectAudioFiles] = useState<string[]>([]);
  const [loadingAudio, setLoadingAudio] = useState(false);

  useEffect(() => {
    if (!project) return;
    loadScript(project)
      .then((data) => {
        if (data?.existe) {
          onGuionChange(data.texto || "");
          setScriptLoaded(true);
        } else {
          setScriptLoaded(false);
        }
      })
      .catch(() => setScriptLoaded(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  // Lista TODOS los audios generados en el proyecto (Paso 3 de voz, o subidos a
  // mano a jobs/<project>/audio) -- antes el render solo veia "el" audio del
  // proyecto (el backend elegia uno por su cuenta). "principal" es el mas
  // reciente por mtime; se preselecciona pero el usuario puede cambiarlo.
  useEffect(() => {
    if (!project) {
      setProjectAudioFiles([]);
      return;
    }
    let cancelled = false;
    setLoadingAudio(true);
    loadAudio(project)
      .then((data) => {
        if (cancelled) return;
        const archivos = data.archivos || [];
        setProjectAudioFiles(archivos);
        if (archivos.length && (!audioFilename || !archivos.includes(audioFilename))) {
          onAudioFilenameChange(data.principal || archivos[0]);
        }
      })
      .catch(() => {
        if (!cancelled) setProjectAudioFiles([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingAudio(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project, galleryRefresh]);

  function addImages(files: File[]) {
    onImagesChange([...images, ...files.map((file) => ({ file, url: URL.createObjectURL(file) }))]);
  }

  function moveImage(index: number, dir: number) {
    const next = [...images];
    const target = index + dir;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onImagesChange(next);
  }

  function removeImage(index: number) {
    onImagesChange(images.filter((_, i) => i !== index));
  }

  async function handleUploadProjectImages(files: File[]) {
    setUploadingImage(true);
    setImageUploadMsg(null);
    try {
      for (const f of files) {
        await uploadProjectImage(project, f);
      }
      setImageUploadMsg({ type: "ok", text: t("projectRenderPanel.uploadedOk", { count: files.length }) });
      setGalleryRefresh((n) => n + 1);
    } catch (err) {
      setImageUploadMsg({ type: "error", text: (err as Error).message });
    } finally {
      setUploadingImage(false);
    }
  }

  async function handleUploadProjectVideos(files: File[]) {
    setUploadingVideo(true);
    setVideoUploadMsg(null);
    try {
      for (const f of files) {
        await uploadProjectVideo(project, f);
      }
      setVideoUploadMsg({ type: "ok", text: t("projectRenderPanel.uploadedOk", { count: files.length }) });
      setGalleryRefresh((n) => n + 1);
    } catch (err) {
      setVideoUploadMsg({ type: "error", text: (err as Error).message });
    } finally {
      setUploadingVideo(false);
    }
  }

  const lineCount = guion.split("\n").filter((l) => l.trim()).length;

  const canContinue = usesProject ? !!project : audioFile && (renderMode !== "images" || images.length > 0);

  return (
    <div>
      <WizardPageHeader title={t("projectRenderPanel.wizardStep1Title")} sub={t("projectRenderPanel.wizardStep1Sub")} />

      {/* Modo de Renderizado */}
      <Card icon="⚙️" iconBg="rgba(56,189,248,.12)" title={t("projectRenderPanel.renderModeTitleCased")} sub={t("projectRenderPanel.renderModeSub")} full>
        <div className="flex flex-wrap gap-2.5">
          {RENDER_MODES.map((m) => (
            <label
              key={m.value}
              className={`flex cursor-pointer items-center gap-2 rounded-[10px] border-[1.5px] px-4 py-2.5 text-[13px] transition-colors ${
                renderMode === m.value
                  ? "border-[var(--vf-accent)] bg-[var(--vf-accent)]/10 font-semibold"
                  : "border-[var(--vf-b2)] bg-[var(--vf-p)]"
              }`}
            >
              <input
                type="radio"
                name="renderMode"
                value={m.value}
                checked={renderMode === m.value}
                onChange={() => onRenderModeChange(m.value as RenderModeValue)}
                className="accent-[var(--vf-accent)]"
              />
              {m.icon} {t(m.labelKey)}
              {m.descKey && <small className="ml-1 text-[var(--vf-muted)]">({t(m.descKey)})</small>}
            </label>
          ))}
        </div>

        {usesProject && (
          <div className="mt-4">
            {hideProjectPicker ? (
              <div className="mb-2.5 flex flex-wrap items-center gap-2">
                <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                  {t("projectRenderPanel.activeProject")}
                </span>
                <span className="rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-p)] px-3 py-2 font-mono text-xs text-[var(--vf-text)]">
                  {project}
                </span>
              </div>
            ) : (
              <div className="mb-2.5 flex flex-wrap items-center gap-2">
                <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                  {t("projectRenderPanel.activeProject")}
                </span>
                <Select
                  value={project}
                  onChange={onProjectChange}
                  className="rounded-lg border border-[var(--vf-b2)] bg-[var(--vf-p)] p-2 font-mono text-xs text-[var(--vf-text)]"
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
            {!project && (
              <p className="rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),.05)] p-3 text-sm text-[var(--vf-muted)]">
                {t("projectRenderPanel.selectProjectToContinue")}
              </p>
            )}
          </div>
        )}
      </Card>

      {usesProject && project && (
        <div className="mt-4">
          <AssetGallery
            project={project}
            renderMode={renderMode}
            refreshToken={galleryRefresh}
            onSelectionChange={onAssetSelectionChange}
          />
        </div>
      )}

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {/* Audio */}
        <Card icon="🎵" iconBg="rgba(124,106,255,.15)" title={t("projectRenderPanel.audioTitle")} sub="mp3, wav, m4a">
          {usesProject && (
            <label className="mb-2.5 flex items-center gap-2 font-mono text-[11px] text-[var(--vf-muted)]">
              <input
                type="checkbox"
                checked={useProjectAudio}
                onChange={(e) => onUseProjectAudioChange(e.target.checked)}
                className="h-3.5 w-3.5 accent-[var(--vf-accent)]"
              />
              {t("projectRenderPanel.useProjectAudio")}
            </label>
          )}
          {usesProject && useProjectAudio && (
            <>
              {loadingAudio && (
                <p className="font-mono text-xs text-[var(--vf-muted)]">{t("projectRenderPanel.galleryLoading")}</p>
              )}
              {!loadingAudio && projectAudioFiles.length === 0 && (
                <p className="rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),.05)] p-3 text-xs text-[var(--vf-muted)]">
                  {t("projectRenderPanel.audioNoneInProject")}
                </p>
              )}
              {!loadingAudio && projectAudioFiles.length > 0 && (
                <ul className="flex max-h-56 flex-col gap-1.5 overflow-y-auto pr-1">
                  {projectAudioFiles.map((name) => (
                    <li
                      key={name}
                      className={`flex items-center gap-2 rounded-lg border p-1.5 transition-colors ${
                        audioFilename === name
                          ? "border-[var(--vf-accent)] bg-[var(--vf-accent)]/10"
                          : "border-[var(--vf-border)] bg-black/20"
                      }`}
                    >
                      <label className="flex flex-1 cursor-pointer items-center gap-2 overflow-hidden">
                        <input
                          type="radio"
                          name="projectAudioFile"
                          checked={audioFilename === name}
                          onChange={() => onAudioFilenameChange(name)}
                          className="accent-[var(--vf-accent)]"
                        />
                        <span className="truncate text-[11px] text-[var(--vf-text)]" title={name}>
                          {name}
                        </span>
                      </label>
                      <audio src={audioFileUrl(project, name)} controls preload="none" className="h-6 w-28" />
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
          {!(usesProject && useProjectAudio) && (
            <>
              {!audioFile ? (
                <DropZone
                  icon="🎙️"
                  label={
                    <>
                      <strong className="text-[var(--vf-c2)]">{t("projectRenderPanel.clickOrDrag")}</strong> {t("projectRenderPanel.yourAudio")}
                    </>
                  }
                  hint={t("projectRenderPanel.audioFormats") || ""}
                  accept=".mp3,.wav,.m4a,.ogg,.aac"
                  onFiles={(files) => onAudioFileChange(files[0])}
                />
              ) : (
                <div className="flex items-center gap-2.5 rounded-[10px] bg-[var(--vf-p)] p-2.5">
                  <span className="text-lg">🎵</span>
                  <div className="flex-1 overflow-hidden">
                    <div className="truncate text-[13px] font-semibold text-[var(--vf-text)]">{audioFile.name}</div>
                    <div className="font-mono text-[11px] text-[var(--vf-muted)]">{formatSize(audioFile.size)}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onAudioFileChange(null)}
                    className="text-base text-[var(--vf-m2)] transition-colors hover:text-[var(--vf-danger)]"
                  >
                    ✕
                  </button>
                </div>
              )}
            </>
          )}
        </Card>

        {/* Imagenes / Videos -- en flujo de proyecto la zona de subida es especifica
            del tipo que necesita el modo activo (nunca la generica de imagenes para
            un modo de solo-video); en quick-render (sin proyecto) se mantiene la
            subida manual de imagenes de siempre. */}
        {usesProject && project ? (
          <>
            {(renderMode === "images" || renderMode === "smart") && (
              <Card
                icon="🖼️"
                iconBg="rgba(251,191,36,.12)"
                title={t("projectRenderPanel.uploadImageTitle")}
                sub={t("projectRenderPanel.imagesFormats") || ""}
              >
                <AssetUploadZone
                  icon="📸"
                  label={
                    <>
                      <strong className="text-[var(--vf-c2)]">{t("projectRenderPanel.clickOrDrag")}</strong>{" "}
                      {t("projectRenderPanel.theImages")}
                    </>
                  }
                  hint={t("projectRenderPanel.selectMultipleAtOnce") || ""}
                  accept={["jpg", "jpeg", "png", "webp", "gif", "bmp"]}
                  wrongTypeMessage={t("projectRenderPanel.mustBeImage")}
                  fetchErrorMessage={t("projectRenderPanel.dragFetchError")}
                  multiple
                  uploading={uploadingImage}
                  onFiles={handleUploadProjectImages}
                />
                {imageUploadMsg && (
                  <p
                    className={`mt-2 text-xs ${imageUploadMsg.type === "ok" ? "text-[var(--vf-success)]" : "text-[var(--vf-danger)]"}`}
                  >
                    {imageUploadMsg.text}
                  </p>
                )}
              </Card>
            )}
            {(renderMode === "videos" || renderMode === "smart") && (
              <Card
                icon="🎬"
                iconBg="rgba(34,211,160,.12)"
                title={t("projectRenderPanel.uploadVideoTitle")}
                sub={t("projectRenderPanel.videosFormats") || ""}
              >
                <AssetUploadZone
                  icon="🎞️"
                  label={
                    <>
                      <strong className="text-[var(--vf-c2)]">{t("projectRenderPanel.clickOrDrag")}</strong>{" "}
                      {t("projectRenderPanel.theVideos")}
                    </>
                  }
                  hint={t("projectRenderPanel.videosHint") || ""}
                  accept={["mp4"]}
                  wrongTypeMessage={t("projectRenderPanel.mustBeVideo")}
                  fetchErrorMessage={t("projectRenderPanel.dragFetchError")}
                  multiple
                  uploading={uploadingVideo}
                  onFiles={handleUploadProjectVideos}
                />
                {videoUploadMsg && (
                  <p
                    className={`mt-2 text-xs ${videoUploadMsg.type === "ok" ? "text-[var(--vf-success)]" : "text-[var(--vf-danger)]"}`}
                  >
                    {videoUploadMsg.text}
                  </p>
                )}
              </Card>
            )}
          </>
        ) : (
          <Card icon="🖼️" iconBg="rgba(251,191,36,.12)" title={t("projectRenderPanel.imagesCountTitle", { count: images.length })} sub={t("projectRenderPanel.imagesFormats") || ""}>
            <DropZone
              icon="📸"
              label={
                <>
                  <strong className="text-[var(--vf-c2)]">{t("projectRenderPanel.clickOrDrag")}</strong> {t("projectRenderPanel.theImages")}
                </>
              }
              hint={t("projectRenderPanel.selectMultipleAtOnce") || ""}
              accept=".jpg,.jpeg,.png,.webp"
              multiple
              onFiles={addImages}
            />
            {images.length > 0 && (
              <>
                <p className="mt-2 font-mono text-xs text-[var(--vf-success)]">
                  {t("videoShared.imageLoadedCount", { count: images.length })}
                </p>
                <ul className="mt-2 flex max-h-56 flex-col gap-1.5 overflow-y-auto pr-1">
                  {images.map((img, i) => (
                    <li
                      key={img.url}
                      className="flex items-center gap-2 rounded-lg border border-[var(--vf-border)] bg-black/20 p-1.5"
                    >
                      <img src={img.url} alt="" className="h-9 w-9 rounded object-cover" />
                      <span className="flex-1 truncate text-[11px] text-[var(--vf-muted)]">
                        {i + 1}. {img.file.name}
                      </span>
                      <button
                        type="button"
                        onClick={() => moveImage(i, -1)}
                        disabled={i === 0}
                        className="rounded border border-[var(--vf-b2)] px-1.5 py-0.5 text-[11px] text-[var(--vf-muted)] disabled:opacity-30"
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        onClick={() => moveImage(i, 1)}
                        disabled={i === images.length - 1}
                        className="rounded border border-[var(--vf-b2)] px-1.5 py-0.5 text-[11px] text-[var(--vf-muted)] disabled:opacity-30"
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        onClick={() => removeImage(i)}
                        className="rounded border border-[var(--vf-danger)]/40 px-1.5 py-0.5 text-[11px] text-[var(--vf-danger)]"
                      >
                        ✕
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Card>
        )}

        {/* Guion */}
        <Card icon="📄" iconBg="rgba(34,211,160,.12)" title={t("projectRenderPanel.scriptTitle")} sub={t("projectRenderPanel.scriptSub")} full>
          {usesProject && (
            <label className="mb-2.5 flex items-center gap-2 font-mono text-[11px] text-[var(--vf-muted)]">
              <input
                type="checkbox"
                checked={useProjectScript}
                onChange={(e) => onUseProjectScriptChange(e.target.checked)}
                className="h-3.5 w-3.5 accent-[var(--vf-accent)]"
              />
              {t("projectRenderPanel.useProjectScript")}
              {scriptLoaded && <span className="text-[var(--vf-success)]">{t("projectRenderPanel.scriptLoadedCheck")}</span>}
            </label>
          )}
          {!(usesProject && useProjectScript) && (
            <>
              <textarea
                value={guion}
                onChange={(e) => onGuionChange(e.target.value)}
                rows={6}
                placeholder={t("projectRenderPanel.wizardScriptPlaceholder") || ""}
                className="w-full rounded-[10px] border border-[var(--vf-b2)] bg-[var(--vf-p)] p-3 font-mono text-[13px] leading-relaxed text-[var(--vf-text)] outline-none transition-colors focus:border-[var(--vf-accent)]"
              />
              <p className="mt-1.5 text-right font-mono text-[11px] text-[var(--vf-m2)]">
                {t("projectRenderPanel.charsAndLines", { count: guion.length.toLocaleString(), lines: lineCount })}
              </p>
            </>
          )}
        </Card>
      </div>

      {error && <p className="mt-4 text-sm text-[var(--vf-danger)]">{error}</p>}

      <div className="mt-6 flex gap-3">
        <button
          type="button"
          disabled={!canContinue}
          onClick={onContinue}
          className="flex-1 rounded-xl px-4 py-4 text-base font-bold text-white shadow-[0_4px_20px_rgba(124,106,255,.3)] transition-all hover:-translate-y-px hover:shadow-[0_8px_30px_rgba(124,106,255,.45)] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 disabled:hover:shadow-none"
          style={{ background: "linear-gradient(135deg, var(--vf-accent), #9f7aea)" }}
        >
          {t("projectRenderPanel.continueToEffects")}
        </button>
      </div>
    </div>
  );
}
