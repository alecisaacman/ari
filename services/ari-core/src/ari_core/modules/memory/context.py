from __future__ import annotations

from pathlib import Path

from ...core.paths import DB_PATH
from .db import list_memory_blocks, memory_block_to_payload, search_memory_blocks


def build_memory_context(
    query: str = "",
    *,
    layers: list[str] | None = None,
    limit: int = 10,
    db_path: Path = DB_PATH,
) -> dict[str, object]:
    selected_layers = [layer for layer in layers or [] if layer]
    blocks = _load_blocks(query, selected_layers, limit=limit, db_path=db_path)
    return {
        "query": query,
        "layers": selected_layers,
        "limit": limit,
        "blocks": blocks[:limit],
        "summary": _summary(query, selected_layers, blocks[:limit]),
    }


def _load_blocks(
    query: str,
    layers: list[str],
    *,
    limit: int,
    db_path: Path,
) -> list[dict[str, object]]:
    loaded: list[dict[str, object]] = []
    if layers:
        for layer in layers:
            rows = _query_layer(query, layer=layer, limit=limit, db_path=db_path)
            loaded.extend(memory_block_to_payload(row) for row in rows)
    else:
        rows = _query_layer(query, layer=None, limit=limit, db_path=db_path)
        loaded.extend(memory_block_to_payload(row) for row in rows)

    deduped = {str(block["id"]): block for block in loaded}
    return sorted(
        deduped.values(),
        key=lambda block: (int(block.get("importance", 0)), str(block.get("updated_at", ""))),
        reverse=True,
    )


def _query_layer(
    query: str,
    *,
    layer: str | None,
    limit: int,
    db_path: Path,
):
    if not query.strip():
        return list_memory_blocks(layer=layer, limit=limit, db_path=db_path)
    rows = search_memory_blocks(query, layer=layer, limit=limit, db_path=db_path)
    if rows:
        return rows
    collected = []
    for term in _query_terms(query):
        collected.extend(search_memory_blocks(term, layer=layer, limit=limit, db_path=db_path))
    return collected


def _query_terms(query: str) -> list[str]:
    stop_words = {"a", "an", "and", "for", "in", "of", "the", "to", "use", "with"}
    return [
        token.strip().lower()
        for token in query.replace("-", " ").split()
        if len(token.strip()) >= 4 and token.strip().lower() not in stop_words
    ]


def _summary(query: str, layers: list[str], blocks: list[dict[str, object]]) -> str:
    layer_text = ", ".join(layers) if layers else "all layers"
    query_text = query.strip() or "latest memory"
    return f"Loaded {len(blocks)} memory block(s) for {query_text} across {layer_text}."
