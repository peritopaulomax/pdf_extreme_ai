# PDF Extreme AI — Repository Map

## Missão

Explicar como o repositório está organizado.

## Resumo

`pdf_extreme_ai` é uma aplicação RAG (Retrieval-Augmented Generation) para PDFs jurídicos/periciais. O repositório está organizado como um monorepo com três camadas principais: motor RAG compartilhado (`core/`), API FastAPI (`backend/`) e interface React (`frontend/`). Existe também uma UI legada em Streamlit (`legacy/`). Todos os dados de runtime ficam em `data/`.

## Árvore Comentada

```
pdf_extreme_ai/
├── backend/            # API FastAPI v2 + auth + services
│   ├── api/            # Routers HTTP (auth, projects, chat, ingest, etc.)
│   ├── auth/           # Sessão, hash de senha, store JSON
│   ├── services/       # Orquestração de negócio (chat, ingest, export, proofread)
│   ├── core/           # Shim que importa core/ da raiz via bootstrap
│   ├── main.py         # Entrypoint FastAPI
│   └── requirements.txt
├── core/               # Motor RAG compartilhado (ingest, retrieval, LLM, prompts)
│   ├── ingest_service.py
│   ├── retrieval_pipeline.py
│   ├── query_planner.py
│   ├── answer_validator.py
│   ├── rag_prompts.py
│   ├── runtime_config.py
│   └── ...
├── frontend/           # SPA React + TypeScript + Vite
│   ├── src/
│   │   ├── api/        # Clientes HTTP e tipos
│   │   ├── components/ # UI (ChatPanel, DocumentsPanel, UnifiedSidebar, etc.)
│   │   ├── pages/      # Login, PrimeiroAcesso, UsuariosConfig
│   │   ├── hooks/      # useChatTurn, useLayoutWidths
│   │   └── context/    # AuthContext
│   ├── package.json
│   └── vite.config.ts
├── legacy/             # UI Streamlit legada (app.py ~2000 linhas)
├── data/               # Runtime: projetos, auth, índices, checkpoints, conversas
├── scripts/            # Utilitários CLI (ingest, eval, bootstrap_admin, etc.)
├── tests/              # Testes backend (pytest) e core (unittest/pytest)
├── docs/               # Especificações e documentação
└── eval/               # Perguntas gold para avaliação RAG
```

## Diretórios

| Diretório | Responsabilidade | Criticidade |
|---|---|---|
| `backend/` | API REST FastAPI v2; orquestra frontend e core | Tier 0 |
| `core/` | Motor RAG: ingestão, retrieval híbrido, chat, LLM | Tier 0 |
| `frontend/` | Interface web React | Tier 1 |
| `legacy/` | UI Streamlit legada; ainda funcional | Tier 2 |
| `data/` | Persistência de runtime (JSON, SQLite, uploads) | Tier 0 |
| `scripts/` | Automação CLI e operação | Tier 2 |
| `tests/` | Testes automatizados | Tier 1 |
| `docs/` | Especificações e documentação | Tier 2 |
| `eval/` | Dataset gold para eval offline | Tier 2 |

## Entrypoints

| Arquivo | Função |
|---|---|
| `backend/main.py` | Cria app FastAPI, registra routers, middleware de sessão/CORS |
| `frontend/src/main.tsx` | Monta aplicação React |
| `frontend/index.html` | HTML de entrada do Vite |
| `legacy/app.py` | Aplicação Streamlit legada |
| `scripts/ingest.py` | Ingestão batch de PDFs por projeto |
| `scripts/eval_rag.py` | Avaliação offline recall@k |
| `scripts/bootstrap_admin.py` | Cria administrador inicial em `data/auth/` |
| `core/ingest_service.py` | Pipeline de ingestão de PDFs |
| `core/retrieval_pipeline.py` | HybridRetriever semântico+lexical |

## Configurações

| Arquivo | Função |
|---|---|
| `.env` / `.env.example` | Variáveis de ambiente (Qdrant, Ollama, perfis RAG, paths de modelos) |
| `docker-compose.yml` | Serviço Qdrant |
| `environment.yml` | Ambiente conda |
| `backend/requirements.txt` | Dependências Python da API |
| `frontend/package.json` | Dependências Node do frontend |
| `frontend/vite.config.ts` | Proxy `/api` para backend e config de build |

## Scripts

| Script | Função |
|---|---|
| `scripts/ingest.py` | Ingestão CLI de PDFs |
| `scripts/eval_rag.py` | Eval RAG offline |
| `scripts/test_qdrant_connection.py` | Testa conexão com Qdrant |
| `scripts/bootstrap_admin.py` | Bootstrap de admin |
| `scripts/assign_project_owners.py` | Migração de ownership de projetos |
| `scripts/upgrade_nvidia_driver.sh` | Instalação de driver NVIDIA (operação destrutiva) |

## Testes

| Local | Tipo | Framework |
|---|---|---|
| `tests/core/` | Unitários/contratos do motor | pytest/unittest |
| `tests/backend/` | API FastAPI, auth, chat turns, contratos | pytest |
| `frontend/src/**/*.test.*` | Hooks, componentes, API client | vitest |

## Dependências Importantes

- **Backend/API:** FastAPI, Uvicorn, Pydantic, python-dotenv, Werkzeug, Starlette SessionMiddleware
- **Motor RAG:** LlamaIndex, Qdrant client, HuggingFace Transformers/SentenceTransformers, PyMuPDF, SQLite FTS5, Ollama
- **Frontend:** React, React Router, TanStack Query, react-markdown, Vite, Vitest
- **Infraestrutura:** Docker + Qdrant, Ollama (externo)

## Arquivos Críticos

| Arquivo | Por que é crítico |
|---|---|
| `backend/main.py` | Entrypoint da API |
| `backend/services/chat_service.py` | Orquestração de todo o chat RAG/free |
| `backend/services/stack_manager.py` | Cache e montagem do stack RAG por projeto |
| `core/ingest_service.py` | Pipeline de ingestão |
| `core/retrieval_pipeline.py` | Recuperação híbrida |
| `core/answer_validator.py` | Validação e retry de respostas |
| `core/runtime_config.py` | Configuração central |
| `core/project_store.py` | CRUD de projetos em JSON |
| `frontend/src/App.tsx` | Rotas e shell da aplicação |
| `frontend/src/components/ChatPanel.tsx` | Chat principal |
| `data/projects_registry.json` | Registry central de projetos |

## Evidências

- `README.md`
- `docs/PROJECT_OVERVIEW.md`
- `backend/main.py`
- `frontend/package.json`
- `docker-compose.yml`
- `.env.example`
- Estrutura de diretórios do working directory
