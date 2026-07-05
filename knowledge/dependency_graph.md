# PDF Extreme AI — Dependency Graph

## Visão Geral

O sistema depende de uma pilha local de modelos e serviços (Ollama, Qdrant, HuggingFace), além de bibliotecas Python e Node. A camada FastAPI depende do motor `core/`, enquanto o frontend depende exclusivamente da API.

## Dependências Internas

| Componente | Depende de |
|---|---|
| Frontend React | Backend FastAPI (REST + SSE) |
| Backend FastAPI | `core/` (motor RAG), `backend/auth/`, `backend/services/` |
| `backend/services/chat_service.py` | `core/`, `backend/services/stack_manager.py`, `backend/services/chat_turn_store.py` |
| `backend/services/ingest_runner.py` | `core/ingest_service.py`, `core/project_store.py` |
| `backend/services/stack_manager.py` | `core/`, `llama-index`, `qdrant-client` |
| `core/ingest_service.py` | `core/pdf_extraction.py`, `core/index_bootstrap.py`, `core/retrieval_lexical.py`, `core/page_index.py`, `core/entity_timeline.py`, `core/cross_doc_graph.py` |
| `core/retrieval_pipeline.py` | `core/query_planner.py`, `core/query_expansion.py`, `core/retrieval_lexical.py`, `core/page_index.py`, `core/exhaustive_retrieval.py`, `core/cross_doc_graph.py` |
| `core/chat_memory.py` | `core/conversation_memory.py`, `core/runtime_config.py` |

## Dependências Externas

### Python (Motor + Backend)

| Dependência | Versão / Uso |
|---|---|
| `fastapi` | >=0.110.0 — API REST |
| `uvicorn[standard]` | >=0.27.0 — Servidor ASGI |
| `python-multipart` | >=0.0.9 — Upload de arquivos |
| `python-dotenv` | >=1.0.0 — `.env` |
| `pydantic` | >=2.0.0 — Validação de schemas |
| `werkzeug` | >=3.0.0 — Hash de senha |
| `itsdangerous` | >=2.1.0 — Sessão |
| `cryptography` | >=42.0.0 — Criptografia de credenciais de serviço |
| `pytest` | >=8.0.0 — Testes |
| `httpx` | >=0.27.0 — Cliente HTTP |
| `llama-index-core` | Orquestração RAG |
| `llama-index-embeddings-huggingface` | Embeddings BGE-M3 |
| `llama-index-vector-stores-qdrant` | Integração Qdrant |
| `llama-index-llms-ollama` | Integração Ollama |
| `qdrant-client` | Cliente Qdrant |
| `torch` | Inferência de embeddings/reranker |
| `sentence-transformers` | Modelos de sentence embedding |
| `transformers` | HuggingFace transformers |
| `pymupdf` / `pypdf` | Extração de PDF |
| `pytesseract` / `Pillow` | OCR opcional |
| `ollama` (biblioteca) | Comunicação com Ollama |

### Node (Frontend)

| Dependência | Versão / Uso |
|---|---|
| `react` | 18.3.1 — UI |
| `react-dom` | 18.3.1 — DOM |
| `react-router-dom` | 6.28.0 — Roteamento |
| `@tanstack/react-query` | 5.62.0 — Estado servidor |
| `react-markdown` | 10.1.0 — Renderização Markdown |
| `remark-gfm` | 4.0.1 — Tabelas Markdown |
| `vite` | 5.4.11 — Build/dev |
| `vitest` | 4.1.7 — Testes |
| `typescript` | 5.6.2 — Tipagem |

## Bancos

| Banco | Uso | Criticidade |
|---|---|---|
| Qdrant | Vetores semânticos por projeto | Alta |
| SQLite FTS5 | Índices lexicais por projeto | Alta |
| JSON em disco | Registry, conversas, auth, memória | Alta |

## Cache

| Cache | Uso | Dependências |
|---|---|---|
| LRU de stacks RAG | Até 16 stacks por projeto | `backend/services/stack_manager.py` |
| GPU runtime lock | Exclusão mútua ingest/chat na GPU | `core/gpu_runtime.py` |

## Filas

- Não há fila dedicada. Jobs de ingest e chat async rodam em threads daemon dentro do processo FastAPI.

## Storage

| Storage | Uso |
|---|---|
| Filesystem local | Uploads, checkpoints, conversas, memória, entidades, grafo |
| Docker volume `qdrant_data` | Persistência do Qdrant |

## APIs Externas

| API | Direção | Uso |
|---|---|---|
| Ollama HTTP API | Outbound | Geração de texto/thinking |
| Qdrant gRPC/HTTP | Outbound | Armazenamento e busca vetorial |

## Modelos de IA

| Modelo | Provedor | Uso |
|---|---|---|
| `BAAI/bge-m3` | HuggingFace local | Embeddings (1024 dim) |
| `BAAI/bge-reranker-base` | HuggingFace local | Reranker cross-encoder |
| `gemma4:26b` | Ollama | LLM padrão |
| `gemma4:e4b` | Ollama | LLM alternativo |

## Grafo Resumido

```text
Frontend React
      ↓ REST + SSE
Backend FastAPI
      ├── Auth (JSON em disco)
      ├── Projects (JSON registry)
      ├── Conversations (JSON)
      ├── Ingest Runner
      │       ↓
      │   core/ingest_service.py
      │       ↓
      │   PyMuPDF / pypdf / OCR
      │       ↓
      │   HuggingFaceEmbedding (bge-m3)
      │       ↓
      │   Qdrant + SQLite FTS5
      │
      ├── Chat Service
      │       ↓
      │   core/retrieval_pipeline.py (HybridRetriever)
      │   core/query_planner.py
      │   core/answer_validator.py
      │       ↓
      │   Ollama (gemma4)
      │
      └── Proofread / Export
              ↓
          core/proofread_service.py / export_service.py
```

## Falhas em Cascata

| Falha | Impacto |
|---|---|
| Qdrant indisponível | Chat RAG perde recuperação semântica; ingest falha |
| Ollama indisponível | Sem geração de resposta em chat e corretor |
| Embedding falha | Ingestão e query semântica falham |
| SQLite FTS5 corrompido | Recall lexical degradado |
| `projects_registry.json` corrompido | Sistema não consegue listar projetos |
| FastAPI cai durante job async | Turno/ingest em andamento pode ser perdido |

## SPOFs

| SPOF | Descrição |
|---|---|
| Processo FastAPI único | Sem replicação/load balancing |
| Qdrant single container | Sem cluster |
| Ollama único | Sem failover |
| JSON registry único | Sem replicação/backup automático |

## Evidências

- `backend/requirements.txt`
- `frontend/package.json`
- `docker-compose.yml`
- `.env.example`
- `core/runtime_config.py`
- `backend/services/stack_manager.py`
- `docs/PROJECT_OVERVIEW.md`
