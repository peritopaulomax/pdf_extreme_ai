from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from api.schemas import ChatRequest
from auth.dependencies import require_auth
from core.bootstrap import bootstrap_legacy
from services.chat_service import chat_async_turns_enabled, run_chat_turn, start_async_chat_turn
from services.project_access import require_project

router = APIRouter(prefix="/projects/{project_id}/chat", tags=["chat"])


def _resolve_chat_params(body: ChatRequest, workspace: str):
    bootstrap_legacy()
    from runtime_config import configure_runtime_env

    settings = configure_runtime_env()
    model = (body.model or settings.llm_default_model).strip()
    profile = body.profile
    if workspace == "rag" and body.deep_mode and (not profile or profile.lower() == "automatico"):
        profile = "pericial"
    return model, profile


def _sse_response(project_id: str, body: ChatRequest, workspace: str, user: dict):
    require_project(user["usuario"], project_id)
    model, profile = _resolve_chat_params(body, workspace)

    def generate():
        yield from run_chat_turn(
            project_id=project_id,
            conversation_id=body.conversation_id,
            message=body.message,
            model=model,
            workspace=workspace,
            profile=profile,
            audit_mode=body.audit_mode,
            use_project_memory=body.use_project_memory,
            session_rules=body.session_rules,
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


def _async_response(project_id: str, body: ChatRequest, workspace: str, user: dict):
    require_project(user["usuario"], project_id)
    model, profile = _resolve_chat_params(body, workspace)
    result = start_async_chat_turn(
        project_id=project_id,
        conversation_id=body.conversation_id,
        message=body.message,
        model=model,
        workspace=workspace,
        profile=profile,
        audit_mode=body.audit_mode,
        use_project_memory=body.use_project_memory,
        session_rules=body.session_rules,
    )
    return JSONResponse(status_code=202, content=result)


@router.post("/rag")
def chat_rag(
    project_id: str,
    body: ChatRequest,
    user: dict = Depends(require_auth),
):
    if chat_async_turns_enabled():
        return _async_response(project_id, body, "rag", user)
    return _sse_response(project_id, body, "rag", user)


@router.post("/free")
def chat_free(
    project_id: str,
    body: ChatRequest,
    user: dict = Depends(require_auth),
):
    if chat_async_turns_enabled():
        return _async_response(project_id, body, "free", user)
    return _sse_response(project_id, body, "free", user)
