import { apiFetch } from "./client";
import type { ProjectRecord } from "./types";

export async function fetchProjects(): Promise<ProjectRecord[]> {
  const data = await apiFetch<{ projects: ProjectRecord[] }>("/projects");
  return data.projects;
}

export async function fetchProject(projectId: string): Promise<ProjectRecord> {
  return apiFetch<ProjectRecord>(`/projects/${projectId}`);
}

export async function createProject(name: string): Promise<ProjectRecord> {
  return apiFetch<ProjectRecord>("/projects", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function renameProject(
  projectId: string,
  name: string,
): Promise<ProjectRecord> {
  return apiFetch<ProjectRecord>(`/projects/${projectId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function deleteProject(projectId: string): Promise<void> {
  await apiFetch(`/projects/${projectId}`, { method: "DELETE" });
}
