import { useCallback, useRef, useState } from "react";
import { streamChat } from "../api/chat";
import type {
  ChatDoneEvent,
  ChatMessage,
  ChatMetaEvent,
  ChatMode,
  ChatRequestBody,
  RetrievedChunk,
} from "../api/types";

export interface StreamingState {
  isStreaming: boolean;
  statusMessage: string | null;
  liveThinking: string | null;
  liveAssistant: string;
  error: string | null;
  warning: string | null;
}

export function useChatStream() {
  const abortRef = useRef<AbortController | null>(null);
  const [streaming, setStreaming] = useState<StreamingState>({
    isStreaming: false,
    statusMessage: null,
    liveThinking: null,
    liveAssistant: "",
    error: null,
    warning: null,
  });

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming((s) => ({ ...s, isStreaming: false }));
  }, []);

  const sendMessage = useCallback(
    async (
      projectId: string,
      mode: ChatMode,
      body: ChatRequestBody,
      onComplete: (result: {
        conversationId: string;
        assistantMessage: ChatMessage;
      }) => void,
    ): Promise<{ error: string | null }> => {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      let assistantText = "";
      let thinking: string | null = null;
      let telemetry: string | null = null;
      let retrievedChunks: RetrievedChunk[] = [];
      let validationIssues: string[] = [];
      let conversationId = body.conversation_id || "";
      let streamError: string | null = null;
      let streamWarning: string | null = null;
      let doneEvent: ChatDoneEvent | null = null;
      let pendingStreamReset = false;

      setStreaming({
        isStreaming: true,
        statusMessage: "Enviando...",
        liveThinking: null,
        liveAssistant: "",
        error: null,
        warning: null,
      });

      try {
        await streamChat(
          projectId,
          mode,
          body,
          {
            onStatus: (message, status) => {
              if (status?.reset_stream) {
                const visibleAssistant = assistantText;
                assistantText = "";
                thinking = null;
                pendingStreamReset = true;
                setStreaming((s) => ({
                  ...s,
                  statusMessage: message,
                  liveAssistant: visibleAssistant || s.liveAssistant,
                  liveThinking: null,
                }));
                return;
              }
              setStreaming((s) => ({ ...s, statusMessage: message }));
            },
            onThinking: (text) => {
              thinking = text;
              setStreaming((s) => ({
                ...s,
                liveThinking: text,
                statusMessage: null,
              }));
            },
            onToken: (text) => {
              if (pendingStreamReset) {
                assistantText = text;
                pendingStreamReset = false;
              } else {
                assistantText += text;
              }
              setStreaming((s) => ({
                ...s,
                liveAssistant: assistantText,
                statusMessage: null,
              }));
            },
            onMeta: (meta: ChatMetaEvent) => {
              if (meta.conversation_id) conversationId = meta.conversation_id;
              if (meta.telemetry) telemetry = meta.telemetry;
              if (meta.retrieved_chunks?.length) {
                retrievedChunks = meta.retrieved_chunks;
              }
              if (meta.validation_issues?.length) {
                validationIssues = meta.validation_issues;
              }
            },
            onDone: (done) => {
              pendingStreamReset = false;
              doneEvent = done;
              if (done.assistant_text) assistantText = done.assistant_text;
              if (done.thinking) thinking = done.thinking;
              if (done.conversation_id) conversationId = done.conversation_id;
              if (done.interrupted) {
                streamWarning =
                  done.interruption_reason ||
                  "Resposta interrompida durante stream. Revise e repita se necessário.";
              }
              if (!done.assistant_text?.trim() && !streamError) {
                streamError =
                  done.interruption_reason ||
                  "O modelo concluiu sem gerar texto de resposta.";
              }
            },
            onError: (message) => {
              streamError = message;
            },
          },
          ac.signal,
        );

        if (!ac.signal.aborted && assistantText) {
          const assistantMessage: ChatMessage = {
            role: "assistant",
            content: assistantText,
          };
          if (thinking) assistantMessage.thinking = thinking;
          if (telemetry) assistantMessage.telemetry = telemetry;
          if (retrievedChunks.length) {
            assistantMessage.retrieved_chunks = retrievedChunks;
          }
          if (validationIssues.length) {
            assistantMessage.validation_issues = validationIssues;
          }
          if (streamError || doneEvent?.interrupted) {
            const issue =
              "Resposta interrompida durante stream. Revise e repita se necessário.";
            const merged = new Set(assistantMessage.validation_issues ?? []);
            merged.add(issue);
            assistantMessage.validation_issues = Array.from(merged);
          }
          onComplete({ conversationId, assistantMessage });
        }
      } catch (e) {
        if (!ac.signal.aborted) {
          streamError = e instanceof Error ? e.message : String(e);
        }
      } finally {
        if (!ac.signal.aborted) {
          const showError =
            streamError && !assistantText.trim()
              ? streamError
              : !assistantText.trim() && !streamError
                ? "O modelo concluiu sem gerar texto de resposta."
                : null;
          const warning =
            streamWarning || (streamError && assistantText ? "Resposta interrompida durante stream." : null);
          setStreaming({
            isStreaming: false,
            statusMessage: null,
            liveThinking: null,
            liveAssistant: "",
            error: showError,
            warning,
          });
        }
        abortRef.current = null;
      }

      return {
        error:
          !ac.signal.aborted && !assistantText.trim()
            ? streamError || "O modelo concluiu sem gerar texto de resposta."
            : null,
      };
    },
    [],
  );

  return { streaming, sendMessage, cancel };
}
