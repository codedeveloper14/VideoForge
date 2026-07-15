import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { abrirVideoFinal, listFinalVideos } from "../api/projects";

export default function ProjectDetailPage() {
  const { nombre = "" } = useParams<{ nombre: string }>();
  const [videos, setVideos] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [folderMsg, setFolderMsg] = useState("");

  useEffect(() => {
    listFinalVideos(nombre)
      .then((data) => setVideos(data.videos || []))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [nombre]);

  async function handleAbrirCarpeta() {
    setFolderMsg("Abriendo carpeta…");
    try {
      const data = await abrirVideoFinal(nombre);
      setFolderMsg(data.ok ? "" : data.error || "No se pudo abrir la carpeta.");
    } catch (err) {
      setFolderMsg((err as Error).message);
    }
  }

  return (
    <div>
      <Link to="/app/home" className="text-sm text-[var(--vf-muted)] hover:underline">
        ← Proyectos
      </Link>
      <h1 className="mb-6 mt-2 text-2xl font-semibold">{nombre}</h1>

      <div className="mb-6 flex flex-wrap gap-2">
        <Link
          to={`/app/guion?project=${encodeURIComponent(nombre)}`}
          className="rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface)] px-3 py-1.5 text-sm hover:bg-[var(--vf-surface-2)]"
        >
          Guion
        </Link>
        <Link
          to={`/app/voz?project=${encodeURIComponent(nombre)}`}
          className="rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface)] px-3 py-1.5 text-sm hover:bg-[var(--vf-surface-2)]"
        >
          Voz
        </Link>
        <Link
          to={`/app/imagen?project=${encodeURIComponent(nombre)}`}
          className="rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface)] px-3 py-1.5 text-sm hover:bg-[var(--vf-surface-2)]"
        >
          Imagen
        </Link>
        <Link
          to={`/app/video?project=${encodeURIComponent(nombre)}`}
          className="rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface)] px-3 py-1.5 text-sm hover:bg-[var(--vf-surface-2)]"
        >
          Video
        </Link>
        <Link
          to={`/app/editor/${encodeURIComponent(nombre)}`}
          className="rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface)] px-3 py-1.5 text-sm hover:bg-[var(--vf-surface-2)]"
        >
          Editor
        </Link>
        <Link
          to={`/app/render?project=${encodeURIComponent(nombre)}`}
          className="rounded-lg px-3 py-1.5 text-sm font-medium text-white hover:bg-[var(--vf-accent-hover)]"
          style={{ background: "var(--vf-accent)" }}
        >
          Renderizar
        </Link>
      </div>

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Videos finales</h2>
        <div className="flex items-center gap-2">
          {folderMsg && <span className="text-xs text-[var(--vf-muted)]">{folderMsg}</span>}
          <button
            onClick={handleAbrirCarpeta}
            className="rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface)] px-3 py-1.5 text-sm hover:bg-[var(--vf-surface-2)]"
          >
            📁 Abrir carpeta
          </button>
        </div>
      </div>
      {loading ? (
        <p className="text-[var(--vf-muted)]">Cargando…</p>
      ) : error ? (
        <p className="text-sm text-[var(--vf-danger)]">{error}</p>
      ) : videos.length === 0 ? (
        <p className="text-[var(--vf-muted)]">Todavía no hay videos renderizados.</p>
      ) : (
        <ul className="space-y-2">
          {videos.map((file) => (
            <li
              key={file}
              className="flex items-center justify-between rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface)] px-4 py-2 text-sm"
            >
              <span className="truncate">{file}</span>
              <a
                href={`/api/proyectos/video_final?project=${encodeURIComponent(nombre)}&file=${encodeURIComponent(file)}&dl=1`}
                className="text-[var(--vf-accent)] hover:underline"
              >
                Descargar
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
