from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from ...core.paths import DB_PATH
from ..networking.db import get_connection, initialize_database
from .models import MemoryBlock, MemoryBlockLayer


def _normalize_tags(tags: list[str] | None = None) -> str:
    return json.dumps(tags or [])


def remember_ari_memory(
    memory_type: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    db_path: Path = DB_PATH,
) -> sqlite3.Row:
    initialize_database(db_path=db_path)
    tags_json = _normalize_tags(tags)
    with get_connection(db_path) as connection:
        existing = connection.execute(
            """
            select id, type, title, content, tags_json, created_at, updated_at
            from ari_memories
            where type = ? and title = ?
            limit 1
            """,
            (memory_type, title),
        ).fetchone()

        if existing is None:
            cursor = connection.execute(
                """
                insert into ari_memories (type, title, content, tags_json)
                values (?, ?, ?, ?)
                """,
                (memory_type, title, content, tags_json),
            )
            memory_id = int(cursor.lastrowid)
            connection.commit()
            row = connection.execute(
                """
                select id, type, title, content, tags_json, created_at, updated_at
                from ari_memories
                where id = ?
                """,
                (memory_id,),
            ).fetchone()
            assert row is not None
            return row

        if existing["content"] == content and existing["tags_json"] == tags_json:
            return existing

        connection.execute(
            """
            update ari_memories
            set content = ?,
                tags_json = ?,
                updated_at = current_timestamp
            where id = ?
            """,
            (content, tags_json, existing["id"]),
        )
        connection.commit()
        row = connection.execute(
            """
            select id, type, title, content, tags_json, created_at, updated_at
            from ari_memories
            where id = ?
            """,
            (existing["id"],),
        ).fetchone()
    assert row is not None
    return row


def list_ari_memories(
    memory_types: list[str] | None = None,
    limit: int = 20,
    db_path: Path = DB_PATH,
) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []

    try:
        with get_connection(db_path) as connection:
            if memory_types:
                placeholders = ", ".join("?" for _ in memory_types)
                cursor = connection.execute(
                    f"""
                    select id, type, title, content, tags_json, created_at, updated_at
                    from ari_memories
                    where type in ({placeholders})
                    order by updated_at desc, id desc
                    limit ?
                    """,
                    (*memory_types, limit),
                )
            else:
                cursor = connection.execute(
                    """
                    select id, type, title, content, tags_json, created_at, updated_at
                    from ari_memories
                    order by updated_at desc, id desc
                    limit ?
                    """,
                    (limit,),
                )
            return list(cursor.fetchall())
    except sqlite3.OperationalError as error:
        if "no such table: ari_memories" in str(error):
            return []
        raise


def search_ari_memories(
    query: str,
    limit: int = 10,
    memory_types: list[str] | None = None,
    db_path: Path = DB_PATH,
) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []

    normalized_query = query.strip()
    search_value = f"%{normalized_query}%"
    try:
        with get_connection(db_path) as connection:
            if memory_types:
                placeholders = ", ".join("?" for _ in memory_types)
                type_params: tuple[str, ...] = tuple(memory_types)
                type_clause = f"and type in ({placeholders})"
            else:
                type_params = ()
                type_clause = ""

            if normalized_query:
                cursor = connection.execute(
                    f"""
                    select id, type, title, content, tags_json, created_at, updated_at
                    from ari_memories
                    where (title like ? collate nocase
                       or content like ? collate nocase
                       or tags_json like ? collate nocase)
                      {type_clause}
                    order by updated_at desc, id desc
                    limit ?
                    """,
                    (search_value, search_value, search_value, *type_params, limit),
                )
            else:
                if memory_types:
                    cursor = connection.execute(
                        f"""
                        select id, type, title, content, tags_json, created_at, updated_at
                        from ari_memories
                        where type in ({placeholders})
                        order by updated_at desc, id desc
                        limit ?
                        """,
                        (*type_params, limit),
                    )
                else:
                    cursor = connection.execute(
                        """
                        select id, type, title, content, tags_json, created_at, updated_at
                        from ari_memories
                        order by updated_at desc, id desc
                        limit ?
                        """,
                        (limit,),
                    )
            return list(cursor.fetchall())
    except sqlite3.OperationalError as error:
        if "no such table: ari_memories" in str(error):
            return []
        raise


def get_ari_memory(memory_id: int, db_path: Path = DB_PATH) -> sqlite3.Row | None:
    if not db_path.exists():
        return None

    try:
        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                select id, type, title, content, tags_json, created_at, updated_at
                from ari_memories
                where id = ?
                """,
                (memory_id,),
            ).fetchone()
        return row
    except sqlite3.OperationalError as error:
        if "no such table: ari_memories" in str(error):
            return None
        raise


def create_memory_block(
    *,
    layer: MemoryBlockLayer,
    kind: str,
    title: str,
    body: str,
    source: str,
    importance: int = 3,
    confidence: float = 1.0,
    tags: Sequence[str] = (),
    subject_ids: Sequence[str] = (),
    evidence: Sequence[dict[str, object]] = (),
    db_path: Path = DB_PATH,
) -> sqlite3.Row:
    block = MemoryBlock(
        layer=layer,
        kind=_required_text(kind, "kind"),
        title=_required_text(title, "title"),
        body=_required_text(body, "body"),
        source=_required_text(source, "source"),
        importance=_bounded_int(importance, "importance", minimum=1, maximum=5),
        confidence=_bounded_float(confidence, "confidence", minimum=0.0, maximum=1.0),
        tags=tuple(str(tag) for tag in tags if str(tag).strip()),
        subject_ids=tuple(str(item) for item in subject_ids if str(item).strip()),
        evidence=tuple(dict(item) for item in evidence),
    )
    initialize_database(db_path=db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            insert into ari_memory_blocks (
                id,
                layer,
                kind,
                title,
                body,
                source,
                importance,
                confidence,
                tags_json,
                subject_ids_json,
                evidence_json,
                created_at,
                updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                block.id,
                block.layer,
                block.kind,
                block.title,
                block.body,
                block.source,
                block.importance,
                block.confidence,
                json.dumps(list(block.tags)),
                json.dumps(list(block.subject_ids)),
                json.dumps(list(block.evidence)),
                block.created_at,
                block.updated_at,
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            select *
            from ari_memory_blocks
            where id = ?
            """,
            (block.id,),
        ).fetchone()
    assert row is not None
    return row


def list_memory_blocks(
    *,
    layer: str | None = None,
    limit: int = 20,
    db_path: Path = DB_PATH,
) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    try:
        with get_connection(db_path) as connection:
            if layer:
                rows = connection.execute(
                    """
                    select *
                    from ari_memory_blocks
                    where layer = ?
                    order by updated_at desc, created_at desc
                    limit ?
                    """,
                    (layer, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    select *
                    from ari_memory_blocks
                    order by updated_at desc, created_at desc
                    limit ?
                    """,
                    (limit,),
                ).fetchall()
        return list(rows)
    except sqlite3.OperationalError as error:
        if "no such table: ari_memory_blocks" in str(error):
            return []
        raise


def search_memory_blocks(
    query: str,
    *,
    layer: str | None = None,
    limit: int = 20,
    db_path: Path = DB_PATH,
) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    search_value = f"%{query.strip()}%"
    try:
        with get_connection(db_path) as connection:
            if layer:
                rows = connection.execute(
                    """
                    select *
                    from ari_memory_blocks
                    where layer = ?
                      and (
                        title like ? collate nocase
                        or body like ? collate nocase
                        or kind like ? collate nocase
                        or tags_json like ? collate nocase
                      )
                    order by updated_at desc, created_at desc
                    limit ?
                    """,
                    (layer, search_value, search_value, search_value, search_value, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    select *
                    from ari_memory_blocks
                    where title like ? collate nocase
                       or body like ? collate nocase
                       or kind like ? collate nocase
                       or tags_json like ? collate nocase
                    order by updated_at desc, created_at desc
                    limit ?
                    """,
                    (search_value, search_value, search_value, search_value, limit),
                ).fetchall()
        return list(rows)
    except sqlite3.OperationalError as error:
        if "no such table: ari_memory_blocks" in str(error):
            return []
        raise


def get_memory_block(block_id: str, db_path: Path = DB_PATH) -> sqlite3.Row | None:
    if not db_path.exists():
        return None
    try:
        with get_connection(db_path) as connection:
            return connection.execute(
                """
                select *
                from ari_memory_blocks
                where id = ?
                """,
                (block_id,),
            ).fetchone()
    except sqlite3.OperationalError as error:
        if "no such table: ari_memory_blocks" in str(error):
            return None
        raise


def memory_block_to_payload(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "layer": row["layer"],
        "kind": row["kind"],
        "title": row["title"],
        "body": row["body"],
        "source": row["source"],
        "importance": int(row["importance"]),
        "confidence": float(row["confidence"]),
        "tags": _json_list(row["tags_json"]),
        "subject_ids": _json_list(row["subject_ids_json"]),
        "evidence": _json_dict_list(row["evidence_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _bounded_int(value: int, field_name: str, *, minimum: int, maximum: int) -> int:
    normalized = int(value)
    if normalized < minimum or normalized > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}.")
    return normalized


def _bounded_float(value: float, field_name: str, *, minimum: float, maximum: float) -> float:
    normalized = float(value)
    if normalized < minimum or normalized > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}.")
    return normalized


def _json_list(raw: str) -> list[str]:
    decoded = json.loads(raw or "[]")
    if not isinstance(decoded, list):
        return []
    return [str(value) for value in decoded]


def _json_dict_list(raw: str) -> list[dict[str, object]]:
    decoded = json.loads(raw or "[]")
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, dict)]
