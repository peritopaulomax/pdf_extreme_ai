import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as chatTurnApi from "../api/chat-turn";
import { useChatTurn } from "./useChatTurn";

vi.mock("../api/chat-turn", () => ({
  postChatTurn: vi.fn(),
  subscribeTurnEvents: vi.fn(),
  consumeChatStreamResponse: vi.fn(),
  cancelTurn: vi.fn(),
}));

const idleStreaming = {
  isStreaming: false,
  statusMessage: null,
  liveThinking: null,
  liveAssistant: "",
  error: null,
  warning: null,
  activeTurnId: null,
  streamConversationId: null,
};

describe("useChatTurn", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("test_startTurn_posts_and_subscribes_sse", async () => {
    vi.mocked(chatTurnApi.postChatTurn).mockResolvedValue({
      mode: "async",
      turn_id: "t_1",
      conversation_id: "conv_1",
    });
    vi.mocked(chatTurnApi.subscribeTurnEvents).mockImplementation(
      async (_p, _t, _c, callbacks) => {
        callbacks.onToken?.("Resposta ");
        callbacks.onToken?.("final");
        callbacks.onDone?.({
          assistant_text: "Resposta final",
          conversation_id: "conv_1",
        });
      },
    );

    const { result } = renderHook(() => useChatTurn());
    const onComplete = vi.fn();

    await act(async () => {
      await result.current.sendMessage(
        "proj-1",
        "rag",
        { message: "Oi", conversation_id: null },
        onComplete,
      );
    });

    expect(chatTurnApi.postChatTurn).toHaveBeenCalled();
    expect(chatTurnApi.subscribeTurnEvents).toHaveBeenCalledWith(
      "proj-1",
      "t_1",
      "conv_1",
      expect.any(Object),
      expect.any(AbortSignal),
    );
    expect(onComplete).toHaveBeenCalled();
    await waitFor(() => {
      expect(result.current.streaming.isStreaming).toBe(false);
    });
  });

  it("test_snapshot_prepopulates_liveAssistant_before_tokens", async () => {
    vi.mocked(chatTurnApi.postChatTurn).mockResolvedValue({
      mode: "async",
      turn_id: "t_1",
      conversation_id: "conv_1",
    });
    const snapshots: string[] = [];
    vi.mocked(chatTurnApi.subscribeTurnEvents).mockImplementation(
      async (_p, _t, _c, callbacks) => {
        callbacks.onSnapshot?.({
          assistant_text: "Ja salvo",
          status: "running",
        });
        snapshots.push("snap");
        callbacks.onDone?.({
          assistant_text: "Ja salvo",
          conversation_id: "conv_1",
        });
      },
    );

    const { result } = renderHook(() => useChatTurn());

    await act(async () => {
      await result.current.sendMessage(
        "proj-1",
        "rag",
        { message: "Oi", conversation_id: "conv_1" },
        vi.fn(),
      );
    });

    expect(snapshots.length).toBeGreaterThan(0);
    expect(result.current.streaming.isStreaming).toBe(false);
  });

  it("test_reset_stream_keeps_previous_answer_visible_until_retry_token", async () => {
    vi.mocked(chatTurnApi.postChatTurn).mockResolvedValue({
      mode: "async",
      turn_id: "t_1",
      conversation_id: "conv_1",
    });

    let releaseRetry: (() => void) | undefined;
    vi.mocked(chatTurnApi.subscribeTurnEvents).mockImplementation(
      async (_p, _t, _c, callbacks) => {
        callbacks.onToken?.("Resposta antiga");
        callbacks.onStatus?.("Validacao: repetindo em modo mais profundo...", {
          reset_stream: true,
        });
        await new Promise<void>((resolve) => {
          releaseRetry = () => {
            callbacks.onToken?.("Resposta nova");
            callbacks.onDone?.({
              assistant_text: "Resposta nova",
              conversation_id: "conv_1",
            });
            resolve();
          };
        });
      },
    );

    const { result } = renderHook(() => useChatTurn());
    let sendPromise: Promise<{ error: string | null }> | undefined;

    act(() => {
      sendPromise = result.current.sendMessage(
        "proj-1",
        "rag",
        { message: "Oi", conversation_id: "conv_1" },
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

  it("test_resumeTurn_subscribes_when_active_turn_in_conversation", async () => {
    vi.mocked(chatTurnApi.subscribeTurnEvents).mockImplementation(
      async (_p, _t, _c, callbacks) => {
        callbacks.onDone?.({
          assistant_text: "Retomado",
          conversation_id: "conv_1",
        });
      },
    );

    const { result } = renderHook(() => useChatTurn());

    await act(async () => {
      await result.current.resumeTurn("proj-1", "conv_1", "t_active", vi.fn());
    });

    expect(chatTurnApi.subscribeTurnEvents).toHaveBeenCalledWith(
      "proj-1",
      "t_active",
      "conv_1",
      expect.any(Object),
      expect.any(AbortSignal),
    );
    await waitFor(() => {
      expect(result.current.streaming.isStreaming).toBe(false);
    });
  });

  it("test_detachLocalStream_aborts_without_server_cancel", async () => {
    const { result } = renderHook(() => useChatTurn());
    vi.mocked(chatTurnApi.postChatTurn).mockResolvedValue({
      mode: "async",
      turn_id: "t_1",
      conversation_id: "conv_1",
    });
    let capturedSignal: AbortSignal | undefined;
    vi.mocked(chatTurnApi.subscribeTurnEvents).mockImplementation(
      async (_p, _t, _c, _cb, signal) => {
        capturedSignal = signal;
        await new Promise(() => {});
      },
    );

    act(() => {
      void result.current.sendMessage(
        "proj-1",
        "rag",
        { message: "Oi", conversation_id: null },
        vi.fn(),
      );
    });

    await waitFor(() => expect(result.current.streaming.isStreaming).toBe(true));

    act(() => {
      result.current.detachLocalStream();
    });

    expect(capturedSignal?.aborted).toBe(true);
    expect(chatTurnApi.cancelTurn).not.toHaveBeenCalled();
    expect(result.current.streaming.isStreaming).toBe(false);
  });

  it("test_switchConversation_aborts_local_sse_only", async () => {
    vi.mocked(chatTurnApi.postChatTurn).mockResolvedValue({
      mode: "async",
      turn_id: "t_1",
      conversation_id: "conv_1",
    });
    let capturedSignal: AbortSignal | undefined;
    vi.mocked(chatTurnApi.subscribeTurnEvents).mockImplementation(
      async (_p, _t, _c, _cb, signal) => {
        capturedSignal = signal;
        await new Promise(() => {});
      },
    );

    const { result } = renderHook(() => useChatTurn());

    act(() => {
      void result.current.sendMessage(
        "proj-1",
        "rag",
        { message: "Oi", conversation_id: null },
        vi.fn(),
      );
    });

    await waitFor(() => expect(result.current.streaming.isStreaming).toBe(true));

    act(() => {
      result.current.cancel();
    });

    expect(capturedSignal?.aborted).toBe(true);
  });

  it("test_cancel_calls_api_and_stops_streaming", async () => {
    vi.mocked(chatTurnApi.postChatTurn).mockResolvedValue({
      mode: "async",
      turn_id: "t_1",
      conversation_id: "conv_1",
    });
    vi.mocked(chatTurnApi.subscribeTurnEvents).mockImplementation(
      async () => {
        await new Promise(() => {});
      },
    );

    const { result } = renderHook(() => useChatTurn());

    act(() => {
      void result.current.sendMessage(
        "proj-1",
        "rag",
        { message: "Oi", conversation_id: null },
        vi.fn(),
      );
    });

    await waitFor(() => expect(result.current.streaming.isStreaming).toBe(true));

    await act(async () => {
      result.current.cancel();
    });

    expect(chatTurnApi.cancelTurn).toHaveBeenCalledWith(
      "proj-1",
      "t_1",
      "conv_1",
      expect.any(AbortSignal),
    );
    expect(result.current.streaming.isStreaming).toBe(false);
  });

  it("test_resumeTurn_seeds_live_state_from_disk_before_subscribe", async () => {
    vi.mocked(chatTurnApi.subscribeTurnEvents).mockImplementation(
      async () => {
        await new Promise(() => {});
      },
    );

    const { result } = renderHook(() => useChatTurn());

    act(() => {
      void result.current.resumeTurn(
        "proj-1",
        "conv_1",
        "t_active",
        vi.fn(),
        { assistant_text: "Parcial", thinking: "Pensando" },
      );
    });

    await waitFor(() => {
      expect(result.current.streaming.liveAssistant).toBe("Parcial");
      expect(result.current.streaming.liveThinking).toBe("Pensando");
      expect(result.current.streaming.isStreaming).toBe(true);
    });

    result.current.detachLocalStream();
  });

  it("test_completed_turn_does_not_leave_ghost_streaming_state", async () => {
    vi.mocked(chatTurnApi.subscribeTurnEvents).mockImplementation(
      async (_p, _t, _c, callbacks) => {
        callbacks.onSnapshot?.({
          assistant_text: "Pronto",
          status: "completed",
        });
        callbacks.onDone?.({
          assistant_text: "Pronto",
          conversation_id: "conv_1",
        });
      },
    );

    const { result } = renderHook(() => useChatTurn());

    await act(async () => {
      await result.current.resumeTurn("proj-1", "conv_1", "t_done", vi.fn());
    });

    expect(result.current.streaming.isStreaming).toBe(false);
    expect(result.current.streaming.error).toBeNull();
  });
});
