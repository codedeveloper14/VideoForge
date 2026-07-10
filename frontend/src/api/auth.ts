import { api } from "./client";

export interface LoginResult {
  ok: boolean;
  user: string;
  must_change_password?: boolean;
}

export interface MeResult {
  authenticated: boolean;
  username?: string;
}

export function login(username: string, password: string) {
  return api
    .post<LoginResult>("/login", { username, password })
    .then((r) => r.data);
}

export function register(
  username: string,
  email: string,
  password: string,
  plan = "basico",
) {
  return api
    .post<LoginResult>("/register", { username, email, password, plan })
    .then((r) => r.data);
}

export function changePassword(username: string, newPassword: string) {
  return api
    .post<{ ok: boolean }>("/change-password", {
      username,
      new_password: newPassword,
    })
    .then((r) => r.data);
}

export function logout() {
  return api.post<{ ok: boolean }>("/logout").then((r) => r.data);
}

export function me() {
  return api.get<MeResult>("/auth/me").then((r) => r.data);
}
