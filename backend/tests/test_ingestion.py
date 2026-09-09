import pytest
from psycopg import sql
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnprocessableError
from app.db import raw
from app.models import Project, Upload
from app.services.inference import ColumnType, infer_table
from app.services.ingestion import (
    ColumnSpec,
    ForeignKeySpec,
    TableSpec,
    commit_upload,
)

pytestmark = pytest.mark.integration

CUSTOMERS = b"id,name\n1,Ada\n2,Grace\n"
ORDERS = b"order_id,customer_id,amount\n10,1,99.50\n11,2,10.00\n"


def spec_from(filename: str, data: bytes, **overrides: object) -> TableSpec:
    """Build a TableSpec the way the review screen would, from inference."""
    inferred = infer_table(filename, data)
    return TableSpec(
        name=inferred.name,
        source_filename=filename,
        columns=tuple(
            ColumnSpec(
                name=column.name,
                source_name=column.source_name,
                type=column.type,
                nullable=column.nullable,
            )
            for column in inferred.columns
        ),
        **overrides,  # type: ignore[arg-type]
    )


async def _scalar(session: AsyncSession, statement: sql.Composable) -> object:
    return await raw.fetch_value(await raw.connection_of(session), statement)


async def test_commit_creates_the_table_and_copies_every_row(
    session: AsyncSession, project: Project
) -> None:
    result = await commit_upload(
        session, project, [spec_from("customers.csv", CUSTOMERS)],
        {"customers.csv": CUSTOMERS},
    )

    assert result[0].name == "customers"
    assert result[0].row_count == 2
    count = await _scalar(
        session,
        sql.SQL("SELECT count(*) FROM {}.customers").format(
            sql.Identifier(project.schema_name or "")
        ),
    )
    assert count == 2


async def test_a_nominated_primary_key_becomes_the_constraint(
    session: AsyncSession, project: Project
) -> None:
    await commit_upload(
        session, project,
        [spec_from("customers.csv", CUSTOMERS, primary_key="id")],
        {"customers.csv": CUSTOMERS},
    )

    key = await _scalar(
        session,
        sql.SQL(
            "SELECT column_name FROM information_schema.key_column_usage "
            "WHERE table_schema = {} AND table_name = 'customers'"
        ).format(sql.Literal(project.schema_name)),
    )
    assert key == "id"


async def test_no_nominated_key_generates_a_surrogate_id(
    session: AsyncSession, project: Project
) -> None:
    await commit_upload(
        session, project, [spec_from("orders.csv", ORDERS)], {"orders.csv": ORDERS}
    )

    key = await _scalar(
        session,
        sql.SQL(
            "SELECT column_name FROM information_schema.key_column_usage "
            "WHERE table_schema = {} AND table_name = 'orders'"
        ).format(sql.Literal(project.schema_name)),
    )
    assert key == "id"


async def test_a_declared_foreign_key_is_created(
    session: AsyncSession, project: Project
) -> None:
    await commit_upload(
        session,
        project,
        [
            spec_from("customers.csv", CUSTOMERS, primary_key="id"),
            spec_from(
                "orders.csv",
                ORDERS,
                foreign_keys=(
                    ForeignKeySpec(
                        column="customer_id",
                        references_table="customers",
                        references_column="id",
                    ),
                ),
            ),
        ],
        {"customers.csv": CUSTOMERS, "orders.csv": ORDERS},
    )

    count = await _scalar(
        session,
        sql.SQL(
            "SELECT count(*) FROM information_schema.table_constraints "
            "WHERE table_schema = {} AND constraint_type = 'FOREIGN KEY'"
        ).format(sql.Literal(project.schema_name)),
    )
    assert count == 1


async def test_a_foreign_key_to_a_table_not_in_the_batch_is_refused(
    session: AsyncSession, project: Project
) -> None:
    with pytest.raises(UnprocessableError, match="not one of the tables"):
        await commit_upload(
            session,
            project,
            [
                spec_from(
                    "orders.csv",
                    ORDERS,
                    foreign_keys=(
                        ForeignKeySpec(
                            column="customer_id",
                            references_table="elsewhere",
                            references_column="id",
                        ),
                    ),
                )
            ],
            {"orders.csv": ORDERS},
        )


async def test_a_nullable_column_cannot_be_the_primary_key(
    session: AsyncSession, project: Project
) -> None:
    gappy = b"id,name\n1,Ada\n,Grace\n"

    with pytest.raises(UnprocessableError, match="empty values"):
        await commit_upload(
            session, project,
            [spec_from("customers.csv", gappy, primary_key="id")],
            {"customers.csv": gappy},
        )


async def test_a_spec_naming_a_file_that_was_not_uploaded_is_refused(
    session: AsyncSession, project: Project
) -> None:
    with pytest.raises(UnprocessableError, match="not one of the uploaded files"):
        await commit_upload(
            session, project, [spec_from("customers.csv", CUSTOMERS)], {}
        )


async def test_table_count_is_refreshed_on_the_project(
    session: AsyncSession, project: Project
) -> None:
    await commit_upload(
        session,
        project,
        [spec_from("customers.csv", CUSTOMERS), spec_from("orders.csv", ORDERS)],
        {"customers.csv": CUSTOMERS, "orders.csv": ORDERS},
    )

    assert project.table_count == 2


async def test_an_uploads_row_records_the_filename_and_size(
    session: AsyncSession, project: Project
) -> None:
    await commit_upload(
        session, project, [spec_from("customers.csv", CUSTOMERS)],
        {"customers.csv": CUSTOMERS},
    )

    upload = await session.scalar(select(Upload).where(Upload.project_id == project.id))
    assert upload is not None
    assert upload.original_filename == "customers.csv"
    assert upload.table_name == "customers"
    assert upload.row_count == 2
    assert upload.byte_size == len(CUSTOMERS)


async def test_a_header_that_looks_like_sql_becomes_a_column_not_an_incident(
    session: AsyncSession, project: Project
) -> None:
    hostile = b'x"); DROP TABLE dbpilot.users; --,ok\n1,2\n'

    await commit_upload(
        session, project, [spec_from("t.csv", hostile)], {"t.csv": hostile}
    )

    still_there = await _scalar(
        session, sql.SQL("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_schema = 'dbpilot' AND table_name = 'users'")
    )
    assert still_there == 1


async def test_a_cell_that_looks_like_sql_is_stored_as_data(
    session: AsyncSession, project: Project
) -> None:
    hostile = b"note\n\"'); DROP TABLE dbpilot.users; --\"\n"

    await commit_upload(
        session, project, [spec_from("t.csv", hostile)], {"t.csv": hostile}
    )

    stored = await _scalar(
        session,
        sql.SQL("SELECT note FROM {}.t").format(sql.Identifier(project.schema_name or "")),
    )
    assert stored == "'); DROP TABLE dbpilot.users; --"


async def test_committing_twice_replaces_the_table(
    session: AsyncSession, project: Project
) -> None:
    await commit_upload(
        session, project, [spec_from("customers.csv", CUSTOMERS)],
        {"customers.csv": CUSTOMERS},
    )
    smaller = b"id,name\n1,Ada\n"

    result = await commit_upload(
        session, project, [spec_from("customers.csv", smaller)],
        {"customers.csv": smaller},
    )

    assert result[0].row_count == 1


async def test_the_declared_types_are_what_postgresql_created(
    session: AsyncSession, project: Project
) -> None:
    spec = spec_from("orders.csv", ORDERS)
    # The user overrides amount from numeric to text on the review screen.
    corrected = TableSpec(
        name=spec.name,
        source_filename=spec.source_filename,
        columns=tuple(
            ColumnSpec(c.name, c.source_name, ColumnType.text, c.nullable)
            if c.name == "amount"
            else c
            for c in spec.columns
        ),
    )

    await commit_upload(session, project, [corrected], {"orders.csv": ORDERS})

    data_type = await _scalar(
        session,
        sql.SQL(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = {} AND table_name = 'orders' AND column_name = 'amount'"
        ).format(sql.Literal(project.schema_name)),
    )
    assert data_type == "text"


async def test_a_csv_that_already_has_an_id_column_keeps_it(
    session: AsyncSession, project: Project
) -> None:
    """The generated key must not collide with a column the file already has."""
    await commit_upload(
        session, project, [spec_from("customers.csv", CUSTOMERS)],
        {"customers.csv": CUSTOMERS},
    )

    names = await raw.fetch_all(
        await raw.connection_of(session),
        sql.SQL(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = {} AND table_name = 'customers' "
            "ORDER BY ordinal_position"
        ).format(sql.Literal(project.schema_name)),
    )
    assert [row[0] for row in names] == ["dbpilot_id", "id", "name"]
