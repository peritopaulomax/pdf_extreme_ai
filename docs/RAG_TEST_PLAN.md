# RAG Test Plan

Plano de testes dirigido por especificação para as melhorias de RAG do `pdf_extreme_ai_v2`.

## Objetivo

Criar uma suíte TDD que:

1. valide o contrato do `pdf_extreme_ai_v2` na borda API/SSE/React;
2. importe o engine legado real quando necessário para garantir paridade comportamental;
3. deixe testes vermelhos para as features ainda não implementadas, servindo de trilha para o desenvolvimento incremental.

> **Nota:** várias features listadas abaixo (A–L) já estão implementadas no motor atual (`multi_query`, `cross_doc_graph`, diversificação RRF, etc.). O plano deve ser revisado para marcar essas features como concluídas e manter vermelhos apenas os testes de funcionalidades futuras.

## Escopo

O escopo desta suíte é deliberadamente duplo:

- `pdf_extreme_ai_v2` como aplicação principal, cobrindo API FastAPI, `chat_service`, `stack_manager`, hooks React e componentes;
- engine legado importado via `backend/core/bootstrap.py`, cobrindo `plan_query`, `expand_query`, `validate_answer`, `LexicalIndex`, `HybridRetriever` e prompts.

## Estrutura da suíte

### Backend: contratos do engine legado importado pelo v2

- `backend/tests/test_rag_contracts.py`

Cobertura:

- triggers narrativos / cronologia no planner;
- expansão sempre ativa;
- preservação de identificadores nos prompts;
- retry agressivo no validador;
- contrato futuro da busca lexical escalonada;
- contrato futuro de diversificação de resultados;
- existência dos módulos futuros `multi_query` e `cross_doc_graph`;
- pontos de extensão futuros para classificação documental.

### Backend: fluxo v2

- `backend/tests/test_chat_rag_flow.py`

Cobertura:

- `/projects/{id}/chat/rag` e `/projects/{id}/chat/free`;
- headers SSE;
- ordenação de eventos `status`, `token`, `meta`, `done`;
- retry via fallback;
- cache e invalidação de `stack_manager`.

### Frontend

- `frontend/src/lib/sse.test.ts`
- `frontend/src/api/chat.test.ts`
- `frontend/src/hooks/useChatStream.test.tsx`
- `frontend/src/components/chat-ui.test.tsx`

Cobertura:

- parser SSE;
- `streamChat()` com callbacks por evento;
- `useChatStream()` agregando thinking, tokens, meta e done;
- `ChatSettingsPopover`, `MessageList` e `ChatPanel`;
- contratos futuros de `validation_issues` e “Modo profundo”.

## Mapeamento por feature

| Feature | Testes |
|---|---|
| B | `test_rag_contracts.py::test_plan_query_promotes_historico_oficios_para_busca_exaustiva` |
| C | `test_rag_contracts.py::test_expand_query_enriches_analytic_legal_queries_even_without_forensic_terms` |
| D | `test_rag_contracts.py::test_validate_answer_retries_on_low_coverage_in_light_mode` e `test_chat_rag_flow.py::test_run_chat_turn_uses_retry_prompt_when_validation_requests_retry` |
| E | `test_rag_contracts.py::test_build_session_prompts_mentions_preserving_document_identifiers` |
| F | `test_rag_contracts.py::test_rrf_fusion_should_diversify_results_when_many_candidates_share_same_page` |
| G | `test_rag_contracts.py::test_lexical_search_contract_prefers_documents_matching_all_core_terms` |
| H | `test_rag_contracts.py::test_document_metadata_classifier_hook_contract_exists` |
| I | `useChatStream.test.tsx::test_preserves_validation_issues_for_future_low_coverage_ui` e `chat-ui.test.tsx::test_message_list_contract_for_low_coverage_banner` |
| J | `chat-ui.test.tsx::test_chat_settings_popover_contract_exposes_deep_mode_control` |
| K | `test_rag_contracts.py::test_cross_doc_graph_module_contract_exists` |
| L | `test_rag_contracts.py::test_rrf_fusion_should_diversify_results_when_many_candidates_share_same_page` |
| A | `test_rag_contracts.py::test_multi_query_module_contract_exists` |

## Estratégia de execução

### Backend

```bash
cd /home/labfaces/pdf_extreme_ai/pdf_extreme_ai_v2
pytest backend/tests/test_rag_contracts.py backend/tests/test_chat_rag_flow.py tests/test_api_smoke.py
```

### Frontend

```bash
cd /home/labfaces/pdf_extreme_ai/pdf_extreme_ai_v2/frontend
npm test
```

## Leitura esperada dos resultados

- alguns testes devem passar imediatamente, porque cobrem o contrato atual;
- os testes ligados às features A, B, C, D, E, F, G, H, I, J, K e L devem inicialmente falhar em maior ou menor grau;
- essas falhas são esperadas e servem como gate para a implementação das melhorias.

## Critério de progressão

Só avançar para implementação da feature quando:

1. o teste correspondente estiver escrito;
2. a falha estiver entendida e reproduzível;
3. a mudança de código puder ser validada localmente contra a suíte.

