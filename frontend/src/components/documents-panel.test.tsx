import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchConfig } from "../api/config";
import {
  deleteDocumentsSelected,
  fetchDocuments,
} from "../api/documents";
import { streamReprocessDocuments } from "../lib/ingestStream";
import { DocumentsPanel } from "./DocumentsPanel";

vi.mock("../api/config", () => ({
  fetchConfig: vi.fn(),
}));

vi.mock("../api/documents", () => ({
  fetchDocuments: vi.fn(),
  deleteDocumentsSelected: vi.fn(),
}));

vi.mock("../lib/ingestStream", () => ({
  streamIngest: vi.fn(),
  streamReprocessDocuments: vi.fn(),
}));

function renderWithQueryClient(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("documents panel selection actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchConfig).mockResolvedValue({
      llm_models: ["gemma4:26b"],
      llm_default_model: "gemma4:26b",
      ui_ingest_max_files: 12,
      ui_ingest_max_file_mb: 512,
      ingest_quality_warn_threshold: 0.35,
    });
    vi.mocked(fetchDocuments).mockResolvedValue({
      documents: [
        { file_id: "doc-1", display_name: "Autos.pdf", status: "indexed", pages: 10, chunks: 20 },
        { file_id: "doc-2", display_name: "Oficio.pdf", status: "indexed", pages: 3, chunks: 8 },
      ],
    });
    vi.mocked(deleteDocumentsSelected).mockResolvedValue({
      deleted: true,
      file_ids: ["doc-1"],
      deleted_count: 1,
    });
    vi.mocked(streamReprocessDocuments).mockImplementation(
      async (_projectId, _fileIds, _params, callbacks) => {
        callbacks.onStatus?.("Reprocessando 2 arquivo(s) selecionado(s)...");
        callbacks.onProgress?.({ message: "Extraindo texto", current: 1, total: 2, percent: 50 });
        callbacks.onDone?.({
          files_processed: 2,
          files_total: 2,
          total_pages: 13,
          total_chunks: 28,
          elapsed_s: 1.1,
          per_file: [],
          logs: ["Extraindo texto"],
        });
      },
    );
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("removes only selected documents after confirmation", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<DocumentsPanel projectId="proj-1" />);

    await waitFor(() => {
      expect(screen.getByText("Autos.pdf")).toBeInTheDocument();
      expect(screen.getByText("Oficio.pdf")).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: /^Remover$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Reprocessar$/i })).not.toBeInTheDocument();

    await user.click(screen.getByLabelText("Selecionar Autos.pdf"));
    await user.click(screen.getByRole("button", { name: /Remover selecionados \(1\)/i }));

    expect(window.confirm).toHaveBeenCalled();
    expect(deleteDocumentsSelected).toHaveBeenCalledWith("proj-1", ["doc-1"]);
  });

  it("reprocesses only selected documents and forwards OCR flag", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<DocumentsPanel projectId="proj-1" />);

    await waitFor(() => {
      expect(screen.getByText("Autos.pdf")).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText(/Forçar OCR no próximo ingest/i));
    await user.click(screen.getByLabelText("Selecionar Autos.pdf"));
    await user.click(screen.getByLabelText("Selecionar Oficio.pdf"));
    await user.click(screen.getByRole("button", { name: /Reprocessar selecionados \(2\)/i }));

    expect(window.confirm).toHaveBeenCalled();
    expect(streamReprocessDocuments).toHaveBeenCalledWith(
      "proj-1",
      ["doc-1", "doc-2"],
      { force_ocr: true },
      expect.any(Object),
    );
    expect(screen.getByText(/Reprocessado: 2\/2 arquivos/i)).toBeInTheDocument();
  });
});
