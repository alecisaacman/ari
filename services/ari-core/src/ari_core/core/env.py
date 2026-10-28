"""Alec's private settings file, ARI_HOME/ari.env, shared by every ARI process."""

from __future__ import annotations

import os
from pathlib import Path


def ari_home() -> Path:
    return Path(os.environ.get("ARI_HOME", str(Path.home() / "ARI"))).expanduser()


def load_local_env(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from Alec's private env file without overriding the environment.

    Secrets and personal identifiers live here (ARI_HOME/ari.env, mode 600), never
    in a plist or the repository.
    """
    path = path or ari_home() / "ari.env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        value = value.strip().strip("'\"")
        # A blank value is a placeholder; loading it would shadow real credentials.
        if sep and key and value and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value)
