from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.schemas import ProofreadRequest
from core.bootstrap import bootstrap_legacy
from services.stack_manager import get_cached_stack
from services.sse import format_sse

router = APIRouter(tags=["proofread"])


@router.post("/proofread")
def proofread(body: ProofreadRequest):
    bootstrap_legacy()
    from proofread_service import run_proofread
    from runtime_config import configure_runtime_env

    settings = configure_runtime_env()
    model = (body.model or settings.llm_default_model).strip()
    stack = get_cached_stack(
        model,
        None,
        "",
        "general",
        "proofread",
    )
    result = run_proofread(
        stack.capture_llm,
        body.text,
        max_chars=body.max_chars,
    )
    if not result.get("error") and not result.get("raw_fallback"):
        from proofread_service import build_highlighted_html

        corrected = str(result.get("corrected_text") or "")
        source = str(result.get("source_text") or body.text)
        changes = list(result.get("changes") or [])
        result["highlighted_html"] = build_highlighted_html(
            corrected, source, changes
        )
    return result


@router.post("/proofread/stream")
def proofread_stream(body: ProofreadRequest):
    bootstrap_legacy()
    from proofread_service import build_highlighted_html, iter_proofread_blocks
    from runtime_config import configure_runtime_env

    settings = configure_runtime_env()
    model = (body.model or settings.llm_default_model).strip()
    stack = get_cached_stack(
        model,
        None,
        "",
        "general",
        "proofread",
    )

    def _events():
        corrected_parts: list[str] = []
        source_parts: list[str] = []
        all_changes: list[dict] = []
        raw_fallback = False
        raw_responses: list[str] = []
        for item in iter_proofread_blocks(
            stack.capture_llm,
            body.text,
            max_chars=body.max_chars,
        ):
            event = str(item.pop("event", "message"))
            if event == "block":
                source_parts.append(str(item.get("source_text") or ""))
                corrected_parts.append(str(item.get("corrected_text") or ""))
                all_changes.extend(list(item.get("changes") or []))
                raw_fallback = raw_fallback or bool(item.get("raw_fallback"))
                if item.get("raw_response"):
                    raw_responses.append(str(item.get("raw_response")))
            if event == "done":
                break
            yield format_sse(event, item)
            if event == "error":
                return

        corrected = "\n\n".join(corrected_parts)
        source = "\n\n".join(source_parts) or body.text
        result = {
            "corrected_text": corrected,
            "source_text": source,
            "changes": all_changes,
            "error": None,
            "raw_fallback": raw_fallback,
            "raw_response": "\n\n".join(raw_responses) if raw_responses else None,
        }
        if not raw_fallback:
            result["highlighted_html"] = build_highlighted_html(
                corrected,
                source,
                all_changes,
            )
        yield format_sse("done", result)

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
