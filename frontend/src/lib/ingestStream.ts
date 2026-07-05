import { API_URL } from "../api/client";
import { parseSseChunk, parseSseData } from "./sse";

export interface IngestProgress {
  stage?: string;
  message?: string;
  current?: number;
  total?: number;
  percent?: number | null;
  file?: string;
}

export interface IngestDone {
  files_processed?: number;
  files_total?: number;
  total_pages?: number;
  total_chunks?: number;
  elapsed_s?: number;
  errors?: string[];
  per_file?: Array<Record<string, unknown>>;
  logs?: string[];
  skipped?: string[];
  message?: string;
}

type IngestCallbacks = {
  onStatus?: (msg: string) => void;
  onProgress?: (p: IngestProgress) => void;
  onDone?: (d: IngestDone) => void;
  onError?: (msg: string) => void;
};

async function consumeIngestStream(
  url: string,
  init: RequestInit,
  callbacks: {
    onStatus?: (msg: string) => void;
    onProgress?: (p: IngestProgress) => void;
    onDone?: (d: IngestDone) => void;
    onError?: (msg: string) => void;
  },
): Promise<void> {
  const res = await fetch(url, {
    credentials: "include",
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let msg = text;
    try {
      const j = JSON.parse(text);
      const d = j.detail;
      msg = Array.isArray(d)
        ? d.map((x: { msg?: string }) => x.msg || String(x)).join("; ")
        : String(d || text);
    } catch {
      /* raw */
    }
    callbacks.onError?.(msg || `HTTP ${res.status}`);
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    callbacks.onError?.("Sem stream de resposta");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { messages, remainder } = parseSseChunk(buffer);
    buffer = remainder;
    for (const msg of messages) {
      if (msg.event === "status") {
        const p = parseSseData<{ message?: string }>(msg.data);
        if (p?.message) callbacks.onStatus?.(p.message);
      } else if (msg.event === "progress") {
        const p = parseSseData<IngestProgress>(msg.data);
        if (p) callbacks.onProgress?.(p);
      } else if (msg.event === "done") {
        const p = parseSseData<IngestDone>(msg.data);
        if (p) callbacks.onDone?.(p);
      } else if (msg.event === "error") {
        const p = parseSseData<{ message?: string }>(msg.data);
        callbacks.onError?.(p?.message || msg.data);
      }
    }
  }
}

export async function streamIngest(
  projectId: string,
  formData: FormData,
  params: { rebuild?: boolean; force_ocr?: boolean },
  callbacks: IngestCallbacks,
): Promise<void> {
  const qs = new URLSearchParams();
  if (params.rebuild) qs.set("rebuild", "true");
  if (params.force_ocr) qs.set("force_ocr", "true");
  const suffix = qs.toString() ? `?${qs}` : "";
  const url = `${API_URL}/projects/${projectId}/ingest/stream${suffix}`;
  return consumeIngestStream(
    url,
    {
      method: "POST",
      body: formData,
    },
    callbacks,
  );
}

export async function streamReprocessDocuments(
  projectId: string,
  fileIds: string[],
  params: { force_ocr?: boolean },
  callbacks: IngestCallbacks,
): Promise<void> {
  const url = `${API_URL}/projects/${projectId}/documents/reprocess/stream`;
  return consumeIngestStream(
    url,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        file_ids: fileIds,
        force_ocr: Boolean(params.force_ocr),
      }),
    },
    callbacks,
  );
}
