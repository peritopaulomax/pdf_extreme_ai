# PDF Extreme AI — Component Catalog

## Componentes

| Componente | Tipo | Responsabilidade | Criticidade | Status |
|---|---|---|---|---|
| Frontend React | Frontend | Interface web SPA | Tier 1 | Ativo |
| FastAPI App | Backend | API REST e middleware | Tier 0 | Ativo |
| Auth Store | Service | Persistência de usuários em JSON | Tier 0 | Ativo |
| Session Middleware | Middleware | Cookies de sessão assinados | Tier 0 | Ativo |
| Project Store | Service | CRUD de projetos em JSON | Tier 0 | Ativo |
| Conversation Store | Service | Persistência de conversas JSON | Tier 0 | Ativo |
| Ingest Runner | Worker/Service | Orquestra ingestão com SSE | Tier 0 | Ativo |
| Chat Service | Service | Orquestra chat RAG/free/sync/async | Tier 0 | Ativo |
| Chat Turn Store | Service | Persistência de turnos | Tier 0 | Ativo |
| Chat Turn Runner | Worker | Jobs de turno assíncronos em thread | Tier 0 | Ativo |
| Stack Manager | Service | Cache e montagem de stack RAG | Tier 0 | Ativo |
| HybridRetriever | Model | Recuperação híbrida semântica+lexical | Tier 0 | Ativo |
| Query Planner | Model | Planejamento de query (perfil/intent) | Tier 1 | Ativo |
| Query Expansion | Model | Expansão léxica/forense de query | Tier 1 | Ativo |
| Answer Validator | Model | Validação e retry de respostas | Tier 1 | Ativo |
| Ingest Service | Pipeline | Pipeline completo de ingestão | Tier 0 | Ativo |
| PDF Extraction | Pipeline | Extração de texto/OCR de PDFs | Tier 0 | Ativo |
| Lexical Index | Database | Índice FTS5 chunk-level | Tier 1 | Ativo |
| Page Index | Database | Índice FTS5 por página | Tier 1 | Ativo |
| Qdrant Vector Store | Database | Vetores semânticos | Tier 0 | Ativo |
| Ollama LLM Adapter | Model | Geração via Ollama com thinking | Tier 0 | Ativo |
| Free Chat Engine | Model | Chat sem retrieval | Tier 2 | Ativo |
| Proofread Service | Model | Corretor ortográfico | Tier 2 | Ativo |
| Export Service | Service | Formatação markdown | Tier 2 | Ativo |
| Runtime Config | Infrastructure | Configuração central | Tier 0 | Ativo |
| GPU Runtime | Infrastructure | Controle de VRAM/GPU | Tier 1 | Ativo |
| Project Memory | Service | Memória narrativa do caso | Tier 1 | Ativo |
| Case Memory | Service | Enriquecimento de memória no chat | Tier 1 | Ativo |
| Entity Timeline | Model | NER leve | Tier 2 | Ativo |
| Cross-Doc Graph | Model | Grafo de referências | Tier 2 | Ativo |
| UI Streamlit | Frontend | Interface legada | Tier 2 | Legado |

## Detalhes por Componente

### Frontend React
- **Entrypoints:** `frontend/src/main.tsx`, `frontend/src/App.tsx`
- **Dependências:** FastAPI Backend
- **Dependentes:** Nenhum (é a interface)
- **Fluxos:** Login, projetos, upload, chat, corretor, configuração
- **Dados:** `localStorage` (larguras de layout), query params (project/conversation)
- **Riscos:** Código legado não usado, CSS monolítico, hardcodes de modelo
- **Evidências:** `frontend/src/`

### FastAPI App
- **Entrypoints:** `backend/main.py`
- **Dependências:** Starlette, FastAPI
- **Dependentes:** Frontend React
- **Fluxos:** Recebe requisições, aplica auth, delega a routers
- **Dados:** Sessão cookie
- **Riscos:** Secret default, CORS default amplo
- **Evidências:** `backend/main.py`

### Auth Store
- **Entrypoints:** `backend/auth/store.py`
- **Dependências:** JSON, Werkzeug
- **Dependentes:** `backend/api/auth.py`
- **Fluxos:** Carrega admins/consultores, verifica senha, cadastra, reseta
- **Dados:** `data/auth/admins.json`, `data/auth/usuarios_app.json`
- **Riscos:** Arquivos JSON sem lock, rate limit em memória
- **Evidências:** `backend/auth/store.py`

### Project Store
- **Entrypoints:** `core/project_store.py`
- **Dependências:** JSON, paths
- **Dependentes:** Backend API, legacy Streamlit
- **Fluxos:** Cria, lê, atualiza, lista projetos
- **Dados:** `data/projects_registry.json`
- **Riscos:** Não tem `delete_project` no core (API v2 implementa própria), carrega registry inteiro
- **Evidências:** `core/project_store.py`

### Chat Service
- **Entrypoints:** `backend/services/chat_service.py`
- **Dependências:** Stack Manager, Chat Turn Store, core/
- **Dependentes:** `backend/api/chat.py`, `backend/api/chat_turns.py`
- **Fluxos:** run_chat_turn, start_async_chat_turn
- **Dados:** Conversas JSON
- **Riscos:** Arquivo muito grande (~1280 linhas), alta complexidade ciclomática
- **Evidências:** `backend/services/chat_service.py`

### HybridRetriever
- **Entrypoints:** `core/retrieval_pipeline.py`
- **Dependências:** Qdrant, LexicalIndex, PageLexicalIndex, query_planner, query_expansion
- **Dependentes:** Chat Service
- **Fluxos:** _retrieve → planejamento → busca paralela → RRF → diversificação → reranker
- **Dados:** Vetores Qdrant, índices FTS5
- **Riscos:** Método _retrieve monolítico (~200 linhas)
- **Evidências:** `core/retrieval_pipeline.py`

### Ollama LLM Adapter
- **Entrypoints:** `core/ollama_thinking_stream.py`, `core/llm_thinking.py`
- **Dependências:** Ollama, LlamaIndex
- **Dependentes:** Chat Service, Proofread Service
- **Fluxos:** Stream tokens com thinking
- **Dados:** Respostas do Ollama
- **Riscos:** Dependência de formatos internos do Ollama/LlamaIndex
- **Evidências:** `core/ollama_thinking_stream.py`, `core/llm_thinking.py`

## Gate

**Quais componentes existem?** O sistema possui frontend React, API FastAPI, serviços de auth/projects/chat/ingest/export, motor RAG em `core/` com ingestão, retrieval híbrido, LLM Ollama, índices Qdrant/SQLite, e UI Streamlit legada.

## Evidências

- `backend/`
- `core/`
- `frontend/src/`
- `legacy/app.py`
