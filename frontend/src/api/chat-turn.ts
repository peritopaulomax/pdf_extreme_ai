import { API_URL } from "./client";
import { dispatchSse, type ChatStreamCallbacks } from "./chat";
import { parseSseChunk } from "../lib/sse";
import type { ChatMode, ChatRequestBody, TurnStartResponse } from "./types";

export type ChatPostResult =
  | { mode: "async"; turn_id: string; conversation_id: string }
  | { mode: "stream"; response: Response };

export async function postChatTurn(
  projectId: string,
  mode: ChatMode,
  body: ChatRequestBody,
  signal?: AbortSignal,
): Promise<ChatPostResult> {
  const url = `${API_URL}/projects/${projectId}/chat/${mode}`;
  const res = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
    },
    body: JSON.stringify(body),
    signal,
  });

  if (res.status === 202) {
    const data = (await res.json()) as TurnStartResponse;
    return {
      mode: "async",
      turn_id: data.turn_id,
      conversation_id: data.conversation_id,
    };
  }

  return { mode: "stream", response: res };
}

export async function consumeChatStreamResponse(
  res: Response,
  callbacks: ChatStreamCallbacks,
): Promise<void> {
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
}

export async function subscribeTurnEvents(
  projectId: string,
  turnId: string,
  conversationId: string,
  callbacks: ChatStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const params = new URLSearchParams({ conversation_id: conversationId });
  const url = `${API_URL}/projects/${projectId}/chat/turns/${turnId}/events?${params}`;
  const res = await fetch(url, {
    method: "GET",
    credentials: "include",
    headers: { Accept: "text/event-stream" },
    signal,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    callbacks.onError?.(text || `HTTP ${res.status}`);
    return;
  }

  await consumeChatStreamResponse(res, callbacks);
}

export async function cancelTurn(
  projectId: string,
  turnId: string,
  conversationId: string,
  signal?: AbortSignal,
): Promise<void> {
  const params = new URLSearchParams({ conversation_id: conversationId });
  const url = `${API_URL}/projects/${projectId}/chat/turns/${turnId}/cancel?${params}`;
  await fetch(url, {
    method: "POST",
    credentials: "include",
    signal,
  });
}
