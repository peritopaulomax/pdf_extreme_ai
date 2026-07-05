# PDF Extreme AI — Core Summary

## O que é

Motor RAG compartilhado entre API FastAPI e UI Streamlit legada. Especializado em documentos jurídicos.

## Componentes principais

| Módulo | Função |
|---|---|
| `ingest_service.py` | Pipeline de ingestão de PDFs |
| `pdf_extraction.py` | Extração de texto e OCR condicional |
| `retrieval_pipeline.py` | HybridRetriever semântico+lexical |
| `query_planner.py` | Perfil e intent da pergunta |
| `query_expansion.py` | Expansão léxica/forense |
| `retrieval_lexical.py` | Índice FTS5 chunk-level |
| `page_index.py` | Índice FTS5 por página |
| `answer_validator.py` | Validação e retry de respostas |
| `analytical_synthesis.py` | Map-reduce para perguntas amplas |
| `audit_synthesis.py` | Síntese modo auditoria |
| `rag_prompts.py` | Prompts jurídicos |
| `free_chat_engine.py` | Chat sem retrieval |
| `ollama_thinking_stream.py` | Stream Ollama com thinking |
| `llm_thinking.py` | Captura de thinking |
| `runtime_config.py` | Configuração central |
| `project_store.py` | CRUD de projetos JSON |
| `conversation_store.py` | Persistência de conversas JSON |

## Fluxo de ingestão

```text
PDF → extração → chunks → embedding BGE-M3 → Qdrant
                          ↓
                    SQLite FTS5 (chunk + page)
                          ↓
                    entidades + grafo cross-doc
```

## Fluxo de consulta

```text
Pergunta → planner → expansion → multi-query
  ↓
semântico + lexical + página
  ↓
RRF → diversificação → boost → reranker BGE
  ↓
CondensePlusContext → Ollama → validator → retry/fallback
```

## Riscos

- `HybridRetriever._retrieve` monolítico
- `ingest_service.py` com muitas responsabilidades
- Manipulação global de `os.environ`
- Monkey-patch em LlamaIndex
- Dependência de formatos internos do Ollama

## Dívidas

- Lógica de UI no core (`retrieved_chunks_ui.py`, `proofread_ui.py`)
- Bootstrap que modifica `sys.path`/`os.chdir`
- Persistência JSON sem locks
- Caminhos de modelos hardcoded
