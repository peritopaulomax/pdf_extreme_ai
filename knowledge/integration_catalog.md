# PDF Extreme AI — Integration Catalog

## Tabela Principal

| Integração | Tipo | Direção | Criticidade | Status |
|---|---|---|---|---|
| Frontend ↔ Backend | API | Inbound | Crítica | Ativa |
| Backend ↔ Ollama | AI Service | Outbound | Crítica | Ativa |
| Backend ↔ Qdrant | Database | Outbound | Crítica | Ativa |
| Backend ↔ SQLite FTS5 | Database | Outbound | Alta | Ativa |
| Backend ↔ Filesystem | Storage | Bidirectional | Crítica | Ativa |
| Backend ↔ Legacy Streamlit | Compartilhamento de dados | Bidirectional | Baixa | Legada |

## Integrações

### Frontend ↔ Backend
- **Nome:** API REST + SSE
- **Objetivo:** Frontend consome dados e serviços do backend
- **Tipo:** API
- **Direção:** Inbound (do ponto de vista do backend)
- **Dependências:** FastAPI, CORS, cookie de sessão
- **Fluxos Afetados:** Login, projetos, upload, chat, corretor, export, configuração
- **SLA:** Não definido
- **Timeout:** Configurado no cliente fetch
- **Retry:** Não implementado de forma centralizada
- **Fallback:** Redirect para `/login` em 401
- **Observabilidade:** Logs de erro no console do navegador
- **Riscos:** CORS default amplo; endpoints `/proofread` e `/export` públicos
- **Evidências:** `frontend/src/api/`, `backend/api/`, `frontend/vite.config.ts`

### Backend ↔ Ollama
- **Nome:** Ollama LLM
- **Objetivo:** Geração de texto e thinking
- **Tipo:** AI Service
- **Direção:** Outbound
- **Dependências:** Ollama em execução local/remoto
- **Fluxos Afetados:** Chat RAG, chat livre, corretor
- **SLA:** Não definido
- **Timeout:** `OLLAMA_TIMEOUT_DEFAULT=180s`, `OLLAMA_TIMEOUT_HEAVY=600s`
- **Retry:** Implementado no chat_service (fallback sem reranker)
- **Fallback:** Sem geração de resposta
- **Observabilidade:** Timeout idle de 90s no streaming
- **Riscos:** Indisponibilidade, modelos grandes exigem VRAM
- **Evidências:** `core/ollama_thinking_stream.py`, `core/runtime_config.py`, `backend/services/chat_service.py`

### Backend ↔ Qdrant
- **Nome:** Qdrant Vector Store
- **Objetivo:** Armazenar e buscar embeddings
- **Tipo:** Database
- **Direção:** Outbound
- **Dependências:** Qdrant container/docker
- **Fluxos Afetados:** Ingestão, chat RAG
- **SLA:** Não definido
- **Timeout:** `QDRANT_TIMEOUT=20`
- **Retry:** Não identificado
- **Fallback:** Sem recuperação semântica
- **Observabilidade:** Diagnósticos de retrieval na telemetria
- **Riscos:** Volume único, sem cluster
- **Evidências:** `core/index_bootstrap.py`, `core/runtime_config.py`, `docker-compose.yml`

### Backend ↔ SQLite FTS5
- **Nome:** SQLite Lexical Index
- **Objetivo:** Busca lexical de texto completo
- **Tipo:** Database
- **Direção:** Outbound
- **Dependências:** SQLite com FTS5
- **Fluxos Afetados:** Ingestão, chat RAG, modo auditoria
- **SLA:** Não definido
- **Timeout:** Padrão SQLite
- **Retry:** Não identificado
- **Fallback:** Sem recall lexical
- **Observabilidade:** `literal_hits` na telemetria
- **Riscos:** Corrupção de arquivo SQLite
- **Evidências:** `core/retrieval_lexical.py`, `core/page_index.py`

### Backend ↔ Filesystem
- **Nome:** Local Filesystem
- **Objetivo:** Persistir uploads, conversas, registry, auth, memória
- **Tipo:** Storage
- **Direção:** Bidirectional
- **Dependências:** Paths configurados em `.env`
- **Fluxos Afetados:** Todos
- **SLA:** N/A
- **Timeout:** N/A
- **Retry:** `.tmp` + `replace` em alguns saves
- **Fallback:** Nenhum
- **Observabilidade:** Nenhum
- **Riscos:** Concorrência em JSON, dados de produção no repo
- **Evidências:** `core/paths.py`, `core/project_store.py`, `core/conversation_store.py`, `data/`

### Backend ↔ Legacy Streamlit
- **Nome:** Legacy UI
- **Objetivo:** Compartilhamento de dados e motor entre UI antiga e nova
- **Tipo:** Compartilhamento de dados
- **Direção:** Bidirectional
- **Dependências:** `core/`
- **Fluxos Afetados:** Todos (duplicação funcional)
- **SLA:** N/A
- **Timeout:** N/A
- **Retry:** N/A
- **Fallback:** N/A
- **Observabilidade:** Nenhum
- **Riscos:** Divergência de funcionalidades; manutenção dupla
- **Evidências:** `legacy/app.py`, `docs/MIGRATION_MAP.md`

## Gate

**De quem dependemos?** Ollama, Qdrant, SQLite FTS5, filesystem local.

**Quem depende de nós?** Frontend React (e indiretamente usuários finais).

## Evidências

- `backend/api/`
- `frontend/src/api/`
- `core/runtime_config.py`
- `docker-compose.yml`
- `docs/MIGRATION_MAP.md`
