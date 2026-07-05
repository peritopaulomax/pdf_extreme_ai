import { API_URL } from "./client";
import { parseSseChunk, parseSseData } from "../lib/sse";
import type {
  ChatDoneEvent,
  ChatMetaEvent,
  ChatRequestBody,
  ChatMode,
  TurnSnapshotEvent,
} from "./types";

export interface ChatStatusEvent {
  message?: string;
  reset_stream?: boolean;
}

export interface ChatStreamCallbacks {
  onStatus?: (message: string, status?: ChatStatusEvent) => void;
  onSnapshot?: (snap: TurnSnapshotEvent) => void;
  onThinking?: (text: string) => void;
  onToken?: (text: string) => void;
  onMeta?: (meta: ChatMetaEvent) => void;
  onDone?: (done: ChatDoneEvent) => void;
  onError?: (message: string) => void;
}

const CHAT_STREAM_TIMEOUT_MS = 20 * 60 * 1000;

function buildTimeoutSignal(
  externalSignal?: AbortSignal,
  timeoutMs: number = CHAT_STREAM_TIMEOUT_MS,
): {
  signal?: AbortSignal;
  cleanup: () => void;
  didTimeout: () => boolean;
} {
  if (!externalSignal && timeoutMs <= 0) {
    return { signal: undefined, cleanup: () => {}, didTimeout: () => false };
  }
  const ac = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  let timedOut = false;

  const onAbort = () => ac.abort();
  if (externalSignal) {
    if (externalSignal.aborted) ac.abort();
    else externalSignal.addEventListener("abort", onAbort, { once: true });
  }
  if (timeoutMs > 0) {
    timeoutId = setTimeout(() => {
      timedOut = true;
      ac.abort();
    }, timeoutMs);
  }

  return {
    signal: ac.signal,
    cleanup: () => {
      if (timeoutId) clearTimeout(timeoutId);
      if (externalSignal) externalSignal.removeEventListener("abort", onAbort);
    },
    didTimeout: () => timedOut,
  };
}

export async function streamChat(
  projectId: string,
  mode: ChatMode,
  body: ChatRequestBody,
  callbacks: ChatStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const url = `${API_URL}/projects/${projectId}/chat/${mode}`;
  const timeoutCtx = buildTimeoutSignal(signal);
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
      signal: timeoutCtx.signal,
    });
  } catch (err) {
    if (timeoutCtx.didTimeout()) {
      callbacks.onError?.("Resposta interrompida por tempo limite do stream.");
      return;
    }
    throw err;
  }

  try {
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      callbacks.onError?.(text || `HTTP ${res.status}`);
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
        dispatchSse(msg.event, msg.data, callbacks);
      }
    }

    if (buffer.trim()) {
      const { messages } = parseSseChunk(buffer + "\n\n");
      for (const msg of messages) {
        dispatchSse(msg.event, msg.data, callbacks);
      }
    }
  } finally {
    timeoutCtx.cleanup();
  }
}

export function dispatchSse(
  event: string,
  data: string,
  callbacks: ChatStreamCallbacks,
): void {
  switch (event) {
    case "snapshot": {
      const p = parseSseData<TurnSnapshotEvent>(data);
      if (p) callbacks.onSnapshot?.(p);
      break;
    }
    case "status": {
      const p = parseSseData<ChatStatusEvent>(data);
      if (p?.message) callbacks.onStatus?.(p.message, p);
      break;
    }
    case "thinking": {
      const p = parseSseData<{ text?: string }>(data);
      if (p?.text) callbacks.onThinking?.(p.text);
      break;
    }
    case "token": {
      const p = parseSseData<{ text?: string }>(data);
      if (p?.text) callbacks.onToken?.(p.text);
      break;
    }
    case "meta": {
      const p = parseSseData<ChatMetaEvent>(data);
      if (p) callbacks.onMeta?.(p);
      break;
    }
    case "done": {
      const p = parseSseData<ChatDoneEvent>(data);
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
