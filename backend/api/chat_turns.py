from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from auth.dependencies import require_auth
from services.chat_turn_runner import get_job, request_cancel, subscribe_turn_events
from services.chat_turn_store import cancel_turn, get_turn_snapshot
from services.project_access import require_project

router = APIRouter(prefix="/projects/{project_id}/chat/turns", tags=["chat"])


@router.get("/{turn_id}/events")
def turn_events(
    project_id: str,
    turn_id: str,
    conversation_id: str,
    user: dict = Depends(require_auth),
):
    require_project(user["usuario"], project_id)
    snap = get_turn_snapshot(project_id, conversation_id, turn_id)
    if snap is None:
        raise HTTPException(404, "Turno nao encontrado")

    def generate():
        yield from subscribe_turn_events(
            project_id=project_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{turn_id}/cancel")
def cancel_turn_endpoint(
    project_id: str,
    turn_id: str,
    conversation_id: str,
    user: dict = Depends(require_auth),
):
    require_project(user["usuario"], project_id)
    request_cancel(project_id, turn_id)
    cancel_turn(
        project_id=project_id,
        conversation_id=conversation_id,
        turn_id=turn_id,
    )
    job = get_job(project_id, turn_id)
    if job is not None:
        job.cancel_event.set()
    return {"status": "cancelled", "turn_id": turn_id}
