from __future__ import annotations

import time

import conversation_store as conv_store
import pytest

from services import chat_turn_store as turn_store


@pytest.fixture
def project_id(tmp_path, monkeypatch):
    root = tmp_path / "data/projects"
    root.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    pid = "proj-turn-test"
    (root / pid / "conversations").mkdir(parents=True)
    return pid


def test_begin_turn_persists_user_and_running_assistant_immediately(project_id):
    result = turn_store.begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Qual o resumo?",
        model_name="gemma4:26b",
    )
    rec = conv_store.load(project_id, result.conversation_id)
    assert rec is not None
    assert rec.active_turn_id == result.turn_id
    assert len(rec.messages) == 2
    assert rec.messages[0]["role"] == "user"
    assert rec.messages[0]["turn_id"] == result.turn_id
    assert rec.messages[1]["role"] == "assistant"
    assert rec.messages[1]["status"] == "running"


def test_checkpoint_updates_partial_content_and_thinking(project_id):
    begun = turn_store.begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Pergunta",
    )
    turn_store.checkpoint_turn(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
        content="Parcial",
        thinking="Pensando",
        force=True,
    )
    snap = turn_store.get_turn_snapshot(project_id, begun.conversation_id, begun.turn_id)
    assert snap["assistant_text"] == "Parcial"
    assert snap["thinking"] == "Pensando"


def test_checkpoint_debounce_skips_rapid_writes(project_id, monkeypatch):
    monkeypatch.setattr(turn_store, "_CHECKPOINT_DEBOUNCE_S", 10.0)
    begun = turn_store.begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Pergunta",
    )
    turn_store.checkpoint_turn(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
        content="A",
        force=True,
    )
    ok = turn_store.checkpoint_turn(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
        content="B",
        force=False,
    )
    assert ok is False
    snap = turn_store.get_turn_snapshot(project_id, begun.conversation_id, begun.turn_id)
    assert snap["assistant_text"] == "A"


def test_complete_turn_sets_status_completed_and_clears_active_turn(project_id):
    begun = turn_store.begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Pergunta",
    )
    turn_store.complete_turn(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
        content="Resposta final [Doc.pdf, pag. 1]",
        telemetry="modo=rag",
    )
    rec = conv_store.load(project_id, begun.conversation_id)
    assert rec.active_turn_id is None
    assert rec.messages[-1]["status"] == "completed"
    assert rec.messages[-1]["telemetry"] == "modo=rag"


def test_fail_turn_sets_status_failed_with_error(project_id):
    begun = turn_store.begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Pergunta",
    )
    turn_store.fail_turn(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
        error="Modelo vazio",
    )
    rec = conv_store.load(project_id, begun.conversation_id)
    assert len(rec.messages) == 2
    assert rec.messages[0]["role"] == "user"
    assert rec.messages[-1]["status"] == "failed"
    assert rec.messages[-1]["error"] == "Modelo vazio"


def test_cancel_turn_sets_status_cancelled(project_id):
    begun = turn_store.begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Pergunta",
    )
    turn_store.cancel_turn(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
    )
    rec = conv_store.load(project_id, begun.conversation_id)
    assert rec.active_turn_id is None
    assert rec.messages[-1]["status"] == "cancelled"


def test_only_one_active_turn_per_conversation(project_id):
    first = turn_store.begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Primeira",
    )
    second = turn_store.begin_turn(
        project_id=project_id,
        conversation_id=first.conversation_id,
        user_content="Segunda",
    )
    rec = conv_store.load(project_id, first.conversation_id)
    assert rec.active_turn_id == second.turn_id
    first_assistant = turn_store.get_turn_snapshot(
        project_id, first.conversation_id, first.turn_id
    )
    assert first_assistant["status"] == "cancelled"
    assert len(rec.messages) == 4
