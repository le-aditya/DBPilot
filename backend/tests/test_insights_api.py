"""Dashboard, history, saved queries and exports, against real data."""

import pytest
from httpx import AsyncClient

from tests.conftest import CommittedProject

pytestmark = pytest.mark.integration


async def run(client: AsyncClient, project: CommittedProject, sql: str) -> dict:
    response = await client.post(
        f"/projects/{project.id}/execute",
        headers=project.headers,
        json={"sql": sql},
    )
    return response.json()


# --- history -----------------------------------------------------------------


async def test_history_records_every_attempt_newest_first(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    await run(live_client, committed_project, "SELECT 1 FROM people")
    await run(live_client, committed_project, "DELETE FROM people")

    body = (
        await live_client.get(
            f"/projects/{committed_project.id}/history",
            headers=committed_project.headers,
        )
    ).json()

    assert body["total"] == 2
    assert body["queries"][0]["status"] == "blocked"
    assert body["queries"][1]["status"] == "success"


async def test_history_can_be_filtered_to_blocked_attempts(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    """The blocked list is the safety evidence, so it must be readable on its own."""
    await run(live_client, committed_project, "SELECT 1 FROM people")
    await run(live_client, committed_project, "DROP TABLE people")

    body = (
        await live_client.get(
            f"/projects/{committed_project.id}/history",
            headers=committed_project.headers,
            params={"status_filter": "blocked"},
        )
    ).json()

    assert body["total"] == 1
    assert body["queries"][0]["status"] == "blocked"


async def test_history_pages(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    for _ in range(3):
        await run(live_client, committed_project, "SELECT 1 FROM people")

    body = (
        await live_client.get(
            f"/projects/{committed_project.id}/history",
            headers=committed_project.headers,
            params={"limit": 2, "offset": 2},
        )
    ).json()

    assert body["total"] == 3
    assert len(body["queries"]) == 1


async def test_another_users_history_is_a_404(
    live_client: AsyncClient,
    committed_project: CommittedProject,
    other_committed_project: CommittedProject,
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/history",
        headers=other_committed_project.headers,
    )

    assert response.status_code == 404


# --- dashboard ---------------------------------------------------------------


async def test_the_dashboard_counts_what_happened(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    await run(live_client, committed_project, "SELECT 1 FROM people")
    await run(live_client, committed_project, "DELETE FROM people")

    body = (
        await live_client.get(
            f"/projects/{committed_project.id}/dashboard",
            headers=committed_project.headers,
        )
    ).json()

    assert body["queries_run"] == 2
    assert body["blocked_count"] == 1
    assert body["queries_this_week"] == 2
    assert body["table_count"] == 1


async def test_the_dashboard_reports_timings_from_the_stored_columns(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    await run(live_client, committed_project, "SELECT * FROM people")

    body = (
        await live_client.get(
            f"/projects/{committed_project.id}/dashboard",
            headers=committed_project.headers,
        )
    ).json()

    assert body["average_duration_ms"] is not None
    assert body["slowest"][0]["duration_ms"] is not None


async def test_the_dashboard_reports_the_data_size(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    body = (
        await live_client.get(
            f"/projects/{committed_project.id}/dashboard",
            headers=committed_project.headers,
        )
    ).json()

    assert body["storage_bytes"] > 0


async def test_a_project_with_no_queries_has_an_empty_dashboard_not_an_error(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    body = (
        await live_client.get(
            f"/projects/{committed_project.id}/dashboard",
            headers=committed_project.headers,
        )
    ).json()

    assert body["queries_run"] == 0
    assert body["recent"] == []
    assert body["average_duration_ms"] is None


# --- saved queries -----------------------------------------------------------


async def test_saving_a_query_extracts_its_parameters(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.post(
        "/saved-queries",
        headers=committed_project.headers,
        json={
            "name": "By name",
            "sql_template": "SELECT * FROM people WHERE name = :who",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert [p["name"] for p in body["parameters"]] == ["who"]


async def test_a_saved_query_runs_with_supplied_values(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    saved = (
        await live_client.post(
            "/saved-queries",
            headers=committed_project.headers,
            json={
                "name": "By name",
                "sql_template": "SELECT name FROM people WHERE name = :who",
            },
        )
    ).json()

    body = (
        await live_client.post(
            f"/projects/{committed_project.id}/saved-queries/{saved['id']}/run",
            headers=committed_project.headers,
            json={"values": {"who": "Ada"}},
        )
    ).json()

    assert body["status"] == "success"
    assert body["rows"] == [["Ada"]]


async def test_a_parameter_value_cannot_smuggle_sql(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    """The design's whole reason for binding: a value never becomes structure."""
    saved = (
        await live_client.post(
            "/saved-queries",
            headers=committed_project.headers,
            json={
                "name": "By name",
                "sql_template": "SELECT name FROM people WHERE name = :who",
            },
        )
    ).json()

    body = (
        await live_client.post(
            f"/projects/{committed_project.id}/saved-queries/{saved['id']}/run",
            headers=committed_project.headers,
            json={"values": {"who": "Ada'; DROP TABLE people; --"}},
        )
    ).json()

    assert body["status"] == "success"
    assert body["rows"] == []  # nobody is called that

    still_there = await run(live_client, committed_project, "SELECT count(*) FROM people")
    assert still_there["rows"][0][0] == 3


async def test_a_saved_query_that_writes_is_refused_at_save_time(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.post(
        "/saved-queries",
        headers=committed_project.headers,
        json={"name": "Bad", "sql_template": "DELETE FROM people WHERE id = :id"},
    )

    assert response.status_code == 422


async def test_a_missing_parameter_value_says_which(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    saved = (
        await live_client.post(
            "/saved-queries",
            headers=committed_project.headers,
            json={
                "name": "By name",
                "sql_template": "SELECT * FROM people WHERE name = :who",
            },
        )
    ).json()

    response = await live_client.post(
        f"/projects/{committed_project.id}/saved-queries/{saved['id']}/run",
        headers=committed_project.headers,
        json={"values": {}},
    )

    assert response.status_code == 422
    assert "who" in response.json()["error"]["message"]


async def test_a_duplicate_saved_name_is_a_409(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    payload = {"name": "Same", "sql_template": "SELECT 1"}
    await live_client.post("/saved-queries", headers=committed_project.headers, json=payload)

    response = await live_client.post(
        "/saved-queries", headers=committed_project.headers, json=payload
    )

    assert response.status_code == 409


async def test_saved_queries_are_private_to_their_owner(
    live_client: AsyncClient,
    committed_project: CommittedProject,
    other_committed_project: CommittedProject,
) -> None:
    saved = (
        await live_client.post(
            "/saved-queries",
            headers=committed_project.headers,
            json={"name": "Mine", "sql_template": "SELECT 1"},
        )
    ).json()

    listing = await live_client.get(
        "/saved-queries", headers=other_committed_project.headers
    )
    deleting = await live_client.delete(
        f"/saved-queries/{saved['id']}", headers=other_committed_project.headers
    )

    assert listing.json() == []
    assert deleting.status_code == 404


async def test_a_saved_query_can_be_deleted(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    saved = (
        await live_client.post(
            "/saved-queries",
            headers=committed_project.headers,
            json={"name": "Temp", "sql_template": "SELECT 1"},
        )
    ).json()

    response = await live_client.delete(
        f"/saved-queries/{saved['id']}", headers=committed_project.headers
    )
    listing = await live_client.get("/saved-queries", headers=committed_project.headers)

    assert response.status_code == 204
    assert listing.json() == []


# --- export ------------------------------------------------------------------


async def test_csv_export_has_a_header_and_every_row(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/export",
        headers=committed_project.headers,
        params={"format": "csv", "sql": "SELECT name FROM people ORDER BY id"},
    )

    assert response.status_code == 200
    assert response.text.strip().splitlines() == ["name", "Ada", "Grace", "Alan"]


async def test_json_export_is_objects_keyed_by_column(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/export",
        headers=committed_project.headers,
        params={"format": "json", "sql": "SELECT name FROM people ORDER BY id LIMIT 1"},
    )

    assert response.json() == [{"name": "Ada"}]


async def test_markdown_export_documents_the_schema(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/export",
        headers=committed_project.headers,
        params={"format": "markdown"},
    )

    body = response.text
    assert "## people" in body
    assert "| `name` | `text` |" in body


async def test_an_export_still_goes_through_the_gate(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/export",
        headers=committed_project.headers,
        params={"format": "csv", "sql": "DELETE FROM people"},
    )

    assert response.status_code == 422


async def test_an_unknown_format_is_refused(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/export",
        headers=committed_project.headers,
        params={"format": "xlsx", "sql": "SELECT 1"},
    )

    assert response.status_code == 422
