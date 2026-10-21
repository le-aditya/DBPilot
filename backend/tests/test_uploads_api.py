import json

import pytest
from httpx import AsyncClient
from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import raw

pytestmark = pytest.mark.integration

CUSTOMERS = b"Order ID,Amount\n1,10.50\n2,11.25\n"


def csv_file(name: str = "sales.csv", data: bytes = CUSTOMERS) -> list[tuple]:
    return [("files", (name, data, "text/csv"))]


async def test_analysis_returns_a_proposal(
    client: AsyncClient, auth_headers: dict[str, str], api_project: dict
) -> None:
    response = await client.post(
        f"/projects/{api_project['id']}/upload", headers=auth_headers, files=csv_file()
    )

    assert response.status_code == 200
    table = response.json()["tables"][0]
    assert table["name"] == "sales"
    assert [c["name"] for c in table["columns"]] == ["order_id", "amount"]
    assert [c["type"] for c in table["columns"]] == ["integer", "numeric"]
    assert table["columns"][0]["samples"] == ["1", "2"]


async def test_analysis_creates_no_schema(
    client: AsyncClient,
    auth_headers: dict[str, str],
    api_project: dict,
    session: AsyncSession,
) -> None:
    await client.post(
        f"/projects/{api_project['id']}/upload", headers=auth_headers, files=csv_file()
    )

    count = await raw.fetch_value(
        await raw.connection_of(session),
        sql.SQL(
            r"SELECT count(*) FROM information_schema.schemata "
            r"WHERE schema_name LIKE 'user\_%'"
        ),
    )
    assert count == 0


async def test_another_users_project_is_a_404_not_a_403(
    client: AsyncClient, other_headers: dict[str, str], api_project: dict
) -> None:
    response = await client.post(
        f"/projects/{api_project['id']}/upload", headers=other_headers, files=csv_file()
    )

    assert response.status_code == 404


async def test_a_non_csv_file_is_refused(
    client: AsyncClient, auth_headers: dict[str, str], api_project: dict
) -> None:
    response = await client.post(
        f"/projects/{api_project['id']}/upload",
        headers=auth_headers,
        files=csv_file("notes.txt", b"hello"),
    )

    assert response.status_code == 422
    assert "not a .csv" in response.json()["error"]["message"]


async def test_an_empty_file_names_the_file_that_failed(
    client: AsyncClient, auth_headers: dict[str, str], api_project: dict
) -> None:
    response = await client.post(
        f"/projects/{api_project['id']}/upload",
        headers=auth_headers,
        files=csv_file("empty.csv", b""),
    )

    assert response.status_code == 422
    assert "empty.csv" in response.json()["error"]["message"]


async def test_a_file_over_the_limit_is_refused(
    client: AsyncClient,
    auth_headers: dict[str, str],
    api_project: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_bytes", 100, raising=False)

    response = await client.post(
        f"/projects/{api_project['id']}/upload",
        headers=auth_headers,
        files=csv_file("big.csv", b"a\n" + b"1\n" * 500),
    )

    assert response.status_code == 413
    assert "big.csv" in response.json()["error"]["message"]


async def test_a_full_round_trip_applies_the_users_corrections(
    client: AsyncClient,
    auth_headers: dict[str, str],
    api_project: dict,
    session: AsyncSession,
) -> None:
    analysis = await client.post(
        f"/projects/{api_project['id']}/upload", headers=auth_headers, files=csv_file()
    )
    table = analysis.json()["tables"][0]
    # The user decides amount is really text, and nominates order_id as the key.
    for column in table["columns"]:
        if column["name"] == "amount":
            column["type"] = "text"
    spec = {
        "tables": [
            {
                "name": table["name"],
                "source_filename": table["source_filename"],
                "columns": table["columns"],
                "primary_key": "order_id",
                "foreign_keys": [],
            }
        ]
    }

    response = await client.post(
        f"/projects/{api_project['id']}/upload/commit",
        headers=auth_headers,
        files=csv_file(),
        data={"spec": json.dumps(spec)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tables"] == [{"name": "sales", "row_count": 2}]
    assert body["table_count"] == 1
    assert body["schema_name"].startswith("user_")

    data_type = await raw.fetch_value(
        await raw.connection_of(session),
        sql.SQL(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = {} AND table_name = 'sales' AND column_name = 'amount'"
        ).format(sql.Literal(body["schema_name"])),
    )
    assert data_type == "text"


async def test_a_spec_naming_a_missing_file_says_which(
    client: AsyncClient, auth_headers: dict[str, str], api_project: dict
) -> None:
    spec = {
        "tables": [
            {
                "name": "sales",
                "source_filename": "not-uploaded.csv",
                "columns": [
                    {
                        "name": "a",
                        "source_name": "a",
                        "type": "integer",
                        "nullable": False,
                    }
                ],
            }
        ]
    }

    response = await client.post(
        f"/projects/{api_project['id']}/upload/commit",
        headers=auth_headers,
        files=csv_file(),
        data={"spec": json.dumps(spec)},
    )

    assert response.status_code == 422
    assert "not-uploaded.csv" in response.json()["error"]["message"]


async def test_unparseable_spec_json_is_a_422(
    client: AsyncClient, auth_headers: dict[str, str], api_project: dict
) -> None:
    response = await client.post(
        f"/projects/{api_project['id']}/upload/commit",
        headers=auth_headers,
        files=csv_file(),
        data={"spec": "{not json"},
    )

    assert response.status_code == 422


async def test_commit_on_another_users_project_is_a_404(
    client: AsyncClient, other_headers: dict[str, str], api_project: dict
) -> None:
    response = await client.post(
        f"/projects/{api_project['id']}/upload/commit",
        headers=other_headers,
        files=csv_file(),
        data={"spec": json.dumps({"tables": []})},
    )

    assert response.status_code == 404


async def test_a_first_analysis_has_nothing_to_diff(
    client: AsyncClient, auth_headers: dict[str, str], api_project: dict
) -> None:
    response = await client.post(
        f"/projects/{api_project['id']}/upload", headers=auth_headers, files=csv_file()
    )

    assert response.json()["tables"][0]["diff"] is None


async def test_reanalysing_a_file_reports_the_column_changes(
    client: AsyncClient, auth_headers: dict[str, str], api_project: dict
) -> None:
    """Re-uploading replaces the table, so the review must show what that means."""
    url = f"/projects/{api_project['id']}/upload"
    analysis = await client.post(url, headers=auth_headers, files=csv_file())
    table = analysis.json()["tables"][0]
    spec = {
        "tables": [
            {
                "name": table["name"],
                "source_filename": table["source_filename"],
                "columns": table["columns"],
                "primary_key": None,
                "foreign_keys": [],
            }
        ]
    }
    await client.post(
        f"{url}/commit",
        headers=auth_headers,
        files=csv_file(),
        data={"spec": json.dumps(spec)},
    )

    # A column is added and `amount` stops looking numeric.
    changed = b"Order ID,Amount,Note\n1,ten,hello\n2,eleven,bye\n"
    again = await client.post(url, headers=auth_headers, files=csv_file(data=changed))

    diff = again.json()["tables"][0]["diff"]
    assert diff["existing"] is True
    assert diff["previous_row_count"] == 2
    assert diff["added_columns"] == ["note"]
    assert diff["removed_columns"] == []
    assert diff["type_changes"] == [
        {"column": "amount", "was": "numeric", "now": "text"}
    ]
    assert diff["unchanged"] is False


async def test_an_identical_reupload_is_reported_as_unchanged(
    client: AsyncClient, auth_headers: dict[str, str], api_project: dict
) -> None:
    url = f"/projects/{api_project['id']}/upload"
    analysis = await client.post(url, headers=auth_headers, files=csv_file())
    table = analysis.json()["tables"][0]
    spec = {
        "tables": [
            {
                "name": table["name"],
                "source_filename": table["source_filename"],
                "columns": table["columns"],
                "primary_key": None,
                "foreign_keys": [],
            }
        ]
    }
    await client.post(
        f"{url}/commit",
        headers=auth_headers,
        files=csv_file(),
        data={"spec": json.dumps(spec)},
    )

    again = await client.post(url, headers=auth_headers, files=csv_file())

    diff = again.json()["tables"][0]["diff"]
    assert diff["existing"] is True
    assert diff["unchanged"] is True
    assert diff["type_changes"] == []
