import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createConversation,
  deleteConversation,
  fetchConversations,
  renameConversation,
} from "../api/conversations";
import type { ConversationRecord } from "../api/types";

interface Props {
  projectId: string | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNew: (id: string) => void;
}

export function ConversationList({
  projectId,
  selectedId,
  onSelect,
  onNew,
}: Props) {
  const qc = useQueryClient();
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const { data: conversations = [], isLoading } = useQuery({
    queryKey: ["conversations", projectId],
    queryFn: () => fetchConversations(projectId!),
    enabled: !!projectId,
  });

  const createMut = useMutation({
    mutationFn: () => createConversation(projectId!),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["conversations", projectId] });
      onNew(c.conversation_id);
      onSelect(c.conversation_id);
    },
  });

  const renameMut = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      renameConversation(projectId!, id, title),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["conversations", projectId] });
      setRenamingId(null);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteConversation(projectId!, id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["conversations", projectId] });
      if (selectedId === id) onSelect("");
    },
  });

  if (!projectId) {
    return (
      <aside className="sidebar sidebar--conversations">
        <p className="muted sidebar__empty">Selecione um projeto</p>
      </aside>
    );
  }

  return (
    <aside className="sidebar sidebar--conversations">
      <header className="sidebar__header sidebar__header--compact">
        <h2 className="sidebar__subtitle">Conversas</h2>
        <button
          type="button"
          className="btn btn--primary btn--sm"
          disabled={createMut.isPending}
          onClick={() => createMut.mutate()}
          title="Nova conversa"
        >
          Nova
        </button>
      </header>

      <div className="sidebar__list">
        {isLoading && <p className="muted">Carregando...</p>}
        {conversations.map((c) => (
          <ConversationItem
            key={c.conversation_id}
            conversation={c}
            selected={selectedId === c.conversation_id}
            isRenaming={renamingId === c.conversation_id}
            renameValue={renameValue}
            onSelect={() => onSelect(c.conversation_id)}
            onStartRename={() => {
              setRenamingId(c.conversation_id);
              setRenameValue(c.title);
            }}
            onRenameChange={setRenameValue}
            onRenameSubmit={() => {
              if (renameValue.trim()) {
                renameMut.mutate({
                  id: c.conversation_id,
                  title: renameValue.trim(),
                });
              } else {
                setRenamingId(null);
              }
            }}
            onRenameCancel={() => setRenamingId(null)}
            onDelete={() => {
              if (
                confirm(
                  `Excluir conversa "${c.title}"? Esta ação não pode ser desfeita.`,
                )
              ) {
                deleteMut.mutate(c.conversation_id);
              }
            }}
          />
        ))}
        {!isLoading && conversations.length === 0 && (
          <p className="muted">Nenhuma conversa. Clique em Nova.</p>
        )}
      </div>
    </aside>
  );
}

function ConversationItem({
  conversation,
  selected,
  isRenaming,
  renameValue,
  onSelect,
  onStartRename,
  onRenameChange,
  onRenameSubmit,
  onRenameCancel,
  onDelete,
}: {
  conversation: ConversationRecord;
  selected: boolean;
  isRenaming: boolean;
  renameValue: string;
  onSelect: () => void;
  onStartRename: () => void;
  onRenameChange: (v: string) => void;
  onRenameSubmit: () => void;
  onRenameCancel: () => void;
  onDelete: () => void;
}) {
  if (isRenaming) {
    return (
      <div className="list-item list-item--editing">
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
    <div className={`list-item ${selected ? "list-item--active" : ""}`}>
      <button type="button" className="list-item__main" onClick={onSelect}>
        <span className="list-item__title">{conversation.title}</span>
        <span className="list-item__meta">
          {conversation.messages.length} msgs
        </span>
      </button>
      <div className="list-item__actions">
        <button
          type="button"
          className="list-item__action"
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
          className="list-item__action list-item__action--danger"
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
