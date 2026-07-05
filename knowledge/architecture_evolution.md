# PDF Extreme AI — Architecture Evolution

## Estado Atual

Monorepo com motor RAG em `core/`, API FastAPI em `backend/` e SPA React em `frontend/`. A UI Streamlit legada (`legacy/app.py`) ainda existe e compartilha o mesmo motor e dados. Persistência via JSON em disco, Qdrant e SQLite FTS5.

## Linha do Tempo

### Protótipo Streamlit
- **Data:** Início do projeto
- **Estado Anterior:** Nenhum
- **Estado Atual:** Aplicação Streamlit monolítica em `legacy/app.py` com motor RAG embutido
- **Motivação:** Prova de conceito rápida
- **Benefícios:** Iteração rápida
- **Custos:** Acoplamento UI/lógica
- **Riscos:** Difícil escalar/testar
- **Evidências:** `legacy/app.py`

### Extração do Motor Core
- **Data:** Transição inicial
- **Estado Anterior:** Código misturado no app Streamlit
- **Estado Atual:** Módulos Python em `core/` organizados por responsabilidade
- **Motivação:** Reuso e testabilidade
- **Benefícios:** Motor compartilhável
- **Custos:** Necessidade de bootstrap de paths
- **Riscos:** Acoplamento residual com UI legada
- **Evidências:** `core/`

### API FastAPI v2
- **Data:** Em andamento
- **Estado Anterior:** Apenas Streamlit
- **Estado Atual:** API REST com auth, projetos, ingest, chat, export, proofread
- **Motivação:** Frontend moderno e separação de camadas
- **Benefícios:** API reutilizável, testes de integração
- **Custos:** Manutenção dupla durante migração
- **Riscos:** Divergência com legacy
- **Evidências:** `backend/`

### Frontend React
- **Data:** Em andamento
- **Estado Anterior:** Streamlit
- **Estado Atual:** SPA React com Vite, React Query, React Router
- **Motivação:** Melhor UX e desempenho
- **Benefícios:** Interface moderna, desacoplada
- **Custos:** Duplicação de funcionalidades
- **Riscos:** Componentes legados e testes desatualizados
- **Evidências:** `frontend/src/`

## Mudanças Estruturais

| Mudança | De | Para |
|---|---|---|
| UI | Streamlit monolítico | React SPA + FastAPI |
| Motor | Inline no app | `core/` compartilhado |
| Auth | Streamlit session state | Cookie assinado Starlette |
| Chat | Síncrono simples | Síncrono + async com turnos |
| Deploy | `streamlit run` | Uvicorn + Vite static |

## Deriva Arquitetural

| Aspecto | Planejado | Implementado | Divergências |
|---|---|---|---|
| Camadas | Separadas | Parcialmente separadas (UI no core) | `retrieved_chunks_ui.py`, `proofread_ui.py` |
| Persistência | JSON | JSON + SQLite + Qdrant | Nenhuma novidade |
| Auth | Cookie seguro | Cookie com secret default | Risco em produção |
| Async jobs | — | Threads daemon | Não é fila persistente |
| Testes | Verdes | 7 falhas backend, 1 frontend | Suites quebradas |

## Dívida Evolutiva

- Duplicação de UI
- Lógica de UI no core
- Persistência JSON sem lock
- Testes quebrados
- Documentação com paths desatualizados

## Oportunidades

- Concluir migração e remover `legacy/app.py`
- Refatorar `chat_service.py` e `HybridRetriever`
- Migrar para banco relacional
- Adicionar fila persistente para jobs
- Clusterizar infraestrutura

## Gate

**Como a arquitetura evoluiu?** De protótipo Streamlit monolítico para monorepo com motor RAG compartilhado, API FastAPI e frontend React, ainda em transição com dívidas técnicas significativas.

## Evidências

- `legacy/app.py`
- `backend/main.py`
- `frontend/src/main.tsx`
- `docs/MIGRATION_MAP.md`
- `docs/PROJECT_OVERVIEW.md`
