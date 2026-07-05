import { apiFetch } from "./client";
import type { ProjectDocument } from "./types";

export function fetchDocuments(
  projectId: string,
): Promise<{ documents: ProjectDocument[] }> {
  return apiFetch(`/projects/${projectId}/documents`);
}

export function deleteDocument(
  projectId: string,
  fileId: string,
): Promise<void> {
  return apiFetch(`/projects/${projectId}/documents/${fileId}`, {
    method: "DELETE",
  });
}

export function reprocessDocument(
  projectId: string,
  fileId: string,
  forceOcr = false,
): Promise<Record<string, unknown>> {
  const q = forceOcr ? "?force_ocr=true" : "";
  return apiFetch(`/projects/${projectId}/documents/${fileId}/reprocess${q}`, {
    method: "POST",
  });
}

export function deleteDocumentsSelected(
  projectId: string,
  fileIds: string[],
): Promise<{ deleted: boolean; file_ids: string[]; deleted_count: number }> {
  return apiFetch(`/projects/${projectId}/documents/remove`, {
    method: "POST",
    body: JSON.stringify({ file_ids: fileIds }),
  });
}

export function reprocessDocumentsSelected(
  projectId: string,
  fileIds: string[],
  forceOcr = false,
): Promise<{
  reprocessed: boolean;
  file_ids: string[];
  reprocessed_count: number;
  files_processed?: number;
  files_total?: number;
  total_pages?: number;
  total_chunks?: number;
  elapsed_s?: number;
  per_file?: ProjectDocument[];
}> {
  return apiFetch(`/projects/${projectId}/documents/reprocess`, {
    method: "POST",
    body: JSON.stringify({ file_ids: fileIds, force_ocr: forceOcr }),
  });
}
