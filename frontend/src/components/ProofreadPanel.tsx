import { useState } from "react";
import { streamProofread } from "../api/proofread";
import { MODEL_OPTIONS, type ProofreadResult } from "../api/types";
import { downloadText } from "../lib/exportMd";

export function ProofreadPanel() {
  const [text, setText] = useState("");
  const [model, setModel] = useState("gemma4:26b");
  const [isPending, setIsPending] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProofreadResult | null>(null);

  const handleProofread = async () => {
    const source = text.trim();
    if (!source || isPending) return;
    setIsPending(true);
    setStatusMessage("Preparando correção...");
    setError(null);
    setResult(null);
    const correctedParts: string[] = [];
    const changes: ProofreadResult["changes"] = [];
    try {
      await streamProofread(source, model, {
        onStart: (total) => {
          setStatusMessage(total > 1 ? `Texto dividido em ${total} blocos.` : "Corrigindo texto...");
        },
        onStatus: setStatusMessage,
        onBlock: (block) => {
          correctedParts.push(block.corrected_text);
          changes.push(...(block.changes || []));
          setResult({
            corrected_text: correctedParts.join("\n\n"),
            source_text: source,
            changes: [...changes],
            error: null,
            raw_fallback: Boolean(block.raw_fallback),
            raw_response: block.raw_response || undefined,
          });
          setStatusMessage(`Bloco ${block.block_index}/${block.total_blocks} concluído.`);
        },
        onDone: (done) => {
          setResult(done);
          setStatusMessage("Correção concluída.");
        },
        onError: (message) => {
          setError(message);
          setStatusMessage(null);
        },
      });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
      setStatusMessage(null);
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div className="proofread-panel">
      <h2 className="project-panel__title">Corretor ortográfico e gramatical</h2>
      <p className="muted">
        Cole um trecho para corrigir. Não usa PDFs do projeto nem RAG. Prompt
        fixo em <code>proofread_prompts.py</code>.
      </p>

      <label className="toolbar-field">
        <span>Modelo</span>
        <select
          className="select"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          disabled={isPending}
        >
          {MODEL_OPTIONS.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </label>

      <textarea
        className="proofread-input"
        rows={12}
        value={text}
        placeholder="Cole o parágrafo ou extrato aqui..."
        onChange={(e) => setText(e.target.value)}
      />

      <button
        type="button"
        className="btn btn--primary"
        disabled={!text.trim() || isPending}
        onClick={handleProofread}
      >
        {isPending ? "Corrigindo..." : "Corrigir texto"}
      </button>

      {statusMessage && <p className="muted">{statusMessage}</p>}

      {error && <p className="error-banner">{error}</p>}

      {result?.error && <p className="error-banner">{result.error}</p>}

      {result?.raw_fallback && (
        <p className="ingest-alert">
          Resposta fora do formato JSON; exibindo texto bruto.
        </p>
      )}

      {result && !result.error && !result.raw_fallback && (
        <>
          <h3>Texto corrigido (alterações destacadas)</h3>
          {result.highlighted_html ? (
            <div
              className="proofread-highlight"
              dangerouslySetInnerHTML={{ __html: result.highlighted_html }}
            />
          ) : (
            <pre className="proofread-plain">{result.corrected_text}</pre>
          )}

          {result.changes.length > 0 ? (
            <div className="proofread-changes">
              <h3>Alterações</h3>
              <ol>
                {result.changes.map((ch, i) => (
                  <li key={i}>
                    <code>{ch.original}</code> → <code>{ch.corrected}</code>
                    <br />
                    <em>{ch.reason || "—"}</em>
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <p className="success-text">
              Nenhum erro gramatical ou ortográfico identificado.
            </p>
          )}

          <div className="config-actions">
            <button
              type="button"
              className="btn"
              onClick={() =>
                downloadText(
                  "texto_corrigido.txt",
                  result.corrected_text,
                  "text/plain",
                )
              }
            >
              Baixar texto corrigido
            </button>
          </div>
        </>
      )}
    </div>
  );
}
