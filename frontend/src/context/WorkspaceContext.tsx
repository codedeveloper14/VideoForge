import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";

const STORAGE_KEY = "vf_workspace_tabs";

export type PipelinePage = "guion" | "imagen" | "voz" | "video" | "render";

interface WorkspaceContextValue {
  tabs: string[];
  openProject: (projectName: string, page?: PipelinePage) => void;
  closeTab: (projectName: string) => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

function loadTabs(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((t) => typeof t === "string") : [];
  } catch {
    return [];
  }
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [tabs, setTabs] = useState<string[]>(loadTabs);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tabs));
  }, [tabs]);

  const openProject = useCallback(
    (projectName: string, page: PipelinePage = "guion") => {
      setTabs((prev) => (prev.includes(projectName) ? prev : [...prev, projectName]));
      navigate(`/app/${page}?project=${encodeURIComponent(projectName)}`);
    },
    [navigate],
  );

  const closeTab = useCallback(
    (projectName: string) => {
      setTabs((prev) => prev.filter((t) => t !== projectName));
    },
    [],
  );

  return (
    <WorkspaceContext.Provider value={{ tabs, openProject, closeTab }}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}
