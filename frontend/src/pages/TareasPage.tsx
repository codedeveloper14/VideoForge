import { useEffect, useState } from "react";

interface Task {
  id: string;
  text: string;
  done: boolean;
  created: number;
}

const STORAGE_KEY = "vf_tasks";

function loadTasks(): Task[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveTasks(tasks: Task[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));
}

export default function TareasPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [text, setText] = useState("");

  useEffect(() => {
    setTasks(loadTasks());
  }, []);

  function persist(next: Task[]) {
    setTasks(next);
    saveTasks(next);
  }

  function addTask(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;
    persist([{ id: crypto.randomUUID(), text: trimmed, done: false, created: Date.now() }, ...tasks]);
    setText("");
  }

  function toggleTask(id: string) {
    persist(tasks.map((t) => (t.id === id ? { ...t, done: !t.done } : t)));
  }

  function deleteTask(id: string) {
    persist(tasks.filter((t) => t.id !== id));
  }

  const pending = tasks.filter((t) => !t.done);
  const done = tasks.filter((t) => t.done);

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <div className="mb-1.5 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-[var(--vf-c1)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--vf-c1)]" />
          Tareas
        </div>
        <h1 className="text-2xl font-bold text-[var(--vf-text)]">
          Tus <span className="text-[var(--vf-c1)]">pendientes</span>
        </h1>
      </div>

      <form onSubmit={addTask} className="mb-6 flex gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Escribe una nueva tarea…"
          className="flex-1 rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none focus:border-[var(--vf-c1)]"
        />
        <button
          type="submit"
          className="rounded-lg px-4 py-2.5 text-sm font-semibold text-white"
          style={{ background: "linear-gradient(135deg, var(--vf-c1), #9f7aea)" }}
        >
          + Agregar
        </button>
      </form>

      {tasks.length === 0 ? (
        <p className="py-10 text-center font-mono text-xs text-[var(--vf-muted)]">
          Sin tareas activas.
        </p>
      ) : (
        <div className="space-y-4">
          {pending.length > 0 && (
            <div className="space-y-1.5">
              {pending.map((t) => (
                <div
                  key={t.id}
                  className="flex items-center gap-3 rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface)] px-3.5 py-2.5"
                >
                  <button
                    onClick={() => toggleTask(t.id)}
                    className="h-4 w-4 flex-shrink-0 rounded border border-[var(--vf-border)]"
                  />
                  <span className="flex-1 text-sm text-[var(--vf-text)]">{t.text}</span>
                  <button
                    onClick={() => deleteTask(t.id)}
                    className="text-xs text-[var(--vf-muted)] hover:text-[var(--vf-danger)]"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
          {done.length > 0 && (
            <div className="space-y-1.5 opacity-50">
              {done.map((t) => (
                <div
                  key={t.id}
                  className="flex items-center gap-3 rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface)] px-3.5 py-2.5"
                >
                  <button
                    onClick={() => toggleTask(t.id)}
                    className="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border border-[var(--vf-c5)] bg-[var(--vf-c5)] text-[9px] text-black"
                  >
                    ✓
                  </button>
                  <span className="flex-1 text-sm text-[var(--vf-text)] line-through">{t.text}</span>
                  <button
                    onClick={() => deleteTask(t.id)}
                    className="text-xs text-[var(--vf-muted)] hover:text-[var(--vf-danger)]"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
