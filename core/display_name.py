"""Metadado display_name para citacoes legiveis (remove prefixo file_id do nome armazenado)."""

from __future__ import annotations

import re
from typing import Optional

try:
    from llama_index.core.postprocessor import BaseNodePostprocessor
except ImportError:  # pragma: no cover - versoes mais antigas
    from llama_index.core.postprocessor.types import BaseNodePostprocessor

from llama_index.core.schema import NodeWithScore, QueryBundle

_UPLOAD_PREFIX = re.compile(r"^([0-9a-f]{16})_(.+)$", re.IGNORECASE)


def human_source_label(source_file: str) -> str:
    s = (source_file or "").strip()
    if not s:
        return ""
    m = _UPLOAD_PREFIX.match(s)
    if m:
        return m.group(2)
    return s


class DisplayNamePostprocessor(BaseNodePostprocessor):
    """Preenche metadata['display_name'] quando ausente, a partir de source_file."""

    @classmethod
    def class_name(cls) -> str:
        return "DisplayNamePostprocessor"

    def _postprocess_nodes(
        self,
        nodes: list[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> list[NodeWithScore]:
        for nws in nodes:
            meta = getattr(nws.node, "metadata", None)
            if not isinstance(meta, dict):
                continue
            if str(meta.get("display_name", "") or "").strip():
                continue
            sf = str(meta.get("source_file", "") or "")
            label = human_source_label(sf)
            if label:
                meta["display_name"] = label
        return nodes
