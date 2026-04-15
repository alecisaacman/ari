import sqlite3
from pathlib import Path
from typing import Optional

from ...core.paths import DB_PATH
from ..networking.db import get_connection, initialize_database


def create_ari_task(title: str, notes: str = "", db_path: Path = DB_PATH) -> sqlite3.Row:
    initialize_database(db_path=db_path)
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            insert into ari_tasks (title, status, notes)
            values (?, 'open', ?)
            """,
            (title, notes),
        )
        task_id = int(cursor.lastrowid)
        connection.commit()
        row = connection.execute(
            """
            select id, title, status, notes, created_at, updated_at
            from ari_tasks
            where id = ?
            """,
            (task_id,),
        ).fetchone()
    assert row is not None
    return row


def list_ari_tasks(limit: int = 20, db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    try:
        with get_connection(db_path) as connection:
            cursor = connection.execute(
                """
                select id, title, status, notes, created_at, updated_at
                from ari_tasks
                order by updated_at desc, id desc
                limit ?
                """,
                (limit,),
            )
            return list(cursor.fetchall())
    except sqlite3.OperationalError as error:
        if "no such table: ari_tasks" in str(error):
            return []
        raise


def get_ari_task(task_id: int, db_path: Path = DB_PATH) -> Optional[sqlite3.Row]:
    if not db_path.exists():
        return None
    try:
        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                select id, title, status, notes, created_at, updated_at
                from ari_tasks
                where id = ?
                """,
                (task_id,),
            ).fetchone()
        return row
    except sqlite3.OperationalError as error:
        if "no such table: ari_tasks" in str(error):
            return None
        raise


def search_ari_tasks(query: str, limit: int = 10, db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    normalized_query = query.strip()
    search_value = f"%{normalized_query}%"
    try:
        with get_connection(db_path) as connection:
            if normalized_query:
                cursor = connection.execute(
                    """
                    select id, title, status, notes, created_at, updated_at
                    from ari_tasks
                    where title like ? collate nocase
                       or notes like ? collate nocase
                    order by updated_at desc, id desc
                    limit ?
                    """,
                    (search_value, search_value, limit),
                )
            else:
                cursor = connection.execute(
                    """
                    select id, title, status, notes, created_at, updated_at
                    from ari_tasks
                    order by updated_at desc, id desc
                    limit ?
                    """,
                    (limit,),
                )
            return list(cursor.fetchall())
    except sqlite3.OperationalError as error:
        if "no such table: ari_tasks" in str(error):
            return []
        raise
