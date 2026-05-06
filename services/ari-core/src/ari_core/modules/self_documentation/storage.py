from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ari_core.core.paths import DB_PATH
from ari_core.modules.coordination.db import (
    get_coordination_entity,
    list_coordination_entities,
    put_coordination_entity,
)

from .content_package import ContentPackage, content_package_from_dict
from .content_seed import ContentSeed, content_seed_from_dict

CONTENT_SEED_ENTITY = "self_documentation_content_seed"
CONTENT_PACKAGE_ENTITY = "self_documentation_content_package"


def store_content_seed(
    seed: ContentSeed,
    *,
    db_path: Path = DB_PATH,
) -> ContentSeed:
    payload = seed.to_dict()
    row = put_coordination_entity(
        CONTENT_SEED_ENTITY,
        {
            "seed_id": seed.seed_id,
            "source_commit_range": seed.source_commit_range,
            "title": seed.title,
            "summary": seed.one_sentence_summary,
            "payload_json": _dumps(payload),
            "created_at": seed.created_at,
            "updated_at": _now_iso(),
        },
        db_path=db_path,
    )
    return _seed_from_row(row)


def get_content_seed(
    seed_id: str,
    *,
    db_path: Path = DB_PATH,
) -> ContentSeed | None:
    row = get_coordination_entity(CONTENT_SEED_ENTITY, seed_id, db_path=db_path)
    if row is None:
        return None
    return _seed_from_row(row)


def list_content_seeds(
    *,
    limit: int = 20,
    db_path: Path = DB_PATH,
) -> tuple[ContentSeed, ...]:
    rows = list_coordination_entities(CONTENT_SEED_ENTITY, limit=limit, db_path=db_path)
    return tuple(_seed_from_row(row) for row in rows)


def store_content_package(
    package: ContentPackage,
    *,
    db_path: Path = DB_PATH,
) -> ContentPackage:
    payload = package.to_dict()
    row = put_coordination_entity(
        CONTENT_PACKAGE_ENTITY,
        {
            "package_id": package.package_id,
            "source_seed_id": package.source_seed_id,
            "title": package.title,
            "content_angle": package.content_angle,
            "payload_json": _dumps(payload),
            "created_at": package.created_at,
            "updated_at": _now_iso(),
        },
        db_path=db_path,
    )
    return _package_from_row(row)


def get_content_package(
    package_id: str,
    *,
    db_path: Path = DB_PATH,
) -> ContentPackage | None:
    row = get_coordination_entity(CONTENT_PACKAGE_ENTITY, package_id, db_path=db_path)
    if row is None:
        return None
    return _package_from_row(row)


def list_content_packages(
    *,
    limit: int = 20,
    db_path: Path = DB_PATH,
) -> tuple[ContentPackage, ...]:
    rows = list_coordination_entities(
        CONTENT_PACKAGE_ENTITY,
        limit=limit,
        db_path=db_path,
    )
    return tuple(_package_from_row(row) for row in rows)


def _seed_from_row(row: Any) -> ContentSeed:
    payload = json.loads(row["payload_json"])
    if not isinstance(payload, dict):
        raise ValueError("Persisted ContentSeed payload must be an object.")
    return content_seed_from_dict(payload)


def _package_from_row(row: Any) -> ContentPackage:
    payload = json.loads(row["payload_json"])
    if not isinstance(payload, dict):
        raise ValueError("Persisted ContentPackage payload must be an object.")
    return content_package_from_dict(payload)


def _dumps(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
