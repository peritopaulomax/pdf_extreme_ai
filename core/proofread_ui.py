"""UI Streamlit do modo Corretor ortografico."""

from __future__ import annotations

import streamlit as st

from proofread_service import build_highlighted_html, run_proofread


def render_proofread_workspace(llm, *, max_chars: int = 12000) -> None:
    st.subheader("Corretor ortografico e gramatical")
    st.caption(
        "Cole um trecho para corrigir. Nao usa PDFs do projeto nem RAG. "
        "Correcoes em **negrito** e fundo amarelo; supressoes destacam as palavras antes e depois."
    )

    text = st.text_area(
        "Texto para corrigir",
        height=220,
        placeholder="Cole o paragrafo ou extrato aqui...",
        key="proofread_input_text",
    )
    run = st.button("Corrigir texto", type="primary", key="proofread_run_btn")

    if run:
        with st.spinner("Corrigindo..."):
            result = run_proofread(llm, text, max_chars=max_chars)
        st.session_state.proofread_last_result = result

    result = st.session_state.get("proofread_last_result")
    if not result:
        return

    if result.get("error"):
        st.error(str(result["error"]))
        return

    if result.get("raw_fallback"):
        st.warning("Resposta fora do formato JSON; exibindo texto bruto do modelo.")
        st.markdown(result.get("raw_response", ""))
        return

    corrected = str(result.get("corrected_text") or "")
    source = str(
        result.get("source_text")
        or st.session_state.get("proofread_input_text")
        or ""
    )
    changes = list(result.get("changes") or [])

    st.markdown("#### Texto corrigido (alteracoes destacadas)")
    highlighted_html = build_highlighted_html(corrected, source, changes)
    st.markdown(highlighted_html, unsafe_allow_html=True)

    if changes:
        st.markdown("#### Alteracoes")
        for i, ch in enumerate(changes, start=1):
            st.markdown(
                f"**{i}.** `{ch.get('original', '')}` → `{ch.get('corrected', '')}`  \n"
                f"*{ch.get('reason', '')}*"
            )
    else:
        st.success("Nenhum erro gramatical ou ortografico identificado.")

    dl_cols = st.columns(2)
    with dl_cols[0]:
        st.download_button(
            "Baixar texto corrigido",
            data=corrected,
            file_name="texto_corrigido.txt",
            mime="text/plain",
            key="proofread_dl_clean",
        )
    with dl_cols[1]:
        st.download_button(
            "Baixar com lista de alteracoes",
            data=_export_md(corrected, changes),
            file_name="correcao.md",
            mime="text/markdown",
            key="proofread_dl_md",
        )


def _export_md(corrected: str, changes: list[dict[str, str]]) -> str:
    lines = ["# Correcao ortografica", "", "## Texto corrigido", "", corrected, ""]
    if changes:
        lines.append("## Alteracoes")
        for i, ch in enumerate(changes, 1):
            lines.append(
                f"{i}. **{ch.get('original', '')}** → **{ch.get('corrected', '')}** — {ch.get('reason', '')}"
            )
    return "\n".join(lines)
