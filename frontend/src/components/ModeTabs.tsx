import type { WorkspaceMode } from "../api/types";

const MODES: { id: WorkspaceMode; label: string }[] = [
  { id: "rag", label: "Autos (RAG)" },
  { id: "free", label: "Chat livre" },
  { id: "proofread", label: "Corretor" },
];

interface Props {
  mode: WorkspaceMode;
  onChange: (mode: WorkspaceMode) => void;
}

export function ModeTabs({ mode, onChange }: Props) {
  return (
    <div className="mode-tabs" role="tablist">
      {MODES.map((m) => (
        <button
          key={m.id}
          type="button"
          role="tab"
          aria-selected={mode === m.id}
          className={`mode-tabs__tab ${mode === m.id ? "mode-tabs__tab--active" : ""}`}
          onClick={() => onChange(m.id)}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}
