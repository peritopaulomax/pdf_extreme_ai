# PDF Extreme AI — Architecture

## Metadados

- **Status:** Ativo
- **Última Atualização:** 2026-07-05
- **Confiança Geral:** Alta
- **Autor:** Repository Intelligence
- **Versão:** 0.3.0 (conforme `backend/main.py`)

## Resumo Executivo

**O que é:** Assistente RAG para PDFs jurídicos/periciais.

**Qual problema resolve:** Permite fazer perguntas em linguagem natural sobre autos e documentos jurídicos em PDF, obtendo respostas com citações por página/arquivo, recall lexical de termos críticos e validação automática.

**Como funciona em alto nível:** O usuário interage via SPA React que consome API FastAPI. A API orquestra o motor RAG em `core/`, que extrai texto de PDFs, indexa semanticamente (Qdrant + BGE-M3) e lexicalmente (SQLite FTS5), recupera trechos híbridos, reranka e gera respostas via Ollama (modelos Gemma4).

## Classificação

- **Monorepo** com **Monolito Modular** (backend FastAPI) + **Motor compartilhado** (`core/`) + **Frontend SPA** (React).
- Especialização: **RAG System**.

## Visão Arquitetural

```text
Usuário
  ↓
Frontend React (Vite)
  ↓
FastAPI Backend
  ↓
Motor RAG (core/)
  ├── Ingestão: pdf_extraction.py → chunking → Qdrant + SQLite FTS5
  ├── Recuperação: HybridRetriever (semântico + lexical + página + RRF)
  ├── Geração: CondensePlusContextChatEngine / SimpleChatEngine → Ollama
  └── Validação: answer_validator.py
  ↓
Qdrant (vetores) + SQLite FTS5 (lexical) + Ollama (LLM)
  ↓
Storage local: data/projects/<id>/ (uploads, conversas, memória)
```

## Componentes

| Componente | Responsabilidade | Criticidade | Evidências |
|---|---|---|---|
| Frontend React | Interface web: projetos, upload, chat, corretor, config | Tier 1 | `frontend/src/` |
| FastAPI App | API REST, sessão, CORS, roteamento | Tier 0 | `backend/main.py` |
| Auth Service | Login, sessão cookie, RBAC admin/consultor | Tier 0 | `backend/auth/` |
| Project Service | CRUD de projetos, ownership, regras, memória | Tier 0 | `backend/api/projects.py`, `backend/api/project_settings.py`, `core/project_store.py` |
| Document Service | Upload, remoção, reprocessamento de PDFs | Tier 1 | `backend/api/documents.py`, `backend/services/documents_service.py` |
| Ingest Runner | Orquestra ingestão de PDFs com SSE | Tier 0 | `backend/services/ingest_runner.py`, `core/ingest_service.py` |
| Chat Service | Orquestra chat RAG/free, async turns, retry, fallback | Tier 0 | `backend/services/chat_service.py` |
| Chat Turn Store | Persistência de turnos em JSON | Tier 0 | `backend/services/chat_turn_store.py`, `backend/services/chat_turn_runner.py` |
| Stack Manager | Cache e montagem do stack RAG por projeto | Tier 0 | `backend/services/stack_manager.py` |
| HybridRetriever | Recuperação híbrida semântica+lexical | Tier 0 | `core/retrieval_pipeline.py` |
| Query Planner | Classifica intent e perfil da pergunta | Tier 1 | `core/query_planner.py` |
| Answer Validator | Valida citações e dispara retry | Tier 1 | `core/answer_validator.py` |
| LLM Adapter | Ollama com suporte a thinking/streaming | Tier 0 | `core/ollama_thinking_stream.py`, `core/llm_thinking.py` |
| Lexical Index | Índice FTS5 chunk-level | Tier 1 | `core/retrieval_lexical.py` |
| Page Index | Índice FTS5 por página | Tier 1 | `core/page_index.py` |
| Qdrant Vector Store | Armazena embeddings BGE-M3 | Tier 0 | `core/index_bootstrap.py`, `qdrant_data/` |
| Export Service | Formata markdown de resposta | Tier 2 | `backend/services/export_service.py`, `backend/api/export.py` |
| Proofread Service | Corretor ortográfico via LLM | Tier 2 | `core/proofread_service.py`, `backend/api/proofread.py` |

## Camadas

| Camada | Onde | Responsabilidade |
|---|---|---|
| Presentation | `frontend/src/`, `legacy/app.py` | UI React e Streamlit legada |
| Application | `backend/api/`, `backend/services/` | Rotas HTTP, orquestração, sessão |
| Domain | `core/` | Motor RAG, regras de retrieval, prompts, validação |
| Infrastructure | `core/runtime_config.py`, `core/paths.py`, `docker-compose.yml`, Qdrant, Ollama | Config, persistência, serviços externos |

## Frontend

- **Tecnologia:** React 18 + TypeScript + Vite
- **Entrypoint:** `frontend/src/main.tsx`
- **Build:** `vite build` (TypeScript compilação)
- **Deploy:** Static files ou dev server Vite
- **Dependências:** react-router-dom, @tanstack/react-query, react-markdown, remark-gfm
- **Rotas:** `/login`, `/primeiro-acesso`, `/configuracoes/usuarios`, `/`

## Backend

- **Tecnologia:** Python 3.11 + FastAPI
- **Entrypoint:** `backend/main.py`
- **Framework:** FastAPI + Starlette SessionMiddleware + CORS
- **Dependências:** fastapi, uvicorn, pydantic, python-dotenv, werkzeug, cryptography
- **Responsabilidades:** API REST, autenticação sessão, orquestração do motor RAG

## Workers

- **Ingest runner:** roda em thread daemon, emite SSE de progresso.
- **Chat turn runner:** roda turnos assíncronos em background, pub/sub em memória.
- Não há fila dedicada (RabbitMQ/Kafka); jobs rodam em threads dentro do processo FastAPI.

## Banco de Dados

| Tecnologia | Responsabilidade | Criticidade |
|---|---|---|
| Qdrant | Vetores semânticos por projeto | Tier 0 |
| SQLite FTS5 | Índices lexicais (`lexical_fts`, `page_fts`) | Tier 1 |
| JSON em disco | Registry de projetos, conversas, auth, memória | Tier 0 |

## Cache

- **LRU de stacks RAG:** `backend/services/stack_manager.py` mantém até 16 stacks por projeto.
- **GPU lock:** `core/gpu_runtime.py` coordena ingest vs chat na GPU.

## Storage

- **Tecnologia:** filesystem local
- **Objetos armazenados:** uploads de PDF, checkpoints de ingest, conversas JSON, memória do caso, entidades, grafo cross-doc
- **Criticidade:** Tier 0

## Autenticação

- **Método:** Sessão cookie assinada (`pdf_extreme_session`) via Starlette SessionMiddleware
- **Provedor:** Próprio (JSON em disco)
- **Fluxos:** login, logout, primeiro acesso, reset de senha de consultores

## Autorização

- **Papéis:** admin, consultor
- **Permissões:** admin pode gerenciar usuários; consultor acessa apenas seus projetos (`owner_id`)
- **Restrições:** isolamento por projeto via 404 quando owner não bate

## Observabilidade

| Tipo | Implementação |
|---|---|
| Logs | `print`/logs do Python; sem logger estruturado centralizado |
| Métricas | Telemetria de retrieval exposta na UI (`fused`, `literal_hits`, etc.) |
| Tracing | Não identificado |
| Alertas | Não identificado |

## Fluxos Principais

### 1. Ingestão de PDF
- **Nome:** Ingestão de PDF
- **Objetivo:** Extrair texto de PDFs e indexar semanticamente e lexicalmente.
- **Fluxo:** Upload → validação → persistência em `data/projects/<id>/uploads/` → `ingest_service.run_ingest` → extração (PyMuPDF/pypdf/OCR) → chunking (`SentenceWindowNodeParser`) → indexação Qdrant + SQLite FTS5 + page_fts → extração de entidades.
- **Dependências:** Qdrant, Ollama (pode ser pausado), HuggingFace embedding, SQLite
- **Riscos:** Falha do embedding, corrupção de checkpoint, OCR ruim

### 2. Chat RAG
- **Nome:** Chat RAG
- **Objetivo:** Responder perguntas sobre documentos indexados.
- **Fluxo:** Pergunta → query_planner → query_expansion → HybridRetriever (semântico+lexical+página) → RRF → reranker BGE → CondensePlusContextChatEngine → Ollama → answer_validator → retry/fallback se necessário → persistência da conversa.
- **Dependências:** Qdrant, SQLite FTS5, Ollama, BGE reranker
- **Riscos:** LLM indisponível, resposta vazia, baixa cobertura, thinking mal formatado

### 3. Chat Livre
- **Nome:** Chat Livre
- **Objetivo:** Conversa geral sem retrieval.
- **Fluxo:** Pergunta → SimpleChatEngine → Ollama → resposta streaming.
- **Dependências:** Ollama
- **Riscos:** Indisponibilidade do Ollama

### 4. Corretor Ortográfico
- **Nome:** Corretor
- **Objetivo:** Corrigir texto colado.
- **Fluxo:** Texto → `proofread_service` → LLM JSON → renderização HTML com destaques.
- **Dependências:** Ollama
- **Riscos:** Resposta JSON malformada

### 5. Exportação de Resposta
- **Nome:** Export Markdown
- **Objetivo:** Exportar pergunta, resposta, thinking e trechos para markdown.
- **Fluxo:** Dados da resposta → `export_service.build_assistant_export_md` → download.
- **Dependências:** Nenhuma externa
- **Riscos:** Endpoint público sem autenticação

## Dependências Críticas

| Dependência | Tipo | Criticidade | Impacto |
|---|---|---|---|
| Qdrant | Banco vetorial | Tier 0 | Sem ele, não há recuperação semântica |
| Ollama | LLM local | Tier 0 | Sem ele, não há geração de resposta |
| BGE-M3 embedding | Modelo local | Tier 0 | Sem ele, não há indexação/recuperação semântica |
| BGE reranker | Modelo local | Tier 1 | Degradação de qualidade se ausente |
| SQLite FTS5 | Banco lexical | Tier 1 | Degrada recall lexical se ausente |
| HuggingFace Transformers | Biblioteca | Tier 0 | Necessário para embeddings/reranker |
| LlamaIndex | Framework RAG | Tier 0 | Orquestração do RAG |

## Pontos Únicos de FALHA (SPOFs)

| SPOF | Impacto | Mitigação Atual |
|---|---|---|
| Processo único do FastAPI | Indisponibilidade total | Nenhuma (deploy single-instance) |
| Qdrant single container | Perda de busca semântica | Volume Docker em `qdrant_data/` |
| Ollama externo single instance | Sem geração de resposta | Nenhuma |
| JSON registry (`projects_registry.json`) | Corrupção afeta todos os projetos | Backup manual |
| Sessão cookie `SESSION_SECRET` default | Sessões previsíveis em produção | Configurar `SESSION_SECRET` |

## Riscos Arquiteturais

| Risco | Impacto | Probabilidade | Mitigação |
|---|---|---|---|
| Acoplamento backend com core legado | Mudanças no core quebram API | Alta | Testes de contrato |
| Lógica de UI no core (`retrieved_chunks_ui.py`, `proofread_ui.py`) | Motor carrega Streamlit desnecessariamente | Média | Refatorar para camada de apresentação |
| Duplicação Streamlit vs FastAPI | Divergência de funcionalidades | Alta | Deprecar legacy |
| Jobs em threads daemon | Perda de job em caso de queda | Média | Migrar para fila/job queue |
| Manipulação global de `os.environ` | Efeitos colaterais difíceis de rastrear | Média | Centralizar config imutável |

## Dívida Arquitetural

| Dívida | Impacto | Prioridade |
|---|---|---|
| `chat_service.py` ~1280 linhas com múltiplos modos | Difícil manutenção e testes | Alta |
| `HybridRetriever._retrieve` ~200 linhas monolítico | Difícil evolução do retrieval | Alta |
| `ingest_service.py` com muitos imports e responsabilidades | Difícil testar isoladamente | Média |
| Bootstrap que manipula `sys.path` e `os.chdir` | Fragilidade de imports | Média |
| Duplicação de `core/bootstrap.py` e `backend/core/bootstrap.py` | Confusão de paths | Baixa |

## Inconsistências (Divergências Documento ↔ Código)

| Documento | Divergência | Código Real |
|---|---|---|
| `docs/PROJECT_OVERVIEW.md:288-299` | Referencia `projects_data/` e `.lexical_<id>.db` no cwd | `data/projects/<id>/` e `data/lexical/<id>.db` |
| `docs/OPERATIONS.md:86` | Referencia `projects_data/` | `data/projects/` |
| `docs/MIGRATION_MAP.md:91` | Menciona `ProjectStore.delete_project` ausente | API v2 implementa em `backend/services/project_cleanup.py` |

## Confiança

- **Alta** para estrutura geral, componentes e fluxos principais (diretamente evidenciados nos subagentes e arquivos lidos).
- **Média** para detalhes internos de alguns post-processadores e prompts específicos.

## Evidências

- `backend/main.py`
- `frontend/src/App.tsx`
- `frontend/vite.config.ts`
- `core/ingest_service.py`
- `core/retrieval_pipeline.py`
- `core/runtime_config.py`
- `backend/services/chat_service.py`
- `backend/services/stack_manager.py`
- `docs/PROJECT_OVERVIEW.md`
- `docs/MIGRATION_MAP.md`
