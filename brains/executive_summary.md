# PDF Extreme AI — Executive Summary

## O que é

PDF Extreme AI é um assistente RAG para PDFs jurídicos/periciais. O usuário faz upload de autos, faz perguntas em linguagem natural e recebe respostas com citações por página e arquivo.

## Estado atual

- **Motor RAG maduro:** recuperação híbrida (Qdrant semântico + SQLite FTS5 lexical + RRF + reranker BGE), validação de respostas, modos auditoria/analítico, suporte a thinking do Ollama.
- **API FastAPI v2:** cobre auth, projetos, documentos, ingest, chat, chat turns, export e proofread.
- **Frontend React funcional:** SPA com login, projetos, upload, chat, corretor e configuração.
- **UI Streamlit legada (`legacy/app.py`):** ainda existe e compartilha o motor.
- **Persistência:** JSON em disco (`data/`), Qdrant e SQLite FTS5.

## Pontos fortes

- Pipeline RAG especializado para documentos jurídicos
- Múltiplos perfis de retrieval (rápido, preciso, pericial)
- Validação automática de respostas com retry
- Chat turns assíncronos com persistência
- Separação em camadas (core/backend/frontend)

## Pontos de atenção

- **Segurança:** secret default, rotas públicas sensíveis, `dangerouslySetInnerHTML`
- **Concorrência:** JSON sem locks, jobs em threads daemon
- **Qualidade:** testes quebrados (7 backend, 1 frontend)
- **Dívida técnica:** `chat_service.py` e `HybridRetriever` muito grandes, duplicação Streamlit/FastAPI, UI no core
- **Operação:** deploy single-instance, dados de produção no repo

## Recomendações prioritárias

1. Corrigir suites de teste quebradas
2. Configurar `SESSION_SECRET` e proteger rotas públicas
3. Refatorar `chat_service.py` e `HybridRetriever`
4. Mover dados de produção para fora do repositório
5. Planejar remoção do `legacy/app.py`
6. Migrar persistência JSON para banco relacional

## Confiança

Alta. A análise baseou-se em leitura direta de dezenas de arquivos-fonte, execução de testes e inspeção de dados de runtime.
