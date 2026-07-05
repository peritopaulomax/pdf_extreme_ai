import { ProjectConfigPanel } from "./ProjectConfigPanel";

interface Props {
  open: boolean;
  projectId: string | null;
  onClose: () => void;
}

export function ConfigDrawer({ open, projectId, onClose }: Props) {
  if (!open || !projectId) return null;

  return (
    <div className="drawer-overlay" role="dialog" onClick={onClose}>
      <aside
        className="drawer"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="drawer__header">
          <h2>Memória & regras</h2>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Fechar
          </button>
        </header>
        <div className="drawer__body">
          <ProjectConfigPanel projectId={projectId} />
        </div>
      </aside>
    </div>
  );
}
