from __future__ import annotations

import json
import os
import sys
import time

import pytest

import api.chat as chat_api
from auth import store as auth_store
from fastapi.testclient import TestClient
from main import app
from project_store import ProjectStore
from services.sse import format_sse


@pytest.fixture
def authenticated_client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/projects").mkdir(parents=True, exist_ok=True)

    auth_store.salvar_admins(["alice"])
    auth_store.cadastrar_senha_usuario("alice", "Alice1234")

    ps = ProjectStore(str(os.environ["PROJECTS_REGISTRY_PATH"]))
    project = ps.create_project("Projeto Turn API", owner_id="alice")

    client = TestClient(app)
    login = client.post("/auth/login", json={"usuario": "alice", "senha": "Alice1234"})
    assert login.status_code == 200
    return client, project.project_id


def _parse_sse_events(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
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
        events.append((name, json.loads(data) if data else {}))
    return events


def test_post_chat_rag_returns_202_with_turn_and_conversation_ids(
    authenticated_client, monkeypatch
):
    client, project_id = authenticated_client
    monkeypatch.setenv("CHAT_ASYNC_TURNS", "true")

    def fake_start(**kwargs):
        import conversation_store as conv_store
        from services.chat_turn_store import begin_turn
        from services.chat_turn_runner import start_turn_job

        begun = begin_turn(
            project_id=kwargs["project_id"],
            conversation_id=kwargs.get("conversation_id"),
            user_content=kwargs["message"],
            model_name=kwargs.get("model", ""),
        )

        def run():
            yield format_sse("token", {"text": "Resposta API"})
            yield format_sse(
                "done",
                {
                    "assistant_text": "Resposta API",
                    "conversation_id": begun.conversation_id,
                },
            )

        start_turn_job(
            project_id=kwargs["project_id"],
            conversation_id=begun.conversation_id,
            turn_id=begun.turn_id,
            run_turn=run,
        )
        return {"turn_id": begun.turn_id, "conversation_id": begun.conversation_id}

    monkeypatch.setattr(chat_api, "start_async_chat_turn", fake_start)

    resp = client.post(
        f"/projects/{project_id}/chat/rag",
        json={"message": "Teste async", "model": "gemma4:26b"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["turn_id"].startswith("t_")
    assert body["conversation_id"]


def test_get_turn_events_returns_sse_snapshot_and_tokens(authenticated_client, monkeypatch):
    client, project_id = authenticated_client
    monkeypatch.setenv("CHAT_ASYNC_TURNS", "true")

    started: dict = {}

    def fake_start(**kwargs):
        from services.chat_turn_store import begin_turn
        from services.chat_turn_runner import start_turn_job

        begun = begin_turn(
            project_id=kwargs["project_id"],
            conversation_id=None,
            user_content=kwargs["message"],
        )
        started["turn_id"] = begun.turn_id
        started["conversation_id"] = begun.conversation_id

        def run():
            yield format_sse("token", {"text": "Ao vivo"})
            yield format_sse(
                "done",
                {
                    "assistant_text": "Ao vivo",
                    "conversation_id": begun.conversation_id,
                },
            )

        start_turn_job(
            project_id=kwargs["project_id"],
            conversation_id=begun.conversation_id,
            turn_id=begun.turn_id,
            run_turn=run,
        )
        return {"turn_id": begun.turn_id, "conversation_id": begun.conversation_id}

    monkeypatch.setattr(chat_api, "start_async_chat_turn", fake_start)

    post = client.post(
        f"/projects/{project_id}/chat/rag",
        json={"message": "Oi"},
    )
    assert post.status_code == 202
    payload = post.json()
    time.sleep(0.4)

    with client.stream(
        "GET",
        f"/projects/{project_id}/chat/turns/{payload['turn_id']}/events",
        params={"conversation_id": payload["conversation_id"]},
    ) as stream:
        raw = "".join(stream.iter_text())

    events = _parse_sse_events(raw)
    names = [n for n, _ in events]
    assert names[0] == "snapshot"
    assert "token" in names or "done" in names


def test_get_turn_events_requires_auth_and_project_access(authenticated_client):
    client, project_id = authenticated_client
    anon = TestClient(app)
    resp = anon.get(
        f"/projects/{project_id}/chat/turns/t_fake/events",
        params={"conversation_id": "conv"},
    )
    assert resp.status_code == 401


def test_post_cancel_returns_cancelled_turn(authenticated_client, monkeypatch):
    client, project_id = authenticated_client
    from services.chat_turn_store import begin_turn

    begun = begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Cancelar",
    )

    resp = client.post(
        f"/projects/{project_id}/chat/turns/{begun.turn_id}/cancel",
        params={"conversation_id": begun.conversation_id},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_get_conversation_includes_partial_running_assistant(authenticated_client):
    client, project_id = authenticated_client
    from services.chat_turn_store import begin_turn, checkpoint_turn

    begun = begin_turn(
        project_id=project_id,
        conversation_id=None,
        user_content="Parcial",
    )
    checkpoint_turn(
        project_id=project_id,
        conversation_id=begun.conversation_id,
        turn_id=begun.turn_id,
        content="Texto parcial",
        force=True,
    )

    resp = client.get(f"/projects/{project_id}/conversations/{begun.conversation_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("active_turn_id") == begun.turn_id
    assistant = data["messages"][-1]
    assert assistant["status"] == "running"
    assert assistant["content"] == "Texto parcial"
