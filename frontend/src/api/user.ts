import { api } from "./client";
import type { Payment, UserProfile } from "../types";

export function getProfile() {
  return api.get<UserProfile>("/user/profile").then((r) => r.data);
}

export function getPayments() {
  return api.get<Payment[]>("/user/payments").then((r) => r.data);
}
