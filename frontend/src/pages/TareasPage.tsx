import { useEffect, useState } from "react";

type TaskStatus = "todo" | "progress" | "done";
type TaskPriority = "low" | "normal" | "high";

interface Task {
  id: string;
  title: string;
  description: string;
  priority: TaskPriority;
  status: TaskStatus;
  createdAt: string;
}

const STORAGE_KEY = "vf_tasks";

type FilterId = "all" | TaskStatus;

const TABS: { id: FilterId; label: string }[] = [
  { id: "all", label: "Todas" },
  { id: "todo", label: "Pendiente" },
  { id: "progress", label: "En progreso" },
  { id: "done", label: "Hecho" },
];

const PRIORITY_OPTIONS: { value: TaskPriority; label: string }[] = [
  { value: "normal", label: "Normal" },
  { value: "high", label: "Alta" },
  { value: "low", label: "Baja" },
];

const PRIORITY_STYLES: Record<TaskPriority, string> = {
  high: "bg-[rgba(239,68,68,.12)] text-[rgba(239,68,68,.8)] border border-[rgba(239,68,68,.2)]",
  normal: "bg-[var(--vf-c1)]/10 text-[#b4a0ff] border border-[var(--vf-c1)]/20",
  low: "bg-[rgba(var(--vf-fg-rgb),0.05)] text-[rgba(var(--vf-fg-rgb),0.35)] border border-[rgba(var(--vf-fg-rgb),0.1)]",
};

const PRIORITY_LABELS: Record<TaskPriority, string> = {
  high: "Alta",
  normal: "Normal",
  low: "Baja",
};

function loadTasks(): Task[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as Task[]) : [];
  } catch {
    return [];
  }
}

function saveTasks(tasks: Task[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));
  } catch {
    // ignore storage failures (e.g. private mode / quota)
  }
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getDate()}/${d.getMonth() + 1}/${d.getFullYear()}`;
}

function nextStatus(status: TaskStatus): TaskStatus {
  if (status === "todo") return "progress";
  if (status === "progress") return "done";
  return "todo";
}

function NewTaskModal({
  onClose,
  onSave,
}: {
  onClose: () => void;
  onSave: (title: string, description: string, priority: TaskPriority) => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<TaskPriority>("normal");

  function handleSave() {
    const trimmed = title.trim();
    if (!trimmed) return;
    onSave(trimmed, description.trim(), priority);
  }

  return (
    <div
      className="fixed inset-0 z-[8100] flex items-center justify-center bg-black/55"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[480px] rounded-2xl border border-[rgba(var(--vf-fg-rgb),0.1)] bg-[var(--vf-s)] p-7 shadow-[0_24px_64px_rgba(0,0,0,.5)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 text-base font-bold text-[var(--vf-text)]">Nueva tarea</div>

        <div className="mb-3.5">
          <label className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
            Título
          </label>
          <input
            autoFocus
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Título de la tarea..."
            className="w-full rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.09)] bg-[rgba(var(--vf-fg-rgb),0.04)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none transition-colors focus:border-[var(--vf-c1)]/50 focus:shadow-[0_0_0_3px_rgba(108,86,255,.1)]"
          />
        </div>

        <div className="mb-3.5">
          <label className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
            Descripción (opcional)
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Detalles..."
            style={{ minHeight: 60 }}
            className="w-full resize-y rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.09)] bg-[rgba(var(--vf-fg-rgb),0.04)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none transition-colors focus:border-[var(--vf-c1)]/50 focus:shadow-[0_0_0_3px_rgba(108,86,255,.1)]"
          />
        </div>

        <div className="mb-1">
          <label className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
            Prioridad
          </label>
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value as TaskPriority)}
            className="w-full cursor-pointer appearance-none rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.09)] bg-[rgba(var(--vf-fg-rgb),0.04)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none transition-colors focus:border-[var(--vf-c1)]/50 focus:shadow-[0_0_0_3px_rgba(108,86,255,.1)]"
          >
            {PRIORITY_OPTIONS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>

        <div className="mt-5 flex gap-2">
          <button
            onClick={handleSave}
            className="flex-1 rounded-[9px] border-none bg-gradient-to-br from-[#7c6aff] to-[#5b42f3] py-2.5 text-[13px] font-bold text-white transition-transform hover:-translate-y-0.5"
          >
            Guardar
          </button>
          <button
            onClick={onClose}
            className="flex-1 rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.1)] bg-transparent py-2.5 text-[13px] text-[var(--vf-muted)] transition-colors hover:text-[var(--vf-text)] hover:border-[rgba(var(--vf-fg-rgb),0.25)]"
          >
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}

export default function TareasPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState<FilterId>("all");
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    setTasks(loadTasks());
  }, []);

  function persist(next: Task[]) {
    setTasks(next);
    saveTasks(next);
  }

  function handleCreate(title: string, description: string, priority: TaskPriority) {
    const task: Task = {
      id: `task_${Date.now()}`,
      title,
      description,
      priority,
      status: "todo",
      createdAt: new Date().toISOString(),
    };
    persist([task, ...tasks]);
    setModalOpen(false);
  }

  function handleCycleStatus(id: string) {
    persist(
      tasks.map((t) => (t.id === id ? { ...t, status: nextStatus(t.status) } : t)),
    );
  }

  function handleDelete(id: string) {
    if (!confirm("¿Eliminar esta tarea?")) return;
    persist(tasks.filter((t) => t.id !== id));
  }

  const counts: Record<FilterId, number> = {
    all: tasks.length,
    todo: 0,
    progress: 0,
    done: 0,
  };
  tasks.forEach((t) => {
    counts[t.status] += 1;
  });

  const shown = tasks.filter((t) => filter === "all" || t.status === filter);

  return (
    <div className="max-w-[860px]">
      <h1 className="mb-7 text-[34px] font-extrabold tracking-tight bg-gradient-to-r from-[var(--vf-text)] to-[var(--vf-c2)] bg-clip-text text-transparent">
        Tareas
      </h1>

      <div className="mb-7 flex items-center justify-between">
        <div className="flex w-fit gap-1 rounded-[14px] border border-[rgba(var(--vf-fg-rgb),0.06)] bg-[rgba(var(--vf-fg-rgb),0.03)] p-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setFilter(t.id)}
              className={`whitespace-nowrap rounded-[10px] px-4.5 py-2 text-xs font-semibold transition-colors ${
                filter === t.id ? "bg-[rgba(var(--vf-fg-rgb),0.08)] text-[var(--vf-text)]" : "text-[rgba(var(--vf-fg-rgb),0.4)] hover:text-[rgba(var(--vf-fg-rgb),0.7)]"
              }`}
            >
              {t.label}
              {counts[t.id] ? ` (${counts[t.id]})` : ""}
            </button>
          ))}
        </div>

        <button
          onClick={() => setModalOpen(true)}
          className="inline-flex items-center gap-2 rounded-[10px] border border-[var(--vf-c1)]/35 bg-[var(--vf-c1)]/[0.18] px-5 py-2.5 text-[13px] font-semibold text-[#c4b8ff] transition-colors hover:bg-[var(--vf-c1)]/[0.28] hover:border-[var(--vf-c1)]/60"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Nueva tarea
        </button>
      </div>

      <div className="flex flex-col gap-2.5">
        {shown.length === 0 ? (
          <div className="py-15 text-center text-[rgba(var(--vf-fg-rgb),0.4)]">
            <div className="mb-3 text-[32px] opacity-50">&#10003;</div>
            <div className="text-sm">
              {tasks.length === 0 ? "¡Sin tareas! Crea la primera." : "Sin tareas en esta categoría."}
            </div>
          </div>
        ) : (
          shown.map((t) => {
            const isDone = t.status === "done";
            return (
              <div
                key={t.id}
                className={`flex items-start gap-3.5 rounded-xl border border-[rgba(var(--vf-fg-rgb),0.07)] bg-[rgba(var(--vf-fg-rgb),0.03)] px-5 py-4 transition-colors hover:border-[rgba(var(--vf-fg-rgb),0.12)] ${
                  isDone ? "opacity-50" : ""
                }`}
              >
                <button
                  type="button"
                  title={`Estado: ${t.status}. Clic para cambiar.`}
                  onClick={() => handleCycleStatus(t.id)}
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-[6px] border transition-colors ${
                    isDone
                      ? "border-[var(--vf-c1)]/90 bg-[var(--vf-c1)]/70"
                      : t.status === "progress"
                        ? "border-[var(--vf-c2)]/70 bg-[var(--vf-c2)]/20"
                        : "border-[rgba(var(--vf-fg-rgb),0.2)] hover:border-[var(--vf-c1)]/60"
                  }`}
                >
                  {isDone && (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  )}
                  {!isDone && t.status === "progress" && (
                    <span className="h-1.5 w-1.5 rounded-full bg-[var(--vf-c2)]" />
                  )}
                </button>

                <div className="min-w-0 flex-1">
                  <div
                    className={`mb-1 text-sm font-semibold ${
                      isDone ? "text-[rgba(var(--vf-fg-rgb),0.4)] line-through" : "text-[var(--vf-text)]"
                    }`}
                  >
                    {t.title}
                  </div>
                  {t.description && (
                    <div className="mb-2 text-[12.5px] leading-relaxed text-[rgba(var(--vf-fg-rgb),0.4)]">{t.description}</div>
                  )}
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] font-bold tracking-wide ${PRIORITY_STYLES[t.priority]}`}
                    >
                      {PRIORITY_LABELS[t.priority]}
                    </span>
                    {t.status === "progress" && (
                      <span className="rounded px-2 py-0.5 text-[10px] font-bold tracking-wide text-[var(--vf-c2)]">
                        En progreso
                      </span>
                    )}
                    {formatDate(t.createdAt) && (
                      <span className="text-[10.5px] text-[rgba(var(--vf-fg-rgb),0.25)]">{formatDate(t.createdAt)}</span>
                    )}
                  </div>
                </div>

                <button
                  type="button"
                  title="Eliminar"
                  onClick={() => handleDelete(t.id)}
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] text-[rgba(var(--vf-fg-rgb),0.2)] transition-colors hover:bg-[var(--vf-danger)]/[0.08] hover:text-[var(--vf-danger)]/70"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                    <path d="M10 11v6M14 11v6" />
                    <path d="M9 6V4h6v2" />
                  </svg>
                </button>
              </div>
            );
          })
        )}
      </div>

      {modalOpen && <NewTaskModal onClose={() => setModalOpen(false)} onSave={handleCreate} />}
    </div>
  );
}
