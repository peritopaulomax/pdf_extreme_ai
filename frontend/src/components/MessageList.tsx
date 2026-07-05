import { useState } from "react";
import { ThinkingBlock } from "./ThinkingBlock";
import { MarkdownContent } from "./MarkdownContent";
import type { ChatMessage, RetrievedChunk } from "../api/types";
import { buildExportMarkdown, downloadText } from "../lib/exportMd";
import { copyToClipboard } from "../lib/clipboard";

interface ExportContext {
  projectName: string;
  modelName: string;
  getUserPromptForIndex: (assistantIndex: number) => string;
}

interface Props {
  messages: ChatMessage[];
  liveAssistant?: string;
  liveThinking?: string | null;
  statusMessage?: string | null;
  /** turn_id do assistant em geração; evita duplicar bolha se já há running no histórico. */
  activeTurnId?: string | null;
  exportContext?: ExportContext;
}

export function MessageList({
  messages,
  liveAssistant,
  liveThinking,
  statusMessage,
  activeTurnId,
  exportContext,
}: Props) {
  const hasRunningInHistory =
    !!activeTurnId &&
    messages.some(
      (m) =>
        m.role === "assistant" &&
        m.turn_id === activeTurnId &&
        m.status === "running",
    );

  const showLiveBubble =
    (liveAssistant || liveThinking || statusMessage) && !hasRunningInHistory;

  return (
    <div className="messages">
      {messages.map((m, i) => (
        <MessageBubble
          key={m.turn_id ? `${m.role}-${m.turn_id}` : `${m.role}-${i}`}
          message={m}
          index={i}
          isStreamingTurn={
            m.role === "assistant" &&
            m.status === "running" &&
            m.turn_id === activeTurnId
          }
          liveThinking={
            m.role === "assistant" &&
            m.status === "running" &&
            m.turn_id === activeTurnId
              ? (liveThinking ?? null)
              : undefined
          }
          liveContent={
            m.role === "assistant" &&
            m.status === "running" &&
            m.turn_id === activeTurnId
              ? liveAssistant
              : undefined
          }
          statusMessage={
            m.role === "assistant" &&
            m.status === "running" &&
            m.turn_id === activeTurnId
              ? statusMessage
              : undefined
          }
          exportContext={exportContext}
        />
      ))}
      {showLiveBubble && (
        <div className="message message--assistant message--streaming">
          {statusMessage && !liveAssistant && (
            <p className="message__status">{statusMessage}</p>
          )}
          {liveThinking && <ThinkingBlock thinking={liveThinking} defaultExpanded />}
          {liveAssistant && (
            <div className="message__content">
              <MarkdownContent text={liveAssistant} />
              <span className="cursor-blink" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MessageBubble({
  message,
  index,
  isStreamingTurn,
  liveThinking,
  liveContent,
  statusMessage,
  exportContext,
}: {
  message: ChatMessage;
  index: number;
  isStreamingTurn?: boolean;
  liveThinking?: string | null;
  liveContent?: string;
  statusMessage?: string | null;
  exportContext?: ExportContext;
}) {
  const isUser = message.role === "user";
  const displayContent =
    isStreamingTurn && liveContent !== undefined
      ? liveContent || message.content
      : message.content;
  const displayThinking =
    isStreamingTurn && liveThinking !== undefined
      ? liveThinking
      : message.thinking;

  const canExport =
    !isUser && exportContext && displayContent.trim().length > 0 && !isStreamingTurn;

  const [copyState, setCopyState] = useState<"idle" | "ok" | "fail">("idle");

  const buildMd = () => {
    if (!exportContext) return "";
    return buildExportMarkdown({
      projectName: exportContext.projectName,
      modelName: exportContext.modelName,
      userPrompt: exportContext.getUserPromptForIndex(index),
      assistantMessage: message,
    });
  };

  const handleCopy = async () => {
    const md = buildMd();
    const ok = await copyToClipboard(md);
    setCopyState(ok ? "ok" : "fail");
    window.setTimeout(() => setCopyState("idle"), 2500);
  };

  const handleDownload = () => {
    const md = buildMd();
    downloadText(`resposta_${index}.md`, md, "text/markdown");
  };

  return (
    <div
      className={`message message--${message.role}${isStreamingTurn ? " message--streaming" : ""}`}
    >
      {isUser && <div className="message__role">Você</div>}
      {displayThinking && <ThinkingBlock thinking={displayThinking} />}
      {(displayContent || isStreamingTurn) && (
        <div className="message__content">
          {displayContent ? (
            <MarkdownContent text={displayContent} />
          ) : isStreamingTurn ? (
            <p className="muted">{statusMessage || "Gerando resposta..."}</p>
          ) : null}
          {isStreamingTurn && liveContent !== undefined && (
            <span className="cursor-blink" />
          )}
        </div>
      )}
      {message.telemetry && !isStreamingTurn && (
        <p className="message__telemetry">{message.telemetry}</p>
      )}
      {message.validation_issues && message.validation_issues.length > 0 && (
        <div className="message__warning" role="alert">
          {message.validation_issues.map((issue, idx) => (
            <p key={idx}>{issue}</p>
          ))}
        </div>
      )}
      {message.retrieved_chunks && message.retrieved_chunks.length > 0 && (
        <RetrievedChunks chunks={message.retrieved_chunks} />
      )}
      {canExport && (
        <div className="message__export">
          <button type="button" className="btn btn--sm" onClick={handleCopy}>
            {copyState === "ok"
              ? "Copiado!"
              : copyState === "fail"
                ? "Falha ao copiar"
                : "Copiar Markdown"}
          </button>
          <button type="button" className="btn btn--sm" onClick={handleDownload}>
            Exportar .md
          </button>
        </div>
      )}
    </div>
  );
}

function RetrievedChunks({ chunks }: { chunks: RetrievedChunk[] }) {
  return (
    <details className="chunks-expander">
      <summary>Trechos usados nesta resposta ({chunks.length})</summary>
      <ul className="chunks-list">
        {chunks.map((c, i) => (
          <li key={i}>
            {(c.display_name || c.source_file) && (
              <span className="chunks-list__source">
                {c.display_name || c.source_file}
              </span>
            )}
            {c.page != null && c.page > 0 && (
              <span className="chunks-list__page">p.{c.page}</span>
            )}
            {c.doc_type && (
              <span className="chunks-list__page">
                {c.doc_type}
                {c.doc_number ? ` ${c.doc_number}` : ""}
              </span>
            )}
            {c.parent_context && (
              <span className="chunks-list__page">contexto-pai</span>
            )}
            {c.score != null && (
              <span className="chunks-list__score">score {c.score.toFixed(3)}</span>
            )}
            <p>{c.snippet || ""}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}
