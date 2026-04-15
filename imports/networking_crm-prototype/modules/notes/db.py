import sqlite3
from pathlib import Path

from ...core.paths import DB_PATH
from ..networking.db import initialize_database, get_connection


def save_ari_note(title: str, body: str, db_path: Path = DB_PATH) -> sqlite3.Row:
    initialize_database(db_path=db_path)
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            insert into ari_notes (title, body)
            values (?, ?)
            """,
            (title, body),
        )
        note_id = int(cursor.lastrowid)
        connection.commit()
        row = connection.execute(
            """
            select id, title, body, created_at, updated_at
            from ari_notes
            where id = ?
            """,
            (note_id,),
        ).fetchone()
    assert row is not None
    return row


def search_ari_notes(query: str, limit: int = 10, db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    initialize_database(db_path=db_path)
    normalized_query = query.strip()
    search_value = f"%{normalized_query}%"
    with get_connection(db_path) as connection:
        if normalized_query:
            cursor = connection.execute(
                """
                select id, title, body, created_at, updated_at
                from ari_notes
                where title like ? collate nocase
                   or body like ? collate nocase
                order by updated_at desc, id desc
                limit ?
                """,
                (search_value, search_value, limit),
            )
        else:
            cursor = connection.execute(
                """
                select id, title, body, created_at, updated_at
                from ari_notes
                order by updated_at desc, id desc
                limit ?
                """,
                (limit,),
            )
        return list(cursor.fetchall())
