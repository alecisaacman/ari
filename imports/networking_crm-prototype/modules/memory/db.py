import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from ...core.paths import DB_PATH
from ..networking.db import get_connection, initialize_database


def _normalize_tags(tags: Optional[List[str]] = None) -> str:
    return json.dumps(tags or [])


def remember_ari_memory(
    memory_type: str,
    title: str,
    content: str,
    tags: Optional[List[str]] = None,
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
    memory_types: Optional[List[str]] = None,
    limit: int = 20,
    db_path: Path = DB_PATH,
) -> List[sqlite3.Row]:
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
    memory_types: Optional[List[str]] = None,
    db_path: Path = DB_PATH,
) -> List[sqlite3.Row]:
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


def get_ari_memory(memory_id: int, db_path: Path = DB_PATH) -> Optional[sqlite3.Row]:
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
