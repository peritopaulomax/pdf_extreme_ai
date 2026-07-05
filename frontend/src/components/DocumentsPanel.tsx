import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchConfig } from "../api/config";
import {
  deleteDocumentsSelected,
  fetchDocuments,
} from "../api/documents";
import { streamIngest, streamReprocessDocuments } from "../lib/ingestStream";
import type { IngestPerFile, ProjectDocument } from "../api/types";

interface Props {
  projectId: string;
  /** Coluna estreita ao lado do chat (modo RAG). */
  compact?: boolean;
}

export function DocumentsPanel({ projectId, compact }: Props) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [rebuild, setRebuild] = useState(false);
  const [forceOcr, setForceOcr] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [perFile, setPerFile] = useState<IngestPerFile[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const dragDepth = useRef(0);

  const { data: config } = useQuery({
    queryKey: ["config"],
    queryFn: fetchConfig,
  });

  const { data, isLoading } = useQuery({
    queryKey: ["documents", projectId],
    queryFn: () => fetchDocuments(projectId),
  });

  const docs = data?.documents ?? [];

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["documents", projectId] });
    qc.invalidateQueries({ queryKey: ["project", projectId] });
    qc.invalidateQueries({ queryKey: ["projects"] });
  };

  useEffect(() => {
    setSelected((prev) => {
      const validIds = new Set(docs.map((doc) => doc.file_id));
      const next = new Set<string>();
      prev.forEach((fileId) => {
        if (validIds.has(fileId)) next.add(fileId);
      });
      return next.size === prev.size ? prev : next;
    });
  }, [docs]);

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length || ingesting) return;
    setError(null);
    setLogs([]);
    setPerFile([]);
    setProgress(0);

    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("files", f));

    setIngesting(true);
    try {
      await streamIngest(
        projectId,
        fd,
        { rebuild, force_ocr: forceOcr },
        {
          onStatus: (m) => setStatusMsg(m),
          onProgress: (p) => {
            if (p.message) setLogs((prev) => [...prev.slice(-79), p.message!]);
            if (p.percent != null) setProgress(p.percent / 100);
            else if (p.total && p.current)
              setProgress(p.current / p.total);
          },
          onDone: (d) => {
            setProgress(1);
            setStatusMsg(
              `Concluído: ${d.files_processed}/${d.files_total} arquivos | ` +
                `${d.total_pages} páginas | ${d.total_chunks} chunks | ${d.elapsed_s?.toFixed(1)}s`,
            );
            if (d.logs) setLogs(d.logs);
            setPerFile((d.per_file as IngestPerFile[]) || []);
            refresh();
          },
          onError: (m) => setError(m),
        },
      );
    } finally {
      setIngesting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const toggleSelect = (fid: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(fid)) next.delete(fid);
      else next.add(fid);
      return next;
    });
  };

  const selectedDocs = docs.filter((doc) => selected.has(doc.file_id));
  const selectedCount = selectedDocs.length;

  const formatSelectionConfirmation = (action: "reprocess" | "remove") => {
    const title =
      action === "reprocess"
        ? `Reprocessar ${selectedCount} arquivo(s) selecionado(s)?`
        : `Remover ${selectedCount} arquivo(s) selecionado(s)?`;
    const details = selectedDocs
      .slice(0, 8)
      .map((doc) => `- ${doc.display_name || doc.storage_name || doc.file_id}`)
      .join("\n");
    const suffix =
      selectedCount > 8 ? `\n- ... e mais ${selectedCount - 8}` : "";
    const warning =
      action === "reprocess"
        ? "\n\nOs arquivos serão removidos dos índices e ingeridos novamente."
        : "\n\nOs arquivos serão removidos do projeto e dos índices.";
    return `${title}\n\n${details}${suffix}${warning}`;
  };

  const handleRemoveSelected = async () => {
    if (!selectedCount || ingesting) return;
    if (!window.confirm(formatSelectionConfirmation("remove"))) return;
    setIngesting(true);
    setError(null);
    try {
      const fileIds = selectedDocs.map((doc) => doc.file_id);
      const result = await deleteDocumentsSelected(projectId, fileIds);
      setSelected(new Set());
      setStatusMsg(`${result.deleted_count} arquivo(s) removido(s).`);
      setPerFile([]);
      refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setIngesting(false);
    }
  };

  const handleReprocessSelected = async () => {
    if (!selectedCount || ingesting) return;
    if (!window.confirm(formatSelectionConfirmation("reprocess"))) return;
    setIngesting(true);
    setError(null);
    setLogs([]);
    setPerFile([]);
    setProgress(0);
    setStatusMsg("Preparando reprocessamento...");
    try {
      const fileIds = selectedDocs.map((doc) => doc.file_id);
      await streamReprocessDocuments(
        projectId,
        fileIds,
        { force_ocr: forceOcr },
        {
          onStatus: (m) => setStatusMsg(m),
          onProgress: (p) => {
            if (p.message) setLogs((prev) => [...prev.slice(-79), p.message!]);
            if (p.percent != null) setProgress(p.percent / 100);
            else if (p.total && p.current) setProgress(p.current / p.total);
          },
          onDone: (d) => {
            setSelected(new Set());
            setProgress(1);
            setStatusMsg(
              `Reprocessado: ${d.files_processed}/${d.files_total} arquivos | ` +
                `${d.total_pages} páginas | ${d.total_chunks} chunks | ${d.elapsed_s?.toFixed(1)}s`,
            );
            if (d.logs) setLogs(d.logs);
            setPerFile((d.per_file as IngestPerFile[]) || []);
            refresh();
          },
          onError: (m) => setError(m),
        },
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setIngesting(false);
    }
  };

  const threshold = config?.ingest_quality_warn_threshold ?? 0.35;

  const onDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (ingesting) return;
    dragDepth.current += 1;
    setDragOver(true);
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragOver(false);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = 0;
    setDragOver(false);
    if (ingesting) return;
    const files = e.dataTransfer.files;
    if (files?.length) void handleUpload(files);
  };

  const openFilePicker = () => {
    if (!ingesting) fileRef.current?.click();
  };

  return (
    <div className={`project-panel ${compact ? "project-panel--compact" : ""}`}>
      <h2 className="project-panel__title">
        {compact ? "Fontes" : "Base de conhecimento"}
      </h2>
      {config && (
        <p className="muted project-panel__limits">
          Até {config.ui_ingest_max_files} PDF · {config.ui_ingest_max_file_mb} MB
        </p>
      )}

      <div
        className={`drop-zone ${dragOver ? "drop-zone--active" : ""} ${ingesting ? "drop-zone--disabled" : ""}`}
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={openFilePicker}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            openFilePicker();
          }
        }}
        role="button"
        tabIndex={ingesting ? -1 : 0}
        aria-label="Enviar PDFs por clique ou arrastar e soltar"
      >
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,application/pdf"
          multiple
          disabled={ingesting}
          className="drop-zone__input"
          onChange={(e) => handleUpload(e.target.files)}
        />
        <p className="drop-zone__title">
          {dragOver ? "Solte os PDFs aqui" : "Arraste PDFs ou clique para escolher"}
        </p>
        <p className="drop-zone__hint muted">Vários arquivos de uma vez</p>
      </div>

      <div className="project-panel__upload">
        <label className="toolbar-check">
          <input
            type="checkbox"
            checked={rebuild}
            onChange={(e) => setRebuild(e.target.checked)}
            disabled={ingesting}
          />
          Rebuild da base (destrutivo)
        </label>
        <label className="toolbar-check">
          <input
            type="checkbox"
            checked={forceOcr}
            onChange={(e) => setForceOcr(e.target.checked)}
            disabled={ingesting}
          />
          Forçar OCR no próximo ingest
        </label>
      </div>

      {ingesting && (
        <div className="ingest-progress">
          <div
            className="ingest-progress__bar"
            style={{ width: `${Math.round(progress * 100)}%` }}
          />
          <span className="muted">{statusMsg || "Indexando..."}</span>
        </div>
      )}
      {!ingesting && statusMsg && <p className="muted">{statusMsg}</p>}

      {error && <p className="error-banner">{error}</p>}

      <details className="logs-expander" open={!!logs.length}>
        <summary>Logs de ingestão</summary>
        <pre className="logs-pre">
          {logs.length ? logs.join("\n") : "Sem logs nesta sessão."}
        </pre>
      </details>

      {perFile.length > 0 && (
        <IngestAlerts perFile={perFile} threshold={threshold} />
      )}

      {!compact && (
        <h3 className="project-panel__subtitle">Documentos do projeto</h3>
      )}
      {compact && docs.length > 0 && (
        <p className="muted sources-count">{docs.length} arquivo(s)</p>
      )}
      {docs.length > 0 && (
        <div className="project-panel__upload">
          <button
            type="button"
            className="btn btn--sm"
            disabled={ingesting || selectedCount === 0}
            onClick={() => void handleReprocessSelected()}
          >
            Reprocessar selecionados{selectedCount > 0 ? ` (${selectedCount})` : ""}
          </button>
          <button
            type="button"
            className="btn btn--sm btn--danger"
            disabled={ingesting || selectedCount === 0}
            onClick={() => void handleRemoveSelected()}
          >
            Remover selecionados{selectedCount > 0 ? ` (${selectedCount})` : ""}
          </button>
        </div>
      )}
      {isLoading && <p className="muted">Carregando...</p>}
      {!isLoading && docs.length === 0 && (
        <p className="muted">Nenhum documento. Envie PDFs acima.</p>
      )}
      <ul className="doc-list">
        {docs.map((doc) => (
          <DocRow
            key={doc.file_id}
            doc={doc}
            selected={selected.has(doc.file_id)}
            onToggle={() => toggleSelect(doc.file_id)}
            disabled={ingesting}
          />
        ))}
      </ul>
    </div>
  );
}

function DocRow({
  doc,
  selected,
  onToggle,
  disabled,
}: {
  doc: ProjectDocument;
  selected: boolean;
  onToggle: () => void;
  disabled: boolean;
}) {
  return (
    <li className={`doc-row ${selected ? "doc-row--selected" : ""}`}>
      <label className="doc-row__check">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          disabled={disabled}
          aria-label={`Selecionar ${doc.display_name || doc.storage_name || doc.file_id}`}
        />
      </label>
      <div className="doc-row__info">
        <strong>{doc.display_name || doc.storage_name}</strong>
        <span className="muted">
          status={doc.status ?? "?"} | pgs={doc.pages ?? 0} | chunks=
          {doc.chunks ?? 0}
          {doc.size_mb != null ? ` | ${doc.size_mb} MB` : ""}
        </span>
      </div>
    </li>
  );
}

function IngestAlerts({
  perFile,
  threshold,
}: {
  perFile: IngestPerFile[];
  threshold: number;
}) {
  return (
    <div className="ingest-alerts">
      <h4>Alertas da última ingestão</h4>
      {perFile.map((item, i) => {
        const status = String(item.status ?? "");
        const quality = Number(item.quality ?? 1);
        const pages = Number(item.pages ?? 0);
        const src = String(item.source_file || item.file || "?");
        let warn: string | null = null;
        if (status === "empty" || status === "empty_chunks" || pages === 0) {
          warn = `${src}: possível PDF escaneado ou extração falhou.`;
        } else if (quality < threshold) {
          warn = `${src}: qualidade baixa (${quality.toFixed(2)}).`;
        }
        if (!warn) return null;
        return (
          <p key={i} className="ingest-alert">
            {warn}
          </p>
        );
      })}
    </div>
  );
}
