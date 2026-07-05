import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

const PROJECT_KEY = "project";
const CONVERSATION_KEY = "conversation";

/** Sincroniza projeto/conversa com query string (?project=&conversation=) para sobreviver a F5. */
export function useWorkspaceUrl() {
  const [searchParams, setSearchParams] = useSearchParams();

  const projectId = searchParams.get(PROJECT_KEY);
  const conversationId = searchParams.get(CONVERSATION_KEY);

  const setWorkspace = useCallback(
    (project: string | null, conversation: string | null) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (project) next.set(PROJECT_KEY, project);
          else next.delete(PROJECT_KEY);
          if (conversation) next.set(CONVERSATION_KEY, conversation);
          else next.delete(CONVERSATION_KEY);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const setProjectId = useCallback(
    (id: string | null) => {
      setWorkspace(id, null);
    },
    [setWorkspace],
  );

  const setConversationId = useCallback(
    (id: string | null) => {
      setWorkspace(projectId, id);
    },
    [projectId, setWorkspace],
  );

  return useMemo(
    () => ({
      projectId,
      conversationId,
      setProjectId,
      setConversationId,
    }),
    [projectId, conversationId, setProjectId, setConversationId],
  );
}
