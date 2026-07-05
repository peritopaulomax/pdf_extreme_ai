import { describe, expect, it } from "vitest";

import { parseSseChunk, parseSseData } from "./sse";

describe("parseSseChunk", () => {
  it("parses multiple complete SSE messages and preserves the remainder", () => {
    const input =
      'event: status\ndata: {"message":"Buscando"}\n\n' +
      'event: token\ndata: {"text":"Olá"}\n\n' +
      'event: meta\ndata: {"conversation_id":"c1"}';

    const { messages, remainder } = parseSseChunk(input);

    expect(messages).toEqual([
      { event: "status", data: '{"message":"Buscando"}' },
      { event: "token", data: '{"text":"Olá"}' },
    ]);
    expect(remainder).toBe('event: meta\ndata: {"conversation_id":"c1"}');
  });

  it("joins multiline data payloads", () => {
    const input =
      "event: token\n" +
      'data: {"text":"Parte 1"}\n' +
      'data: {"text":"Parte 2"}\n\n';

    const { messages, remainder } = parseSseChunk(input);

    expect(messages).toEqual([
      { event: "token", data: '{"text":"Parte 1"}\n{"text":"Parte 2"}' },
    ]);
    expect(remainder).toBe("");
  });
});

describe("parseSseData", () => {
  it("returns parsed JSON payloads", () => {
    expect(parseSseData<{ text: string }>('{"text":"ok"}')).toEqual({ text: "ok" });
  });

  it("returns null for invalid payloads", () => {
    expect(parseSseData("not-json")).toBeNull();
  });
});

