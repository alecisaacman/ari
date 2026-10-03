from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

UNSET_EXECUTION_ROOT_MARKER = "unset_execution_root"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{UNSET_EXECUTION_ROOT_MARKER}: run with ARI_EXECUTION_ROOT removed, exercising the "
        "production fallback instead of the per-test configured root",
    )


@pytest.fixture(autouse=True)
def configured_execution_root(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Path]:
    """Configure each test's server-side execution root as its own tmp directory.

    Execution roots may only be the configured root or a descendant of it, as in a
    deployment that sets ARI_EXECUTION_ROOT. Tests that need a different configured
    root set the variable themselves, which overrides this default. Tests marked
    `unset_execution_root` get no configured root at all, so the production fallback
    stays tested. An ambient ARI_ALLOW_SELF_MODIFICATION is always removed. A separate
    MonkeyPatch keeps a test's own `monkeypatch.undo()` from removing these settings.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.delenv("ARI_ALLOW_SELF_MODIFICATION", raising=False)
        if request.node.get_closest_marker(UNSET_EXECUTION_ROOT_MARKER):
            patch.delenv("ARI_EXECUTION_ROOT", raising=False)
        else:
            patch.setenv("ARI_EXECUTION_ROOT", str(tmp_path))
        yield tmp_path
