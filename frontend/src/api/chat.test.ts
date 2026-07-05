import { beforeEach, describe, expect, it, vi } from "vitest";

import { streamChat } from "./chat";

function makeStreamResponse(chunks: string[]) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });

  return {
    ok: true,
    body: stream,
  } as Response;
}

describe("streamChat", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("dispatches SSE events to the right callbacks", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      makeStreamResponse([
        'event: status\ndata: {"message":"Buscando"}\n\n',
        'event: thinking\ndata: {"text":"Raciocinando"}\n\n',
        'event: token\ndata: {"text":"Olá"}\n\n',
        'event: meta\ndata: {"conversation_id":"c1","telemetry":"modo=rag"}\n\n',
        'event: done\ndata: {"assistant_text":"Olá","conversation_id":"c1"}\n\n',
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);

    const onStatus = vi.fn();
    const onThinking = vi.fn();
    const onToken = vi.fn();
    const onMeta = vi.fn();
    const onDone = vi.fn();
    const onError = vi.fn();

    await streamChat(
      "proj-1",
      "rag",
      { message: "teste", conversation_id: null },
      { onStatus, onThinking, onToken, onMeta, onDone, onError },
    );

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(onStatus).toHaveBeenCalledWith("Buscando");
    expect(onThinking).toHaveBeenCalledWith("Raciocinando");
    expect(onToken).toHaveBeenCalledWith("Olá");
    expect(onMeta).toHaveBeenCalledWith({
      conversation_id: "c1",
      telemetry: "modo=rag",
    });
    expect(onDone).toHaveBeenCalledWith({
      assistant_text: "Olá",
      conversation_id: "c1",
    });
    expect(onError).not.toHaveBeenCalled();
  });

  it("reports backend HTTP errors using the response body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: () => Promise.resolve("Falha do backend"),
      } as Response),
    );

    const onError = vi.fn();

    await streamChat(
      "proj-1",
      "rag",
      { message: "teste", conversation_id: null },
      { onError },
    );

    expect(onError).toHaveBeenCalledWith("Falha do backend");
  });
});

