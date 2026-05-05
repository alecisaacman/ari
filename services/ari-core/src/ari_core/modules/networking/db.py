import shutil
import sqlite3
from pathlib import Path

from ...core.paths import ARTIFACTS_DIR, DB_PATH, LEGACY_DB_PATH, LOGS_DIR, SCHEMA_PATH, STATE_DIR


def ensure_runtime_dirs(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path == DB_PATH:
        for path in (STATE_DIR, LOGS_DIR, ARTIFACTS_DIR):
            path.mkdir(parents=True, exist_ok=True)
        if not DB_PATH.exists() and LEGACY_DB_PATH.exists():
            shutil.copy2(LEGACY_DB_PATH, DB_PATH)


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    ensure_runtime_dirs(db_path)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("pragma foreign_keys = on")
    return connection


def initialize_database(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> Path:
    ensure_runtime_dirs(db_path)
    schema_sql = schema_path.read_text(encoding="utf-8")
    with get_connection(db_path) as connection:
        connection.executescript(schema_sql)
        _ensure_followups_completed_at_column(connection)
        _ensure_retry_approval_execution_columns(connection)
        connection.commit()
    return db_path


def _ensure_followups_completed_at_column(connection: sqlite3.Connection) -> None:
    followups_table = connection.execute(
        """
        select 1
        from sqlite_master
        where type = 'table' and name = 'follow_ups'
        """
    ).fetchone()
    if followups_table is None:
        return

    columns = connection.execute("pragma table_info(follow_ups)").fetchall()
    column_names = {column["name"] for column in columns}
    if "completed_at" not in column_names:
        connection.execute("alter table follow_ups add column completed_at text")


def _ensure_retry_approval_execution_columns(connection: sqlite3.Connection) -> None:
    table = connection.execute(
        """
        select 1
        from sqlite_master
        where type = 'table' and name = 'ari_runtime_coding_loop_retry_approvals'
        """
    ).fetchone()
    if table is None:
        return

    columns = connection.execute(
        "pragma table_info(ari_runtime_coding_loop_retry_approvals)"
    ).fetchall()
    column_names = {column["name"] for column in columns}
    for column_name in (
        "retry_execution_run_id",
        "retry_execution_status",
        "retry_execution_reason",
        "executed_at",
    ):
        if column_name not in column_names:
            connection.execute(
                "alter table ari_runtime_coding_loop_retry_approvals "
                f"add column {column_name} text"
            )


def add_contact(
    full_name: str,
    company: str | None = None,
    role_title: str | None = None,
    location: str | None = None,
    source: str | None = None,
    email: str | None = None,
    linkedin_url: str | None = None,
    db_path: Path = DB_PATH,
) -> int:
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            insert into contacts (
                full_name,
                company,
                role_title,
                location,
                source,
                email,
                linkedin_url
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (full_name, company, role_title, location, source, email, linkedin_url),
        )
        connection.commit()
        return int(cursor.lastrowid)


def list_contacts(db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            select
                id,
                full_name,
                company,
                role_title,
                location,
                source,
                email,
                linkedin_url,
                created_at,
                updated_at
            from contacts
            order by full_name collate nocase asc, id asc
            """
        )
        return list(cursor.fetchall())


def contact_exists(contact_id: int, db_path: Path = DB_PATH) -> bool:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "select 1 from contacts where id = ?",
            (contact_id,),
        ).fetchone()
    return row is not None


def get_contact(contact_id: int, db_path: Path = DB_PATH) -> sqlite3.Row | None:
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            select
                id,
                full_name,
                company,
                role_title,
                location,
                source,
                email,
                linkedin_url,
                created_at,
                updated_at
            from contacts
            where id = ?
            """,
            (contact_id,),
        ).fetchone()
    return row


def add_note(contact_id: int, body: str, db_path: Path = DB_PATH) -> int:
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            "insert into notes (contact_id, body) values (?, ?)",
            (contact_id, body),
        )
        connection.commit()
        return int(cursor.lastrowid)


def list_notes_for_contact(contact_id: int, db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            select id, contact_id, body, created_at
            from notes
            where contact_id = ?
            order by created_at asc, id asc
            """,
            (contact_id,),
        )
        return list(cursor.fetchall())


def add_followup(
    contact_id: int,
    due_on: str,
    reason: str | None = None,
    db_path: Path = DB_PATH,
) -> int:
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            "insert into follow_ups (contact_id, due_on, reason) values (?, ?, ?)",
            (contact_id, due_on, reason),
        )
        connection.commit()
        return int(cursor.lastrowid)


def followup_exists(followup_id: int, db_path: Path = DB_PATH) -> bool:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "select 1 from follow_ups where id = ?",
            (followup_id,),
        ).fetchone()
    return row is not None


def complete_followup(followup_id: int, db_path: Path = DB_PATH) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            update follow_ups
            set status = 'completed',
                completed_at = current_timestamp
            where id = ?
            """,
            (followup_id,),
        )
        connection.commit()


def list_followups(db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            select
                follow_ups.id,
                follow_ups.contact_id,
                contacts.full_name,
                follow_ups.due_on,
                follow_ups.status,
                follow_ups.reason,
                follow_ups.created_at,
                follow_ups.completed_at
            from follow_ups
            join contacts on contacts.id = follow_ups.contact_id
            order by follow_ups.due_on asc, follow_ups.id asc
            """
        )
        return list(cursor.fetchall())


def list_due_followups(today: str, db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            select
                follow_ups.id,
                follow_ups.contact_id,
                contacts.full_name,
                follow_ups.due_on,
                follow_ups.status,
                follow_ups.reason,
                follow_ups.created_at,
                follow_ups.completed_at
            from follow_ups
            join contacts on contacts.id = follow_ups.contact_id
            where follow_ups.status = 'pending'
              and follow_ups.due_on <= ?
            order by follow_ups.due_on asc, follow_ups.id asc
            """,
            (today,),
        )
        return list(cursor.fetchall())


def list_pending_followups(db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            select
                follow_ups.id,
                follow_ups.contact_id,
                contacts.full_name,
                follow_ups.due_on,
                follow_ups.status,
                follow_ups.reason,
                follow_ups.created_at,
                follow_ups.completed_at
            from follow_ups
            join contacts on contacts.id = follow_ups.contact_id
            where follow_ups.status = 'pending'
            order by follow_ups.due_on asc, follow_ups.id asc
            """
        )
        return list(cursor.fetchall())


def list_followups_for_contact(contact_id: int, db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            select
                id,
                contact_id,
                due_on,
                status,
                reason,
                created_at,
                completed_at
            from follow_ups
            where contact_id = ?
            order by due_on asc, id asc
            """,
            (contact_id,),
        )
        return list(cursor.fetchall())
