import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def _auth_headers(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/auth/register", json={"email": email, "password": "a-good-password"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_creating_a_project_returns_it(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "ada@example.com")

    response = await client.post(
        "/projects", json={"name": "Sales", "source_type": "upload"}, headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Sales"
    assert body["source_type"] == "upload"
    assert body["id"]


async def test_listing_returns_only_your_own_projects(client: AsyncClient) -> None:
    ada = await _auth_headers(client, "ada@example.com")
    grace = await _auth_headers(client, "grace@example.com")
    await client.post(
        "/projects", json={"name": "Ada's", "source_type": "upload"}, headers=ada
    )
    await client.post(
        "/projects", json={"name": "Grace's", "source_type": "upload"}, headers=grace
    )

    response = await client.get("/projects", headers=ada)

    names = [project["name"] for project in response.json()]
    assert names == ["Ada's"]


async def test_duplicate_project_name_for_one_user_is_409(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "ada@example.com")
    await client.post(
        "/projects", json={"name": "Sales", "source_type": "upload"}, headers=headers
    )

    response = await client.post(
        "/projects", json={"name": "Sales", "source_type": "upload"}, headers=headers
    )

    assert response.status_code == 409


async def test_two_users_may_each_have_a_project_of_the_same_name(
    client: AsyncClient,
) -> None:
    ada = await _auth_headers(client, "ada@example.com")
    grace = await _auth_headers(client, "grace@example.com")
    await client.post(
        "/projects", json={"name": "Sales", "source_type": "upload"}, headers=ada
    )

    response = await client.post(
        "/projects", json={"name": "Sales", "source_type": "upload"}, headers=grace
    )

    assert response.status_code == 201


async def test_deleting_your_own_project_succeeds(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "ada@example.com")
    created = await client.post(
        "/projects", json={"name": "Sales", "source_type": "upload"}, headers=headers
    )
    project_id = created.json()["id"]

    response = await client.delete(f"/projects/{project_id}", headers=headers)

    assert response.status_code == 204
    assert (await client.get("/projects", headers=headers)).json() == []


async def test_projects_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/projects")).status_code == 401
    assert (
        await client.post("/projects", json={"name": "x", "source_type": "upload"})
    ).status_code == 401


async def test_an_unknown_project_is_404(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "ada@example.com")

    response = await client.get("/projects/999999", headers=headers)

    assert response.status_code == 404


async def test_project_name_is_required(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "ada@example.com")

    response = await client.post(
        "/projects", json={"name": "  ", "source_type": "upload"}, headers=headers
    )

    assert response.status_code == 422


async def test_validation_errors_name_the_offending_field(
    client: AsyncClient,
) -> None:
    """A custom validator puts a ValueError in pydantic's ctx; the handler must
    not try to serialise it. PRD section 9: say what happened and what to fix."""
    headers = await _auth_headers(client, "ada@example.com")

    response = await client.post(
        "/projects", json={"name": "  ", "source_type": "upload"}, headers=headers
    )

    assert response.status_code == 422
    fields = response.json()["error"]["fields"]
    assert fields[0]["field"] == "name"
    assert "name" in fields[0]["message"].lower()
