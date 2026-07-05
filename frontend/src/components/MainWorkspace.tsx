import type { WorkspaceMode } from "../api/types";
import { ChatPanel } from "./ChatPanel";
import { DocumentsPanel } from "./DocumentsPanel";
import { ModeTabs } from "./ModeTabs";
import { ProofreadPanel } from "./ProofreadPanel";
import { ResizeHandle } from "./ResizeHandle";

interface Props {
  projectId: string | null;
  conversationId: string | null;
  mode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
  onConversationId: (id: string) => void;
  sourcesWidth: number;
  onSourcesWidthChange: (w: number) => void;
  sourcesMin: number;
  sourcesMax: number;
}

export function MainWorkspace({
  projectId,
  conversationId,
  mode,
  onModeChange,
  onConversationId,
  sourcesWidth,
  onSourcesWidthChange,
  sourcesMin,
  sourcesMax,
}: Props) {
  return (
    <div className="workspace">
      <header className="workspace__bar">
        <ModeTabs mode={mode} onChange={onModeChange} />
      </header>

      <div className="workspace__content">
        {mode === "proofread" && (
          <div className="workspace__centered">
            <ProofreadPanel />
          </div>
        )}

        {mode !== "proofread" && !projectId && (
          <div className="workspace__empty">
            <h2>Bem-vindo</h2>
            <p className="muted">
              Crie ou selecione um projeto na barra lateral para começar.
            </p>
          </div>
        )}

        {mode !== "proofread" && projectId && (
          <div
            className={`workspace__main ${mode === "rag" ? "workspace__main--rag" : ""}`}
          >
            {mode === "rag" && (
              <>
                <aside
                  className="sources-column"
                  style={{ width: sourcesWidth, flexShrink: 0 }}
                >
                  <DocumentsPanel projectId={projectId} compact />
                </aside>
                <ResizeHandle
                  getWidth={() => sourcesWidth}
                  onResize={onSourcesWidthChange}
                  min={sourcesMin}
                  max={sourcesMax}
                />
              </>
            )}
            <ChatPanel
              projectId={projectId}
              conversationId={conversationId}
              mode={mode}
              onConversationId={onConversationId}
            />
          </div>
        )}
      </div>
    </div>
  );
}
