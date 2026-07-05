# PDF Extreme AI — Data Flows

## Origem dos Dados

| Origem | Tipo | Descrição |
|---|---|---|
| Upload de PDFs | Arquivos binários | Usuário envia PDFs pelo frontend; backend persiste em `data/projects/<id>/uploads/` |
| Entrada de texto | String | Perguntas no chat, texto no corretor, regras e memória do projeto |
| Dados de autenticação | JSON | Administradores e consultores criados via scripts/API |
| Configuração de runtime | `.env` / variáveis de ambiente | Modelos, timeouts, perfis de retrieval, flags |

## Transformação

### Ingestão
```
PDF (bytes)
  ↓
pdf_extraction.py (PyMuPDF / pypdf / OCR)
  ↓
Texto bruto
  ↓
SentenceWindowNodeParser (chunk ~700 tokens, overlap 120)
  ↓
Chunks com metadados (source_file, page, etc.)
  ↓
HuggingFaceEmbedding (BGE-M3) → vetores 1024 dim
  ↓
Qdrant (coleção do projeto)
  ↓
LexicalIndex.upsert_many → SQLite FTS5
  ↓
PageLexicalIndex.build_from_chunk_rows → page_fts
  ↓
entity_timeline.extract_entities_from_text → entities.json
  ↓
cross_doc_graph.build_graph_from_rows → cross_doc_graph.json
```

### Consulta RAG
```
Pergunta (string)
  ↓
query_planner.plan_query → QueryPlan (perfil, intent, página/faixa, arquivo, seção)
  ↓
query_expansion.expand_query (termos forenses + memória)
  ↓
multi_query.build_multi_queries (intents analíticos)
  ↓
Busca paralela:
  ├── Semântica: Qdrant VectorStoreIndex
  ├── Lexical: LexicalIndex.search
  └── Por página: PageLexicalIndex.search
  ↓
RRF (Reciprocal Rank Fusion, k=60)
  ↓
Diversificação por (source_file, page)
  ↓
Boost por seção, entidades, cross-doc graph, parent context
  ↓
Reranker BGE
  ↓
CondensePlusContextChatEngine (condensa histórico + contexto)
  ↓
Ollama gera resposta
  ↓
answer_validator.validate_answer
  ↓
Retry/fallback se necessário
  ↓
Persistência da mensagem
```

### Chat Livre
```
Pergunta
  ↓
SimpleChatEngine
  ↓
Ollama (prompt de sistema FREE_CHAT_SYSTEM)
  ↓
Resposta streaming
  ↓
Persistência da mensagem
```

### Corretor
```
Texto colado
  ↓
proofread_service.split_proofread_blocks
  ↓
LLM Ollama responde JSON (corrected_text, changes)
  ↓
build_highlighted_html
  ↓
Renderização no frontend (dangerouslySetInnerHTML)
```

## Persistência

| Dado | Onde | Formato |
|---|---|---|
| Registry de projetos | `data/projects_registry.json` | JSON |
| Uploads de PDF | `data/projects/<id>/uploads/` | Arquivos binários |
| Conversas | `data/projects/<id>/conversations/<uuid>.json` | JSON |
| Memória do caso | `data/projects/<id>/project_memory.md` + `.json` | Markdown/JSON |
| Entidades extraídas | `data/projects/<id>/entities.json` | JSON |
| Grafo cross-doc | `data/projects/<id>/cross_doc_graph.json` | JSON |
| Índice lexical | `data/lexical/<id>.db` | SQLite FTS5 |
| Checkpoint de ingest | `data/checkpoints/<id>.json` | JSON |
| Vetores semânticos | `qdrant_data/` (volume Docker) | Qdrant storage |
| Auth | `data/auth/admins.json`, `data/auth/usuarios_app.json` | JSON |

## Consumo

| Dado | Consumidor |
|---|---|
| Vetores Qdrant | HybridRetriever, ingest_service |
| Índices FTS5 | HybridRetriever, modo auditoria |
| Registry JSON | Backend API, legacy Streamlit |
| Conversas JSON | Chat Service, frontend |
| Memória do caso | Chat RAG (contexto), chat livre (opcional) |
| Regras globais | Prompts RAG e chat livre |
| Entidades/grafo | Boost de retrieval, UI de timeline |

## Descarte

- Projetos excluídos: remove registry, uploads, conversas, memória, entidades, grafo, índice lexical, checkpoint e **coleção inteira do Qdrant**.
- Documentos removidos: deleta do índice lexical e do Qdrant por `source_file`.
- Conversas excluídas: arquivo JSON removido.

## Gate

**Como os dados atravessam o sistema?** PDFs são extraídos, chunkados, embedados e indexados em Qdrant e SQLite FTS5; perguntas disparam planejamento, expansão, recuperação híbrida, reranking, geração, validação e persistência; conversas, memória e regras alimentam o contexto.

## Evidências

- `core/ingest_service.py`
- `core/retrieval_pipeline.py`
- `core/query_planner.py`
- `core/query_expansion.py`
- `core/answer_validator.py`
- `core/conversation_store.py`
- `core/project_store.py`
- `core/project_memory.py`
- `core/paths.py`
- `backend/services/project_cleanup.py`
