# Relatório de Divergências — PDF Extreme AI

## Metodologia

Comparação entre código-fonte, artefatos de conhecimento (`knowledge/`, `summaries/`, `brains/`) e documentação em `docs/`.

## Divergências Críticas

### D01 — Paths de dados desatualizados na documentação
- **Categoria:** Estrutural / Documentação
- **Impacto:** Alta
- **Descrição:** `docs/PROJECT_OVERVIEW.md` e `docs/OPERATIONS.md` referenciam `projects_data/` e `.lexical_<id>.db` no diretório de trabalho, mas o código usa `data/projects/<id>/` e `data/lexical/<id>.db`.
- **Evidências:**
  - `docs/PROJECT_OVERVIEW.md:288-299`
  - `docs/OPERATIONS.md:86`
  - `core/paths.py`
  - `data/projects_registry.json`
  - `data/projects/<id>/`
  - `data/lexical/<id>.db`
- **Arquivos Afetados:** `docs/PROJECT_OVERVIEW.md`, `docs/OPERATIONS.md`
- **Correção Recomendada:** Atualizar documentação para refletir `data/projects/<id>/`, `data/lexical/<id>.db` e `data/checkpoints/<id>.json`.

### D02 — `ProjectStore` não possui `delete_project`
- **Categoria:** Arquitetural / Domínio
- **Impacto:** Alta
- **Descrição:** `docs/MIGRATION_MAP.md:91` menciona `ProjectStore.delete_project` como ausente, e de fato a API v2 implementou a lógica de exclusão em `backend/services/project_cleanup.py` manipulando métodos privados do store.
- **Evidências:**
  - `docs/MIGRATION_MAP.md:91`
  - `backend/services/project_cleanup.py:60-72`
  - `core/project_store.py`
- **Arquivos Afetados:** `core/project_store.py`, `backend/services/project_cleanup.py`, `docs/MIGRATION_MAP.md`
- **Correção Recomendada:** Adicionar `delete_project` no `ProjectStore` do core e remover manipulação de métodos privados na API v2.

### D03 — Assinatura de funções de memória mudou sem atualizar testes
- **Categoria:** Testes
- **Impacto:** Crítica
- **Descrição:** `backend/services/chat_service.py` chama `sync_memory_with_session` e `rehydrate_memory_from_messages` com argumentos `settings` e `llm`, mas os fakes em `tests/backend/test_chat_rag_flow.py` não aceitam esses kwargs, causando 7 falhas.
- **Evidências:**
  - `backend/services/chat_service.py:515-530`
  - `core/chat_memory.py:25-71`
  - `tests/backend/test_chat_rag_flow.py:293-739`
- **Arquivos Afetados:** `tests/backend/test_chat_rag_flow.py`
- **Correção Recomendada:** Atualizar fakes para aceitar `settings` e `llm`.

### D04 — Teste frontend desatualizado para `onStatus`
- **Categoria:** Testes
- **Impacto:** Média
- **Descrição:** `frontend/src/api/chat.test.ts` espera `onStatus("Buscando")`, mas `chat.ts` chama `onStatus("Buscando", { message: "Buscando" })`.
- **Evidências:**
  - `frontend/src/api/chat.test.ts`
  - `frontend/src/api/chat.ts`
- **Arquivos Afetados:** `frontend/src/api/chat.test.ts`
- **Correção Recomendada:** Ajustar mock/expect para refletir a nova assinatura.

## Divergências Altas

### D05 — `CHAT_ASYNC_TURNS` default na documentação vs código
- **Categoria:** Comportamental
- **Impacto:** Média
- **Descrição:** `docs/CHAT_TURN_PERSISTENCE_SPEC.md` diz default `false` em testes legados, mas o código verifica apenas `1/true/yes`; ausência é `False`, o que é consistente, porém a documentação não reflete o comportamento da API v2.
- **Evidências:**
  - `docs/CHAT_TURN_PERSISTENCE_SPEC.md`
  - `backend/services/chat_service.py:152`
- **Arquivos Afetados:** `docs/CHAT_TURN_PERSISTENCE_SPEC.md`
- **Correção Recomendada:** Documentar claramente o default e o comportamento da feature flag.

### D06 — `BOOTSTRAP_ADMIN_USER` mencionado na spec mas tratado por script externo
- **Categoria:** Documentação
- **Impacto:** Baixa
- **Descrição:** `docs/AUTH_SPEC.md` menciona `BOOTSTRAP_ADMIN_USER`, mas o bootstrap é feito por `scripts/bootstrap_admin.py`, não pelo backend.
- **Evidências:**
  - `docs/AUTH_SPEC.md`
  - `scripts/bootstrap_admin.py`
- **Arquivos Afetados:** `docs/AUTH_SPEC.md`
- **Correção Recomendada:** Remover referência a `BOOTSTRAP_ADMIN_USER` ou documentar o script.

### D07 — Componentes frontend legados não refletidos na documentação
- **Categoria:** Frontend / Documentação
- **Impacto:** Baixa
- **Descrição:** `frontend/src/components/ProjectSidebar.tsx` e `ConversationList.tsx` existem mas não são usados no `AppShell`. A documentação não menciona a substituição por `UnifiedSidebar`.
- **Evidências:**
  - `frontend/src/components/ProjectSidebar.tsx`
  - `frontend/src/components/ConversationList.tsx`
  - `frontend/src/components/UnifiedSidebar.tsx`
  - `frontend/src/App.tsx`
- **Arquivos Afetados:** Código (remover componentes mortos)
- **Correção Recomendada:** Remover componentes não utilizados ou documentar que são legados.

### D08 — `eval/gold_questions.json` muito pequeno para o propósito declarado
- **Categoria:** Dados / Testes
- **Impacto:** Média
- **Descrição:** O eval RAG é mencionado como ferramenta de avaliação offline, mas contém apenas 2 perguntas, insuficiente para medição confiável.
- **Evidências:**
  - `eval/gold_questions.json`
  - `scripts/eval_rag.py`
- **Arquivos Afetados:** `eval/gold_questions.json`
- **Correção Recomendada:** Expandir dataset ou documentar que é apenas demonstração.

## Divergências Médias

### D09 — Documentação cita UI Streamlit como principal
- **Categoria:** Documentação
- **Impacto:** Média
- **Descrição:** `docs/PROJECT_OVERVIEW.md` descreve a UI principal como Streamlit, mas o `README.md` e o desenvolvimento atual indicam React + FastAPI como UI principal.
- **Evidências:**
  - `docs/PROJECT_OVERVIEW.md:24-27`, `docs/PROJECT_OVERVIEW.md:311-340`
  - `README.md:36-55`
  - `frontend/src/`
- **Arquivos Afetados:** `docs/PROJECT_OVERVIEW.md`
- **Correção Recomendada:** Atualizar seção de UI para refletir React + FastAPI como principal e Streamlit como legado.

### D10 — `RAG_TEST_PLAN.md` menciona features já implementadas como futuras
- **Categoria:** Documentação
- **Impacto:** Baixa
- **Descrição:** `docs/RAG_TEST_PLAN.md` lista features futuras (A–L) como `multi_query`, `cross_doc_graph`, classificação documental, diversificação RRF; várias já estão implementadas.
- **Evidências:**
  - `docs/RAG_TEST_PLAN.md:51-55`
  - `core/multi_query.py`
  - `core/cross_doc_graph.py`
  - `core/retrieval_pipeline.py`
- **Arquivos Afetados:** `docs/RAG_TEST_PLAN.md`
- **Correção Recomendada:** Revisar plano e marcar features implementadas.

## Resumo por Categoria

| Categoria | Crítica | Alta | Média | Baixa |
|---|---|---|---|---|
| Documentação | 1 | 1 | 2 | 1 |
| Testes | 1 | 1 | 0 | 0 |
| Arquitetura/Domínio | 1 | 0 | 0 | 0 |
| Frontend | 0 | 0 | 1 | 1 |
| Dados | 0 | 1 | 0 | 0 |

## Recomendações Imediatas

1. Corrigir testes quebrados (D03, D04)
2. Atualizar paths de dados na documentação (D01)
3. Adicionar `delete_project` no core (D02)
4. Expandir ou documentar limitação do eval (D08)
5. Sincronizar `PROJECT_OVERVIEW.md` com a UI atual (D09)

## Gate

Toda divergência crítica e alta deve gerar atualização imediata da Knowledge Layer e, quando aplicável, do código ou documentação.
