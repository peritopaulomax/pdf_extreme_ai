import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchMemory,
  fetchRules,
  saveMemory,
  saveRules,
} from "../api/projectSettings";

interface Props {
  projectId: string;
}

export function ProjectConfigPanel({ projectId }: Props) {
  const qc = useQueryClient();
  const [rules, setRules] = useState("");
  const [memory, setMemory] = useState("");

  const { data: rulesData } = useQuery({
    queryKey: ["rules", projectId],
    queryFn: () => fetchRules(projectId),
  });

  const { data: memoryData } = useQuery({
    queryKey: ["memory", projectId],
    queryFn: () => fetchMemory(projectId),
  });

  useEffect(() => {
    if (rulesData) setRules(rulesData.global_rules);
  }, [rulesData]);

  useEffect(() => {
    if (memoryData) setMemory(memoryData.text);
  }, [memoryData]);

  const saveRulesMut = useMutation({
    mutationFn: () => saveRules(projectId, rules),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project", projectId] });
      qc.invalidateQueries({ queryKey: ["rules", projectId] });
    },
  });

  const saveMemoryMut = useMutation({
    mutationFn: () => saveMemory(projectId, memory),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memory", projectId] }),
  });

  return (
    <div className="project-panel">
      <section className="config-section">
        <h2 className="project-panel__title">Instruções globais do projeto</h2>
        <p className="muted">
          Regras extras para respostas (persistidas neste projeto, máx. 4000
          caracteres).
        </p>
        <textarea
          className="config-textarea"
          rows={8}
          maxLength={4000}
          value={rules}
          onChange={(e) => setRules(e.target.value)}
        />
        <div className="config-actions">
          <button
            type="button"
            className="btn btn--primary"
            disabled={saveRulesMut.isPending}
            onClick={() => saveRulesMut.mutate()}
          >
            Salvar regras
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => setRules("")}
          >
            Limpar
          </button>
        </div>
      </section>

      <section className="config-section">
        <h2 className="project-panel__title">Memória do caso</h2>
        <p className="muted">
          Contexto editável (Markdown). Pode ser incluído no chat livre com a
          opção na aba Chat.
        </p>
        <textarea
          className="config-textarea"
          rows={14}
          value={memory}
          onChange={(e) => setMemory(e.target.value)}
          placeholder="Partes, eventos, notas do caso..."
        />
        <div className="config-actions">
          <button
            type="button"
            className="btn btn--primary"
            disabled={saveMemoryMut.isPending}
            onClick={() => saveMemoryMut.mutate()}
          >
            Salvar memória
          </button>
        </div>
      </section>
    </div>
  );
}
