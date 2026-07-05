"""Export Markdown de respostas (paridade com app._build_assistant_export_md)."""

from __future__ import annotations


def build_assistant_export_md(
    *,
    project_name: str,
    model_name: str,
    user_prompt: str,
    assistant_md: str,
    thinking: str | None = None,
    telemetry: str | None = None,
    retrieved_chunks: list | None = None,
) -> str:
    lines = [
        f"# Resposta — {project_name}",
        "",
        f"- **Modelo:** {model_name}",
        "",
        "## Pergunta",
        "",
        user_prompt.strip(),
        "",
        "## Resposta",
        "",
        assistant_md.strip(),
        "",
    ]
    if thinking:
        lines += ["## Thinking", "", thinking.strip(), ""]
    if telemetry:
        lines += ["## Telemetria", "", telemetry, ""]
    if retrieved_chunks:
        lines += ["## Trechos recuperados", ""]
        for i, ch in enumerate(retrieved_chunks, start=1):
            name = ch.get("display_name") or ch.get("source_file") or "?"
            page = ch.get("page", 0)
            snippet = ch.get("snippet", "")
            lines.append(f"### {i}. {name} (p.{page})")
            lines.append("")
            lines.append(snippet)
            lines.append("")
    return "\n".join(lines).strip() + "\n"
