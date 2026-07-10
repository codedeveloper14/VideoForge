import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import * as authApi from "../api/auth";
import type { LoginResult } from "../api/auth";

interface AuthContextValue {
  user: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<LoginResult>;
  register: (
    username: string,
    email: string,
    password: string,
    plan?: string,
  ) => Promise<LoginResult>;
  changePassword: (
    username: string,
    newPassword: string,
  ) => Promise<{ ok: boolean }>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await authApi.me();
      setUser(data.authenticated ? (data.username ?? null) : null);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const data = await authApi.login(username, password);
    if (data.must_change_password) {
      return data;
    }
    setUser(data.user);
    return data;
  }, []);

  const register = useCallback(
    async (username: string, email: string, password: string, plan?: string) => {
      const data = await authApi.register(username, email, password, plan);
      setUser(data.user);
      return data;
    },
    [],
  );

  const changePassword = useCallback(
    async (username: string, newPassword: string) => {
      const data = await authApi.changePassword(username, newPassword);
      setUser(username);
      return data;
    },
    [],
  );

  const logout = useCallback(async () => {
    await authApi.logout();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, loading, login, register, changePassword, logout, refresh }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return ctx;
}
