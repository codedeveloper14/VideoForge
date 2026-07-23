import { api } from "./client";

export interface UpdateCheckResult {
  current_version: string;
  latest_version: string | null;
  update_available: boolean;
  release_url: string | null;
}

export function checkForUpdate() {
  return api.get<UpdateCheckResult>("/updates/check").then((r) => r.data);
}
