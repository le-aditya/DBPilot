import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_health_reports_ok_when_the_database_answers(
    client: AsyncClient,
) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["version"]


async def test_unknown_route_returns_the_error_envelope(client: AsyncClient) -> None:
    response = await client.get("/no-such-route")

    assert response.status_code == 404
    assert "error" in response.json()


async def test_app_error_renders_message_and_code() -> None:
    from app.core.errors import NotFoundError

    error = NotFoundError("Project not found")

    assert error.status_code == 404
    assert error.code == "not_found"
    assert error.message == "Project not found"
    assert error.to_payload() == {
        "error": {"code": "not_found", "message": "Project not found"}
    }
