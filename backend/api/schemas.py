from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str


class ProjectRename(BaseModel):
    name: str


class ConversationCreate(BaseModel):
    title: str = "Nova conversa"
    model_name: str = ""


class ConversationRename(BaseModel):
    title: str


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    model: str | None = None
    profile: str | None = None
    audit_mode: bool = False
    deep_mode: bool = False
    use_project_memory: bool = True
    session_rules: str = ""


class ProofreadRequest(BaseModel):
    text: str
    model: str | None = None
    max_chars: int = 12000


class RulesBody(BaseModel):
    global_rules: str = Field(default="", max_length=4000)


class MemoryBody(BaseModel):
    text: str = ""


class DocumentSelectionBody(BaseModel):
    file_ids: list[str] = Field(default_factory=list)


class DocumentReprocessBody(DocumentSelectionBody):
    force_ocr: bool = False
