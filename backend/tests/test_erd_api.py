"""ER diagram, saved layout, explain and optimise, against real data."""

import pytest
from httpx import AsyncClient

from app.ai.fake import FakeProvider
from app.ai.models import ExplainedClause, SQLExplanation
from app.api.deps_ai import set_provider
from app.services.explanation import validated_clauses
from tests.conftest import CommittedProject

pytestmark = pytest.mark.integration


@pytest.fixture
def scripted():
    def install(*answers, unavailable: bool = False) -> FakeProvider:
        provider = FakeProvider(list(answers), unavailable=unavailable)
        set_provider(provider)
        return provider

    yield install
    set_provider(None)


# --- offset validation (pure) ------------------------------------------------


def test_correct_offsets_are_kept() -> None:
    sql = "SELECT a FROM t WHERE b = 1"
    clauses = [ExplainedClause(clause="WHERE b = 1", text="filters", start=16, end=27)]

    assert validated_clauses(sql, clauses)[0].start == 16


def test_wrong_offsets_are_recomputed_by_searching() -> None:
    """A model that miscounts must not highlight the wrong span."""
    sql = "SELECT a FROM t WHERE b = 1"
    clauses = [
        ExplainedClause(clause="WHERE b = 1", text="filters", start=999, end=1200)
    ]

    fixed = validated_clauses(sql, clauses)[0]

    assert sql[fixed.start : fixed.end] == "WHERE b = 1"


def test_unfindable_offsets_degrade_to_plain_text() -> None:
    sql = "SELECT a FROM t"
    clauses = [ExplainedClause(clause="HAVING x", text="not here", start=50, end=60)]

    fixed = validated_clauses(sql, clauses)[0]

    assert (fixed.start, fixed.end) == (0, 0)
    assert fixed.text == "not here"


def test_reversed_offsets_are_repaired() -> None:
    sql = "SELECT a FROM t"
    clauses = [ExplainedClause(clause="FROM t", text="source", start=14, end=2)]

    fixed = validated_clauses(sql, clauses)[0]

    assert sql[fixed.start : fixed.end] == "FROM t"


# --- the diagram -------------------------------------------------------------


async def test_the_diagram_lists_nodes_for_every_table(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/erd", headers=committed_project.headers
    )

    assert response.status_code == 200
    body = response.json()
    assert [node["name"] for node in body["nodes"]] == ["people"]
    assert body["edges"] == []


async def test_a_node_reports_its_key_columns(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    body = (
        await live_client.get(
            f"/projects/{committed_project.id}/erd", headers=committed_project.headers
        )
    ).json()

    keys = [c["name"] for c in body["nodes"][0]["columns"] if c["is_primary_key"]]
    assert keys == ["dbpilot_id"]


async def test_positions_are_absent_until_the_user_drags_something(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    body = (
        await live_client.get(
            f"/projects/{committed_project.id}/erd", headers=committed_project.headers
        )
    ).json()

    assert body["nodes"][0]["x"] is None


async def test_a_saved_layout_comes_back_with_the_diagram(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    await live_client.put(
        f"/projects/{committed_project.id}/erd/layout",
        headers=committed_project.headers,
        json={"node_positions": {"people": {"x": 120.5, "y": -40}}},
    )

    body = (
        await live_client.get(
            f"/projects/{committed_project.id}/erd", headers=committed_project.headers
        )
    ).json()

    assert (body["nodes"][0]["x"], body["nodes"][0]["y"]) == (120.5, -40)


async def test_saving_a_layout_twice_replaces_it(
    live_client: AsyncClient, committed_project: CommittedProject
) -> None:
    """One layout per project, so a second drag must not create a second row."""
    url = f"/projects/{committed_project.id}/erd/layout"
    await live_client.put(
        url,
        headers=committed_project.headers,
        json={"node_positions": {"people": {"x": 1, "y": 1}}},
    )
    response = await live_client.put(
        url,
        headers=committed_project.headers,
        json={"node_positions": {"people": {"x": 9, "y": 9}}},
    )

    assert response.json()["node_positions"]["people"] == {"x": 9.0, "y": 9.0}


async def test_another_users_diagram_is_a_404(
    live_client: AsyncClient,
    committed_project: CommittedProject,
    other_committed_project: CommittedProject,
) -> None:
    response = await live_client.get(
        f"/projects/{committed_project.id}/erd",
        headers=other_committed_project.headers,
    )

    assert response.status_code == 404


# --- explain and optimise ----------------------------------------------------


async def test_explain_returns_clauses_with_usable_offsets(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    sql = "SELECT name FROM people WHERE id = 1"
    scripted(
        SQLExplanation(
            summary="Finds one person by id.",
            clauses=[
                ExplainedClause(
                    clause="WHERE id = 1", text="filters", start=24, end=36
                )
            ],
        )
    )

    body = (
        await live_client.post(
            f"/projects/{committed_project.id}/explain",
            headers=committed_project.headers,
            json={"sql": sql},
        )
    ).json()

    clause = body["clauses"][0]
    assert sql[clause["start"] : clause["end"]] == "WHERE id = 1"


async def test_explain_survives_a_model_that_miscounts(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    sql = "SELECT name FROM people"
    scripted(
        SQLExplanation(
            summary="Lists names.",
            clauses=[
                ExplainedClause(
                    clause="FROM people", text="source", start=900, end=999
                )
            ],
        )
    )

    body = (
        await live_client.post(
            f"/projects/{committed_project.id}/explain",
            headers=committed_project.headers,
            json={"sql": sql},
        )
    ).json()

    clause = body["clauses"][0]
    assert sql[clause["start"] : clause["end"]] == "FROM people"


async def test_explain_degrades_when_the_model_is_down(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    scripted(unavailable=True)

    response = await live_client.post(
        f"/projects/{committed_project.id}/explain",
        headers=committed_project.headers,
        json={"sql": "SELECT 1"},
    )

    assert response.status_code == 503
    assert "unchanged" in response.json()["error"]["message"]


async def test_optimize_reads_a_real_plan(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    provider = scripted(SQLExplanation(summary="Already efficient.", clauses=[]))

    body = (
        await live_client.post(
            f"/projects/{committed_project.id}/optimize",
            headers=committed_project.headers,
            json={"sql": "SELECT * FROM people"},
        )
    ).json()

    assert body["summary"] == "Already efficient."
    # The plan really came from PostgreSQL, not from a placeholder.
    assert "Plan" in provider.prompts[0]


async def test_optimize_refuses_sql_the_gate_would_block(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    """EXPLAIN must not become a way to run what execute would refuse."""
    scripted(SQLExplanation(summary="unused", clauses=[]))

    response = await live_client.post(
        f"/projects/{committed_project.id}/optimize",
        headers=committed_project.headers,
        json={"sql": "DELETE FROM people"},
    )

    assert response.status_code == 422


async def test_optimize_left_the_data_alone(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    """EXPLAIN ANALYZE really executes, so the read-only transaction must hold."""
    scripted(SQLExplanation(summary="ok", clauses=[]))
    await live_client.post(
        f"/projects/{committed_project.id}/optimize",
        headers=committed_project.headers,
        json={"sql": "SELECT * FROM people"},
    )

    check = await live_client.post(
        f"/projects/{committed_project.id}/execute",
        headers=committed_project.headers,
        json={"sql": "SELECT count(*) FROM people"},
    )
    assert check.json()["rows"][0][0] == 3
