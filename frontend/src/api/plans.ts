import { api } from "./client";
import type { Plan } from "../types";

export function listPlans() {
  return api.get<Plan[]>("/plans").then((r) => r.data);
}
