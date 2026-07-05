# Chat Turn Persistence — Plano de testes (TDD)

## Ordem obrigatória

1. Escrever testes (vermelhos).
2. Implementar `chat_turn_store` → T-S1…T-S6.
3. Implementar `chat_turn_runner` → T-R1…T-R6.
4. Implementar API → T-A1…T-A5, T-F1.
5. Implementar frontend → T-U1…T-U6, T-C1…T-C2.

## Matriz spec → teste

| Spec | Teste |
|------|-------|
| FR-01 | T-S1 |
| FR-02 | T-S2 |
| FR-03 | T-R2 |
| FR-04 | T-R4, T-A2 |
| FR-05 | T-A5, T-U3, T-C1 |
| FR-06 | T-S5, T-R6, T-A4, T-U5 |
| FR-07 | T-S6 |
| FR-08 | T-F1 |

## Backend

### `backend/tests/test_chat_turn_store.py`

- T-S1 `test_begin_turn_persists_user_and_running_assistant_immediately`
- T-S2 `test_checkpoint_updates_partial_content_and_thinking`
- T-S3 `test_complete_turn_sets_status_completed_and_clears_active_turn`
- T-S4 `test_fail_turn_sets_status_failed_with_error`
- T-S5 `test_cancel_turn_sets_status_cancelled`
- T-S6 `test_only_one_active_turn_per_conversation`

### `backend/tests/test_chat_turn_runner.py`

- T-R1 `test_run_turn_job_emits_events_to_subscribers`
- T-R2 `test_run_turn_job_continues_after_subscriber_disconnect`
- T-R3 `test_run_turn_job_checkpoints_during_generation`
- T-R4 `test_subscribe_replays_snapshot_then_live_events`
- T-R5 `test_subscribe_on_completed_turn_emits_snapshot_and_done_only`
- T-R6 `test_cancel_stops_runner_and_persists_cancelled`

### `backend/tests/test_chat_turn_api.py`

- T-A1 … T-A5

### `backend/tests/test_chat_rag_flow.py`

- T-F1 `test_legacy_sync_sse_still_works_when_feature_flag_off`

## Frontend

- `src/api/chat-turn.test.ts`
- `src/hooks/useChatTurn.test.tsx`
- `src/components/chat-ui.test.tsx` — T-C1, T-C2

## Comandos

```bash
cd pdf_extreme_ai_v2
pytest backend/tests/test_chat_turn_store.py backend/tests/test_chat_turn_runner.py \
  backend/tests/test_chat_turn_api.py backend/tests/test_chat_rag_flow.py -q

cd frontend && npm test -- --run \
  src/hooks/useChatTurn.test.tsx src/api/chat-turn.test.ts src/components/chat-ui.test.tsx
```

## Gate de progressão

Só mergear implementação quando o teste da fatia correspondente estiver verde.
