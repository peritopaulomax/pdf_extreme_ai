import { useCallback, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../context/AuthContext";
import {
  createConversation,
  deleteConversation,
  fetchConversations,
  renameConversation,
} from "../api/conversations";
import {
  createProject,
  deleteProject,
  fetchProjects,
  renameProject,
} from "../api/projects";
import type { WorkspaceMode } from "../api/types";

interface Props {
  projectId: string | null;
  conversationId: string | null;
  mode: WorkspaceMode;
  onSelectProject: (id: string) => void;
  onSelectConversation: (id: string) => void;
  onOpenConfig: () => void;
}

export function UnifiedSidebar({
  projectId,
  conversationId,
  mode,
  onSelectProject,
  onSelectConversation,
  onOpenConfig,
}: Props) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [newProjectName, setNewProjectName] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [deleteInput, setDeleteInput] = useState("");
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(
    () => new Set(),
  );
  const [renamingConvId, setRenamingConvId] = useState<string | null>(null);
  const [renamingProjectId, setRenamingProjectId] = useState<string | null>(
    null,
  );
  const [renameValue, setRenameValue] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const toggleExpanded = useCallback((pid: string) => {
    setExpandedProjects((prev) => {
      const next = new Set(prev);
      if (next.has(pid)) next.delete(pid);
      else next.add(pid);
      return next;
    });
  }, []);

  const { data: projects = [], isLoading: loadingProjects } = useQuery({
    queryKey: ["projects"],
    queryFn: fetchProjects,
  });

  const createProjectMut = useMutation({
    mutationFn: (name: string) => createProject(name),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      onSelectProject(p.project_id);
      setExpandedProjects((prev) => new Set(prev).add(p.project_id));
      setNewProjectName("");
    },
  });

  const deleteProjectMut = useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      setExpandedProjects((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      if (projectId === id) {
        const rest = projects.filter((p) => p.project_id !== id);
        onSelectProject(rest[0]?.project_id ?? "");
      }
      setDeleteConfirm(null);
      setDeleteInput("");
    },
  });

  const renameProjectMut = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      renameProject(id, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      setRenamingProjectId(null);
      setActionError(null);
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const activeProject = projects.find((p) => p.project_id === projectId);

  return (
    <aside className="nav-sidebar">
      <header className="nav-sidebar__brand">
        <span className="nav-sidebar__logo">PDF Extreme AI</span>
      </header>
      {actionError && (
        <p className="nav-sidebar__action-error" role="alert">
          {actionError}
        </p>
      )}

      <div className="nav-sidebar__block nav-sidebar__block--grow">
        <div className="nav-sidebar__block-head">
          <span className="nav-sidebar__label">Projetos</span>
        </div>
        <div className="nav-sidebar__new-row">
          <input
            className="input input--sm"
            placeholder="Novo caso..."
            value={newProjectName}
            onChange={(e) => setNewProjectName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newProjectName.trim()) {
                createProjectMut.mutate(newProjectName.trim());
              }
            }}
          />
          <button
            type="button"
            className="btn btn--primary btn--icon"
            title="Criar projeto"
            disabled={!newProjectName.trim() || createProjectMut.isPending}
            onClick={() => createProjectMut.mutate(newProjectName.trim())}
          >
            +
          </button>
        </div>
        <div className="nav-sidebar__scroll">
          {loadingProjects && (
            <p className="muted nav-sidebar__hint">Carregando...</p>
          )}
          {projects.map((p) => (
            <ProjectAccordion
              key={p.project_id}
              project={p}
              expanded={expandedProjects.has(p.project_id)}
              selected={projectId === p.project_id}
              conversationId={conversationId}
              mode={mode}
              isRenamingProject={renamingProjectId === p.project_id}
              renamingConvId={renamingConvId}
              renameValue={renameValue}
              onToggle={() => toggleExpanded(p.project_id)}
              onSelectProject={() => onSelectProject(p.project_id)}
              onSelectConversation={onSelectConversation}
              onStartRenameProject={() => {
                setRenamingProjectId(p.project_id);
                setRenamingConvId(null);
                setRenameValue(p.name);
              }}
              onStartRenameConv={(cid, title) => {
                setRenamingConvId(cid);
                setRenamingProjectId(null);
                setRenameValue(title);
              }}
              onRenameChange={setRenameValue}
              onRenameProjectSubmit={() => {
                if (renameValue.trim()) {
                  renameProjectMut.mutate({
                    id: p.project_id,
                    name: renameValue.trim(),
                  });
                } else setRenamingProjectId(null);
              }}
              onRenameProjectCancel={() => setRenamingProjectId(null)}
              onDeleteProject={() => {
                setDeleteConfirm(p.project_id);
                setDeleteInput("");
              }}
              onRenameConvCancel={() => setRenamingConvId(null)}
              onActionError={setActionError}
              onClearActionError={() => setActionError(null)}
            />
          ))}
        </div>
      </div>

      <div className="nav-sidebar__user">
        <span className="nav-sidebar__user-name">
          {user?.usuario}
          <span className="muted"> · {user?.perfil}</span>
        </span>
        <div className="nav-sidebar__user-actions">
          {user?.perfil === "admin" && (
            <Link to="/configuracoes/usuarios" className="btn btn--sm btn--ghost">
              Usuários
            </Link>
          )}
          <button
            type="button"
            className="btn btn--sm btn--ghost"
            onClick={async () => {
              await logout();
              navigate("/login");
            }}
          >
            Sair
          </button>
        </div>
      </div>

      {projectId && (
        <div className="nav-sidebar__footer">
          <button
            type="button"
            className="nav-sidebar__config-btn"
            onClick={onOpenConfig}
          >
            Memória & regras
          </button>
          {activeProject && (
            <p className="nav-sidebar__project-meta muted">
              {activeProject.qdrant_collection}
            </p>
          )}
        </div>
      )}

      {deleteConfirm && (
        <div className="modal-overlay" role="dialog">
          <div className="modal">
            <h3>Excluir projeto</h3>
            <p className="muted">Remove Qdrant, lexical, checkpoint e uploads.</p>
            <p>
              Digite <code>{deleteConfirm}</code> para confirmar:
            </p>
            <input
              className="input"
              value={deleteInput}
              onChange={(e) => setDeleteInput(e.target.value)}
            />
            <div className="modal__actions">
              <button
                type="button"
                className="btn"
                onClick={() => setDeleteConfirm(null)}
              >
                Cancelar
              </button>
              <button
                type="button"
                className="btn btn--danger"
                disabled={
                  deleteInput !== deleteConfirm || deleteProjectMut.isPending
                }
                onClick={() => deleteProjectMut.mutate(deleteConfirm)}
              >
                Excluir
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}

function ProjectAccordion({
  project,
  expanded,
  selected,
  conversationId,
  mode,
  isRenamingProject,
  renamingConvId,
  renameValue,
  onToggle,
  onSelectProject,
  onSelectConversation,
  onStartRenameProject,
  onStartRenameConv,
  onRenameChange,
  onRenameProjectSubmit,
  onRenameProjectCancel,
  onDeleteProject,
  onRenameConvCancel,
  onActionError,
  onClearActionError,
}: {
  project: { project_id: string; name: string };
  expanded: boolean;
  selected: boolean;
  conversationId: string | null;
  mode: WorkspaceMode;
  isRenamingProject: boolean;
  renamingConvId: string | null;
  renameValue: string;
  onToggle: () => void;
  onSelectProject: () => void;
  onSelectConversation: (id: string) => void;
  onStartRenameProject: () => void;
  onStartRenameConv: (convId: string, title: string) => void;
  onRenameChange: (v: string) => void;
  onRenameProjectSubmit: () => void;
  onRenameProjectCancel: () => void;
  onDeleteProject: () => void;
  onRenameConvCancel: () => void;
  onActionError: (msg: string) => void;
  onClearActionError: () => void;
}) {
  const qc = useQueryClient();
  const pid = project.project_id;

  const { data: conversations = [], isLoading } = useQuery({
    queryKey: ["conversations", pid],
    queryFn: () => fetchConversations(pid),
    enabled: expanded && mode !== "proofread",
  });

  const createConvMut = useMutation({
    mutationFn: () => createConversation(pid),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["conversations", pid] });
      onSelectProject();
      onSelectConversation(c.conversation_id);
      onClearActionError();
    },
    onError: (e: Error) => onActionError(e.message),
  });

  const renameConvMut = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      renameConversation(pid, id, title),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["conversations", pid] });
      onRenameConvCancel();
      onClearActionError();
    },
    onError: (e: Error) => onActionError(e.message),
  });

  const deleteConvMut = useMutation({
    mutationFn: (id: string) => deleteConversation(pid, id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["conversations", pid] });
      if (conversationId === id) onSelectConversation("");
      onClearActionError();
    },
    onError: (e: Error) => onActionError(e.message),
  });

  return (
    <div className={`project-accordion ${selected ? "project-accordion--selected" : ""}`}>
      <div className="project-accordion__head">
        <button
          type="button"
          className={`project-accordion__chevron ${expanded ? "project-accordion__chevron--open" : ""}`}
          aria-expanded={expanded}
          aria-label={expanded ? "Recolher conversas" : "Expandir conversas"}
          onClick={(e) => {
            e.stopPropagation();
            onToggle();
          }}
        >
          ▶
        </button>
        <div className="project-accordion__project-row">
          <SidebarListItem
            title={project.name}
            meta={project.project_id}
            active={selected}
            isRenaming={isRenamingProject}
            renameValue={renameValue}
            onSelect={onSelectProject}
            onStartRename={onStartRenameProject}
            onRenameChange={onRenameChange}
            onRenameSubmit={onRenameProjectSubmit}
            onRenameCancel={onRenameProjectCancel}
            onDelete={onDeleteProject}
            compact
          />
        </div>
      </div>

      {expanded && mode !== "proofread" && (
        <div className="project-accordion__body">
          <div className="project-accordion__body-head">
            <span className="muted">Conversas</span>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              disabled={createConvMut.isPending}
              onClick={() => createConvMut.mutate()}
            >
              Nova
            </button>
          </div>
          {isLoading && <p className="muted nav-sidebar__hint">...</p>}
          {conversations.map((c) => (
            <SidebarListItem
              key={c.conversation_id}
              title={c.title}
              meta={`${c.messages.length} msgs`}
              active={conversationId === c.conversation_id}
              isRenaming={renamingConvId === c.conversation_id}
              renameValue={renameValue}
              onSelect={() => {
                onSelectProject();
                onSelectConversation(c.conversation_id);
              }}
              onStartRename={() => onStartRenameConv(c.conversation_id, c.title)}
              onRenameChange={onRenameChange}
              onRenameSubmit={() => {
                if (renameValue.trim()) {
                  renameConvMut.mutate({
                    id: c.conversation_id,
                    title: renameValue.trim(),
                  });
                } else onRenameConvCancel();
              }}
              onRenameCancel={onRenameConvCancel}
              onDelete={() => {
                if (confirm(`Excluir conversa "${c.title}"?`)) {
                  deleteConvMut.mutate(c.conversation_id);
                }
              }}
              nested
            />
          ))}
          {!isLoading && conversations.length === 0 && (
            <p className="muted nav-sidebar__hint">Nenhuma conversa ainda.</p>
          )}
        </div>
      )}
    </div>
  );
}

function SidebarListItem({
  title,
  meta,
  active,
  isRenaming,
  renameValue,
  onSelect,
  onStartRename,
  onRenameChange,
  onRenameSubmit,
  onRenameCancel,
  onDelete,
  compact,
  nested,
}: {
  title: string;
  meta?: string;
  active: boolean;
  isRenaming: boolean;
  renameValue: string;
  onSelect: () => void;
  onStartRename: () => void;
  onRenameChange: (v: string) => void;
  onRenameSubmit: () => void;
  onRenameCancel: () => void;
  onDelete: () => void;
  compact?: boolean;
  nested?: boolean;
}) {
  if (isRenaming) {
    return (
      <div className={`nav-item nav-item--editing ${nested ? "nav-item--nested" : ""}`}>
        <input
          className="input input--sm"
          value={renameValue}
          autoFocus
          onChange={(e) => onRenameChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onRenameSubmit();
            if (e.key === "Escape") onRenameCancel();
          }}
          onBlur={onRenameSubmit}
        />
      </div>
    );
  }
  return (
    <div
      className={`nav-item ${active ? "nav-item--active" : ""} ${nested ? "nav-item--nested" : ""} ${compact ? "nav-item--compact" : ""}`}
    >
      <button type="button" className="nav-item__btn" onClick={onSelect}>
        <span className="nav-item__title">{title}</span>
        {meta && !compact && <span className="nav-item__meta">{meta}</span>}
      </button>
      <div className="nav-item__actions">
        <button
          type="button"
          className="nav-item__icon"
          title="Renomear"
          onClick={(e) => {
            e.stopPropagation();
            onStartRename();
          }}
        >
          ✎
        </button>
        <button
          type="button"
          className="nav-item__icon nav-item__icon--danger"
          title="Excluir"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
        >
          ×
        </button>
      </div>
    </div>
  );
}
