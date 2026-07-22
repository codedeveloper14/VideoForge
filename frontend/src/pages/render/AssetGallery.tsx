// Panel de seleccion de assets del Paso 5 -- lee jobs/<project>/imagen y
// jobs/<project>/video de forma dinamica via getProjectContent(), igual que ya
// hacen las galerias de Paso 2/4. Arranca sin nada seleccionado: el usuario
// debe marcar (o arrastrar) explicitamente lo que quiere incluir en el render
// (ver onSelectionChange, consumido en RenderPage.tsx para armar
// image_filenames / video_filenames del payload).
import { useEffect, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { getProjectContent, imagenFileUrl, videoFileUrl } from "../../api/projects";
import type { ProjectScene } from "../../api/projects";
import { Card } from "./wizardShared";
import type { RenderModeValue } from "./Step1Files";

export interface AssetSelection {
  images: string[];
  videos: string[];
}

interface AssetGalleryProps {
  project: string;
  renderMode: RenderModeValue;
  /** Se incrementa despues de una subida manual para forzar un refetch. */
  refreshToken?: number;
  onSelectionChange?: (selection: AssetSelection) => void;
}

function AssetCard({
  scene,
  project,
  kind,
  selected,
  onToggle,
}: {
  scene: ProjectScene;
  project: string;
  kind: "image" | "video";
  selected: boolean;
  onToggle: () => void;
}) {
  const filename = (kind === "video" ? scene.video : scene.image) as string;
  const url = kind === "video" ? videoFileUrl(project, filename) : imagenFileUrl(project, filename);

  // Un <img> es arrastrable por defecto en el navegador; un <video> NO lo es --
  // por eso ambos declaran draggable + onDragStart explicitamente aca, con el
  // mismo mecanismo (text/uri-list + nombre de archivo), para que arrastrar una
  // tarjeta de video hacia la zona de subida funcione igual que con imagenes.
  function handleDragStart(e: DragEvent<HTMLElement>) {
    e.dataTransfer.setData("text/uri-list", url);
    e.dataTransfer.setData("text/plain", url);
    e.dataTransfer.setData("application/x-vf-filename", filename);
    e.dataTransfer.effectAllowed = "copy";
  }

  return (
    <div
      className={`overflow-hidden rounded-lg border-2 bg-[var(--vf-surface)] transition-all ${
        selected ? "border-[var(--vf-accent)]" : "border-[var(--vf-border)] opacity-45"
      }`}
    >
      <div className="relative aspect-video bg-black/20">
        <label
          className="absolute left-1 top-1 z-10 flex h-5 w-5 cursor-pointer items-center justify-center rounded border border-white/40 bg-black/70"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
        >
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            className="h-3.5 w-3.5 accent-[var(--vf-accent)]"
          />
        </label>
        {kind === "video" ? (
          <video
            src={url}
            className="h-full w-full cursor-grab object-cover active:cursor-grabbing"
            muted
            loop
            playsInline
            preload="metadata"
            draggable
            onDragStart={handleDragStart}
          />
        ) : (
          <img
            src={url}
            alt={scene.index}
            className="h-full w-full cursor-grab object-cover active:cursor-grabbing"
            draggable
            onDragStart={handleDragStart}
          />
        )}
      </div>
      <div className="truncate px-1.5 py-1 font-mono text-[9px] text-[var(--vf-muted)]" title={scene.index}>
        {scene.index}
      </div>
    </div>
  );
}

function AssetGrid({
  scenes,
  project,
  kind,
  selected,
  onToggle,
}: {
  scenes: ProjectScene[];
  project: string;
  kind: "image" | "video";
  selected: Set<string>;
  onToggle: (filename: string) => void;
}) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-2.5">
      {scenes.map((scene) => {
        const filename = (kind === "video" ? scene.video : scene.image) as string;
        return (
          <AssetCard
            key={`${kind}-${scene.index}`}
            scene={scene}
            project={project}
            kind={kind}
            selected={selected.has(filename)}
            onToggle={() => onToggle(filename)}
          />
        );
      })}
    </div>
  );
}

function SelectionBar({
  selectedCount,
  total,
  onSelectAll,
  onSelectNone,
}: {
  selectedCount: number;
  total: number;
  onSelectAll: () => void;
  onSelectNone: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 font-mono text-[10px] text-[var(--vf-muted)]">
      <span>{t("projectRenderPanel.gallerySelectedCount", { selected: selectedCount, total })}</span>
      <button
        type="button"
        onClick={onSelectAll}
        className="rounded border border-[var(--vf-b2)] px-1.5 py-0.5 text-[var(--vf-muted)] transition-colors hover:border-[var(--vf-accent)] hover:text-[var(--vf-text)]"
      >
        {t("projectRenderPanel.gallerySelectAll")}
      </button>
      <button
        type="button"
        onClick={onSelectNone}
        className="rounded border border-[var(--vf-b2)] px-1.5 py-0.5 text-[var(--vf-muted)] transition-colors hover:border-[var(--vf-danger)] hover:text-[var(--vf-danger)]"
      >
        {t("projectRenderPanel.gallerySelectNone")}
      </button>
    </div>
  );
}

export default function AssetGallery({ project, renderMode, refreshToken, onSelectionChange }: AssetGalleryProps) {
  const { t } = useTranslation();
  const [scenes, setScenes] = useState<ProjectScene[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedImages, setSelectedImages] = useState<Set<string>>(new Set());
  const [selectedVideos, setSelectedVideos] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!project) {
      setScenes([]);
      setSelectedImages(new Set());
      setSelectedVideos(new Set());
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    getProjectContent(project)
      .then((data) => {
        if (cancelled) return;
        const loaded = data.scenes || [];
        setScenes(loaded);
        // Arranca vacio: el usuario elige explicitamente que incluir.
        setSelectedImages(new Set());
        setSelectedVideos(new Set());
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project, refreshToken]);

  useEffect(() => {
    onSelectionChange?.({ images: Array.from(selectedImages), videos: Array.from(selectedVideos) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedImages, selectedVideos]);

  if (!project) return null;

  const imageScenes = scenes.filter((s) => !!s.image);
  const videoScenes = scenes.filter((s) => !!s.video);
  const count =
    renderMode === "images" ? imageScenes.length : renderMode === "videos" ? videoScenes.length : scenes.length;

  const subKey =
    renderMode === "images"
      ? "projectRenderPanel.gallerySubImages"
      : renderMode === "videos"
        ? "projectRenderPanel.gallerySubVideos"
        : "projectRenderPanel.gallerySubSmart";

  const emptyKey =
    renderMode === "images"
      ? "projectRenderPanel.galleryEmptyImages"
      : renderMode === "videos"
        ? "projectRenderPanel.galleryEmptyVideos"
        : "projectRenderPanel.galleryEmptySmart";

  const nothingToShow =
    (renderMode === "images" && imageScenes.length === 0) ||
    (renderMode === "videos" && videoScenes.length === 0) ||
    (renderMode === "smart" && imageScenes.length === 0 && videoScenes.length === 0);

  function toggleImage(filename: string) {
    setSelectedImages((prev) => {
      const next = new Set(prev);
      if (next.has(filename)) next.delete(filename);
      else next.add(filename);
      return next;
    });
  }
  function toggleVideo(filename: string) {
    setSelectedVideos((prev) => {
      const next = new Set(prev);
      if (next.has(filename)) next.delete(filename);
      else next.add(filename);
      return next;
    });
  }

  return (
    <Card
      icon="🗂️"
      iconBg="rgba(34,211,160,.12)"
      title={t("projectRenderPanel.galleryTitle", { count })}
      sub={t(subKey) || ""}
      full
    >
      {loading && (
        <p className="py-6 text-center font-mono text-xs text-[var(--vf-muted)]">
          {t("projectRenderPanel.galleryLoading")}
        </p>
      )}
      {!loading && error && <p className="py-6 text-center text-xs text-[var(--vf-danger)]">{error}</p>}
      {!loading && !error && nothingToShow && (
        <p className="py-6 text-center font-mono text-xs text-[var(--vf-m2)]">{t(emptyKey)}</p>
      )}
      {!loading && !error && !nothingToShow && renderMode === "images" && (
        <>
          <div className="mb-2.5 flex justify-end">
            <SelectionBar
              selectedCount={selectedImages.size}
              total={imageScenes.length}
              onSelectAll={() => setSelectedImages(new Set(imageScenes.map((s) => s.image as string)))}
              onSelectNone={() => setSelectedImages(new Set())}
            />
          </div>
          <AssetGrid scenes={imageScenes} project={project} kind="image" selected={selectedImages} onToggle={toggleImage} />
        </>
      )}
      {!loading && !error && !nothingToShow && renderMode === "videos" && (
        <>
          <div className="mb-2.5 flex justify-end">
            <SelectionBar
              selectedCount={selectedVideos.size}
              total={videoScenes.length}
              onSelectAll={() => setSelectedVideos(new Set(videoScenes.map((s) => s.video as string)))}
              onSelectNone={() => setSelectedVideos(new Set())}
            />
          </div>
          <AssetGrid scenes={videoScenes} project={project} kind="video" selected={selectedVideos} onToggle={toggleVideo} />
        </>
      )}
      {!loading && !error && !nothingToShow && renderMode === "smart" && (
        <div className="flex flex-col gap-4">
          {imageScenes.length > 0 && (
            <div>
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="font-mono text-[10px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
                  🖼️ {t("projectRenderPanel.galleryImagesSection", { count: imageScenes.length })}
                </div>
                <SelectionBar
                  selectedCount={selectedImages.size}
                  total={imageScenes.length}
                  onSelectAll={() => setSelectedImages(new Set(imageScenes.map((s) => s.image as string)))}
                  onSelectNone={() => setSelectedImages(new Set())}
                />
              </div>
              <AssetGrid scenes={imageScenes} project={project} kind="image" selected={selectedImages} onToggle={toggleImage} />
            </div>
          )}
          {videoScenes.length > 0 && (
            <div>
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="font-mono text-[10px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
                  🎬 {t("projectRenderPanel.galleryVideosSection", { count: videoScenes.length })}
                </div>
                <SelectionBar
                  selectedCount={selectedVideos.size}
                  total={videoScenes.length}
                  onSelectAll={() => setSelectedVideos(new Set(videoScenes.map((s) => s.video as string)))}
                  onSelectNone={() => setSelectedVideos(new Set())}
                />
              </div>
              <AssetGrid scenes={videoScenes} project={project} kind="video" selected={selectedVideos} onToggle={toggleVideo} />
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
