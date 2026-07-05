from __future__ import annotations

import json
import time

import conversation_store as conv_store
import pytest

from services import chat_turn_runner as runner
from services import chat_turn_store as turn_store
from services.sse import format_sse


@pytest.fixture
def project_id(tmp_path, monkeypatch):
    root = tmp_path / "data/projects"
    root.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return "proj-runner"


def _parse_events(lines: list[str]) -> list[tuple[str, dict]]:
    raw = "".join(lines)
    out: list[tuple[str, dict]] = []
    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        name = "message"
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
        out.append((name, json.loads(data) if data else {}))
    return out


def test_run_turn_job_emits_events_to_subscribers(project_id):
    begun = turn_store.begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Oi",
    )

    def fake_turn():
        yield format_sse("token", {"text": "Olá"})
        yield format_sse("done", {"assistant_text": "Olá", "conversation_id": begun.conversation_id})

    runner.start_turn_job(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
        run_turn=fake_turn,
    )
    time.sleep(0.3)
    events = list(
        runner.subscribe_turn_events(
            project_id=project_id,
            conversation_id=begun.conversation_id,
            turn_id=begun.turn_id,
        )
    )
    parsed = _parse_events(events)
    names = [n for n, _ in parsed]
    assert "snapshot" in names
    assert "token" in names or "done" in names


def test_run_turn_job_continues_after_subscriber_disconnect(project_id):
    begun = turn_store.begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Oi",
    )

    def fake_turn():
        yield format_sse("token", {"text": "A"})
        time.sleep(0.2)
        yield format_sse("token", {"text": "B"})
        yield format_sse(
            "done",
            {"assistant_text": "AB", "conversation_id": begun.conversation_id},
        )

    runner.start_turn_job(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
        run_turn=fake_turn,
    )
    gen = runner.subscribe_turn_events(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
    )
    next(gen)
    gen.close()
    time.sleep(0.6)
    snap = turn_store.get_turn_snapshot(project_id, begun.conversation_id, begun.turn_id)
    assert snap["status"] == "completed"
    assert snap["assistant_text"] == "AB"


def test_run_turn_job_checkpoints_during_generation(project_id):
    begun = turn_store.begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Oi",
    )

    def fake_turn():
        yield format_sse("token", {"text": "X" * 20})
        time.sleep(1.1)
        yield format_sse(
            "done",
            {"assistant_text": "X" * 20, "conversation_id": begun.conversation_id},
        )

    runner.start_turn_job(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
        run_turn=fake_turn,
    )
    time.sleep(0.5)
    snap = turn_store.get_turn_snapshot(project_id, begun.conversation_id, begun.turn_id)
    assert len(snap["assistant_text"]) >= 20
    time.sleep(1.0)
    snap2 = turn_store.get_turn_snapshot(project_id, begun.conversation_id, begun.turn_id)
    assert snap2["status"] == "completed"


def test_subscribe_replays_snapshot_then_live_events(project_id):
    begun = turn_store.begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Oi",
    )

    def fake_turn():
        time.sleep(0.15)
        yield format_sse("token", {"text": "Live"})
        yield format_sse(
            "done",
            {"assistant_text": "Live", "conversation_id": begun.conversation_id},
        )

    runner.start_turn_job(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
        run_turn=fake_turn,
    )
    events = list(
        runner.subscribe_turn_events(
            project_id=project_id,
            conversation_id=begun.conversation_id,
            turn_id=begun.turn_id,
        )
    )
    parsed = _parse_events(events)
    assert parsed[0][0] == "snapshot"
    assert any(n == "token" for n, _ in parsed)


def test_subscribe_on_completed_turn_emits_snapshot_and_done_only(project_id):
    begun = turn_store.begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Oi",
    )
    turn_store.complete_turn(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
        content="Pronto",
    )
    events = list(
        runner.subscribe_turn_events(
            project_id=project_id,
            conversation_id=begun.conversation_id,
            turn_id=begun.turn_id,
        )
    )
    parsed = _parse_events(events)
    names = [n for n, _ in parsed]
    assert names == ["snapshot", "done"]
    assert parsed[0][1]["assistant_text"] == "Pronto"


def test_cancel_stops_runner_and_persists_cancelled(project_id):
    begun = turn_store.begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Oi",
    )

    def slow_turn():
        for i in range(50):
            if runner.get_job(project_id, begun.turn_id) and runner.get_job(
                project_id, begun.turn_id
            ).cancel_event.is_set():
                break
            yield format_sse("token", {"text": "x"})
            time.sleep(0.05)
        yield format_sse("done", {"assistant_text": "xxx"})

    job = runner.start_turn_job(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
        run_turn=slow_turn,
    )
    time.sleep(0.15)
    runner.request_cancel(project_id, begun.turn_id)
    job.cancel_event.set()
    turn_store.cancel_turn(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
    )
    time.sleep(0.3)
    snap = turn_store.get_turn_snapshot(project_id, begun.conversation_id, begun.turn_id)
    assert snap["status"] == "cancelled"
