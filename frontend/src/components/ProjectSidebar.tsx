import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createProject,
  deleteProject,
  fetchProjects,
} from "../api/projects";
import type { ProjectRecord } from "../api/types";

interface Props {
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function ProjectSidebar({ selectedId, onSelect }: Props) {
  const qc = useQueryClient();
  const [newName, setNewName] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [deleteInput, setDeleteInput] = useState("");

  const { data: projects = [], isLoading, error } = useQuery({
    queryKey: ["projects"],
    queryFn: fetchProjects,
  });

  const createMut = useMutation({
    mutationFn: (name: string) => createProject(name),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      onSelect(p.project_id);
      setNewName("");
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      if (selectedId === id) {
        const rest = projects.filter((p) => p.project_id !== id);
        onSelect(rest[0]?.project_id ?? "");
      }
      setDeleteConfirm(null);
      setDeleteInput("");
    },
  });

  return (
    <aside className="sidebar sidebar--projects">
      <header className="sidebar__header">
        <h1 className="sidebar__title">PDF Extreme AI</h1>
        <span className="sidebar__badge">v2</span>
      </header>

      <div className="sidebar__section">
        <label className="sidebar__label">Novo projeto</label>
        <div className="sidebar__row">
          <input
            className="input"
            placeholder="Ex.: Caso X"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newName.trim()) {
                createMut.mutate(newName.trim());
              }
            }}
          />
          <button
            type="button"
            className="btn btn--primary btn--sm"
            disabled={!newName.trim() || createMut.isPending}
            onClick={() => createMut.mutate(newName.trim())}
          >
            +
          </button>
        </div>
        {createMut.isError && (
          <p className="error-text">{String(createMut.error)}</p>
        )}
      </div>

      <div className="sidebar__list">
        {isLoading && <p className="muted">Carregando...</p>}
        {error && <p className="error-text">{String(error)}</p>}
        {projects.map((p) => (
          <ProjectItem
            key={p.project_id}
            project={p}
            selected={selectedId === p.project_id}
            onSelect={() => onSelect(p.project_id)}
            onDelete={() => {
              setDeleteConfirm(p.project_id);
              setDeleteInput("");
            }}
          />
        ))}
      </div>

      {deleteConfirm && (
        <div className="modal-overlay" role="dialog">
          <div className="modal">
            <h3>Excluir projeto</h3>
            <p className="muted">
              Ação destrutiva: remove Qdrant, lexical, checkpoint e uploads.
            </p>
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
                  deleteInput !== deleteConfirm || deleteMut.isPending
                }
                onClick={() => deleteMut.mutate(deleteConfirm)}
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

function ProjectItem({
  project,
  selected,
  onSelect,
  onDelete,
}: {
  project: ProjectRecord;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <div className={`list-item ${selected ? "list-item--active" : ""}`}>
      <button type="button" className="list-item__main" onClick={onSelect}>
        <span className="list-item__title">{project.name}</span>
        <span className="list-item__meta">{project.project_id}</span>
      </button>
      <button
        type="button"
        className="list-item__action"
        title="Excluir projeto"
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
      >
        ×
      </button>
    </div>
  );
}
