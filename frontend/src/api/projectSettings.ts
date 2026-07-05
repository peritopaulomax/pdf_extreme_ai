import { apiFetch } from "./client";

export function fetchRules(projectId: string): Promise<{ global_rules: string }> {
  return apiFetch(`/projects/${projectId}/rules`);
}

export function saveRules(
  projectId: string,
  global_rules: string,
): Promise<{ global_rules: string }> {
  return apiFetch(`/projects/${projectId}/rules`, {
    method: "PATCH",
    body: JSON.stringify({ global_rules }),
  });
}

export function fetchMemory(projectId: string): Promise<{ text: string }> {
  return apiFetch(`/projects/${projectId}/memory`);
}

export function saveMemory(
  projectId: string,
  text: string,
): Promise<{ text: string }> {
  return apiFetch(`/projects/${projectId}/memory`, {
    method: "PUT",
    body: JSON.stringify({ text }),
  });
}
