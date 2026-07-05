# PDF Extreme AI — API Inventory

## APIs REST do Backend

Base URL: `http://127.0.0.1:8765` (ou proxy `/api` no Vite dev server).

### Auth (`/auth`)

| Método | Rota | Body/Query | Auth | Descrição |
|---|---|---|---|---|
| POST | `/auth/login` | `LoginBody` | público | Cria sessão; rate-limit por IP |
| POST | `/auth/logout` | — | sessão | Limpa sessão |
| GET | `/auth/me` | — | `require_auth` | Dados do usuário logado |
| GET | `/auth/primeiro-acesso/check` | `?usuario=` | público | Verifica se usuário pode cadastrar senha |
| POST | `/auth/primeiro-acesso` | `PrimeiroAcessoBody` | público | Cadastra senha |
| GET | `/auth/administradores` | — | `require_admin` | Lista admins |
| POST | `/auth/administradores` | `NomeBody` | `require_admin` | Adiciona admin |
| DELETE | `/auth/administradores` | `NomeBody` | `require_admin` | Remove admin |
| GET | `/auth/consultores` | — | `require_admin` | Lista consultores |
| POST | `/auth/consultores` | `NomeBody` | `require_admin` | Adiciona consultor |
| DELETE | `/auth/consultores` | `NomeBody` | `require_admin` | Remove consultor |
| POST | `/auth/consultores/resetar-senha` | `NomeBody` | `require_admin` | Reseta senha de consultor |

### Config (`/config`)

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| GET | `/config` | `require_auth` | Modelos disponíveis, default e limites de ingest |

### Projects (`/projects`)

| Método | Rota | Body | Auth | Descrição |
|---|---|---|---|---|
| GET | `/projects` | — | `require_auth` | Lista projetos do owner |
| POST | `/projects` | `ProjectCreate` | `require_auth` | Cria projeto |
| GET | `/projects/{id}` | — | `require_auth` | Detalhes do projeto |
| PATCH | `/projects/{id}` | `ProjectRename` | `require_auth` | Renomeia projeto |
| DELETE | `/projects/{id}` | — | `require_auth` | Exclui projeto e assets |

### Project Settings (`/projects/{id}`)

| Método | Rota | Body | Auth | Descrição |
|---|---|---|---|---|
| GET | `/rules` | — | `require_auth` | Regras globais do projeto |
| PATCH | `/rules` | `RulesBody` | `require_auth` | Atualiza regras |
| GET | `/memory` | — | `require_auth` | Memória do caso |
| PUT | `/memory` | `MemoryBody` | `require_auth` | Atualiza memória |

### Documents (`/projects/{id}/documents`)

| Método | Rota | Body | Auth | Descrição |
|---|---|---|---|---|
| GET | `/` | — | `require_auth` | Lista documentos |
| POST | `/remove` | `DocumentSelectionBody` | `require_auth` | Remove selecionados |
| POST | `/reprocess` | `DocumentReprocessBody` | `require_auth` | Reprocessa selecionados |
| POST | `/reprocess/stream` | `DocumentReprocessBody` | `require_auth` | Reprocessa via SSE |
| DELETE | `/{file_id}` | — | `require_auth` | Remove um documento |
| POST | `/{file_id}/reprocess` | — | `require_auth` | Reprocessa um documento |

### Ingest (`/projects/{id}/ingest`)

| Método | Rota | Query | Auth | Descrição |
|---|---|---|---|---|
| POST | `/` | `rebuild`, `reprocess_all`, `force_ocr` | `require_auth` | Upload multipart; retorna resumo |
| POST | `/stream` | mesmas | `require_auth` | Upload multipart; retorna SSE progress |

### Conversations (`/projects/{id}/conversations`)

| Método | Rota | Body | Auth | Descrição |
|---|---|---|---|---|
| GET | `/` | — | `require_auth` | Lista conversas |
| POST | `/` | `ConversationCreate` | `require_auth` | Cria conversa |
| GET | `/{cid}` | — | `require_auth` | Carrega conversa |
| PATCH | `/{cid}` | `ConversationRename` | `require_auth` | Renomeia conversa |
| DELETE | `/{cid}` | — | `require_auth` | Exclui conversa |

### Chat (`/projects/{id}/chat`)

| Método | Rota | Body | Modo | Auth | Descrição |
|---|---|---|---|---|---|
| POST | `/rag` | `ChatRequest` | SSE ou 202 | `require_auth` | Chat RAG |
| POST | `/free` | `ChatRequest` | SSE ou 202 | `require_auth` | Chat livre |

### Chat Turns (`/projects/{id}/chat/turns`)

| Método | Rota | Query | Auth | Descrição |
|---|---|---|---|---|
| GET | `/{turn_id}/events` | `conversation_id` | `require_auth` | SSE de eventos do turno |
| POST | `/{turn_id}/cancel` | `conversation_id` | `require_auth` | Cancela turno |

### Export (`/export`)

| Método | Rota | Body | Auth | Descrição |
|---|---|---|---|---|
| POST | `/export/markdown` | `ExportBody` | **público** | Formata markdown da resposta |

### Proofread (`/proofread`)

| Método | Rota | Body | Auth | Descrição |
|---|---|---|---|---|
| POST | `/proofread` | `ProofreadRequest` | **público** | Corretor síncrono |
| POST | `/proofread/stream` | `ProofreadRequest` | **público** | Corretor streaming |

## Contratos Principais

### `ChatRequest`
```json
{
  "message": "string",
  "conversation_id": "string | null",
  "model": "string",
  "profile": "automatico | rapido | preciso | pericial",
  "audit_mode": "boolean",
  "deep_mode": "boolean",
  "use_project_memory": "boolean",
  "session_rules": "string | null"
}
```

### `ProjectCreate`
```json
{ "name": "string" }
```

### `ConversationCreate`
```json
{ "title": "string" }
```

### `ProofreadRequest`
```json
{
  "text": "string",
  "model": "string",
  "max_chars": "number | null"
}
```

## Autenticação

- Sessão via cookie `pdf_extreme_session` assinado com `SESSION_SECRET`.
- Todas as rotas protegidas usam `Depends(require_auth)` ou `Depends(require_admin)`.
- Rotas públicas: `/health`, `/auth/login`, `/auth/logout`, `/auth/primeiro-acesso*`, `/export/markdown`, `/proofread`, `/proofread/stream`.

## Versionamento

- Versão da API: `0.3.0` (definida em `backend/main.py`).
- Não há versionamento explícito de path (ex.: `/v1/`).

## Gate

**Como sistemas externos interagem?** O frontend React interage via REST + SSE autenticado por cookie. Ollama e Qdrant são consumidos pelo backend. Export e proofread são endpoints públicos.

## Evidências

- `backend/main.py`
- `backend/api/schemas.py`
- `backend/api/auth.py`
- `backend/api/projects.py`
- `backend/api/chat.py`
- `backend/api/chat_turns.py`
- `backend/api/ingest.py`
- `backend/api/documents.py`
- `backend/api/export.py`
- `backend/api/proofread.py`
