# PDF Extreme AI — Change History

## Estado Atual

Sistema em transição da UI Streamlit legada (`legacy/app.py`) para uma arquitetura de API FastAPI + SPA React. O motor RAG em `core/` é compartilhado entre as duas interfaces. Versão da API: `0.3.0`.

## Linha do Tempo

### Fase 1 — Robustez RAG Inicial
- **Data:** Anterior ao atual
- **Estado Anterior:** Protótipo básico de RAG sobre PDFs
- **Estado Atual:** Trechos na UI, retry `light`, alertas de ingest, telemetria `fused`, testes de validator/planner
- **Motivação:** Melhorar qualidade das respostas e confiança do usuário
- **Benefícios:** Citações visíveis, retry automático, diagnósticos de retrieval
- **Custos:** Complexidade adicional no validator
- **Riscos:** Retry pode aumentar latência
- **Evidências:** `core/answer_validator.py`, `core/retrieved_chunks_ui.py`, `tests/core/test_answer_validator.py`

### Fase 2 — Índice por Página e Auditoria
- **Data:** Anterior ao atual
- **Estado Anterior:** Apenas busca semântica e lexical chunk-level
- **Estado Atual:** Índice por página (`page_fts`), modo auditoria, RRF, expansão de query, map-reduce
- **Motivação:** Melhorar recall para termos específicos e perguntas exaustivas
- **Benefícios:** Melhor ancoragem em autos jurídicos
- **Custos:** Mais complexidade no retrieval
- **Riscos:** Modo auditoria pode ser lento
- **Evidências:** `core/page_index.py`, `core/exhaustive_retrieval.py`, `core/audit_synthesis.py`, `core/analytical_synthesis.py`

### Fase 3 — OCR, Entidades e Eval
- **Data:** Anterior ao atual
- **Estado Anterior:** PDFs apenas com texto nativo
- **Estado Atual:** OCR condicional, NER leve (CPF/CNPJ/nomes), `eval_rag.py`
- **Motivação:** Suportar PDFs escaneados e extrair entidades relevantes
- **Benefícios:** Maior cobertura de documentos
- **Custos:** Dependência de Tesseract
- **Riscos:** OCR pode introduzir ruído
- **Evidências:** `core/pdf_extraction.py`, `core/entity_timeline.py`, `scripts/eval_rag.py`

### UX — Três Modos e Nova Interface
- **Data:** Em andamento
- **Estado Anterior:** Apenas Streamlit
- **Estado Atual:** FastAPI + React; três modos (RAG, chat livre, corretor); thinking no chat livre; correção com destaques
- **Motivação:** Interface moderna, melhor UX e separação de camadas
- **Benefícios:** Frontend desacoplado, API reutilizável
- **Custos:** Manutenção dupla durante migração
- **Riscos:** Divergência entre legacy e v2
- **Evidências:** `backend/`, `frontend/src/`, `docs/MIGRATION_MAP.md`

### Chat Turn Persistence
- **Data:** Em andamento
- **Estado Anterior:** Mensagens salvas apenas ao final
- **Estado Atual:** Turnos persistidos desde o início com status, SSE async, cancelamento
- **Motivação:** Resiliência e UX em respostas longas
- **Benefícios:** Recuperação de turnos, cancelamento, progresso
- **Custos:** Complexidade de concorrência
- **Riscos:** Jobs em threads daemon
- **Evidências:** `docs/CHAT_TURN_PERSISTENCE_SPEC.md`, `backend/services/chat_turn_store.py`, `backend/services/chat_turn_runner.py`

## Mudanças Estruturais

| Mudança | Impacto |
|---|---|
| Criação de `backend/` | Nova camada API |
| Criação de `frontend/` | Nova UI React |
| `core/` como motor compartilhado | Reuso entre Streamlit e FastAPI |
| `data/` como runtime unificado | Dados compartilhados entre UIs |
| `docs/MIGRATION_MAP.md` | Plano de migração |

## Dívida Evolutiva

- Manutenção dupla Streamlit + React
- `ProjectStore` legado sem `delete_project`
- Paths de dados em documentação desatualizados
- Testes quebrados por mudanças de assinatura

## Oportunidades

- Remover `legacy/app.py` após paridade completa
- Migrar persistência JSON para banco relacional
- Clusterizar Qdrant/Ollama
- Adicionar observabilidade estruturada

## Gate

**Como chegamos até aqui?** O sistema evoluiu de um protótipo RAG sobre Streamlit para uma aplicação com motor especializado em PDFs jurídicos, recuperação híbrida avançada e uma nova interface React + FastAPI em migração.

## Evidências

- `docs/PROJECT_OVERVIEW.md`
- `docs/MIGRATION_MAP.md`
- `docs/CHAT_TURN_PERSISTENCE_SPEC.md`
- `legacy/app.py`
- `backend/main.py`
- `frontend/src/App.tsx`
