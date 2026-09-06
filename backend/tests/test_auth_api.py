import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

CREDENTIALS = {"email": "ada@example.com", "password": "a-good-password"}


async def test_register_returns_tokens_and_the_user(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json=CREDENTIALS)

    assert response.status_code == 201
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "ada@example.com"


async def test_register_never_returns_the_password_hash(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json=CREDENTIALS)

    assert "password" not in response.text
    assert "$2b$" not in response.text


async def test_register_rejects_a_duplicate_email(client: AsyncClient) -> None:
    await client.post("/auth/register", json=CREDENTIALS)

    response = await client.post("/auth/register", json=CREDENTIALS)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_register_rejects_a_short_password(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register", json={"email": "ada@example.com", "password": "short"}
    )

    assert response.status_code == 422


async def test_register_rejects_a_malformed_email(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register", json={"email": "not-an-email", "password": "a-good-password"}
    )

    assert response.status_code == 422


async def test_login_returns_tokens(client: AsyncClient) -> None:
    await client.post("/auth/register", json=CREDENTIALS)

    response = await client.post("/auth/login", json=CREDENTIALS)

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_with_a_wrong_password_is_401(client: AsyncClient) -> None:
    await client.post("/auth/register", json=CREDENTIALS)

    response = await client.post(
        "/auth/login",
        json={"email": CREDENTIALS["email"], "password": "wrong-password"},
    )

    assert response.status_code == 401


async def test_login_does_not_reveal_whether_an_account_exists(
    client: AsyncClient,
) -> None:
    await client.post("/auth/register", json=CREDENTIALS)

    wrong_password = await client.post(
        "/auth/login",
        json={"email": CREDENTIALS["email"], "password": "wrong-password"},
    )
    unknown_email = await client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password"},
    )

    assert wrong_password.status_code == unknown_email.status_code
    assert (
        wrong_password.json()["error"]["message"]
        == unknown_email.json()["error"]["message"]
    )


async def test_refresh_exchanges_the_token(client: AsyncClient) -> None:
    registered = (await client.post("/auth/register", json=CREDENTIALS)).json()

    response = await client.post(
        "/auth/refresh", json={"refresh_token": registered["refresh_token"]}
    )

    assert response.status_code == 200
    assert response.json()["refresh_token"] != registered["refresh_token"]


async def test_a_spent_refresh_token_is_rejected(client: AsyncClient) -> None:
    registered = (await client.post("/auth/register", json=CREDENTIALS)).json()
    await client.post(
        "/auth/refresh", json={"refresh_token": registered["refresh_token"]}
    )

    response = await client.post(
        "/auth/refresh", json={"refresh_token": registered["refresh_token"]}
    )

    assert response.status_code == 401


async def test_me_returns_the_signed_in_user(client: AsyncClient) -> None:
    registered = (await client.post("/auth/register", json=CREDENTIALS)).json()

    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {registered['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"


async def test_me_without_a_token_is_401(client: AsyncClient) -> None:
    response = await client.get("/auth/me")

    assert response.status_code == 401


async def test_me_rejects_a_refresh_token_used_as_a_bearer(
    client: AsyncClient,
) -> None:
    registered = (await client.post("/auth/register", json=CREDENTIALS)).json()

    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {registered['refresh_token']}"},
    )

    assert response.status_code == 401
