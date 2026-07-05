# PDF Extreme AI — System Brain

## Arquitetura em 60 segundos

```text
Usuário
  ↓
Frontend React (Vite)
  ↓ REST + SSE
FastAPI Backend
  ↓
Motor RAG (core/)
  ├── Ingestão → Qdrant + SQLite FTS5
  ├── Recuperação → semântico + lexical + RRF + reranker
  └── Geração → Ollama gemma4
```

## Componentes críticos

| Componente | Criticidade |
|---|---|
| FastAPI App | Tier 0 |
| Auth Service | Tier 0 |
| Project Store | Tier 0 |
| Chat Service | Tier 0 |
| Stack Manager | Tier 0 |
| HybridRetriever | Tier 0 |
| Ollama LLM Adapter | Tier 0 |
| Qdrant Vector Store | Tier 0 |
| SQLite FTS5 | Tier 1 |
| Frontend React | Tier 1 |

## Fluxos críticos

1. Ingestão de PDF
2. Chat RAG
3. Chat livre
4. Autenticação

## Riscos críticos

- Sessão com secret default
- Rotas `/proofread` e `/export` públicas
- Dados de produção em `data/`
- FastAPI/Qdrant/Ollama single-instance
- Testes quebrados
- Registry JSON sem lock

## Dívidas críticas

- `chat_service.py` gigante
- `HybridRetriever._retrieve` monolítico
- Duplicação Streamlit ↔ FastAPI
- UI legada no core
- Persistência JSON sem locks
