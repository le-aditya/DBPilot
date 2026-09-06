"""PRD F1: all data is scoped to the owning user, at every layer.

Layer 1 of the four-layer model in design document §6. Layers 2 to 4 arrive
with query execution in Phase 4 and get their own adversarial suite.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PASSWORD = "a-good-password"


async def _register(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _project_for(client: AsyncClient, headers: dict[str, str], name: str) -> int:
    response = await client.post(
        "/projects", json={"name": name, "source_type": "upload"}, headers=headers
    )
    return int(response.json()["id"])


async def test_another_users_project_reads_as_missing(client: AsyncClient) -> None:
    ada = await _register(client, "ada@example.com")
    grace = await _register(client, "grace@example.com")
    ada_project = await _project_for(client, ada, "Ada's")

    response = await client.get(f"/projects/{ada_project}", headers=grace)

    assert response.status_code == 404, "403 would confirm the project exists"


async def test_another_user_cannot_delete_your_project(client: AsyncClient) -> None:
    ada = await _register(client, "ada@example.com")
    grace = await _register(client, "grace@example.com")
    ada_project = await _project_for(client, ada, "Ada's")

    response = await client.delete(f"/projects/{ada_project}", headers=grace)

    assert response.status_code == 404
    still_there = await client.get(f"/projects/{ada_project}", headers=ada)
    assert still_there.status_code == 200


async def test_a_missing_project_and_a_forbidden_one_are_indistinguishable(
    client: AsyncClient,
) -> None:
    """Identical responses, so probing cannot enumerate other users' ids."""
    ada = await _register(client, "ada@example.com")
    grace = await _register(client, "grace@example.com")
    ada_project = await _project_for(client, ada, "Ada's")

    forbidden = await client.get(f"/projects/{ada_project}", headers=grace)
    missing = await client.get("/projects/99999999", headers=grace)

    assert forbidden.status_code == missing.status_code
    assert forbidden.json() == missing.json()


async def test_a_users_token_does_not_grant_another_users_listing(
    client: AsyncClient,
) -> None:
    ada = await _register(client, "ada@example.com")
    grace = await _register(client, "grace@example.com")
    await _project_for(client, ada, "Ada's")
    await _project_for(client, grace, "Grace's")

    ada_list = (await client.get("/projects", headers=ada)).json()
    grace_list = (await client.get("/projects", headers=grace)).json()

    assert {p["name"] for p in ada_list} == {"Ada's"}
    assert {p["name"] for p in grace_list} == {"Grace's"}


async def test_a_tampered_token_grants_nothing(client: AsyncClient) -> None:
    ada = await _register(client, "ada@example.com")
    header = ada["Authorization"]
    tampered = header[:-1] + ("a" if header[-1] != "a" else "b")

    response = await client.get("/projects", headers={"Authorization": tampered})

    assert response.status_code == 401


async def test_signing_out_everywhere_stops_the_stolen_token(
    client: AsyncClient,
) -> None:
    """Replay triggers family revocation, so the thief's token dies too."""
    registered = (
        await client.post(
            "/auth/register", json={"email": "ada@example.com", "password": PASSWORD}
        )
    ).json()
    stolen = registered["refresh_token"]

    # The real client rotates once.
    rotated = (
        await client.post("/auth/refresh", json={"refresh_token": stolen})
    ).json()

    # The thief replays the copy they took.
    replay = await client.post("/auth/refresh", json={"refresh_token": stolen})
    assert replay.status_code == 401

    # And the genuine client's newest token is dead too, forcing a real sign-in.
    after = await client.post(
        "/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    )
    assert after.status_code == 401
