"""The server must reach PostgreSQL, not just the ASGI transport.

httpx's ASGITransport runs the app inside the test's own event loop, which the
policy already fixed. uvicorn builds its own loop, so only a real subprocess
proves the server can actually query the database.
"""

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def running_server() -> Iterator[str]:
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "run.py", "--port", str(port)],
        cwd=BACKEND,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"server exited early:\n{process.communicate()[0]}")
            try:
                urllib.request.urlopen(f"{base}/health", timeout=1).read()
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                time.sleep(0.3)
        else:
            pytest.fail("server did not become reachable within 30s")
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def test_served_health_reports_a_live_database(running_server: str) -> None:
    """Regression: uvicorn's own loop must be one psycopg can drive."""
    import json

    with urllib.request.urlopen(f"{running_server}/health", timeout=10) as response:
        body = json.load(response)

    assert body["database"] is True, (
        "The served app could not reach PostgreSQL. If this fails on Windows, "
        "uvicorn is building a ProactorEventLoop that psycopg cannot drive."
    )
    assert body["status"] == "ok"
