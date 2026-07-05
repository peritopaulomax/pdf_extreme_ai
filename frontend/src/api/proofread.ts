import { API_URL, apiFetch } from "./client";
import { parseSseChunk, parseSseData } from "../lib/sse";
import type { ProofreadResult } from "./types";

export function runProofread(
  text: string,
  model?: string,
  maxChars = 12000,
): Promise<ProofreadResult> {
  return apiFetch<ProofreadResult>("/proofread", {
    method: "POST",
    body: JSON.stringify({ text, model, max_chars: maxChars }),
  });
}

export interface ProofreadBlockEvent {
  block_index: number;
  total_blocks: number;
  source_text: string;
  corrected_text: string;
  changes: ProofreadResult["changes"];
  raw_fallback?: boolean;
  raw_response?: string | null;
}

export interface ProofreadStreamCallbacks {
  onStart?: (totalBlocks: number) => void;
  onStatus?: (message: string) => void;
  onBlock?: (block: ProofreadBlockEvent) => void;
  onDone?: (result: ProofreadResult) => void;
  onError?: (message: string) => void;
}

export async function streamProofread(
  text: string,
  model: string | undefined,
  callbacks: ProofreadStreamCallbacks,
  maxChars = 12000,
): Promise<void> {
  const res = await fetch(`${API_URL}/proofread/stream`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ text, model, max_chars: maxChars }),
  });
  if (!res.ok) {
    callbacks.onError?.((await res.text().catch(() => "")) || `HTTP ${res.status}`);
    return;
  }
  const reader = res.body?.getReader();
  if (!reader) {
    callbacks.onError?.("Resposta sem stream");
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
      dispatchProofreadEvent(msg.event, msg.data, callbacks);
    }
  }
  if (buffer.trim()) {
    const { messages } = parseSseChunk(buffer + "\n\n");
    for (const msg of messages) {
      dispatchProofreadEvent(msg.event, msg.data, callbacks);
    }
  }
}

function dispatchProofreadEvent(
  event: string,
  data: string,
  callbacks: ProofreadStreamCallbacks,
): void {
  switch (event) {
    case "start": {
      const p = parseSseData<{ total_blocks?: number }>(data);
      callbacks.onStart?.(p?.total_blocks || 0);
      break;
    }
    case "status": {
      const p = parseSseData<{ message?: string }>(data);
      if (p?.message) callbacks.onStatus?.(p.message);
      break;
    }
    case "block": {
      const p = parseSseData<ProofreadBlockEvent>(data);
      if (p) callbacks.onBlock?.(p);
      break;
    }
    case "done": {
      const p = parseSseData<ProofreadResult>(data);
      if (p) callbacks.onDone?.(p);
      break;
    }
    case "error": {
      const p = parseSseData<{ message?: string }>(data);
      callbacks.onError?.(p?.message || data);
      break;
    }
    default:
      break;
  }
}
