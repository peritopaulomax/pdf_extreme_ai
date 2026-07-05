# PDF Extreme AI — Test Strategy

## Cobertura

### Unitários
- Local: `tests/core/test_answer_validator.py`, `tests/core/test_query_planner.py`, `tests/core/test_proofread_highlight.py`, `tests/core/test_app_workspace.py`
- Foco: Validator, planner, workspace, proofread, chat blocks
- Framework: unittest + pytest

### Integração / Contratos
- Local: `tests/backend/test_rag_contracts.py`
- Foco: Planner, expansão, prompts, validator, índice lexical, RRF

### Fluxo de Chat (mockado)
- Local: `tests/backend/test_chat_rag_flow.py`
- Foco: SSE, retry, interrupção, fallback, stack cache
- Estado: **7 falhas** por descompasso de assinatura entre `chat_service.py` e fakes

### Persistência de Turnos
- Local: `tests/backend/test_chat_turn_store.py`, `tests/backend/test_chat_turn_runner.py`, `tests/backend/test_chat_turn_api.py`
- Foco: Turnos async, checkpoints, cancelamento, SSE

### Auth e Ownership
- Local: `tests/backend/test_auth.py`, `tests/backend/test_project_ownership.py`
- Foco: Login, reset, RBAC, isolamento de projetos

### Documentos
- Local: `tests/backend/test_documents_api.py`
- Foco: Delete, reprocess, streaming de ingest

### Smoke
- Local: `tests/core/test_api_smoke.py`
- Foco: Health, CRUD conversas, proofread
- Observação: faz skip condicional se Ollama retornar 500

### Frontend
- Local: `frontend/src/**/*.test.*`
- Foco: Hooks, componentes, API client, SSE
- Framework: vitest + jsdom + Testing Library
- Estado: **1 falha** em `frontend/src/api/chat.test.ts` (onStatus recebe 2 args)

## Matriz de Testes

| Componente | Tipo de Teste | Prioridade |
|---|---|---|
| answer_validator | Unitário | Alta |
| query_planner | Unitário / Contrato | Alta |
| retrieval_pipeline | Contrato (mockado) | Alta |
| chat_service | Integração mockada | Alta |
| chat_turn_store/runner/api | Integração | Alta |
| auth | Integração | Alta |
| project_ownership | Integração | Alta |
| documents_api | Integração | Média |
| ingest_service | **Ausente** | Alta (lacuna) |
| pdf_extraction/OCR | **Ausente** | Média (lacuna) |
| Qdrant/Ollama real | **Ausente** | Alta (lacuna) |
| frontend ChatPanel | Componente | Média |
| frontend useChatTurn | Hook | Média |

## Críticos

- Fluxos críticos: chat RAG, ingestão, autenticação
- Integrações críticas: backend ↔ Ollama, backend ↔ Qdrant
- Dados críticos: `projects_registry.json`, conversas

## Lacunas

| Lacuna | Impacto |
|---|---|
| Nenhum teste de ingestão end-to-end | Mudanças no pipeline de ingest podem quebrar sem detectar |
| Nenhum teste de `project_store.py`/`conversation_store.py` isolado | Lógica de persistência não coberta |
| Nenhum teste de segurança | Session fixation, CSRF, brute-force não cobertos |
| `test_api_smoke.py` faz skip se Ollama falha | Pode mascarar regressões |
| `test_chat_rag_flow.py` depende de ~15 fakes | Qualquer mudança de assinatura quebra a suite |
| Dados de produção em `data/` | Dificulta CI e aumenta risco de vazamento |
| Eval gold muito pequeno (`eval/gold_questions.json` tem 2 perguntas) | Não permite avaliação confiável de recall |

## Riscos

| Risco | Impacto |
|---|---|
| Testes quebrados na área crítica de chat | Regressões não detectadas |
| Dependência massiva de mocks | Testes frágeis |
| Falta de testes de integração real | Problemas só aparecem em produção |

## Roadmap de Testes

| Ação | Benefício | Prioridade |
|---|---|---|
| Corrigir `test_chat_rag_flow.py` (assinar `settings`/`llm`) | Suite backend verde | Alta |
| Corrigir `frontend/src/api/chat.test.ts` | Suite frontend verde | Alta |
| Adicionar testes para `project_store.py` e `conversation_store.py` | Cobrir persistência | Alta |
| Adicionar teste de integração mínimo com Qdrant + Ollama | Detectar problemas reais | Média |
| Expandir `eval/gold_questions.json` | Avaliação RAG confiável | Média |
| Adicionar testes de segurança (auth) | Reduzir riscos | Média |
| Remover `data/` do controle de versão | CI saudável | Alta |

## Gate

**O que ainda não está protegido?** Ingestão end-to-end, persistência JSON isolada, integração real com Qdrant/Ollama, segurança de sessão e testes de frontend para componentes atuais (alguns testes cobrem hooks legados).

## Evidências

- `tests/`
- `frontend/src/**/*.test.*`
- `docs/CHAT_TURN_PERSISTENCE_TEST_PLAN.md`
- `docs/RAG_TEST_PLAN.md`
- `eval/gold_questions.json`
