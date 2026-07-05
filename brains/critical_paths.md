# PDF Extreme AI — Critical Paths

## Caminho 1: Ingestão de PDF

```text
Frontend: DocumentsPanel
  ↓ POST /projects/{id}/ingest/stream
Backend: api/ingest.py
  ↓
Backend: services/ingest_runner.py
  ↓
Core: ingest_service.run_ingest
  ↓
Core: pdf_extraction.extract_pdf_to_documents
  ↓
Core: SentenceWindowNodeParser
  ↓
Core: VectorStoreIndex → Qdrant
  ↓
Core: LexicalIndex.upsert_many + PageLexicalIndex.build_from_chunk_rows
  ↓
Core: entity_timeline + cross_doc_graph
  ↓
SSE progress → Frontend
```

**Se falhar:** usuário não consegue usar documentos no chat RAG.

## Caminho 2: Chat RAG

```text
Frontend: ChatPanel
  ↓ POST /projects/{id}/chat/rag
Backend: api/chat.py
  ↓
Backend: services/chat_service.run_chat_turn
  ↓
Backend: services/stack_manager.load_project_stack
  ↓
Core: query_planner.plan_query
  ↓
Core: query_expansion.expand_query
  ↓
Core: HybridRetriever._retrieve
  ↓
Core: RRF + reranker BGE
  ↓
Core: CondensePlusContextChatEngine
  ↓
Core: OllamaThinkingStream
  ↓
Core: answer_validator.validate_answer
  ↓
SSE tokens/thinking → Frontend
```

**Se falhar:** funcionalidade principal do sistema inoperante.

## Caminho 3: Autenticação

```text
Frontend: LoginPage
  ↓ POST /auth/login
Backend: api/auth.py
  ↓
Backend: auth/store.py
  ↓
Starlette SessionMiddleware (cookie)
```

**Se falhar:** nenhum usuário acessa o sistema.

## Caminho 4: Criação de Projeto

```text
Frontend: UnifiedSidebar
  ↓ POST /projects
Backend: api/projects.py
  ↓
Core: project_store.create_project
  ↓
Cria diretórios em data/projects/<id>/
  ↓
Registro em data/projects_registry.json
```

**Se falhar:** usuário não consegue organizar documentos.

## Pontos de pressão

| Caminho | Ponto de pressão |
|---|---|
| Ingestão | Embedding em GPU/VRAM, Qdrant disponível |
| Chat RAG | Ollama disponível, reranker CPU lento |
| Autenticação | `SESSION_SECRET` configurado |
| Criação de projeto | Registry JSON sem lock |

## Gate

Os caminhos críticos são: ingestão de PDF, chat RAG, autenticação e criação de projeto. A falha de qualquer um paralisa funcionalidades centrais.
