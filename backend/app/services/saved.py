"""Saved queries. PRD F8, design document section 11."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.models import SavedQuery, SavedQueryVersion
from app.services.parameters import Parameter, ParameterType, extract_parameters, for_parsing
from app.services.safety import Allowed, gate


def _as_dicts(parameters: list[Parameter]) -> list[dict[str, Any]]:
    return [
        {
            "name": parameter.name,
            "type": parameter.type.value,
            "label": parameter.label,
            "default": parameter.default,
        }
        for parameter in parameters
    ]


def as_parameters(stored: list[dict[str, Any]]) -> list[Parameter]:
    return [
        Parameter(
            name=str(entry["name"]),
            type=ParameterType(entry.get("type", "text")),
            label=str(entry.get("label", "")),
            default=entry.get("default"),
        )
        for entry in stored
    ]


def _check_template(template: str, parameters: list[Parameter]) -> None:
    """Gate the template before it is ever stored.

    Saving happens once and running happens many times, so refusing at save time
    means a template that could never run is never kept in the first place.
    """
    decision = gate(for_parsing(template, parameters))
    if not isinstance(decision, Allowed):
        raise UnprocessableError(decision.detail)


async def save_query(
    session: AsyncSession,
    *,
    user_id: int,
    name: str,
    sql_template: str,
    query_id: int | None = None,
    parameters: list[Parameter] | None = None,
) -> SavedQuery:
    resolved = parameters if parameters is not None else extract_parameters(sql_template)
    _check_template(sql_template, resolved)

    existing = await session.scalar(
        select(SavedQuery).where(SavedQuery.user_id == user_id, SavedQuery.name == name)
    )
    if existing is not None:
        raise ConflictError(f"You already have a saved query called {name!r}.")

    saved = SavedQuery(
        user_id=user_id,
        name=name,
        sql_template=sql_template,
        query_id=query_id,
        parameters=_as_dicts(resolved),
    )
    session.add(saved)
    await session.flush()
    session.add(
        SavedQueryVersion(
            saved_query_id=saved.id,
            revision=1,
            sql_template=saved.sql_template,
            parameters=saved.parameters,
        )
    )
    await session.flush()
    return saved


async def update_saved(
    session: AsyncSession,
    *,
    user_id: int,
    saved_id: int,
    name: str | None = None,
    sql_template: str | None = None,
) -> SavedQuery:
    """Rename a saved query, change its SQL, or both.

    A changed template appends a revision rather than overwriting the old text:
    the previous version stays runnable and comparable, which is the whole point
    of keeping history. A rename alone is not a new revision.
    """
    saved = await get_saved(session, user_id=user_id, saved_id=saved_id)

    if name is not None and name != saved.name:
        existing = await session.scalar(
            select(SavedQuery).where(SavedQuery.user_id == user_id, SavedQuery.name == name)
        )
        if existing is not None:
            raise ConflictError(f"You already have a saved query called {name!r}.")
        saved.name = name

    if sql_template is not None and sql_template != saved.sql_template:
        resolved = extract_parameters(sql_template)
        _check_template(sql_template, resolved)

        latest = await session.scalar(
            select(func.max(SavedQueryVersion.revision)).where(
                SavedQueryVersion.saved_query_id == saved.id
            )
        )
        if latest is None:
            # A query saved before versioning existed: record what it says now
            # before replacing it, so the diff has something to compare against.
            session.add(
                SavedQueryVersion(
                    saved_query_id=saved.id,
                    revision=1,
                    sql_template=saved.sql_template,
                    parameters=saved.parameters,
                )
            )
            latest = 1

        saved.sql_template = sql_template
        saved.parameters = _as_dicts(resolved)
        # The query this was saved from no longer answers this SQL.
        saved.query_id = None
        session.add(
            SavedQueryVersion(
                saved_query_id=saved.id,
                revision=latest + 1,
                sql_template=sql_template,
                parameters=saved.parameters,
            )
        )

    await session.flush()
    return saved


async def list_versions(
    session: AsyncSession, *, saved_id: int
) -> list[SavedQueryVersion]:
    """Newest first, so the most recent change is the one you read first."""
    rows = await session.scalars(
        select(SavedQueryVersion)
        .where(SavedQueryVersion.saved_query_id == saved_id)
        .order_by(SavedQueryVersion.revision.desc())
    )
    return list(rows)


async def list_saved(session: AsyncSession, *, user_id: int) -> list[SavedQuery]:
    rows = await session.scalars(
        select(SavedQuery)
        .where(SavedQuery.user_id == user_id)
        .order_by(SavedQuery.created_at)
    )
    return list(rows)


async def get_saved(session: AsyncSession, *, user_id: int, saved_id: int) -> SavedQuery:
    """Someone else's saved query is a 404, never a 403 (design section 6)."""
    saved = await session.scalar(
        select(SavedQuery).where(
            SavedQuery.id == saved_id, SavedQuery.user_id == user_id
        )
    )
    if saved is None:
        raise NotFoundError("That saved query does not exist.")
    return saved


async def delete_saved(session: AsyncSession, saved: SavedQuery) -> None:
    await session.delete(saved)
    await session.flush()
