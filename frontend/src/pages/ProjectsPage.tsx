import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { createProject, deleteProject, listProjects } from "../api/projects";
import TopTabBar from "../components/TopTabBar";
import type { Project } from "../types";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [nombre, setNombre] = useState("");
  const [creating, setCreating] = useState(false);

  function load() {
    setLoading(true);
    listProjects()
      .then(setProjects)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!nombre.trim()) return;
    setCreating(true);
    setError("");
    try {
      await createProject(nombre.trim());
      setNombre("");
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(name: string) {
    if (!confirm(`¿Borrar el proyecto "${name}"? Esta acción no se puede deshacer.`)) return;
    setError("");
    try {
      await deleteProject(name);
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <TopTabBar />
      <h1 className="mb-6 text-2xl font-semibold">Proyectos</h1>

      <form onSubmit={handleCreate} className="mb-6 flex gap-2">
        <input
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          placeholder="Nombre del nuevo proyecto"
          className="flex-1 max-w-sm rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--vf-accent)]"
        />
        <button
          type="submit"
          disabled={creating}
          className="rounded-lg bg-[var(--vf-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--vf-accent-hover)] disabled:opacity-50"
        >
          {creating ? "Creando…" : "Crear proyecto"}
        </button>
      </form>

      {error && <p className="mb-4 text-sm text-[var(--vf-danger)]">{error}</p>}

      {loading ? (
        <p className="text-[var(--vf-muted)]">Cargando proyectos…</p>
      ) : projects.length === 0 ? (
        <p className="text-[var(--vf-muted)]">Aún no tienes proyectos.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <div
              key={p.nombre}
              className="flex flex-col rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5"
            >
              <h2 className="truncate text-lg font-semibold">{p.nombre}</h2>
              <p className="mt-1 text-sm text-[var(--vf-muted)]">
                {p.videos} videos · {p.audios} audios
              </p>
              <div className="mt-4 flex gap-2">
                <Link
                  to={`/app/proyectos/${encodeURIComponent(p.nombre)}`}
                  className="flex-1 rounded-lg border border-[var(--vf-border)] py-1.5 text-center text-sm hover:bg-[var(--vf-surface-2)]"
                >
                  Ver
                </Link>
                <button
                  onClick={() => handleDelete(p.nombre)}
                  className="rounded-lg border border-[var(--vf-border)] px-3 py-1.5 text-sm text-[var(--vf-danger)] hover:bg-[var(--vf-surface-2)]"
                >
                  Borrar
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
