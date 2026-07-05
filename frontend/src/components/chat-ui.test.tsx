import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "./ChatPanel";
import { ChatSettingsPopover } from "./ChatSettingsPopover";
import { MessageList } from "./MessageList";
import type { ChatMessage } from "../api/types";
import { fetchConversation } from "../api/conversations";
import { fetchDocuments } from "../api/documents";
import { fetchProject } from "../api/projects";
import { useChatTurn } from "../hooks/useChatTurn";

vi.mock("../api/projects", () => ({
  fetchProject: vi.fn(),
}));

vi.mock("../api/documents", () => ({
  fetchDocuments: vi.fn(),
}));

vi.mock("../api/conversations", () => ({
  fetchConversation: vi.fn(),
}));

vi.mock("../hooks/useChatTurn", () => ({
  useChatTurn: vi.fn(),
}));

function renderWithQueryClient(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>{ui}</QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("chat UI contracts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchProject).mockResolvedValue({
      project_id: "proj-1",
      name: "Projeto 2021.0091600",
      global_rules: "Use citações com [arquivo, pag.]",
      documents: [],
    });
    vi.mocked(fetchDocuments).mockResolvedValue({
      documents: [{ file_id: "doc-1", display_name: "Autos.pdf" }],
    });
    vi.mocked(fetchConversation).mockResolvedValue({
      conversation_id: "conv-1",
      title: "Conversa",
      model_name: "gemma4:26b",
      messages: [],
    });
    vi.mocked(useChatTurn).mockReturnValue({
      streaming: {
        isStreaming: false,
        statusMessage: null,
        liveThinking: null,
        liveAssistant: "",
        error: null,
        warning: null,
        activeTurnId: null,
        streamConversationId: null,
      },
      sendMessage: vi.fn(),
      cancel: vi.fn(),
      resumeTurn: vi.fn().mockResolvedValue({ ok: true }),
      detachLocalStream: vi.fn(),
    });
  });

  it("renders telemetry and retrieved chunks in the message list", () => {
    const messages: ChatMessage[] = [
      {
        role: "assistant",
        content: "Resposta com suporte documental.",
        telemetry: "modo=rag | fused=8",
        retrieved_chunks: [{ display_name: "Ofício.pdf", page: 182, snippet: "Trecho do ofício" }],
      },
    ];

    render(<MessageList messages={messages} />);

    expect(screen.getByText("modo=rag | fused=8")).toBeInTheDocument();
    expect(screen.getByText(/Trechos usados nesta resposta/i)).toBeInTheDocument();
    expect(screen.getByText("Ofício.pdf")).toBeInTheDocument();
    expect(screen.getByText("p.182")).toBeInTheDocument();
  });

  it("exposes rag profile and audit controls", async () => {
    const user = userEvent.setup();
    const onProfileChange = vi.fn();
    const onAuditModeChange = vi.fn();
    const onUseProjectMemoryChange = vi.fn();

    render(
      <ChatSettingsPopover
        mode="rag"
        profile="automatico"
        auditMode={false}
        useProjectMemory={false}
        onProfileChange={onProfileChange}
        onAuditModeChange={onAuditModeChange}
        onUseProjectMemoryChange={onUseProjectMemoryChange}
      />,
    );

    await user.click(screen.getByTitle("Configurações do chat"));
    await user.selectOptions(screen.getByRole("combobox"), "pericial");
    await user.click(screen.getByLabelText(/Modo auditoria/i));

    expect(onProfileChange).toHaveBeenCalledWith("pericial");
    expect(onAuditModeChange).toHaveBeenCalledWith(true);
    expect(onUseProjectMemoryChange).not.toHaveBeenCalled();
  });

  it("chat settings popover contract exposes deep mode control", async () => {
    const user = userEvent.setup();

    render(
      <ChatSettingsPopover
        mode="rag"
        profile="automatico"
        auditMode={false}
        useProjectMemory={false}
        onProfileChange={vi.fn()}
        onAuditModeChange={vi.fn()}
        onUseProjectMemoryChange={vi.fn()}
      />,
    );

    await user.click(screen.getByTitle("Configurações do chat"));

    expect(screen.getByLabelText(/Modo profundo/i)).toBeInTheDocument();
  });

  it("message list contract for low coverage banner", () => {
    const messages = [
      {
        role: "assistant",
        content: "Resposta parcial.",
        telemetry: "modo=rag | fused=2",
        validation_issues: ["Cobertura baixa (fused < 3) para esta pergunta."],
      },
    ] as unknown as ChatMessage[];

    render(<MessageList messages={messages} />);

    expect(screen.getByText(/Cobertura baixa/i)).toBeInTheDocument();
  });

  it("test_chat_panel_shows_running_assistant_from_server_on_load", async () => {
    vi.mocked(fetchConversation).mockResolvedValue({
      conversation_id: "conv-1",
      title: "Conversa",
      model_name: "gemma4:26b",
      active_turn_id: "t_running",
      messages: [
        { role: "user", content: "Pergunta", turn_id: "t_running" },
        {
          role: "assistant",
          content: "Parcial no servidor",
          status: "running",
          turn_id: "t_running",
        },
      ],
    });

    renderWithQueryClient(
      <ChatPanel
        projectId="proj-1"
        conversationId="conv-1"
        mode="rag"
        onConversationId={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Parcial no servidor")).toBeInTheDocument();
    });
  });

  it("test_chat_panel_resumes_sse_when_active_turn_present", async () => {
    const resumeTurn = vi.fn().mockResolvedValue({ ok: true });
    vi.mocked(fetchConversation).mockResolvedValue({
      conversation_id: "conv-1",
      title: "Conversa",
      model_name: "gemma4:26b",
      active_turn_id: "t_running",
      messages: [
        { role: "user", content: "Pergunta", turn_id: "t_running" },
        {
          role: "assistant",
          content: "",
          status: "running",
          turn_id: "t_running",
        },
      ],
    });
    vi.mocked(useChatTurn).mockReturnValue({
      streaming: {
        isStreaming: false,
        statusMessage: null,
        liveThinking: null,
        liveAssistant: "",
        error: null,
        warning: null,
        activeTurnId: null,
      },
      sendMessage: vi.fn(),
      cancel: vi.fn(),
      resumeTurn,
      detachLocalStream: vi.fn(),
    });

    renderWithQueryClient(
      <ChatPanel
        projectId="proj-1"
        conversationId="conv-1"
        mode="rag"
        onConversationId={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(resumeTurn).toHaveBeenCalledWith(
        "proj-1",
        "conv-1",
        "t_running",
        expect.any(Function),
        expect.objectContaining({ assistant_text: "" }),
      );
    });
  });

  it("submits rag settings through ChatPanel", async () => {
    const user = userEvent.setup();
    const sendMessage = vi.fn(async (_projectId, _mode, _body, onComplete) => {
      onComplete({
        conversationId: "conv-1",
        assistantMessage: {
          role: "assistant",
          content: "Resposta final",
        },
      });
      return { error: null };
    });
    const onConversationId = vi.fn();

    vi.mocked(useChatTurn).mockReturnValue({
      streaming: {
        isStreaming: false,
        statusMessage: null,
        liveThinking: null,
        liveAssistant: "",
        error: null,
        warning: null,
        activeTurnId: null,
      },
      sendMessage,
      cancel: vi.fn(),
      resumeTurn: vi.fn().mockResolvedValue({ ok: true }),
      detachLocalStream: vi.fn(),
    });

    renderWithQueryClient(
      <ChatPanel
        projectId="proj-1"
        conversationId={null}
        mode="rag"
        onConversationId={onConversationId}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("1 fonte")).toBeInTheDocument();
    });

    await user.click(screen.getByTitle("Configurações do chat"));
    await user.selectOptions(screen.getAllByRole("combobox")[0], "pericial");
    await user.click(screen.getByLabelText(/Modo auditoria/i));
    await user.type(screen.getByPlaceholderText("Pergunte sobre os autos..."), "Quais ofícios foram expedidos?");
    await user.click(screen.getByRole("button", { name: "Enviar" }));

    expect(sendMessage).toHaveBeenCalledWith(
      "proj-1",
      "rag",
      expect.objectContaining({
        message: "Quais ofícios foram expedidos?",
        profile: "pericial",
        audit_mode: true,
        use_project_memory: true,
        session_rules: "Use citações com [arquivo, pag.]",
      }),
      expect.any(Function),
      expect.any(Function),
    );
    expect(onConversationId).toHaveBeenCalledWith("conv-1");
  });
});

