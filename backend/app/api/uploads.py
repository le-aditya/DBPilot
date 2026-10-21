"""CSV import. PRD F2.1, in the two steps design document section 7 describes.

`POST /projects/{id}/upload` proposes a schema and creates nothing.
`POST /projects/{id}/upload/commit` takes the corrected schema and builds it.

The client re-sends the files with the commit rather than the server stashing
them between calls. A stash would need a temp store, a key, an expiry and a
cleanup job, and the design (section 2) rules out adding a scheduler; re-reading
a file of at most 25 MB is cheaper than all of that.
"""

import json
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import ValidationError

from app.api.deps import OwnedProject, SessionDep
from app.core.config import get_settings
from app.core.errors import PayloadTooLargeError, UnprocessableError
from app.schemas.upload import (
    ColumnProposal,
    ColumnTypeChange,
    CommittedTableResponse,
    TableDiff,
    TableProposal,
    UploadAnalysis,
    UploadCommit,
    UploadResult,
)
from app.services.inference import ColumnType, infer_table
from app.services.ingestion import commit_upload
from app.services.introspection import TableDescription, describe_schema

router = APIRouter(prefix="/projects/{project_id}", tags=["uploads"])

CHUNK_BYTES = 64 * 1024

# PostgreSQL reports a column's storage type, not the inference name, so the two
# are compared by family: `bigint` and `integer` are both an integer upload.
_TYPE_FAMILY: dict[str, set[str]] = {
    ColumnType.integer.value: {"smallint", "integer", "bigint"},
    ColumnType.numeric.value: {"numeric", "real", "double precision"},
    ColumnType.boolean.value: {"boolean"},
    ColumnType.date.value: {"date"},
    ColumnType.timestamp.value: {
        "timestamp without time zone",
        "timestamp with time zone",
    },
    ColumnType.text.value: {
        "text",
        "character varying",
        "character",
        "uuid",
        "json",
        "jsonb",
    },
}


def _family(data_type: str) -> str:
    lowered = data_type.lower()
    for family, names in _TYPE_FAMILY.items():
        if lowered in names:
            return family
    return lowered


def _is_generated_key(column: object) -> bool:
    """The surrogate id DBPilot adds when the user nominated no key.

    It was never in the CSV, so it must not show up as a dropped column when the
    same file is uploaded again.
    """
    is_primary = bool(getattr(column, "is_primary_key", False))
    default = str(getattr(column, "default", "") or "")
    return is_primary and "nextval" in default


def _diff(
    proposal: TableProposal, existing: TableDescription | None
) -> TableDiff | None:
    """Compare a proposal with the table of the same name, if there is one."""
    if existing is None:
        return None

    before = {
        column.name: column
        for column in existing.columns
        if not _is_generated_key(column)
    }
    after = {column.name for column in proposal.columns}

    added = [column.name for column in proposal.columns if column.name not in before]
    removed = [name for name in before if name not in after]
    retyped = [
        ColumnTypeChange(
            column=column.name,
            was=before[column.name].data_type,
            now=column.type,
        )
        for column in proposal.columns
        if column.name in before
        and _family(before[column.name].data_type) != _family(column.type.value)
    ]

    return TableDiff(
        existing=True,
        previous_row_count=existing.row_count,
        previous_columns=list(before),
        added_columns=added,
        removed_columns=removed,
        type_changes=retyped,
        unchanged=not (added or removed or retyped),
    )


async def _read_within_limit(upload: UploadFile) -> bytes:
    """Read a file, giving up the moment it exceeds the limit.

    Read in chunks rather than checking Content-Length: the header is a claim by
    the client, and buffering 2 GB to discover it lied is exactly what the limit
    exists to prevent.
    """
    limit = get_settings().max_upload_bytes
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(CHUNK_BYTES):
        total += len(chunk)
        if total > limit:
            raise PayloadTooLargeError(
                f"{upload.filename} is larger than the "
                f"{limit // (1024 * 1024)} MB limit."
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _collect(files: list[UploadFile]) -> dict[str, bytes]:
    if not files:
        raise UnprocessableError("Choose at least one CSV file.")

    collected: dict[str, bytes] = {}
    for upload in files:
        name = upload.filename or ""
        if not name.lower().endswith(".csv"):
            raise UnprocessableError(f"{name or 'That file'} is not a .csv file.")
        collected[name] = await _read_within_limit(upload)
    return collected


@router.post("/upload")
async def analyse(
    project: OwnedProject,
    session: SessionDep,
    files: Annotated[list[UploadFile], File()],
) -> UploadAnalysis:
    """Infer a schema and hand it back for review. Creates nothing.

    Re-uploading a file replaces its table, so the proposal carries what that
    would change. The comparison is read through the app's own catalog access
    rather than the project's read-only role, exactly like the schema explorer.
    """
    collected = await _collect(files)
    existing = {
        table.name: table
        for table in await describe_schema(session, project.schema_name)
    }

    proposals: list[TableProposal] = []
    for filename, data in collected.items():
        try:
            inferred = infer_table(filename, data)
        except ValueError as error:
            raise UnprocessableError(str(error)) from error
        proposal = TableProposal(
            name=inferred.name,
            source_filename=inferred.source_filename,
            sampled_rows=inferred.sampled_rows,
            columns=[
                ColumnProposal(
                    name=column.name,
                    source_name=column.source_name,
                    type=column.type,
                    nullable=column.nullable,
                    samples=list(column.samples),
                )
                for column in inferred.columns
            ],
        )
        proposal.diff = _diff(proposal, existing.get(proposal.name))
        proposals.append(proposal)
    return UploadAnalysis(tables=proposals)


@router.post("/upload/commit")
async def commit(
    project: OwnedProject,
    session: SessionDep,
    files: Annotated[list[UploadFile], File()],
    spec: Annotated[str, Form()],
) -> UploadResult:
    """Build the reviewed schema and load the data into it."""
    collected = await _collect(files)
    try:
        parsed = UploadCommit.model_validate(json.loads(spec))
    except (json.JSONDecodeError, ValidationError) as error:
        raise UnprocessableError(f"The schema you sent could not be read: {error}") from error

    committed = await commit_upload(
        session, project, [table.to_spec() for table in parsed.tables], collected
    )
    await session.commit()

    return UploadResult(
        schema_name=project.schema_name or "",
        table_count=project.table_count or 0,
        tables=[
            CommittedTableResponse(name=table.name, row_count=table.row_count)
            for table in committed
        ],
    )
