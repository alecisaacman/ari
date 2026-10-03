from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def configured_execution_root(tmp_path: Path) -> Iterator[Path]:
    """Configure each test's server-side execution root as its own tmp directory.

    Execution roots may only be the configured root or a descendant of it, as in a
    deployment that sets ARI_EXECUTION_ROOT. Tests that need a different configured
    root set the variable themselves, which overrides this default. A separate
    MonkeyPatch keeps a test's own `monkeypatch.undo()` from removing it.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("ARI_EXECUTION_ROOT", str(tmp_path))
        yield tmp_path
