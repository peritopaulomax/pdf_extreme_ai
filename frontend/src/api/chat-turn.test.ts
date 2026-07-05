import { beforeEach, describe, expect, it, vi } from "vitest";

import { dispatchSse } from "./chat";
import {
  cancelTurn,
  consumeChatStreamResponse,
  postChatTurn,
  subscribeTurnEvents,
} from "./chat-turn";

vi.mock("./client", () => ({
  API_URL: "http://test",
}));

describe("chat-turn api", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("postChatTurn returns async payload on 202", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 202,
        json: async () => ({
          turn_id: "t_abc",
          conversation_id: "conv_1",
        }),
      }),
    );

    const result = await postChatTurn("proj-1", "rag", {
      message: "Oi",
      conversation_id: null,
    });
    expect(result).toEqual({
      mode: "async",
      turn_id: "t_abc",
      conversation_id: "conv_1",
    });
  });

  it("dispatchSse handles snapshot event", () => {
    const onSnapshot = vi.fn();
    dispatchSse(
      "snapshot",
      JSON.stringify({
        assistant_text: "Parcial",
        status: "running",
      }),
      { onSnapshot },
    );
    expect(onSnapshot).toHaveBeenCalledWith({
      assistant_text: "Parcial",
      status: "running",
    });
  });

  it("subscribeTurnEvents calls turn events endpoint", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'event: snapshot\ndata: {"assistant_text":"","status":"running"}\n\n',
          ),
        );
        controller.enqueue(
          encoder.encode(
            'event: done\ndata: {"assistant_text":"Ok","conversation_id":"conv_1"}\n\n',
          ),
        );
        controller.close();
      },
    });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body,
      }),
    );

    const onDone = vi.fn();
    await subscribeTurnEvents("proj-1", "t_abc", "conv_1", { onDone });
    expect(fetch).toHaveBeenCalledWith(
      "http://test/projects/proj-1/chat/turns/t_abc/events?conversation_id=conv_1",
      expect.objectContaining({ method: "GET" }),
    );
    expect(onDone).toHaveBeenCalled();
  });

  it("cancelTurn posts to cancel endpoint", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
    await cancelTurn("proj-1", "t_abc", "conv_1");
    expect(fetch).toHaveBeenCalledWith(
      "http://test/projects/proj-1/chat/turns/t_abc/cancel?conversation_id=conv_1",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("consumeChatStreamResponse parses token events", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode('event: token\ndata: {"text":"Hi"}\n\n'),
        );
        controller.close();
      },
    });

    const onToken = vi.fn();
    await consumeChatStreamResponse({ ok: true, body } as Response, { onToken });
    expect(onToken).toHaveBeenCalledWith("Hi");
  });
});
