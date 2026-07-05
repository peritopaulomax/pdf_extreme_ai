import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { streamReprocessDocuments } from "./ingestStream";

function makeStreamResponse(chunks: string[]) {
  let index = 0;
  return {
    ok: true,
    body: {
      getReader() {
        return {
          async read() {
            if (index >= chunks.length) {
              return { done: true, value: undefined };
            }
            const encoder = new TextEncoder();
            const value = encoder.encode(chunks[index]);
            index += 1;
            return { done: false, value };
          },
        };
      },
    },
  } as Response;
}

describe("streamReprocessDocuments", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("streams status, progress and done from the reprocess endpoint", async () => {
    fetchMock.mockResolvedValue(
      makeStreamResponse([
        'event: status\ndata: {"message":"Reprocessando 2 arquivo(s) selecionado(s)..."}\n\n',
        'event: progress\ndata: {"message":"Extraindo texto","current":1,"total":2,"percent":50}\n\n',
        'event: done\ndata: {"files_processed":2,"files_total":2,"total_pages":11,"total_chunks":35,"elapsed_s":1.4}\n\n',
      ]),
    );

    const onStatus = vi.fn();
    const onProgress = vi.fn();
    const onDone = vi.fn();

    await streamReprocessDocuments(
      "proj-1",
      ["doc-1", "doc-2"],
      { force_ocr: true },
      { onStatus, onProgress, onDone },
    );

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/projects/proj-1/documents/reprocess/stream"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
      }),
    );
    expect(onStatus).toHaveBeenCalledWith("Reprocessando 2 arquivo(s) selecionado(s)...");
    expect(onProgress).toHaveBeenCalledWith(
      expect.objectContaining({ message: "Extraindo texto", percent: 50 }),
    );
    expect(onDone).toHaveBeenCalledWith(
      expect.objectContaining({ files_processed: 2, files_total: 2, total_chunks: 35 }),
    );
  });
});
