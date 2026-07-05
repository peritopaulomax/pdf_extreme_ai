# Chat Turn Persistence — Especificação

Geração de chat desacoplada do browser: turno persistido desde o início, job em background, checkpoints no JSON da conversa e reconexão via SSE.

## Requisitos funcionais

| ID | Requisito |
|----|-----------|
| FR-01 | Ao enviar mensagem com `CHAT_ASYNC_TURNS=true`, o servidor grava user + assistant `status=running` antes de qualquer token. |
| FR-02 | Checkpoints atualizam `content`, `thinking` e `updated_at` no disco (debounce 1s + flush em `meta`/`done`/`failed`). |
| FR-03 | Cliente desconectado (refresh, troca de aba) não cancela o job em background. |
| FR-04 | `GET /projects/{id}/chat/turns/{turn_id}/events` emite `snapshot` e depois eventos ao vivo ou tail do buffer. |
| FR-05 | Ao voltar à conversa, `GET /conversations/{id}` expõe mensagem parcial e `active_turn_id`; a UI reconecta SSE. |
| FR-06 | `POST .../turns/{turn_id}/cancel` marca `cancelled` e interrompe o runner cooperativamente. |
| FR-07 | Novo turno na mesma conversa com turno ativo faz **auto-cancel** do anterior. |
| FR-08 | Com `CHAT_ASYNC_TURNS=false`, mantém `POST /chat/rag|free` SSE síncrono atual (regressão). |

## Modelo de dados

Mensagem user:

```json
{
  "role": "user",
  "content": "...",
  "turn_id": "t_abc123",
  "created_at": "2026-05-27T12:00:00+00:00"
}
```

Mensagem assistant:

```json
{
  "role": "assistant",
  "content": "",
  "thinking": "",
  "turn_id": "t_abc123",
  "status": "running",
  "updated_at": "2026-05-27T12:00:01+00:00",
  "error": null,
  "telemetry": null,
  "retrieved_chunks": [],
  "validation_issues": []
}
```

`status`: `running` | `completed` | `failed` | `cancelled`.

Conversa: campo opcional `active_turn_id` (string ou null).

## APIs

| Método | Rota | Resposta |
|--------|------|----------|
| POST | `/projects/{id}/chat/rag` | `202` `{ turn_id, conversation_id }` se async; senão SSE |
| POST | `/projects/{id}/chat/free` | idem |
| GET | `/projects/{id}/chat/turns/{turn_id}/events` | SSE |
| POST | `/projects/{id}/chat/turns/{turn_id}/cancel` | `{ status: "cancelled" }` |

### SSE `/events`

1. `event: snapshot` — estado do disco.
2. `status`, `thinking`, `token`, `meta`, `done`, `error` — paridade com chat síncrono.
3. `done` quando `status` terminal.

## Feature flag

- Env: `CHAT_ASYNC_TURNS=true|false` (default `false` em testes legados).

## Edge cases

- **Restart uvicorn:** turnos `running` no disco → `failed` com mensagem ao primeiro subscribe ou no startup do runner.
- **Escrita concorrente:** `conversation_store.save` atômico (temp + rename).
- **Turno já completed:** subscribe emite `snapshot` + `done` sem re-gerar.

## Não-objetivos (MVP)

- Múltiplos turnos `running` por conversa.
- Fila distribuída (Redis/Celery).
- Sincronização multi-dispositivo além do mesmo servidor.
