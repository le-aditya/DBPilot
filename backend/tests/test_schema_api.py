import pytest
from httpx import AsyncClient

from tests.conftest import CommittedProject

pytestmark = pytest.mark.integration


async def test_schema_lists_the_tables_with_row_counts(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/schema", headers=committed_project.headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_name"] == committed_project.schema_name
    table = body["tables"][0]
    assert table["name"] == "people"
    assert table["row_count"] == 3


async def test_schema_reports_columns_in_order_with_their_types(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/schema", headers=committed_project.headers
    )

    columns = response.json()["tables"][0]["columns"]
    assert [c["name"] for c in columns] == ["dbpilot_id", "id", "name", "amount", "shipped"]
    types = {c["name"]: c["data_type"] for c in columns}
    assert types["amount"] == "numeric"
    assert types["shipped"] == "boolean"


async def test_schema_flags_the_primary_key(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/schema", headers=committed_project.headers
    )

    columns = response.json()["tables"][0]["columns"]
    keys = [c["name"] for c in columns if c["is_primary_key"]]
    assert keys == ["dbpilot_id"]


async def test_schema_lists_indexes(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/schema", headers=committed_project.headers
    )

    indexes = response.json()["tables"][0]["indexes"]
    assert any("pkey" in index["name"] for index in indexes)


async def test_a_project_with_no_data_yet_returns_an_empty_schema(
    client: AsyncClient, auth_headers: dict[str, str], api_project: dict
) -> None:
    response = await client.get(
        f"/projects/{api_project['id']}/schema", headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json() == {"schema_name": None, "tables": []}


async def test_another_users_schema_is_a_404(
    live_client: AsyncClient,
    other_committed_project: CommittedProject,
    committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/schema",
        headers=other_committed_project.headers,
    )

    assert response.status_code == 404


async def test_preview_returns_rows_and_the_total(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/tables/people/preview",
        headers=committed_project.headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["rows"]) == 3
    assert "name" in body["columns"]


async def test_preview_serialises_numerics_as_strings_not_errors(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/tables/people/preview",
        headers=committed_project.headers,
        params={"sort": "id"},
    )

    body = response.json()
    amount = body["columns"].index("amount")
    assert body["rows"][0][amount] == "10.50"


async def test_preview_sorts_by_the_requested_column(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/tables/people/preview",
        headers=committed_project.headers,
        params={"sort": "name", "direction": "desc"},
    )

    body = response.json()
    names = [row[body["columns"].index("name")] for row in body["rows"]]
    assert names == ["Grace", "Alan", "Ada"]


async def test_preview_pages_with_offset(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/tables/people/preview",
        headers=committed_project.headers,
        params={"sort": "id", "limit": 1, "offset": 1},
    )

    body = response.json()
    assert [row[body["columns"].index("name")] for row in body["rows"]] == ["Grace"]


async def test_preview_clamps_an_oversized_limit(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/tables/people/preview",
        headers=committed_project.headers,
        params={"limit": 9999},
    )

    assert response.json()["limit"] == 100


async def test_preview_of_an_unknown_table_is_a_404(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/tables/nope/preview",
        headers=committed_project.headers,
    )

    assert response.status_code == 404


async def test_preview_refuses_a_sort_column_that_does_not_exist(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    """The sort key is matched against introspection, never composed blindly."""
    response = await live_client.get(
        f"/projects/{committed_project.id}/tables/people/preview",
        headers=committed_project.headers,
        params={"sort": "name; DROP TABLE people"},
    )

    assert response.status_code == 422


async def test_preview_refuses_an_unknown_direction(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/tables/people/preview",
        headers=committed_project.headers,
        params={"sort": "name", "direction": "sideways"},
    )

    assert response.status_code == 422


async def test_another_users_preview_is_a_404(
    live_client: AsyncClient,
    other_committed_project: CommittedProject,
    committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/tables/people/preview",
        headers=other_committed_project.headers,
    )

    assert response.status_code == 404
