import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchConversation } from "../api/conversations";
import { fetchDocuments } from "../api/documents";
import { fetchProject } from "../api/projects";
import { useChatTurn } from "../hooks/useChatTurn";
import type { StreamingState } from "../hooks/useChatTurn";
import type { ChatMessage, ChatMode } from "../api/types";
import { MODEL_OPTIONS } from "../api/types";
import { ChatInput } from "./ChatInput";
import { ChatSettingsPopover } from "./ChatSettingsPopover";
import { MessageList } from "./MessageList";

interface Props {
  projectId: string;
  conversationId: string | null;
  mode: ChatMode;
  onConversationId: (id: string) => void;
}

async function loadConversationFresh(
  qc: ReturnType<typeof useQueryClient>,
  projectId: string,
  conversationId: string,
) {
  return qc.fetchQuery({
    queryKey: ["conversation", projectId, conversationId],
    queryFn: () => fetchConversation(projectId, conversationId),
    staleTime: 0,
  });
}

function isLiveStreamForConversation(
  streaming: StreamingState,
  conversationId: string | null,
): boolean {
  return (
    streaming.isStreaming &&
    !!conversationId &&
    streaming.streamConversationId === conversationId
  );
}

export function ChatPanel({
  projectId,
  conversationId,
  mode,
  onConversationId,
}: Props) {
  const qc = useQueryClient();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [model, setModel] = useState("gemma4:26b");
  const [profile, setProfile] = useState("automatico");
  const [auditMode, setAuditMode] = useState(false);
  const [deepMode, setDeepMode] = useState(false);
  const [useProjectMemory, setUseProjectMemory] = useState(false);
  const { streaming, sendMessage, cancel, resumeTurn, detachLocalStream } =
    useChatTurn();

  const streamingRef = useRef(streaming);
  streamingRef.current = streaming;

  const prevConversationIdRef = useRef<string | null>(conversationId);
  const resumeInFlightRef = useRef<string | null>(null);
  const resumeAttemptsRef = useRef<Record<string, number>>({});

  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => fetchProject(projectId),
  });

  const { data: conversation, isLoading } = useQuery({
    queryKey: ["conversation", projectId, conversationId],
    queryFn: () => fetchConversation(projectId, conversationId!),
    enabled: !!conversationId,
    staleTime: 0,
    refetchOnMount: "always",
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data?.active_turn_id) return false;
      const live = isLiveStreamForConversation(streamingRef.current, conversationId);
      return live ? 2000 : 1500;
    },
  });

  const { data: docsData } = useQuery({
    queryKey: ["documents", projectId],
    queryFn: () => fetchDocuments(projectId),
    enabled: mode === "rag",
  });

  const docCount = docsData?.documents?.length ?? 0;

  const streamBelongsHere = isLiveStreamForConversation(streaming, conversationId);

  const liveAssistant = streamBelongsHere ? streaming.liveAssistant : undefined;
  const liveThinking = streamBelongsHere ? streaming.liveThinking : undefined;
  const statusMessage = streamBelongsHere ? streaming.statusMessage : undefined;
  const activeTurnId =
    streamBelongsHere
      ? streaming.activeTurnId
      : conversation?.active_turn_id ?? null;

  const tryResumeTurn = useCallback(
    async (turnId: string, diskMessages: ChatMessage[]) => {
      if (!conversationId || resumeInFlightRef.current === turnId) return;

      const live = streamingRef.current;
      if (
        live.isStreaming &&
        live.streamConversationId === conversationId &&
        live.activeTurnId === turnId
      ) {
        return;
      }

      const attempts = resumeAttemptsRef.current[turnId] ?? 0;
      if (attempts >= 5) return;

      const assistant = diskMessages.find(
        (m) => m.role === "assistant" && m.turn_id === turnId,
      );
      if (!assistant || assistant.status !== "running") return;

      resumeInFlightRef.current = turnId;
      resumeAttemptsRef.current[turnId] = attempts + 1;

      const result = await resumeTurn(
        projectId,
        conversationId,
        turnId,
        async ({ conversationId: cid }) => {
          resumeAttemptsRef.current[turnId] = 0;
          const data = await loadConversationFresh(qc, projectId, cid);
          if (data?.messages) setMessages(data.messages);
          qc.invalidateQueries({ queryKey: ["conversations", projectId] });
        },
        {
          assistant_text: assistant.content || "",
          thinking: assistant.thinking ?? null,
        },
      );

      resumeInFlightRef.current = null;

      if (!result.ok) {
        window.setTimeout(() => {
          void loadConversationFresh(qc, projectId, conversationId)
            .then((fresh) => {
              if (fresh?.messages) setMessages(fresh.messages);
              const freshAssistant = fresh?.messages?.find(
                (m) => m.role === "assistant" && m.turn_id === turnId,
              );
              if (
                fresh?.active_turn_id === turnId &&
                freshAssistant?.status === "running"
              ) {
                void tryResumeTurn(turnId, fresh.messages || []);
              }
            })
            .catch(() => {
              resumeAttemptsRef.current[turnId] = 5;
            });
        }, 2000);
      }
    },
    [conversationId, projectId, qc, resumeTurn],
  );

  useEffect(() => {
    if (prevConversationIdRef.current !== conversationId) {
      detachLocalStream();
      resumeInFlightRef.current = null;
      prevConversationIdRef.current = conversationId;
    }
  }, [conversationId, detachLocalStream]);

  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      return;
    }
    if (!conversation) return;

    const live = isLiveStreamForConversation(streamingRef.current, conversationId);

    if (!live) {
      setMessages(conversation.messages || []);
    }

    if (conversation.model_name) setModel(conversation.model_name);
  }, [conversation, conversationId]);

  useEffect(() => {
    if (!conversationId || !conversation?.active_turn_id) return;
    const turnId = conversation.active_turn_id;
    const last = conversation.messages[conversation.messages.length - 1];
    if (last?.role !== "assistant" || last.status !== "running") return;
    void tryResumeTurn(turnId, conversation.messages || []);
  }, [
    conversation?.active_turn_id,
    conversation?.updated_at,
    conversationId,
    tryResumeTurn,
    conversation?.messages,
  ]);

  const syncConversationFromServer = async (cid: string) => {
    onConversationId(cid);
    qc.invalidateQueries({ queryKey: ["conversations", projectId] });
    const data = await loadConversationFresh(qc, projectId, cid);
    if (data?.messages) setMessages(data.messages);
    return data;
  };

  const handleSubmit = async () => {
    const text = draft.trim();
    if (!text || streaming.isStreaming) return;

    setDraft("");
    const sessionRules = project?.global_rules?.trim() || "";
    const submitConversationId = conversationId;

    await sendMessage(
      projectId,
      mode,
      {
        message: text,
        conversation_id: conversationId,
        model,
        profile: mode === "rag" ? (deepMode ? "pericial" : profile) : undefined,
        audit_mode: mode === "rag" ? auditMode : false,
        deep_mode: mode === "rag" ? deepMode : false,
        use_project_memory: mode === "free" ? useProjectMemory : true,
        session_rules: sessionRules,
      },
      async ({ conversationId: cid }) => {
        if (conversationId === cid || !conversationId) {
          resumeAttemptsRef.current = {};
          await syncConversationFromServer(cid);
        }
      },
      async (started) => {
        const cid = started.conversation_id;
        onConversationId(cid);
        if (started.turn_id) {
          resumeAttemptsRef.current[started.turn_id] = 0;
        }
        qc.invalidateQueries({ queryKey: ["conversations", projectId] });
        const data = await loadConversationFresh(qc, projectId, cid);
        if (data?.messages) {
          setMessages(data.messages);
        }
      },
    ).then((result) => {
      if (result.error && submitConversationId) {
        void loadConversationFresh(qc, projectId, submitConversationId).then(
          (data) => {
            if (data?.messages) setMessages(data.messages);
          },
        );
      }
    });
  };

  const convTitle = conversation?.title ?? "Nova conversa";

  return (
    <section className="chat-column">
      <header className="chat-column__header">
        <div className="chat-column__titles">
          <h1 className="chat-column__project">{project?.name ?? projectId}</h1>
          <p className="chat-column__conversation muted">{convTitle}</p>
        </div>
        <div className="chat-column__header-actions">
          {mode === "rag" && (
            <span className="sources-badge" title="PDFs no projeto">
              {docCount} fonte{docCount !== 1 ? "s" : ""}
            </span>
          )}
          <ChatSettingsPopover
            mode={mode}
            profile={profile}
            auditMode={auditMode}
            deepMode={deepMode}
            useProjectMemory={useProjectMemory}
            onProfileChange={setProfile}
            onAuditModeChange={setAuditMode}
            onDeepModeChange={setDeepMode}
            onUseProjectMemoryChange={setUseProjectMemory}
            disabled={streaming.isStreaming && streamBelongsHere}
          />
          {streaming.isStreaming && streamBelongsHere && (
            <button type="button" className="btn btn--ghost btn--sm" onClick={cancel}>
              Parar
            </button>
          )}
        </div>
      </header>

      <div className="chat-column__thread-wrap">
        {isLoading && conversationId && (
          <p className="muted chat-column__hint">Carregando conversa...</p>
        )}
        {!conversationId && !streaming.isStreaming && (
          <p className="muted chat-column__hint">
            {mode === "rag" && docCount === 0
              ? "Adicione PDFs em Fontes (à esquerda) ou envie a primeira pergunta."
              : "Clique em Nova conversa ou envie a primeira pergunta."}
          </p>
        )}
        {streaming.error && streamBelongsHere && (
          <p className="error-banner">{streaming.error}</p>
        )}
        {streaming.warning && streamBelongsHere && (
          <p className="error-banner">{streaming.warning}</p>
        )}
        <div className="chat-thread">
          <MessageList
            messages={messages}
            liveAssistant={liveAssistant}
            liveThinking={liveThinking}
            statusMessage={statusMessage}
            activeTurnId={activeTurnId}
            exportContext={
              project
                ? {
                    projectName: project.name,
                    modelName: model,
                    getUserPromptForIndex: (assistantIdx) => {
                      for (let i = assistantIdx - 1; i >= 0; i--) {
                        if (messages[i]?.role === "user")
                          return messages[i].content;
                      }
                      return "";
                    },
                  }
                : undefined
            }
          />
        </div>
      </div>

      <footer className="chat-column__composer">
        <ChatInput
          value={draft}
          onChange={setDraft}
          onSubmit={handleSubmit}
          disabled={streaming.isStreaming && streamBelongsHere}
          placeholder="Pergunte sobre os autos..."
          model={model}
          onModelChange={setModel}
          modelOptions={MODEL_OPTIONS}
        />
      </footer>
    </section>
  );
}
