from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import ConversationCreate, ConversationRename
from auth.dependencies import require_auth
from services.project_access import require_project

router = APIRouter(prefix="/projects/{project_id}/conversations", tags=["conversations"])


@router.get("")
def list_conversations(project_id: str, user: dict = Depends(require_auth)):
    require_project(user["usuario"], project_id)
    import conversation_store as conv_store

    return {
        "conversations": [
            asdict(c) for c in conv_store.list_conversations(project_id)
        ]
    }


@router.post("")
def create_conversation(
    project_id: str,
    body: ConversationCreate,
    user: dict = Depends(require_auth),
):
    require_project(user["usuario"], project_id)
    import conversation_store as conv_store

    rec = conv_store.create(
        project_id, title=body.title, model_name=body.model_name
    )
    return asdict(rec)


@router.get("/{conversation_id}")
def get_conversation(
    project_id: str,
    conversation_id: str,
    user: dict = Depends(require_auth),
):
    require_project(user["usuario"], project_id)
    import conversation_store as conv_store

    rec = conv_store.load(project_id, conversation_id)
    if rec is None:
        raise HTTPException(404, "Conversa nao encontrada")
    return asdict(rec)


@router.patch("/{conversation_id}")
def rename_conversation(
    project_id: str,
    conversation_id: str,
    body: ConversationRename,
    user: dict = Depends(require_auth),
):
    require_project(user["usuario"], project_id)
    import conversation_store as conv_store

    rec = conv_store.rename(project_id, conversation_id, body.title)
    if rec is None:
        raise HTTPException(404, "Conversa nao encontrada")
    return asdict(rec)


@router.delete("/{conversation_id}")
def delete_conversation(
    project_id: str,
    conversation_id: str,
    user: dict = Depends(require_auth),
):
    require_project(user["usuario"], project_id)
    import conversation_store as conv_store

    ok = conv_store.delete(project_id, conversation_id)
    if not ok:
        raise HTTPException(404, "Conversa nao encontrada")
    return {"deleted": True}
