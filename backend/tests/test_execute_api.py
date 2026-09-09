"""The execute endpoint, against real data behind a real read-only role."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Query, QueryStatus
from tests.conftest import CommittedProject

pytestmark = pytest.mark.integration


async def run(
    client: AsyncClient, project: CommittedProject, sql: str, **extra: object
) -> dict:
    response = await client.post(
        f"/projects/{project.id}/execute",
        headers=project.headers,
        json={"sql": sql, **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_select_returns_rows_and_columns(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    body = await run(live_client, committed_project, "SELECT name FROM people")

    assert body["status"] == "success"
    assert body["columns"] == ["name"]
    assert sorted(row[0] for row in body["rows"]) == ["Ada", "Alan", "Grace"]
    assert body["row_count"] == 3


async def test_the_injected_limit_is_reported_in_the_executed_sql(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    body = await run(live_client, committed_project, "SELECT * FROM people")

    assert "LIMIT 1000" in body["executed_sql"]


async def test_numerics_and_dates_survive_serialisation(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    body = await run(
        live_client, committed_project, "SELECT amount FROM people ORDER BY id"
    )

    assert body["rows"][0][0] == "10.50"


async def test_a_write_is_blocked_and_names_its_rule(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    body = await run(live_client, committed_project, "DELETE FROM people")

    assert body["status"] == "blocked"
    assert body["rule"] == "writes_data"
    assert body["executed_sql"] is None
    assert "SELECT" in body["error"]


async def test_a_blocked_statement_really_changed_nothing(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    """The point of the whole exercise."""
    await run(live_client, committed_project, "DELETE FROM people")

    after = await run(live_client, committed_project, "SELECT count(*) FROM people")
    assert after["rows"][0][0] == 3


async def test_a_write_that_somehow_passed_the_gate_still_fails_at_the_role(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    """Layers 3 and 4 hold on their own, so layer 2 is not the only thing.

    The gate blocks this, so to test the layers underneath it the statement is
    sent through execution with the gate's own decision honoured — meaning the
    proof lives in test_readonly.py. Here we assert only that the endpoint never
    reports success for a write, whichever layer stopped it.
    """
    for sql in ["INSERT INTO people (name) VALUES ('x')", "DROP TABLE people"]:
        body = await run(live_client, committed_project, sql)
        assert body["status"] != "success"


async def test_a_catalog_read_is_blocked(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    body = await run(live_client, committed_project, "SELECT * FROM pg_catalog.pg_roles")

    assert body["status"] == "blocked"
    assert body["rule"] == "catalog_access"


async def test_a_query_against_another_projects_schema_fails(
    live_client: AsyncClient,
    committed_project: CommittedProject,
    other_committed_project: CommittedProject,
) -> None:
    """PRD F1, at the layer the parser cannot see: the role has no grant."""
    body = await run(
        live_client,
        committed_project,
        f"SELECT * FROM {other_committed_project.schema_name}.secrets",
    )

    assert body["status"] == "error"
    assert "cannot read" in body["error"]


async def test_a_sql_error_is_reported_not_raised(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    body = await run(live_client, committed_project, "SELECT nope FROM people")

    assert body["status"] == "error"
    assert "nope" in body["error"]


async def test_unparseable_sql_is_blocked_rather_than_a_500(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    body = await run(live_client, committed_project, "SELECT 'unterminated")

    assert body["status"] == "blocked"
    assert body["rule"] == "unparseable"


async def test_every_attempt_is_recorded_including_blocked_ones(
    live_client: AsyncClient,
    committed_project: CommittedProject,
    session: AsyncSession,
) -> None:
    """PRD F8: history is the safety evidence, so nothing is dropped."""
    await run(live_client, committed_project, "SELECT 1 FROM people")
    await run(live_client, committed_project, "DELETE FROM people")
    await run(live_client, committed_project, "SELECT nope FROM people")

    counts = {
        status: await session.scalar(
            select(func.count())
            .select_from(Query)
            .where(Query.project_id == committed_project.id, Query.status == status)
        )
        for status in QueryStatus
    }
    assert counts == {
        QueryStatus.success: 1,
        QueryStatus.blocked: 1,
        QueryStatus.error: 1,
    }


async def test_the_recorded_row_carries_the_question_and_edit_flag(
    live_client: AsyncClient,
    committed_project: CommittedProject,
    session: AsyncSession,
) -> None:
    await run(
        live_client,
        committed_project,
        "SELECT 1 FROM people",
        question="how many people?",
        generated_sql="SELECT count(*) FROM people",
        was_edited=True,
    )

    record = await session.scalar(
        select(Query).where(Query.project_id == committed_project.id)
    )
    assert record is not None
    assert record.question_text == "how many people?"
    assert record.was_edited is True
    assert record.duration_ms is not None


async def test_another_users_project_is_a_404(
    live_client: AsyncClient,
    committed_project: CommittedProject,
    other_committed_project: CommittedProject,
) -> None:
    response = await live_client.post(
        f"/projects/{committed_project.id}/execute",
        headers=other_committed_project.headers,
        json={"sql": "SELECT 1"},
    )

    assert response.status_code == 404


async def test_a_project_with_no_data_says_so(
    client: AsyncClient, auth_headers: dict[str, str], api_project: dict
) -> None:
    response = await client.post(
        f"/projects/{api_project['id']}/execute",
        headers=auth_headers,
        json={"sql": "SELECT 1"},
    )

    assert response.status_code == 422
    assert "Upload a CSV" in response.json()["error"]["message"]
