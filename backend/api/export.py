from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from services.export_service import build_assistant_export_md

router = APIRouter(tags=["export"])


class ExportBody(BaseModel):
    project_name: str = "Projeto"
    model_name: str = ""
    user_prompt: str
    assistant_md: str
    thinking: str | None = None
    telemetry: str | None = None
    retrieved_chunks: list | None = None


@router.post("/export/markdown")
def export_markdown(body: ExportBody):
    md = build_assistant_export_md(
        project_name=body.project_name,
        model_name=body.model_name,
        user_prompt=body.user_prompt,
        assistant_md=body.assistant_md,
        thinking=body.thinking,
        telemetry=body.telemetry,
        retrieved_chunks=body.retrieved_chunks,
    )
    return {"markdown": md}
