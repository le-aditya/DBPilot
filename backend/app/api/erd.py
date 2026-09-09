"""ER diagram, its saved layout, and the explain/optimise panels. PRD F4, F6."""

from fastapi import APIRouter
from psycopg import sql
from sqlalchemy import select

from app.ai.provider import ProviderUnavailable
from app.api.deps import CurrentUser, OwnedProject, SessionDep
from app.api.deps_ai import get_provider
from app.core.errors import ServiceUnavailableError, UnprocessableError
from app.db import raw
from app.db.readonly import readonly_connection
from app.models import DiagramLayout
from app.schemas.erd import (
    ClauseResponse,
    ErdColumnResponse,
    ErdEdgeResponse,
    ErdNodeResponse,
    ErdResponse,
    ExplainRequest,
    ExplanationResponse,
    LayoutRequest,
    LayoutResponse,
    Position,
)
from app.services.erd import build_erd
from app.services.explanation import explain_sql, optimise_sql
from app.services.introspection import describe_schema
from app.services.safety import Allowed, Blocked, gate

router = APIRouter(prefix="/projects/{project_id}", tags=["diagram"])


async def _layout(session: SessionDep, project_id: int) -> DiagramLayout | None:
    return await session.scalar(
        select(DiagramLayout).where(DiagramLayout.project_id == project_id)
    )


@router.get("/erd")
async def diagram(project: OwnedProject, session: SessionDep) -> ErdResponse:
    """Nodes, edges and any positions the user has dragged them to."""
    tables = await describe_schema(session, project.schema_name)
    erd = build_erd(tables)
    saved = await _layout(session, project.id)
    positions = saved.node_positions if saved else {}

    return ErdResponse(
        nodes=[
            ErdNodeResponse(
                name=node.name,
                row_count=node.row_count,
                is_junction=node.is_junction,
                columns=[
                    ErdColumnResponse(
                        name=column.name,
                        data_type=column.data_type,
                        nullable=column.nullable,
                        is_primary_key=column.is_primary_key,
                        is_foreign_key=column.is_foreign_key,
                    )
                    for column in node.columns
                ],
                x=(positions.get(node.name) or {}).get("x"),
                y=(positions.get(node.name) or {}).get("y"),
            )
            for node in erd.nodes
        ],
        edges=[
            ErdEdgeResponse(
                source=edge.source,
                target=edge.target,
                source_column=edge.source_column,
                target_column=edge.target_column,
                cardinality=edge.cardinality,
                via=edge.via,
            )
            for edge in erd.edges
        ],
    )


@router.put("/erd/layout")
async def save_layout(
    body: LayoutRequest, project: OwnedProject, session: SessionDep
) -> LayoutResponse:
    """Persist dragged positions. Upserted, because there is one layout per project."""
    stored = {name: {"x": p.x, "y": p.y} for name, p in body.node_positions.items()}
    saved = await _layout(session, project.id)
    if saved is None:
        saved = DiagramLayout(project_id=project.id, node_positions=stored)
        session.add(saved)
    else:
        saved.node_positions = stored
    await session.commit()

    return LayoutResponse(
        node_positions={
            name: Position(x=value["x"], y=value["y"]) for name, value in stored.items()
        }
    )


@router.post("/explain")
async def explain(
    body: ExplainRequest, project: OwnedProject, user: CurrentUser
) -> ExplanationResponse:
    """Clause-by-clause, with offsets the frontend uses to highlight on hover."""
    del project, user  # ownership is the dependency's job; nothing else is needed
    try:
        answer = await explain_sql(get_provider(), body.sql)
    except ProviderUnavailable as error:
        raise ServiceUnavailableError(f"{error} The SQL itself is unchanged.") from error

    return ExplanationResponse(
        summary=answer.summary,
        clauses=[
            ClauseResponse(
                clause=clause.clause, text=clause.text, start=clause.start, end=clause.end
            )
            for clause in answer.clauses
        ],
    )


@router.post("/optimize")
async def optimize(
    body: ExplainRequest, project: OwnedProject, session: SessionDep
) -> ExplanationResponse:
    """Run EXPLAIN inside the read-only transaction, then read the plan back.

    The plan comes from the same gated, read-only path as any other query, so
    "optimise" cannot become a way to run something the gate would refuse.
    """
    del session
    if project.schema_name is None:
        raise UnprocessableError("This project has no data yet.")

    decision = gate(body.sql)
    if isinstance(decision, Blocked):
        raise UnprocessableError(decision.detail)
    assert isinstance(decision, Allowed)

    async with readonly_connection(project) as connection:
        rows = await raw.fetch_all(
            connection,
            sql.SQL("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {}").format(
                sql.SQL(decision.sql)
            ),
        )
    plan = str(rows[0][0]) if rows else "[]"

    try:
        answer = await optimise_sql(get_provider(), decision.sql, plan)
    except ProviderUnavailable as error:
        raise ServiceUnavailableError(f"{error} The query still runs.") from error

    return ExplanationResponse(
        summary=answer.summary,
        clauses=[
            ClauseResponse(
                clause=clause.clause, text=clause.text, start=clause.start, end=clause.end
            )
            for clause in answer.clauses
        ],
    )
