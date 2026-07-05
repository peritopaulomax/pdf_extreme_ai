# PDF Extreme AI — Technical Debt

## Matriz de Dívida Técnica

| ID | Dívida | Evidência | Impacto | Esforço | Prioridade |
|---|---|---|---|---|---|
| D01 | `chat_service.py` ~1280 linhas, múltiplos modos | `backend/services/chat_service.py` | Difícil manutenção/testes | Alto | Alta |
| D02 | `HybridRetriever._retrieve` monolítico (~200 linhas) | `core/retrieval_pipeline.py` | Difícil evoluir retrieval | Médio | Alta |
| D03 | `ingest_service.py` com muitas responsabilidades | `core/ingest_service.py` | Difícil testar isoladamente | Médio | Média |
| D04 | Lógica de UI no `core/` (Streamlit) | `core/retrieved_chunks_ui.py`, `core/proofread_ui.py` | Motor carrega UI legada | Médio | Média |
| D05 | Bootstrap manipula `sys.path` e `os.chdir` | `core/bootstrap.py`, `backend/core/bootstrap.py` | Fragilidade de imports | Baixo | Média |
| D06 | Duplicação de `core/bootstrap.py` e `backend/core/bootstrap.py` | Ambos existem | Confusão de paths | Baixo | Baixa |
| D07 | Duplicação Streamlit ↔ FastAPI | `legacy/app.py` vs `backend/services/chat_service.py` | Manutenção dupla | Alto | Alta |
| D08 | Testes quebrados por assinatura de fakes | `tests/backend/test_chat_rag_flow.py` | Suite vermelha | Baixo | Alta |
| D09 | Teste frontend desatualizado | `frontend/src/api/chat.test.ts` | Suite vermelha | Baixo | Alta |
| D10 | Manipulação global de `os.environ` | `core/runtime_config.py`, `core/http_proxy_bootstrap.py` | Efeitos colaterais | Médio | Média |
| D11 | Monkey-patch em LlamaIndex no import | `core/llama_index_stream_queue_patch.py` | Fragilidade com upgrades | Baixo | Média |
| D12 | Persistência JSON sem locks | `core/project_store.py`, `core/conversation_store.py` | Corrupção em concorrência | Médio | Alta |
| D13 | `ProjectStore` não tem `delete_project` | `core/project_store.py` | API v2 implementa própria | Baixo | Média |
| D14 | CSS monolítico ~1790 linhas | `frontend/src/index.css` | Difícil manter | Médio | Baixa |
| D15 | Componentes legados não utilizados | `frontend/src/components/ProjectSidebar.tsx`, `ConversationList.tsx` | Poluição de código | Baixo | Baixa |
| D16 | Duplicação de hooks de streaming | `useChatStream.ts` vs `useChatTurn.ts` | Divergência | Baixo | Média |
| D17 | Hardcodes de modelo no frontend e backend | `frontend/src/api/types.ts`, `core/runtime_config.py` | Deploy duplicado | Baixo | Média |
| D18 | Paths absolutos de modelos | `core/runtime_config.py`, `.env.example` | Portabilidade ruim | Baixo | Alta |
| D19 | Documentação com paths desatualizados | `docs/PROJECT_OVERVIEW.md`, `docs/OPERATIONS.md` | Divergência | Baixo | Média |
| D20 | Dados de produção em `data/` | `data/projects/`, `data/auth/` | CI e segurança | Baixo | Alta |

## Acoplamento

- Backend importa `core/` via bootstrap que modifica `sys.path`.
- `chat_service.py` acoplado a stack manager, chat turn store, runner e muitos módulos do core.
- `HybridRetriever` acoplado a planejamento, expansão, lexical, página, auditoria, cross-doc, entidades.

## Duplicação

- Lógica de chat RAG em `legacy/app.py` e `backend/services/chat_service.py`.
- Lógica de streaming SSE em `useChatStream.ts` e `useChatTurn.ts`.
- Configuração de modelos no frontend e no backend.

## Complexidade

- `chat_service.py`: múltiplos modos (RAG/free), sync/async, retry, fallback, audit, analytical.
- `HybridRetriever._retrieve`: ~200 linhas com múltiplas estratégias.
- `runtime_config.py`: dataclass gigante com ~80 campos.

## Dependências Frágeis

- Monkey-patch em LlamaIndex.
- Dependência de formatos internos do Ollama para thinking.
- Imports locais dentro de funções após `bootstrap_legacy()`.

## Arquitetura Degradada

- Lógica de UI no core.
- Duplicação de UI (Streamlit + React).
- Jobs em threads ao invés de fila.
- Persistência JSON ao invés de banco relacional.

## Testabilidade

- `ingest_service.py` e `HybridRetriever` difíceis de testar sem Qdrant/Ollama.
- `chat_service.py` requer ~15 fakes.
- Testes quebrados indicam degradação.

## Observabilidade

- Logs não estruturados.
- Sem métricas/alertas centralizados.
- Sem tracing.

## Roadmap de Redução

| Ação | Benefício | Prioridade |
|---|---|---|
| Refatorar `chat_service.py` em handlers por modo | Manutenibilidade | Alta |
| Quebrar `HybridRetriever._retrieve` em etapas | Testabilidade | Alta |
| Mover UI do core para camada de apresentação | Separação | Média |
| Remover `legacy/app.py` ou congelar funcionalidade | Reduzir duplicação | Alta |
| Corrigir suites de teste | Confiança | Alta |
| Migrar registry/conversas para SQLite/Postgres | Concorrência | Média |
| Remover dados de produção do VCS | Segurança/CI | Alta |
| Centralizar config de modelos no backend | Consistência | Média |
| Adicionar logger estruturado | Observabilidade | Média |

## Evidências

- `backend/services/chat_service.py`
- `core/retrieval_pipeline.py`
- `core/ingest_service.py`
- `core/llama_index_stream_queue_patch.py`
- `core/runtime_config.py`
- `core/project_store.py`
- `legacy/app.py`
- `frontend/src/index.css`
- `frontend/src/components/ProjectSidebar.tsx`
- `frontend/src/hooks/useChatStream.ts`
- `tests/backend/test_chat_rag_flow.py`
- `frontend/src/api/chat.test.ts`
