import { useEffect, useState, type FormEvent } from "react";
import { createProject, listProjects } from "../api/projects";
import type { Project } from "../types";

interface ProjectPickerModalProps {
  onClose: () => void;
  onSelect: (name: string) => void;
}

export default function ProjectPickerModal({ onClose, onSelect }: ProjectPickerModalProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [nombre, setNombre] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = projects.filter((p) => p.nombre.toLowerCase().includes(search.trim().toLowerCase()));

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!nombre.trim()) return;
    setCreating(true);
    setError("");
    try {
      const result = await createProject(nombre.trim());
      onSelect(result.nombre);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[8100] flex items-start justify-center bg-black/55 pt-24"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[440px] rounded-2xl border border-[rgba(var(--vf-fg-rgb),0.1)] bg-[var(--vf-s)] p-6 shadow-[0_24px_64px_rgba(0,0,0,.5)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 text-base font-bold text-[var(--vf-text)]">Abrir proyecto</div>

        <input
          autoFocus
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar proyecto…"
          className="mb-3 w-full rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.18)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none transition-colors focus:border-[var(--vf-c1)]/50"
        />

        <div className="mb-4 max-h-[240px] overflow-y-auto rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.08)]">
          {loading ? (
            <p className="p-3.5 text-sm text-[var(--vf-muted)]">Cargando…</p>
          ) : filtered.length === 0 ? (
            <p className="p-3.5 text-sm text-[var(--vf-muted)]">Sin resultados.</p>
          ) : (
            filtered.map((p) => (
              <button
                key={p.nombre}
                onClick={() => onSelect(p.nombre)}
                className="flex w-full items-center justify-between gap-2 px-3.5 py-2.5 text-left text-sm text-[var(--vf-text)] transition-colors hover:bg-[rgba(var(--vf-fg-rgb),0.05)]"
              >
                <span className="truncate">{p.nombre}</span>
                <span className="flex-shrink-0 text-[11px] text-[var(--vf-muted)]">
                  {p.videos} videos
                </span>
              </button>
            ))
          )}
        </div>

        <form onSubmit={handleCreate} className="flex gap-2">
          <input
            type="text"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Nombre del nuevo proyecto"
            className="flex-1 rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.18)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none transition-colors focus:border-[var(--vf-c1)]/50"
          />
          <button
            type="submit"
            disabled={creating || !nombre.trim()}
            className="flex-shrink-0 rounded-[9px] border-none bg-gradient-to-br from-[#7c6aff] to-[#5b42f3] px-4 py-2.5 text-[13px] font-bold text-white transition-transform hover:-translate-y-0.5 disabled:opacity-50"
          >
            {creating ? "Creando…" : "Crear"}
          </button>
        </form>

        {error && <p className="mt-3 text-sm text-[var(--vf-danger)]">{error}</p>}
      </div>
    </div>
  );
}
