# PDF Extreme AI

Assistente RAG para PDFs jurídicos — motor compartilhado (`core/`), API FastAPI (`backend/`) e UI React (`frontend/`).

## Estrutura

```
pdf_extreme_ai/
├── core/           # Motor RAG (ingest, retrieval, chat, projetos)
├── backend/        # API FastAPI + auth
├── frontend/       # UI React
├── legacy/         # UI Streamlit (legado)
├── data/           # Runtime: projetos, índices, checkpoints, auth
├── scripts/        # Utilitários CLI
├── tests/          # Testes (core/ e backend/)
└── docs/           # Documentação
```

## Ambiente conda

```bash
conda create -y -n pdf-extreme-ai python=3.11
conda activate pdf-extreme-ai
pip install -r backend/requirements.txt
```

## Infraestrutura

```bash
docker compose up -d qdrant
python scripts/test_qdrant_connection.py
```

Copie `.env.example` para `.env` e ajuste paths de modelos e Ollama.

## UI principal (React + API)

Terminal 1 — API:

```bash
conda activate pdf-extreme-ai
cd backend
uvicorn main:app --host 127.0.0.1 --port 8765 --reload
```

Terminal 2 — Frontend:

```bash
cd frontend
npm install
npm run dev
```

- Frontend: http://127.0.0.1:5173
- API docs: http://127.0.0.1:8765/docs

### Primeiro acesso (auth)

```bash
python scripts/bootstrap_admin.py seu.usuario
```

Abra `/primeiro-acesso` no frontend para cadastrar a senha.

## UI legada (Streamlit)

```bash
conda activate pdf-extreme-ai
streamlit run legacy/app.py
```

## Dados

Todos os dados de runtime ficam em `data/`:

| Path | Conteúdo |
|------|----------|
| `data/projects_registry.json` | Registry de projetos |
| `data/projects/<id>/` | Uploads, conversas, memória |
| `data/lexical/<id>.db` | Índice FTS5 por projeto |
| `data/checkpoints/<id>.json` | Checkpoint de ingest |
| `data/auth/` | Usuários e admins |

## Testes

```bash
conda activate pdf-extreme-ai
pytest tests/core/ tests/backend/ -q
cd frontend && npm test
```

## Documentação

- [OPERATIONS.md](docs/OPERATIONS.md) — variáveis de ambiente e operação
- [PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) — arquitetura
- [AUTH_SPEC.md](docs/AUTH_SPEC.md) — autenticação
