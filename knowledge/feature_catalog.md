# PDF Extreme AI — Feature Catalog

## Tabela Principal

| Feature | Objetivo | Usuários | Componentes | APIs | Criticidade | Status |
|---|---|---|---|---|---|---|
| Projetos isolados | Organizar documentos e conversas por caso | Consultor, Admin | `core/project_store.py`, `backend/api/projects.py` | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}` | Crítica | Ativa |
| Upload de PDFs | Ingerir documentos no projeto | Consultor | `backend/api/ingest.py`, `backend/services/ingest_runner.py`, `core/ingest_service.py` | `POST /projects/{id}/ingest`, `POST /projects/{id}/ingest/stream` | Crítica | Ativa |
| Ingestão semântica | Indexar vetores BGE-M3 no Qdrant | Sistema | `core/ingest_service.py`, `core/index_bootstrap.py` | Interno | Crítica | Ativa |
| Ingestão lexical | Indexar texto em SQLite FTS5 | Sistema | `core/retrieval_lexical.py`, `core/page_index.py` | Interno | Alta | Ativa |
| Chat RAG | Responder perguntas sobre documentos | Consultor | `backend/services/chat_service.py`, `core/retrieval_pipeline.py` | `POST /projects/{id}/chat/rag` | Crítica | Ativa |
| Chat livre | Conversa sem retrieval | Consultor | `backend/services/chat_service.py`, `core/free_chat_engine.py` | `POST /projects/{id}/chat/free` | Média | Ativa |
| Corretor ortográfico | Corrigir texto colado | Consultor | `core/proofread_service.py`, `backend/api/proofread.py` | `POST /proofread`, `POST /proofread/stream` | Média | Ativa |
| Modo auditoria | Varredura exaustiva FTS por termo | Consultor | `core/exhaustive_retrieval.py`, `core/audit_synthesis.py` | `POST /projects/{id}/chat/rag` (audit_mode=true) | Alta | Ativa |
| Modo analítico | Map-reduce para perguntas amplas | Consultor | `core/analytical_synthesis.py` | `POST /projects/{id}/chat/rag` (deep_mode=true) | Alta | Ativa |
| Export Markdown | Exportar resposta com trechos | Consultor | `backend/services/export_service.py`, `backend/api/export.py` | `POST /export/markdown` | Baixa | Ativa |
| Memória do caso | Contexto narrativo editável | Consultor | `core/project_memory.py`, `core/case_memory.py` | `GET/PUT /projects/{id}/memory` | Alta | Ativa |
| Regras globais | Instruções por projeto | Consultor | `core/rag_prompts.py` | `GET/PATCH /projects/{id}/rules` | Média | Ativa |
| Autenticação | Login e sessão | Admin, Consultor | `backend/auth/`, `backend/api/auth.py` | `POST /auth/login`, etc. | Crítica | Ativa |
| Gestão de usuários | CRUD admins/consultores | Admin | `backend/auth/store.py`, `backend/api/auth.py` | `/auth/administradores`, `/auth/consultores` | Alta | Ativa |
| Conversas salvas | Histórico persistente | Consultor | `core/conversation_store.py`, `backend/api/conversations.py` | `/projects/{id}/conversations` | Alta | Ativa |
| Chat turns assíncronos | Persistência desde o início do turno | Consultor | `backend/services/chat_turn_store.py`, `backend/services/chat_turn_runner.py` | `/projects/{id}/chat/turns/{tid}/events` | Alta | Ativa (flag) |
| Entidades e timeline | NER leve (CPF/CNPJ/nomes) | Consultor | `core/entity_timeline.py` | Interno | Baixa | Ativa |
| Grafo cross-doc | Referências entre documentos | Sistema | `core/cross_doc_graph.py` | Interno | Baixa | Ativa |
| OCR condicional | Extrair texto de PDFs escaneados | Sistema | `core/pdf_extraction.py` | `POST /ingest?force_ocr=true` | Média | Experimental |
| UI Streamlit legada | Interface antiga | Consultor | `legacy/app.py` | — | Baixa | Legada |

## Classificação

### Core Features
- Projetos isolados
- Upload de PDFs
- Chat RAG
- Recuperação híbrida
- Validação de respostas
- Autenticação

### Supporting Features
- Export Markdown
- Corretor ortográfico
- Entidades e timeline
- Grafo cross-doc
- OCR condicional

### Administrative Features
- Gestão de usuários
- Regras globais
- Memória do caso

### Experimental Features
- Chat turns assíncronos (flag `CHAT_ASYNC_TURNS`)
- OCR condicional

## Gate

**O que o sistema entrega?** Assistente RAG especializado para PDFs jurídicos, com projetos isolados, upload/ingestão de PDFs, chat RAG com citações, chat livre, corretor ortográfico, modos auditoria/analítico e gestão de usuários.

## Evidências

- `docs/PROJECT_OVERVIEW.md`
- `backend/api/`
- `backend/services/`
- `core/`
- `legacy/app.py`
- `frontend/src/`
