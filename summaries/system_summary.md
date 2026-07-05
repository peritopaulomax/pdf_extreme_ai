# PDF Extreme AI — System Summary

## O que é

Assistente RAG para PDFs jurídicos/periciais. Permite fazer perguntas sobre autos e documentos em PDF, com citações por página/arquivo, busca híbrida semântica+lexical e geração via LLM local.

## Arquitetura em 30 segundos

```text
Frontend React
  ↓ REST + SSE
FastAPI Backend
  ↓
Motor RAG (core/)
  ├── Ingestão: PyMuPDF/pypdf/OCR → chunks → Qdrant + SQLite FTS5
  ├── Recuperação: semântica + lexical + página + RRF + reranker BGE
  ├── Geração: Ollama (gemma4)
  └── Validação: citações e retry automático
```

## Domínio

- Projetos isolados por `owner_id`
- Documentos PDF com metadados de ingestão
- Conversas com turnos (sync/async)
- Memória do caso e regras globais por projeto
- Entidades (CPF/CNPJ/nomes) e grafo cross-doc

## Dependências críticas

- Qdrant (vetores semânticos)
- Ollama (LLM gemma4)
- HuggingFace BGE-M3 (embedding)
- HuggingFace BGE-reranker-base (reranker)
- SQLite FTS5 (lexical)
- FastAPI + Uvicorn + React + Vite

## Modos de uso

1. **Autos (RAG)** — perguntas sobre documentos
2. **Chat livre** — conversa sem retrieval
3. **Corretor** — correção ortográfica/gramatical

## Riscos críticos

- Sessão com secret default em produção
- Rotas `/proofread` e `/export` públicas
- Dados de produção em `data/` no repositório
- Qdrant/Ollama/FastAPI single-instance
- Testes quebrados em chat
- Registry JSON sem lock de concorrência

## Dívidas críticas

- `chat_service.py` ~1280 linhas
- `HybridRetriever._retrieve` monolítico
- Duplicação Streamlit ↔ FastAPI
- Lógica de UI no core
- Persistência JSON sem locks

## Evolução

Em transição: Streamlit legado → FastAPI + React. Motor RAG maduro; API v2 em desenvolvimento; frontend funcional mas com código legado e testes desatualizados.
