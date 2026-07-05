# PDF Extreme AI — Backend Summary

## Stack

- FastAPI + Starlette SessionMiddleware + CORS
- Auth em JSON com hash Werkzeug (pbkdf2:sha256)
- Sessão via cookie `pdf_extreme_session`
- Dependência do motor `core/` via `bootstrap_legacy()`

## Responsabilidades

- API REST para frontend
- Autenticação e RBAC (admin/consultor)
- CRUD de projetos, conversas, documentos
- Orquestração de ingestão (SSE)
- Orquestração de chat (sync/async, RAG/free)
- Export markdown e corretor

## Routers principais

| Router | Prefixo | Proteção |
|---|---|---|
| auth | `/auth` | público (exceto `/me`) |
| projects | `/projects` | autenticado |
| documents | `/projects/{id}/documents` | autenticado |
| ingest | `/projects/{id}/ingest` | autenticado |
| conversations | `/projects/{id}/conversations` | autenticado |
| chat | `/projects/{id}/chat` | autenticado |
| chat_turns | `/projects/{id}/chat/turns` | autenticado |
| export | `/export/markdown` | **público** |
| proofread | `/proofread` | **público** |

## Serviços críticos

- `chat_service.py` — orquestra chat RAG/free, retry, fallback, audit, analytical
- `stack_manager.py` — cache e montagem do stack RAG por projeto
- `ingest_runner.py` — roda ingestão em thread, emite SSE
- `chat_turn_store.py` / `chat_turn_runner.py` — turnos async persistidos

## Riscos

- Secret default
- Rotas públicas sensíveis
- Rate limit em memória
- Jobs em threads daemon
- Acoplamento com `core/bootstrap.py`

## Dívidas

- `chat_service.py` muito grande
- Imports locais após bootstrap
- Manipulação de `_load`/`_save` privados do ProjectStore
- Testes quebrados (`test_chat_rag_flow.py`)
