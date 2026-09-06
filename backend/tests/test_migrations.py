import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.integration


def _test_env() -> dict[str, str]:
    from app.core.config import get_settings

    settings = get_settings()
    assert settings.test_database_url is not None
    return {**os.environ, "DATABASE_URL": settings.test_database_url}


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    """Run alembic against the test database, never the development one."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env=_test_env(),
    )


def test_upgrade_head_then_downgrade_base_round_trips() -> None:
    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr

    down = _alembic("downgrade", "base")
    assert down.returncode == 0, down.stderr

    again = _alembic("upgrade", "head")
    assert again.returncode == 0, again.stderr


def test_migrations_match_the_models() -> None:
    """An empty autogenerate diff proves the revisions and the models agree."""
    _alembic("upgrade", "head")
    check = _alembic("check")

    assert check.returncode == 0, (
        "Models and migrations have drifted:\n" + check.stdout + check.stderr
    )
