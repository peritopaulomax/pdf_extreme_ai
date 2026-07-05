import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useChatStream } from "./useChatStream";
import { streamChat } from "../api/chat";

vi.mock("../api/chat", () => ({
  streamChat: vi.fn(),
}));

describe("useChatStream", () => {
  it("aggregates stream events into the final assistant message", async () => {
    vi.mocked(streamChat).mockImplementation(async (_projectId, _mode, body, callbacks) => {
      callbacks.onStatus?.("Recuperando contexto...");
      callbacks.onThinking?.("Pensando...");
      callbacks.onToken?.("Primeira parte");
      callbacks.onToken?.(" e final");
      callbacks.onMeta?.({
        conversation_id: body.conversation_id ?? "conv-1",
        telemetry: "modo=rag",
        retrieved_chunks: [{ display_name: "Doc.pdf", page: 188, snippet: "Trecho" }],
      });
      callbacks.onDone?.({
        assistant_text: "Primeira parte e final",
        thinking: "Pensando...",
        conversation_id: "conv-1",
      });
    });

    const onComplete = vi.fn();
    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      await result.current.sendMessage(
        "proj-1",
        "rag",
        {
          message: "Pergunta",
          conversation_id: null,
          profile: "preciso",
        },
        onComplete,
      );
    });

    expect(onComplete).toHaveBeenCalledWith({
      conversationId: "conv-1",
      assistantMessage: {
        role: "assistant",
        content: "Primeira parte e final",
        thinking: "Pensando...",
        telemetry: "modo=rag",
        retrieved_chunks: [{ display_name: "Doc.pdf", page: 188, snippet: "Trecho" }],
      },
    });
    expect(result.current.streaming.isStreaming).toBe(false);
    expect(result.current.streaming.error).toBeNull();
    expect(result.current.streaming.warning).toBeNull();
  });

  it("cancels the active stream", async () => {
    let seenAbortSignal: AbortSignal | undefined;
    vi.mocked(streamChat).mockImplementation(async (_projectId, _mode, _body, _callbacks, signal) => {
      seenAbortSignal = signal;
      return new Promise<void>(() => undefined);
    });

    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      void result.current.sendMessage(
        "proj-1",
        "rag",
        { message: "Pergunta", conversation_id: null },
        vi.fn(),
      );
    });

    act(() => {
      result.current.cancel();
    });

    expect(result.current.streaming.isStreaming).toBe(false);
    expect(seenAbortSignal?.aborted).toBe(true);
  });

  it("preserves validation_issues for future low-coverage UI", async () => {
    vi.mocked(streamChat).mockImplementation(async (_projectId, _mode, _body, callbacks) => {
      callbacks.onToken?.("Resposta parcial");
      callbacks.onMeta?.({
        conversation_id: "conv-1",
        telemetry: "modo=rag | fused=2",
        validation_issues: ["Cobertura baixa (fused < 3) para esta pergunta."],
      });
      callbacks.onDone?.({
        assistant_text: "Resposta parcial",
        conversation_id: "conv-1",
      });
    });

    const onComplete = vi.fn();
    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      await result.current.sendMessage(
        "proj-1",
        "rag",
        { message: "Pergunta", conversation_id: null },
        onComplete,
      );
    });

    const assistantMessage = onComplete.mock.calls[0]?.[0]?.assistantMessage as Record<string, unknown>;
    expect(assistantMessage.validation_issues).toEqual([
      "Cobertura baixa (fused < 3) para esta pergunta.",
    ]);
  });

  it("keeps previous answer visible while retry stream is starting", async () => {
    let releaseRetry: (() => void) | undefined;
    vi.mocked(streamChat).mockImplementation(async (_projectId, _mode, body, callbacks) => {
      callbacks.onToken?.("Resposta antiga");
      callbacks.onStatus?.("Validacao: repetindo em modo mais profundo...", {
        reset_stream: true,
      });
      await new Promise<void>((resolve) => {
        releaseRetry = () => {
          callbacks.onToken?.("Resposta nova");
          callbacks.onDone?.({
            assistant_text: "Resposta nova",
            conversation_id: body.conversation_id ?? "conv-1",
          });
          resolve();
        };
      });
    });

    const { result } = renderHook(() => useChatStream());
    let sendPromise: Promise<{ error: string | null }> | undefined;

    act(() => {
      sendPromise = result.current.sendMessage(
        "proj-1",
        "rag",
        { message: "Pergunta", conversation_id: "conv-1" },
        vi.fn(),
      );
    });

    await waitFor(() => {
      expect(result.current.streaming.liveAssistant).toBe("Resposta antiga");
      expect(result.current.streaming.statusMessage).toMatch(/repetindo/i);
    });

    await act(async () => {
      releaseRetry?.();
      await sendPromise;
    });

    expect(result.current.streaming.isStreaming).toBe(false);
    expect(result.current.streaming.error).toBeNull();
  });

  it("shows error when done arrives without assistant text", async () => {
    vi.mocked(streamChat).mockImplementation(async (_projectId, _mode, _body, callbacks) => {
      callbacks.onDone?.({
        assistant_text: "",
        conversation_id: "conv-1",
      });
    });

    const onComplete = vi.fn();
    const { result } = renderHook(() => useChatStream());

    let sendResult: { error: string | null } = { error: null };
    await act(async () => {
      sendResult = await result.current.sendMessage(
        "proj-1",
        "rag",
        { message: "Pergunta", conversation_id: null },
        onComplete,
      );
    });

    expect(onComplete).not.toHaveBeenCalled();
    expect(sendResult.error).toMatch(/sem gerar texto/i);
    expect(result.current.streaming.error).toMatch(/sem gerar texto/i);
  });

  it("keeps partial answer and warns when stream is interrupted", async () => {
    vi.mocked(streamChat).mockImplementation(async (_projectId, _mode, _body, callbacks) => {
      callbacks.onToken?.("Trecho parcial");
      callbacks.onDone?.({
        assistant_text: "Trecho parcial",
        conversation_id: "conv-1",
        interrupted: true,
        interruption_reason: "Sem tokens por 90s; stream interrompido.",
      });
    });

    const onComplete = vi.fn();
    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.sendMessage(
        "proj-1",
        "rag",
        { message: "Pergunta", conversation_id: null },
        onComplete,
      );
    });

    const assistantMessage = onComplete.mock.calls[0]?.[0]?.assistantMessage as Record<string, unknown>;
    expect(assistantMessage.content).toBe("Trecho parcial");
    expect(assistantMessage.validation_issues).toContain(
      "Resposta interrompida durante stream. Revise e repita se necessário.",
    );
    expect(result.current.streaming.warning).toContain("Sem tokens por 90s");
    expect(result.current.streaming.error).toBeNull();
  });
});

