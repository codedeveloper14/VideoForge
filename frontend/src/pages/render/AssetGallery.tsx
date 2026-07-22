// Vista de confirmacion del contenido que el Modo de Renderizado activo va a usar
// -- lee jobs/<project>/imagen y jobs/<project>/video de forma dinamica via
// getProjectContent(), igual que ya hacen las galerias de Paso 2/4 (solo lectura,
// no altera que archivos usa el render en si -- eso lo decide render_service.py).
import { useEffect, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { getProjectContent, imagenFileUrl, videoFileUrl } from "../../api/projects";
import type { ProjectScene } from "../../api/projects";
import { Card } from "./wizardShared";
import type { RenderModeValue } from "./Step1Files";

interface AssetGalleryProps {
  project: string;
  renderMode: RenderModeValue;
  /** Se incrementa despues de una subida manual para forzar un refetch. */
  refreshToken?: number;
}

function AssetCard({
  scene,
  project,
  kind,
}: {
  scene: ProjectScene;
  project: string;
  kind: "image" | "video";
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
    <div className="overflow-hidden rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface)]">
      <div className="relative aspect-video bg-black/20">
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

function AssetGrid({ scenes, project, kind }: { scenes: ProjectScene[]; project: string; kind: "image" | "video" }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-2.5">
      {scenes.map((scene) => (
        <AssetCard key={`${kind}-${scene.index}`} scene={scene} project={project} kind={kind} />
      ))}
    </div>
  );
}

export default function AssetGallery({ project, renderMode, refreshToken }: AssetGalleryProps) {
  const { t } = useTranslation();
  const [scenes, setScenes] = useState<ProjectScene[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!project) {
      setScenes([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    getProjectContent(project)
      .then((data) => {
        if (!cancelled) setScenes(data.scenes || []);
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
        <AssetGrid scenes={imageScenes} project={project} kind="image" />
      )}
      {!loading && !error && !nothingToShow && renderMode === "videos" && (
        <AssetGrid scenes={videoScenes} project={project} kind="video" />
      )}
      {!loading && !error && !nothingToShow && renderMode === "smart" && (
        <div className="flex flex-col gap-4">
          {imageScenes.length > 0 && (
            <div>
              <div className="mb-2 font-mono text-[10px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
                🖼️ {t("projectRenderPanel.galleryImagesSection", { count: imageScenes.length })}
              </div>
              <AssetGrid scenes={imageScenes} project={project} kind="image" />
            </div>
          )}
          {videoScenes.length > 0 && (
            <div>
              <div className="mb-2 font-mono text-[10px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
                🎬 {t("projectRenderPanel.galleryVideosSection", { count: videoScenes.length })}
              </div>
              <AssetGrid scenes={videoScenes} project={project} kind="video" />
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
