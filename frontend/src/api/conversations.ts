import { apiFetch } from "./client";
import type { ConversationRecord } from "./types";

export async function fetchConversations(
  projectId: string,
): Promise<ConversationRecord[]> {
  const data = await apiFetch<{ conversations: ConversationRecord[] }>(
    `/projects/${projectId}/conversations`,
  );
  return data.conversations;
}

export async function fetchConversation(
  projectId: string,
  conversationId: string,
): Promise<ConversationRecord> {
  return apiFetch<ConversationRecord>(
    `/projects/${projectId}/conversations/${conversationId}`,
  );
}

export async function createConversation(
  projectId: string,
  title = "Nova conversa",
  modelName = "",
): Promise<ConversationRecord> {
  return apiFetch<ConversationRecord>(`/projects/${projectId}/conversations`, {
    method: "POST",
    body: JSON.stringify({ title, model_name: modelName }),
  });
}

export async function renameConversation(
  projectId: string,
  conversationId: string,
  title: string,
): Promise<ConversationRecord> {
  return apiFetch<ConversationRecord>(
    `/projects/${projectId}/conversations/${conversationId}`,
    {
      method: "PATCH",
      body: JSON.stringify({ title }),
    },
  );
}

export async function deleteConversation(
  projectId: string,
  conversationId: string,
): Promise<void> {
  await apiFetch(`/projects/${projectId}/conversations/${conversationId}`, {
    method: "DELETE",
  });
}
