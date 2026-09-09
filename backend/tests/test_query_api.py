"""The question endpoint: model output reaches the database only via the gate."""

import pytest
from httpx import AsyncClient

from app.ai.fake import FakeProvider
from app.ai.models import GeneratedSQL
from app.ai.pipeline import get_cache
from app.api.deps_ai import set_provider
from tests.conftest import CommittedProject

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def clear_generation_cache() -> None:
    get_cache().clear()


@pytest.fixture
def scripted():
    """Install a fake provider for one test and remove it afterwards."""

    def install(*answers: GeneratedSQL, unavailable: bool = False) -> FakeProvider:
        provider = FakeProvider(list(answers), unavailable=unavailable)
        set_provider(provider)
        return provider

    yield install
    set_provider(None)


async def ask(client: AsyncClient, project: CommittedProject, question: str):
    return await client.post(
        f"/projects/{project.id}/query",
        headers=project.headers,
        json={"question": question},
    )


async def test_a_question_returns_sql_and_its_results(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    scripted(GeneratedSQL(sql="SELECT name FROM people", confidence="high"))

    response = await ask(live_client, committed_project, "who is in the table?")

    assert response.status_code == 200
    body = response.json()
    assert body["sql"] == "SELECT name FROM people"
    assert body["confidence"] == "high"
    assert body["execution"]["status"] == "success"
    assert sorted(r[0] for r in body["execution"]["rows"]) == ["Ada", "Alan", "Grace"]


async def test_assumptions_are_surfaced_not_buried(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    scripted(
        GeneratedSQL(
            sql="SELECT * FROM people",
            assumptions=["assumed 'recent' = this year"],
        )
    )

    body = (await ask(live_client, committed_project, "recent people")).json()

    assert body["assumptions"] == ["assumed 'recent' = this year"]


async def test_generated_sql_still_goes_through_the_gate(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    """The whole reason the gate was built before the generator."""
    scripted(GeneratedSQL(sql="DELETE FROM people"))

    body = (await ask(live_client, committed_project, "remove everyone")).json()

    assert body["execution"]["status"] == "blocked"
    assert body["execution"]["rule"] == "writes_data"


async def test_a_blocked_generation_changed_nothing(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    scripted(GeneratedSQL(sql="DROP TABLE people"))
    await ask(live_client, committed_project, "drop it")

    set_provider(FakeProvider([GeneratedSQL(sql="SELECT count(*) FROM people")]))
    body = (await ask(live_client, committed_project, "how many?")).json()

    assert body["execution"]["rows"][0][0] == 3


async def test_a_model_that_declines_runs_nothing(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    scripted(GeneratedSQL(sql="", missing="no purchase dates in this schema"))

    body = (await ask(live_client, committed_project, "sales last quarter")).json()

    assert body["sql"] == ""
    assert body["missing"] == "no purchase dates in this schema"
    assert body["execution"] is None


async def test_an_unavailable_model_degrades_to_503_not_a_broken_page(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    """PRD section 13: the SQL editor stays usable when the model is down."""
    scripted(unavailable=True)

    response = await ask(live_client, committed_project, "anything")

    assert response.status_code == 503
    assert "SQL" in response.json()["error"]["message"]


async def test_the_editor_still_works_while_the_model_is_down(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    scripted(unavailable=True)
    await ask(live_client, committed_project, "anything")

    response = await live_client.post(
        f"/projects/{committed_project.id}/execute",
        headers=committed_project.headers,
        json={"sql": "SELECT count(*) FROM people"},
    )

    assert response.status_code == 200
    assert response.json()["rows"][0][0] == 3


async def test_the_sample_rows_sent_to_the_model_come_from_the_project(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    provider = scripted(GeneratedSQL(sql="SELECT 1 FROM people"))

    await ask(live_client, committed_project, "describe the data")

    prompt = provider.prompts[0]
    assert "TABLE people" in prompt
    assert "Ada" in prompt  # a real sampled value


async def test_a_repeated_question_is_answered_from_cache(
    live_client: AsyncClient, committed_project: CommittedProject, scripted
) -> None:
    provider = scripted(GeneratedSQL(sql="SELECT name FROM people"))

    await ask(live_client, committed_project, "same question")
    second = (await ask(live_client, committed_project, "same question")).json()

    assert second["cached"] is True
    assert len(provider.prompts) == 1


async def test_a_project_with_no_data_says_so(
    client: AsyncClient, auth_headers: dict[str, str], api_project: dict
) -> None:
    response = await client.post(
        f"/projects/{api_project['id']}/query",
        headers=auth_headers,
        json={"question": "anything"},
    )

    assert response.status_code == 422


async def test_another_users_project_is_a_404(
    live_client: AsyncClient,
    committed_project: CommittedProject,
    other_committed_project: CommittedProject,
    scripted,
) -> None:
    scripted(GeneratedSQL(sql="SELECT 1"))

    response = await live_client.post(
        f"/projects/{committed_project.id}/query",
        headers=other_committed_project.headers,
        json={"question": "peek"},
    )

    assert response.status_code == 404
