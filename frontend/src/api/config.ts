import { apiFetch } from "./client";
import type { AppConfig } from "./types";

export function fetchConfig(): Promise<AppConfig> {
  return apiFetch<AppConfig>("/config");
}
