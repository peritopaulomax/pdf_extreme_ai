# PDF Extreme AI — Operational Summary

## Como executar

```bash
# Infra
docker compose up -d qdram
python scripts/test_qdrant_connection.py

# Ambiente Python
conda create -y -n pdf-extreme-ai python=3.11
conda activate pdf-extreme-ai
pip install -r backend/requirements.txt

# Config
cp .env.example .env
# ajuste paths de modelos e Ollama

# Backend
cd backend
uvicorn main:app --host 127.0.0.1 --port 8765 --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Primeiro acesso

```bash
python scripts/bootstrap_admin.py seu.usuario
```

Depois abrir `/primeiro-acesso` no frontend para cadastrar senha.

## Variáveis críticas

| Grupo | Variáveis |
|---|---|
| Ollama | `OLLAMA_HOST`, `OLLAMA_MODEL_DEFAULT`, `OLLAMA_THINKING`, `OLLAMA_KEEP_ALIVE` |
| Qdrant | `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_COLLECTION` |
| Modelos | `EMBEDDING_MODEL_PATH`, `RERANKER_MODEL_PATH` |
| RAG | `CHUNK_SIZE`, `INGEST_STRATEGY`, `ENABLE_RERANKER`, perfis `PROFILE_*` |
| Memória | `CHAT_MEMORY_TOKEN_LIMIT`, `CHAT_MEMORY_RECENT_TURNS` |
| Segurança | `SESSION_SECRET`, `SESSION_HTTPS_ONLY`, `CORS_ORIGINS` |

## Testes

```bash
pytest tests/core/ tests/backend/ -q
cd frontend && npm test -- --run
```

## Checks operacionais

- Qdrant respondendo
- Ollama com modelos `gemma4:26b`/`gemma4:e4b`
- Paths de modelos BGE corretos
- `SESSION_SECRET` configurado em produção
- `data/` fora do controle de versão (recomendado)

## Riscos operacionais

- Deploy single-instance
- Dependência de GPU/VRAM
- OCR requer Tesseract
- Modelos locais pesados
- Dados de produção no repo
