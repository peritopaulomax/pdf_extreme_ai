"""Jobs de turno de chat em background com pub/sub SSE."""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from services.chat_turn_store import (
    cancel_turn,
    checkpoint_turn,
    complete_turn,
    fail_turn,
    get_turn_snapshot,
    mark_orphan_running_as_failed,
)
from services.sse import format_sse

logger = logging.getLogger(__name__)

_RING_MAX = 500
_TURN_EVENT_IDLE_TIMEOUT_S = 120.0
_registry_lock = threading.Lock()
_jobs: dict[str, "TurnJob"] = {}


@dataclass
class TurnJob:
    turn_id: str
    project_id: str
    conversation_id: str
    cancel_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    done: bool = False
    ring: list[str] = field(default_factory=list)
    subscribers: list[queue.Queue[str | None]] = field(default_factory=list)
    subscribers_lock: threading.Lock = field(default_factory=threading.Lock)

    def append_event(self, line: str) -> None:
        self.ring.append(line)
        if len(self.ring) > _RING_MAX:
            self.ring = self.ring[-_RING_MAX:]
        with self.subscribers_lock:
            dead: list[queue.Queue[str | None]] = []
            for sub in self.subscribers:
                try:
                    sub.put_nowait(line)
                except queue.Full:
                    dead.append(sub)
            self.subscribers = [s for s in self.subscribers if s not in dead]

    def close_subscribers(self) -> None:
        with self.subscribers_lock:
            for sub in self.subscribers:
                try:
                    sub.put_nowait(None)
                except queue.Full:
                    pass
            self.subscribers.clear()


def _parse_sse_line(line: str) -> tuple[str, dict[str, Any]]:
    event = "message"
    data_str = ""
    for part in line.strip().split("\n"):
        if part.startswith("event:"):
            event = part.split(":", 1)[1].strip()
        elif part.startswith("data:"):
            data_str = part.split(":", 1)[1].strip()
    payload: dict[str, Any] = {}
    if data_str:
        try:
            payload = json.loads(data_str)
        except json.JSONDecodeError:
            payload = {"raw": data_str}
    return event, payload


def _job_key(project_id: str, turn_id: str) -> str:
    return f"{project_id}:{turn_id}"


def _turn_event_idle_timeout_s() -> float:
    raw = os.environ.get("CHAT_TURN_EVENT_IDLE_TIMEOUT_S")
    if not raw:
        return _TURN_EVENT_IDLE_TIMEOUT_S
    try:
        return max(1.0, float(raw))
    except ValueError:
        return _TURN_EVENT_IDLE_TIMEOUT_S


def get_job(project_id: str, turn_id: str) -> TurnJob | None:
    with _registry_lock:
        return _jobs.get(_job_key(project_id, turn_id))


def register_job(job: TurnJob) -> None:
    with _registry_lock:
        _jobs[_job_key(job.project_id, job.turn_id)] = job


def unregister_job(project_id: str, turn_id: str) -> None:
    with _registry_lock:
        _jobs.pop(_job_key(project_id, turn_id), None)


def request_cancel(project_id: str, turn_id: str) -> bool:
    job = get_job(project_id, turn_id)
    if job is None:
        return False
    job.cancel_event.set()
    return True


def _accumulate_from_event(
    event: str,
    payload: dict[str, Any],
    state: dict[str, Any],
) -> None:
    if event == "thinking" and payload.get("text"):
        state["thinking"] = payload["text"]
    elif event == "token" and payload.get("text"):
        state["content"] = state.get("content", "") + payload["text"]
    elif event == "done":
        if payload.get("assistant_text"):
            state["content"] = payload["assistant_text"]
        if payload.get("thinking"):
            state["thinking"] = payload["thinking"]


def start_turn_job(
    *,
    project_id: str,
    conversation_id: str,
    turn_id: str,
    run_turn: Callable[[], Iterator[str]],
) -> TurnJob:
    job = TurnJob(
        turn_id=turn_id,
        project_id=project_id,
        conversation_id=conversation_id,
    )
    register_job(job)

    def _worker() -> None:
        state: dict[str, Any] = {"content": "", "thinking": None}
        last_checkpoint = 0.0
        done_marker = object()
        event_queue: queue.Queue[str | BaseException | object] = queue.Queue()

        def _produce_events() -> None:
            try:
                for produced_line in run_turn():
                    event_queue.put(produced_line)
            except BaseException as exc:  # noqa: BLE001
                event_queue.put(exc)
            finally:
                event_queue.put(done_marker)

        producer = threading.Thread(
            target=_produce_events,
            name=f"chat-turn-producer-{turn_id}",
            daemon=True,
        )
        producer.start()

        try:
            while True:
                try:
                    item = event_queue.get(timeout=_turn_event_idle_timeout_s())
                except queue.Empty:
                    assistant_text = str(state.get("content") or "")
                    thinking = state.get("thinking")
                    reason = (
                        "Fluxo interno ficou sem eventos antes de finalizar; "
                        "resposta parcial preservada."
                    )
                    if assistant_text.strip():
                        complete_turn(
                            project_id=project_id,
                            conversation_id=conversation_id,
                            turn_id=turn_id,
                            content=assistant_text,
                            thinking=thinking,
                            telemetry=state.get("telemetry"),
                            retrieved_chunks=state.get("retrieved_chunks"),
                            validation_issues=[
                                *list(state.get("validation_issues") or []),
                                reason,
                            ],
                        )
                        job.append_event(
                            format_sse(
                                "done",
                                {
                                    "assistant_text": assistant_text,
                                    "thinking": thinking,
                                    "conversation_id": conversation_id,
                                    "interrupted": True,
                                    "interruption_reason": reason,
                                    "telemetry": state.get("telemetry"),
                                    "retrieved_chunks": state.get("retrieved_chunks"),
                                    "validation_issues": [
                                        *list(state.get("validation_issues") or []),
                                        reason,
                                    ],
                                },
                            )
                        )
                    else:
                        fail_turn(
                            project_id=project_id,
                            conversation_id=conversation_id,
                            turn_id=turn_id,
                            error=reason,
                            content=assistant_text,
                            thinking=thinking,
                        )
                        job.append_event(format_sse("error", {"message": reason}))
                    break

                if item is done_marker:
                    break
                if isinstance(item, BaseException):
                    raise item

                line = item
                if job.cancel_event.is_set():
                    cancel_turn(
                        project_id=project_id,
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                    )
                    job.append_event(
                        format_sse(
                            "done",
                            {
                                "assistant_text": state.get("content", ""),
                                "thinking": state.get("thinking"),
                                "conversation_id": conversation_id,
                                "interrupted": True,
                                "interruption_reason": "Cancelado",
                            },
                        )
                    )
                    break

                event, payload = _parse_sse_line(line)
                _accumulate_from_event(event, payload, state)

                if event in ("token", "thinking"):
                    now = time.monotonic()
                    if now - last_checkpoint >= 1.0:
                        checkpoint_turn(
                            project_id=project_id,
                            conversation_id=conversation_id,
                            turn_id=turn_id,
                            content=state.get("content", ""),
                            thinking=state.get("thinking"),
                            force=True,
                        )
                        last_checkpoint = now

                if event == "error":
                    fail_turn(
                        project_id=project_id,
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        error=str(payload.get("message", "Erro")),
                        content=state.get("content", ""),
                        thinking=state.get("thinking"),
                    )
                    job.append_event(line)
                    break

                if event == "done":
                    assistant_text = str(
                        payload.get("assistant_text") or state.get("content") or ""
                    )
                    thinking = payload.get("thinking") or state.get("thinking")
                    if assistant_text.strip():
                        complete_turn(
                            project_id=project_id,
                            conversation_id=conversation_id,
                            turn_id=turn_id,
                            content=assistant_text,
                            thinking=thinking,
                            telemetry=payload.get("telemetry") or state.get("telemetry"),
                            retrieved_chunks=payload.get("retrieved_chunks")
                            or state.get("retrieved_chunks"),
                            validation_issues=payload.get("validation_issues")
                            or state.get("validation_issues"),
                        )
                    else:
                        fail_turn(
                            project_id=project_id,
                            conversation_id=conversation_id,
                            turn_id=turn_id,
                            error=str(
                                payload.get("interruption_reason")
                                or "Resposta vazia"
                            ),
                            content=assistant_text,
                            thinking=thinking,
                        )
                    job.append_event(line)
                    break

                if event == "meta":
                    if payload.get("telemetry"):
                        state["telemetry"] = payload["telemetry"]
                    if payload.get("retrieved_chunks") is not None:
                        state["retrieved_chunks"] = payload["retrieved_chunks"]
                    if payload.get("validation_issues") is not None:
                        state["validation_issues"] = payload["validation_issues"]
                    meta_payload = dict(payload)
                    meta_payload.setdefault("conversation_id", conversation_id)
                    line = format_sse("meta", meta_payload)
                    checkpoint_turn(
                        project_id=project_id,
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        content=state.get("content", ""),
                        thinking=state.get("thinking"),
                        force=True,
                    )

                job.append_event(line)
        except Exception as exc:
            logger.exception("turn job failed turn_id=%s", turn_id)
            fail_turn(
                project_id=project_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                error=str(exc),
                content=state.get("content", ""),
                thinking=state.get("thinking"),
            )
            job.append_event(format_sse("error", {"message": str(exc)}))
        finally:
            job.done = True
            job.close_subscribers()
            unregister_job(project_id, turn_id)

    job.thread = threading.Thread(target=_worker, name=f"chat-turn-{turn_id}", daemon=True)
    job.thread.start()
    return job


def subscribe_turn_events(
    *,
    project_id: str,
    conversation_id: str,
    turn_id: str,
) -> Iterator[str]:
    snap = get_turn_snapshot(project_id, conversation_id, turn_id)
    if snap is None:
        yield format_sse("error", {"message": "Turno nao encontrado"})
        return

    yield format_sse("snapshot", snap)

    status = snap.get("status", "running")
    if status in ("completed", "failed", "cancelled"):
        yield format_sse(
            "done",
            {
                "assistant_text": snap.get("assistant_text", ""),
                "thinking": snap.get("thinking"),
                "conversation_id": conversation_id,
                "interrupted": status != "completed",
                "interruption_reason": snap.get("error"),
            },
        )
        return

    job = get_job(project_id, turn_id)
    if job is None:
        mark_orphan_running_as_failed(project_id, conversation_id)
        snap2 = get_turn_snapshot(project_id, conversation_id, turn_id)
        yield format_sse("snapshot", snap2 or snap)
        yield format_sse(
            "done",
            {
                "assistant_text": (snap2 or snap).get("assistant_text", ""),
                "thinking": (snap2 or snap).get("thinking"),
                "conversation_id": conversation_id,
                "interrupted": True,
                "interruption_reason": (snap2 or snap).get("error"),
            },
        )
        return

    # Snapshot já reflete o disco; só entregar eventos novos da fila (evita duplicar tokens no replay).
    sub: queue.Queue[str | None] = queue.Queue(maxsize=_RING_MAX)
    with job.subscribers_lock:
        job.subscribers.append(sub)

    try:
        while True:
            try:
                item = sub.get(timeout=0.5)
            except queue.Empty:
                if job.done:
                    break
                continue
            if item is None:
                break
            yield item
            if "event: done" in item or "event: error" in item:
                break
    finally:
        with job.subscribers_lock:
            if sub in job.subscribers:
                job.subscribers.remove(sub)
