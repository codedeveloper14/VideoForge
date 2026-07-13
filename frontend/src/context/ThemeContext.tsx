import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "./AuthContext";
import { getProfile, setThemePreference } from "../api/user";

export type Theme = "light" | "dark";

const STORAGE_KEY = "vf_theme";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
}

function readCachedTheme(): Theme {
  const cached = localStorage.getItem(STORAGE_KEY);
  return cached === "light" ? "light" : "dark";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [theme, setThemeState] = useState<Theme>(readCachedTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Al iniciar sesion, el perfil real (guardado en la cuenta) manda sobre el
  // cache local -- asi el tema sigue al usuario entre dispositivos.
  useEffect(() => {
    if (!user) return;
    getProfile()
      .then((profile) => {
        if (profile.theme === "light" || profile.theme === "dark") {
          setThemeState(profile.theme);
          localStorage.setItem(STORAGE_KEY, profile.theme);
        }
      })
      .catch(() => {
        // sin conexion o error: se queda con el tema cacheado localmente
      });
  }, [user]);

  function setTheme(next: Theme) {
    setThemeState(next);
    localStorage.setItem(STORAGE_KEY, next);
    void setThemePreference(next).catch(() => {
      // si falla el guardado remoto, el toggle ya se aplico visualmente;
      // se reintentara guardar la proxima vez que cambie de tema
    });
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme debe usarse dentro de <ThemeProvider>");
  return ctx;
}
