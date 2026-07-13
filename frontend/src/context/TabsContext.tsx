import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

interface OpenTab {
  name: string;
}

interface TabsContextValue {
  tabs: OpenTab[];
  openTab: (name: string) => void;
  closeTab: (name: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

const STORAGE_KEY = "vf_open_tabs";

function loadTabs(): OpenTab[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.filter((t): t is OpenTab => !!t && typeof t.name === "string");
    }
  } catch {
    // localStorage corrupto o inaccesible, se ignora y arranca vacio
  }
  return [];
}

export function TabsProvider({ children }: { children: ReactNode }) {
  const [tabs, setTabs] = useState<OpenTab[]>(loadTabs);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tabs));
  }, [tabs]);

  function openTab(name: string) {
    if (!name) return;
    setTabs((prev) => (prev.some((t) => t.name === name) ? prev : [...prev, { name }]));
  }

  function closeTab(name: string) {
    setTabs((prev) => prev.filter((t) => t.name !== name));
  }

  return <TabsContext.Provider value={{ tabs, openTab, closeTab }}>{children}</TabsContext.Provider>;
}

export function useTabs() {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("useTabs debe usarse dentro de <TabsProvider>");
  return ctx;
}

/** Deduce el proyecto activo a partir de la ruta actual (path param o ?project=). */
export function getProjectFromLocation(pathname: string, search: string): string | null {
  const detailMatch = pathname.match(/^\/app\/proyectos\/([^/]+)/);
  if (detailMatch) return decodeURIComponent(detailMatch[1]);

  const editorMatch = pathname.match(/^\/app\/editor\/([^/]+)/);
  if (editorMatch) return decodeURIComponent(editorMatch[1]);

  const params = new URLSearchParams(search);
  const fromQuery = params.get("project");
  return fromQuery ? fromQuery : null;
}
