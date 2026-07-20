import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type GenerationPhase = "running" | "done" | "error";

export interface GenerationEntry {
  id: string;
  label: string;
  status: GenerationPhase;
  message: string;
  pct: number | null; // null = indeterminado (sin porcentaje conocido todavia)
  startedAt: number;
  // Historial tipo terminal de todos los mensajes que paso `message` -- es lo que
  // se ve al expandir la pastilla (equivalente al log en vivo de la UI vieja).
  log: string[];
}

const MAX_LOG_LINES = 300;

function appendLog(log: string[], line: string | undefined): string[] {
  if (!line || log[log.length - 1] === line) return log;
  const next = [...log, line];
  return next.length > MAX_LOG_LINES ? next.slice(next.length - MAX_LOG_LINES) : next;
}

interface GenerationStatusValue {
  entries: GenerationEntry[];
  start: (id: string, label: string, message?: string) => void;
  update: (id: string, patch: Partial<Pick<GenerationEntry, "message" | "pct">>) => void;
  finish: (id: string, ok: boolean, message?: string) => void;
  dismiss: (id: string) => void;
}

const GenerationStatusContext = createContext<GenerationStatusValue | null>(null);

const AUTO_DISMISS_MS = 6000;

// Chips flotantes de progreso (las "pastillas") que aparecen al iniciar cualquier
// generacion en la app -- estandarizado para que cualquier panel (video, imagen,
// voz, guion, render) las use del mismo modo, en vez de que cada uno construya su
// propia UI de estado.
export function GenerationStatusProvider({ children }: { children: ReactNode }) {
  const [entries, setEntries] = useState<GenerationEntry[]>([]);
  const dismissTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const clearDismissTimer = useCallback((id: string) => {
    const t = dismissTimers.current[id];
    if (t) {
      clearTimeout(t);
      delete dismissTimers.current[id];
    }
  }, []);

  const dismiss = useCallback(
    (id: string) => {
      clearDismissTimer(id);
      setEntries((prev) => prev.filter((e) => e.id !== id));
    },
    [clearDismissTimer],
  );

  const start = useCallback(
    (id: string, label: string, message = "Iniciando...") => {
      clearDismissTimer(id);
      setEntries((prev) => {
        const next: GenerationEntry = {
          id,
          label,
          status: "running",
          message,
          pct: null,
          startedAt: Date.now(),
          log: [message],
        };
        const rest = prev.filter((e) => e.id !== id);
        return [...rest, next];
      });
    },
    [clearDismissTimer],
  );

  const update = useCallback((id: string, patch: Partial<Pick<GenerationEntry, "message" | "pct">>) => {
    setEntries((prev) =>
      prev.map((e) => (e.id === id ? { ...e, ...patch, log: appendLog(e.log, patch.message) } : e)),
    );
  }, []);

  const finish = useCallback(
    (id: string, ok: boolean, message?: string) => {
      setEntries((prev) =>
        prev.map((e) => {
          if (e.id !== id) return e;
          const finalMessage = message ?? (ok ? "Completado." : "Error.");
          return {
            ...e,
            status: ok ? "done" : "error",
            message: finalMessage,
            pct: ok ? 100 : e.pct,
            log: appendLog(e.log, finalMessage),
          };
        }),
      );
      dismissTimers.current[id] = setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    },
    [dismiss],
  );

  const value = useMemo(
    () => ({ entries, start, update, finish, dismiss }),
    [entries, start, update, finish, dismiss],
  );

  return (
    <GenerationStatusContext.Provider value={value}>
      {children}
    </GenerationStatusContext.Provider>
  );
}

export function useGenerationStatus(): GenerationStatusValue {
  const ctx = useContext(GenerationStatusContext);
  if (!ctx) throw new Error("useGenerationStatus debe usarse dentro de <GenerationStatusProvider>");
  return ctx;
}
