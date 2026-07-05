import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelTurn,
  consumeChatStreamResponse,
  postChatTurn,
  subscribeTurnEvents,
} from "../api/chat-turn";
import type {
  ChatDoneEvent,
  ChatMessage,
  ChatMetaEvent,
  ChatMode,
  ChatRequestBody,
  RetrievedChunk,
  TurnSnapshotEvent,
} from "../api/types";
import type { ChatStatusEvent } from "../api/chat";

export interface StreamingState {
  isStreaming: boolean;
  statusMessage: string | null;
  liveThinking: string | null;
  liveAssistant: string;
  error: string | null;
  warning: string | null;
  activeTurnId: string | null;
  /** Conversa à qual o stream local pertence (evita bolha fantasma ao trocar de conversa). */
  streamConversationId: string | null;
}

export interface TurnStartedInfo {
  turn_id: string;
  conversation_id: string;
  mode: "async" | "stream";
}

const IDLE_STREAMING: StreamingState = {
  isStreaming: false,
  statusMessage: null,
  liveThinking: null,
  liveAssistant: "",
  error: null,
  warning: null,
  activeTurnId: null,
  streamConversationId: null,
};

export function useChatTurn() {
  const abortRef = useRef<AbortController | null>(null);
  const activeTurnRef = useRef<{
    turnId: string;
    conversationId: string;
    projectId: string;
  } | null>(null);
  const [streaming, setStreaming] = useState<StreamingState>(IDLE_STREAMING);

  const clearLiveStream = useCallback(() => {
    setStreaming((s) => ({
      ...s,
      isStreaming: false,
      statusMessage: null,
      liveThinking: null,
      liveAssistant: "",
      activeTurnId: null,
      streamConversationId: null,
    }));
  }, []);

  /** Fecha só a inscrição SSE local; o job no servidor continua. */
  const detachLocalStream = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    clearLiveStream();
  }, [clearLiveStream]);

  const cancel = useCallback(() => {
    const active = activeTurnRef.current;
    if (active) {
      void cancelTurn(
        active.projectId,
        active.turnId,
        active.conversationId,
        abortRef.current?.signal,
      );
    }
    abortRef.current?.abort();
    abortRef.current = null;
    activeTurnRef.current = null;
    setStreaming(IDLE_STREAMING);
  }, []);

  const buildCallbacks = useCallback(
    (
      ac: AbortController,
      state: {
        assistantText: string;
        thinking: string | null;
        telemetry: string | null;
        retrievedChunks: RetrievedChunk[];
        validationIssues: string[];
        conversationId: string;
        streamError: string | null;
        streamWarning: string | null;
        doneEvent: ChatDoneEvent | null;
        pendingStreamReset: boolean;
      },
    ) => ({
      onSnapshot: (snap: TurnSnapshotEvent) => {
        state.pendingStreamReset = false;
        state.assistantText = snap.assistant_text || "";
        state.thinking = snap.thinking ?? null;
        setStreaming((s) => ({
          ...s,
          liveAssistant: state.assistantText,
          liveThinking: state.thinking,
          statusMessage:
            snap.status === "running" ? "Retomando geração..." : null,
        }));
      },
      onStatus: (message: string, status?: ChatStatusEvent) => {
        if (status?.reset_stream) {
          const visibleAssistant = state.assistantText;
          state.assistantText = "";
          state.thinking = null;
          state.pendingStreamReset = true;
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
      onThinking: (text: string) => {
        state.thinking = text;
        setStreaming((s) => ({
          ...s,
          liveThinking: text,
          statusMessage: null,
        }));
      },
      onToken: (text: string) => {
        if (state.pendingStreamReset) {
          state.assistantText = text;
          state.pendingStreamReset = false;
        } else {
          state.assistantText += text;
        }
        setStreaming((s) => ({
          ...s,
          liveAssistant: state.assistantText,
          statusMessage: null,
        }));
      },
      onMeta: (meta: ChatMetaEvent) => {
        if (meta.conversation_id) state.conversationId = meta.conversation_id;
        if (meta.telemetry) state.telemetry = meta.telemetry;
        if (meta.retrieved_chunks?.length) {
          state.retrievedChunks = meta.retrieved_chunks;
        }
        if (meta.validation_issues?.length) {
          state.validationIssues = meta.validation_issues;
        }
      },
      onDone: (done: ChatDoneEvent) => {
        state.pendingStreamReset = false;
        state.doneEvent = done;
        if (done.assistant_text) state.assistantText = done.assistant_text;
        if (done.thinking) state.thinking = done.thinking;
        if (done.conversation_id) state.conversationId = done.conversation_id;
        if (done.interrupted) {
          state.streamWarning =
            done.interruption_reason ||
            "Resposta interrompida durante stream. Revise e repita se necessário.";
        }
        if (!done.assistant_text?.trim() && !state.streamError) {
          state.streamError =
            done.interruption_reason ||
            "O modelo concluiu sem gerar texto de resposta.";
        }
      },
      onError: (message: string) => {
        state.streamError = message;
      },
    }),
    [],
  );

  const finalizeStreaming = useCallback(
    (
      ac: AbortController,
      state: {
        assistantText: string;
        thinking: string | null;
        streamError: string | null;
        streamWarning: string | null;
      },
    ) => {
      const wasDetached = ac.signal.aborted;
      const showError =
        !wasDetached &&
        state.streamError &&
        !state.assistantText.trim()
          ? state.streamError
          : !wasDetached &&
              !state.assistantText.trim() &&
              !state.streamError
            ? "O modelo concluiu sem gerar texto de resposta."
            : null;
      const warning =
        !wasDetached &&
        (state.streamWarning ||
          (state.streamError && state.assistantText
            ? "Resposta interrompida durante stream."
            : null));

      if (wasDetached) {
        clearLiveStream();
      } else {
        setStreaming({
          isStreaming: false,
          statusMessage: null,
          liveThinking: null,
          liveAssistant: "",
          error: showError,
          warning: warning || null,
          activeTurnId: null,
          streamConversationId: null,
        });
      }
      abortRef.current = null;
      if (!wasDetached) {
        activeTurnRef.current = null;
      }
    },
    [clearLiveStream],
  );

  const runStream = useCallback(
    async (
      projectId: string,
      mode: ChatMode,
      body: ChatRequestBody,
      onComplete: (result: {
        conversationId: string;
        assistantMessage: ChatMessage;
      }) => void,
      onTurnStarted?: (info: TurnStartedInfo) => void,
    ): Promise<{ error: string | null }> => {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      const state = {
        assistantText: "",
        thinking: null as string | null,
        telemetry: null as string | null,
        retrievedChunks: [] as RetrievedChunk[],
        validationIssues: [] as string[],
        conversationId: body.conversation_id || "",
        streamError: null as string | null,
        streamWarning: null as string | null,
        doneEvent: null as ChatDoneEvent | null,
        pendingStreamReset: false,
      };

      setStreaming({
        isStreaming: true,
        statusMessage: "Enviando...",
        liveThinking: null,
        liveAssistant: "",
        error: null,
        warning: null,
        activeTurnId: null,
        streamConversationId: body.conversation_id || null,
      });

      const callbacks = buildCallbacks(ac, state);

      try {
        const posted = await postChatTurn(projectId, mode, body, ac.signal);

        if (posted.mode === "async") {
          state.conversationId = posted.conversation_id;
          activeTurnRef.current = {
            projectId,
            turnId: posted.turn_id,
            conversationId: posted.conversation_id,
          };
          setStreaming((s) => ({
            ...s,
            activeTurnId: posted.turn_id,
            streamConversationId: posted.conversation_id,
            statusMessage: "Gerando resposta...",
          }));
          onTurnStarted?.({
            turn_id: posted.turn_id,
            conversation_id: posted.conversation_id,
            mode: "async",
          });

          await subscribeTurnEvents(
            projectId,
            posted.turn_id,
            posted.conversation_id,
            callbacks,
            ac.signal,
          );
        } else {
          onTurnStarted?.({
            turn_id: "",
            conversation_id: state.conversationId,
            mode: "stream",
          });
          await consumeChatStreamResponse(posted.response, callbacks);
        }

        if (!ac.signal.aborted && state.assistantText) {
          const assistantMessage: ChatMessage = {
            role: "assistant",
            content: state.assistantText,
          };
          if (state.thinking) assistantMessage.thinking = state.thinking;
          if (state.telemetry) assistantMessage.telemetry = state.telemetry;
          if (state.retrievedChunks.length) {
            assistantMessage.retrieved_chunks = state.retrievedChunks;
          }
          if (state.validationIssues.length) {
            assistantMessage.validation_issues = state.validationIssues;
          }
          onComplete({
            conversationId: state.conversationId,
            assistantMessage,
          });
        }
      } catch (e) {
        if (!ac.signal.aborted) {
          state.streamError = e instanceof Error ? e.message : String(e);
        }
      } finally {
        finalizeStreaming(ac, state);
      }

      return {
        error:
          !ac.signal.aborted && !state.assistantText.trim()
            ? state.streamError || "O modelo concluiu sem gerar texto de resposta."
            : null,
      };
    },
    [buildCallbacks, finalizeStreaming],
  );

  const resumeTurn = useCallback(
    async (
      projectId: string,
      conversationId: string,
      turnId: string,
      onComplete: (result: {
        conversationId: string;
        assistantMessage: ChatMessage;
      }) => void,
      initial?: { assistant_text?: string; thinking?: string | null },
    ): Promise<{ ok: boolean }> => {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      activeTurnRef.current = { projectId, turnId, conversationId };

      const seedText = initial?.assistant_text ?? "";
      const seedThinking = initial?.thinking ?? null;

      const state = {
        assistantText: seedText,
        thinking: seedThinking,
        telemetry: null as string | null,
        retrievedChunks: [] as RetrievedChunk[],
        validationIssues: [] as string[],
        conversationId,
        streamError: null as string | null,
        streamWarning: null as string | null,
        doneEvent: null as ChatDoneEvent | null,
        pendingStreamReset: false,
      };

      setStreaming({
        isStreaming: true,
        statusMessage: "Retomando geração...",
        liveThinking: seedThinking,
        liveAssistant: seedText,
        error: null,
        warning: null,
        activeTurnId: turnId,
        streamConversationId: conversationId,
      });

      const callbacks = buildCallbacks(ac, state);

      try {
        await subscribeTurnEvents(
          projectId,
          turnId,
          conversationId,
          callbacks,
          ac.signal,
        );
        if (!ac.signal.aborted && state.assistantText) {
          const assistantMessage: ChatMessage = {
            role: "assistant",
            content: state.assistantText,
          };
          if (state.thinking) assistantMessage.thinking = state.thinking;
          onComplete({ conversationId, assistantMessage });
        }
      } catch (e) {
        if (!ac.signal.aborted) {
          state.streamError = e instanceof Error ? e.message : String(e);
        }
      } finally {
        finalizeStreaming(ac, state);
      }

      return {
        ok: !ac.signal.aborted && !state.streamError,
      };
    },
    [buildCallbacks, finalizeStreaming],
  );

  const sendMessage = useCallback(
    (
      projectId: string,
      mode: ChatMode,
      body: ChatRequestBody,
      onComplete: (result: {
        conversationId: string;
        assistantMessage: ChatMessage;
      }) => void,
      onTurnStarted?: (info: TurnStartedInfo) => void,
    ) => runStream(projectId, mode, body, onComplete, onTurnStarted),
    [runStream],
  );

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  return {
    streaming,
    sendMessage,
    cancel,
    resumeTurn,
    detachLocalStream,
  };
}
