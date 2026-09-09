# DBPilot Phase 3 — Data In Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user uploads CSV files to a project, corrects the inferred schema, commits it into a private PostgreSQL schema guarded by a per-project read-only role, and browses the result in a schema explorer with a data preview.

**Architecture:** Inference and identifier normalisation are pure functions with no I/O, so the type ladder and the reserved-word rules test without a database. Everything that touches PostgreSQL goes through one raw-connection helper, because DDL and `COPY` need psycopg's `sql` composition — identifiers derived from CSV headers can never be interpolated as text. Provisioning, ingestion and deletion each run inside the caller's transaction, so a half-built schema is impossible and integration tests roll back. Query-shaped reads (the preview) take a *separate* pooled connection so `SET LOCAL ROLE` cannot leak into the metadata session.

**Tech Stack:** psycopg 3 (`psycopg.sql` composition, async `COPY`), SQLAlchemy 2.x async, FastAPI multipart uploads, Python `csv` + `decimal` + `datetime`, React 19 + TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-06-dbpilot-design.md` (§6 layers 3–4, §7, §8, §16)

**Predecessor:** `docs/superpowers/plans/2026-09-06-phase-2-identity.md` (tag `phase-2`)

## Global Constraints

- Python runtime is **3.11.9** (`backend/.venv/Scripts/python`). Never the machine default 3.14.
- Run the server with `python run.py`, never `uvicorn app.main:app`.
- A resource the caller does not own returns **404, never 403** (design §6 layer 1).
- **No identifier derived from user input is ever formatted into SQL as text.** Every table, column, schema and role name goes through `psycopg.sql.Identifier`. This is the single most important rule in the phase.
- Layer 3 uses **`SET TRANSACTION READ ONLY`**, never `SET LOCAL default_transaction_read_only` — the latter does not constrain the open transaction (design §6, corrected 2026-09-09).
- Uploads are **≤ 25 MB per file** (`settings.max_upload_bytes`), enforced while streaming, not after buffering.
- Application metadata stays in schema **`dbpilot`**. Uploaded data goes in **`user_<user_id>_<slug>`** and nowhere else.
- Design tokens are exactly PRD §10.2. No component writes a raw hex value. Accent budget: three lime elements per viewport. `--text-tertiary` never for running copy.
- `alembic check` must report no drift at the end of every task touching a model.
- Every commit message ends with the attribution lines shown in Task 1, Step 5.

---

## File Structure

**Backend**

| File | Responsibility |
|---|---|
| `app/services/identifiers.py` | Normalise CSV headers/filenames to safe PostgreSQL identifiers. Pure. |
| `app/services/inference.py` | CSV sampling, the type ladder, and value coercion. Pure. |
| `app/db/raw.py` | Reach psycopg from a SQLAlchemy connection; execute composed SQL. |
| `app/db/readonly.py` | Layer 3: a separate pooled connection that is role-scoped and always rolls back. |
| `app/services/provisioning.py` | Layer 4: create/drop the project schema, role and grants. |
| `app/services/ingestion.py` | Create tables, `COPY` rows in, record `uploads`, refresh `table_count`. |
| `app/services/introspection.py` | Read `information_schema` as `dbpilot_app`; tables, columns, FKs, indexes, counts. |
| `app/schemas/upload.py` | Analyse/commit request and response bodies. |
| `app/schemas/schema.py` | Schema-explorer and preview response bodies. |
| `app/api/uploads.py` | `POST /projects/{id}/upload`, `POST /projects/{id}/upload/commit` |
| `app/api/schema.py` | `GET /projects/{id}/schema`, `GET /projects/{id}/tables/{t}/preview` |

**Frontend**

| File | Responsibility |
|---|---|
| `src/lib/api.ts` | *Modify:* do not set `Content-Type` for `FormData`; add `apiUpload`. |
| `src/components/Select.tsx` | Token-styled `<select>` primitive. |
| `src/components/Badge.tsx` | PK/FK pills — lime outline for PK (PRD §10.9). |
| `src/features/upload/UploadPanel.tsx` | Pick files, analyse, hold the proposal. |
| `src/features/upload/SchemaReview.tsx` | Correct types, nominate PK, declare FKs, commit. |
| `src/features/schema/SchemaExplorer.tsx` | Rail + detail table (PRD §10.9: no cards). |
| `src/features/schema/TablePreview.tsx` | First 100 rows, paginated, sortable. |
| `src/routes/ProjectDetail.tsx` | `/projects/:id` — hosts upload or explorer. |
| `src/App.tsx` | *Modify:* add the `/projects/:id` route. |
| `src/routes/Projects.tsx` | *Modify:* link each row to its detail page. |

No migration is required: `projects.schema_name`, `projects.readonly_role`, `projects.table_count` and the `uploads` table all exist from `0001_initial`.

---

## Task 1: Identifier normalisation

**Files:**
- Create: `backend/app/services/identifiers.py`
- Test: `backend/tests/test_identifiers.py`

**Interfaces:**
- Produces: `normalise(name: str) -> str`, `unique_names(names: Sequence[str]) -> list[str]`, `schema_name_for(user_id: int, project_name: str) -> str`, `role_name_for(project_id: int) -> str`, `MAX_IDENTIFIER_BYTES = 63`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from app.services.identifiers import (
    MAX_IDENTIFIER_BYTES, normalise, role_name_for, schema_name_for, unique_names,
)

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Order ID", "order_id"),
        ("  Total (USD)  ", "total_usd"),
        ("2024 revenue", "col_2024_revenue"),   # cannot start with a digit
        ("", "column"),                          # a blank header still needs a name
        ("Customer-Name", "customer_name"),
        ("select", "select_col"),                # reserved word
        ("ÉLÈVE", "eleve"),                      # accents fold to ASCII
        ("a" * 100, "a" * MAX_IDENTIFIER_BYTES),
    ],
)
def test_normalise(raw: str, expected: str) -> None:
    assert normalise(raw) == expected

def test_unique_names_disambiguates_collisions() -> None:
    assert unique_names(["Name", "name", "NAME"]) == ["name", "name_2", "name_3"]

def test_schema_name_is_scoped_to_the_user() -> None:
    assert schema_name_for(7, "Q3 Sales!") == "user_7_q3_sales"

def test_schema_name_stays_within_the_identifier_limit() -> None:
    assert len(schema_name_for(7, "x" * 200)) <= MAX_IDENTIFIER_BYTES

def test_role_name_is_derived_from_the_project_id() -> None:
    assert role_name_for(42) == "ro_p42"
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_identifiers.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'app.services.identifiers'`

- [ ] **Step 3: Implement**

```python
"""Turn arbitrary user text into a safe PostgreSQL identifier.

Identifiers cannot be bound as parameters, so every one of them is composed
through psycopg.sql.Identifier at the call site. This module exists so the
*names themselves* are also predictable and readable: lower snake case, ASCII,
never a reserved word, never longer than PostgreSQL will keep.
"""

import re
import unicodedata
from collections.abc import Sequence

MAX_IDENTIFIER_BYTES = 63

# The reserved words a CSV header realistically collides with. Quoting makes any
# of these legal, but a column literally called "select" makes every hand-written
# query awkward, so they get a suffix instead.
_RESERVED = frozenset({
    "all", "analyse", "analyze", "and", "any", "array", "as", "asc", "authorization",
    "between", "both", "case", "cast", "check", "collate", "column", "constraint",
    "create", "cross", "current_date", "current_role", "current_time",
    "current_timestamp", "current_user", "default", "deferrable", "desc", "distinct",
    "do", "else", "end", "except", "false", "for", "foreign", "from", "full", "grant",
    "group", "having", "in", "initially", "inner", "intersect", "into", "is", "join",
    "leading", "left", "like", "limit", "localtime", "localtimestamp", "natural",
    "not", "null", "offset", "on", "only", "or", "order", "outer", "overlaps",
    "placing", "primary", "references", "returning", "right", "select", "session_user",
    "similar", "some", "table", "then", "to", "trailing", "true", "union", "unique",
    "user", "using", "verbose", "when", "where", "window", "with",
})


def normalise(name: str) -> str:
    """Fold `name` into a legal, readable, lower-snake-case identifier."""
    folded = unicodedata.normalize("NFKD", name)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^0-9a-zA-Z]+", "_", ascii_only).strip("_").lower()

    if not cleaned:
        return "column"
    if cleaned[0].isdigit():
        cleaned = f"col_{cleaned}"
    if cleaned in _RESERVED:
        cleaned = f"{cleaned}_col"
    return cleaned[:MAX_IDENTIFIER_BYTES]


def unique_names(names: Sequence[str]) -> list[str]:
    """Normalise a header row, disambiguating names that collide after folding."""
    seen: dict[str, int] = {}
    result: list[str] = []
    for name in names:
        base = normalise(name)
        seen[base] = seen.get(base, 0) + 1
        if seen[base] == 1:
            result.append(base)
        else:
            suffix = f"_{seen[base]}"
            result.append(f"{base[: MAX_IDENTIFIER_BYTES - len(suffix)]}{suffix}")
    return result


def schema_name_for(user_id: int, project_name: str) -> str:
    """`user_<id>_<slug>` — the owner is in the name, so a stray query is obvious."""
    prefix = f"user_{user_id}_"
    slug = normalise(project_name)
    return f"{prefix}{slug[: MAX_IDENTIFIER_BYTES - len(prefix)]}"


def role_name_for(project_id: int) -> str:
    """The read-only role for one project. Design document §6, layer 4."""
    return f"ro_p{project_id}"
```

- [ ] **Step 4: Run it and confirm it passes**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_identifiers.py -q`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/identifiers.py backend/tests/test_identifiers.py
git commit -m "$(cat <<'EOF'
feat(ingest): normalise user text into safe PostgreSQL identifiers

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Sm3ukp6nBQHdqjT3TugY44
EOF
)"
```

---

## Task 2: CSV type inference and coercion

**Files:**
- Create: `backend/app/services/inference.py`
- Test: `backend/tests/test_inference.py`

**Interfaces:**
- Consumes: `app.services.identifiers.unique_names`
- Produces: `ColumnType` (StrEnum: `integer`, `numeric`, `boolean`, `date`, `timestamp`, `text`), frozen `InferredColumn(name, source_name, type, nullable, samples)`, frozen `InferredTable(name, source_filename, columns, sampled_rows)`, `infer_table(filename: str, data: bytes) -> InferredTable`, `coerce(value: str, column_type: ColumnType) -> object | None`, `iter_rows(data: bytes, types: Sequence[ColumnType]) -> Iterator[tuple[object | None, ...]]`, `SAMPLE_ROWS = 1000`

- [ ] **Step 1: Write the failing test**

```python
from datetime import date, datetime
from decimal import Decimal

import pytest
from app.services.inference import ColumnType, coerce, infer_table, iter_rows


def csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def test_infers_the_type_ladder_in_order() -> None:
    table = infer_table(
        "sales.csv",
        csv_bytes(
            "Order ID,Amount,Shipped,Order Date,Created At,Notes\n"
            "1,10.50,true,2024-01-15,2024-01-15 09:30:00,hello\n"
            "2,11.25,false,2024-02-20,2024-02-20 11:00:00,world\n"
        ),
    )
    assert [c.type for c in table.columns] == [
        ColumnType.integer, ColumnType.numeric, ColumnType.boolean,
        ColumnType.date, ColumnType.timestamp, ColumnType.text,
    ]


def test_names_come_from_the_identifier_rules() -> None:
    table = infer_table("Q3 Sales.csv", csv_bytes("Order ID\n1\n"))
    assert table.name == "q3_sales"
    assert table.columns[0].name == "order_id"
    assert table.columns[0].source_name == "Order ID"


def test_a_zero_one_column_is_an_integer_not_a_boolean() -> None:
    # The ladder checks integer first on purpose: 1/0 is more useful as a number.
    table = infer_table("f.csv", csv_bytes("flag\n1\n0\n"))
    assert table.columns[0].type is ColumnType.integer


def test_one_bad_cell_demotes_the_whole_column_to_text() -> None:
    table = infer_table("f.csv", csv_bytes("n\n1\n2\nnot a number\n"))
    assert table.columns[0].type is ColumnType.text


def test_an_empty_cell_makes_the_column_nullable_without_changing_its_type() -> None:
    table = infer_table("f.csv", csv_bytes("n\n1\n\n3\n"))
    assert table.columns[0].type is ColumnType.integer
    assert table.columns[0].nullable is True


def test_a_column_with_no_empty_cells_is_not_nullable() -> None:
    table = infer_table("f.csv", csv_bytes("n\n1\n2\n"))
    assert table.columns[0].nullable is False


def test_an_all_empty_column_is_nullable_text() -> None:
    table = infer_table("f.csv", csv_bytes("a,b\n1,\n2,\n"))
    assert table.columns[1].type is ColumnType.text
    assert table.columns[1].nullable is True


def test_a_utf8_bom_is_not_part_of_the_first_header() -> None:
    table = infer_table("f.csv", b"\xef\xbb\xbfname\nada\n")
    assert table.columns[0].name == "name"


def test_a_file_with_no_data_rows_still_yields_its_columns() -> None:
    table = infer_table("f.csv", csv_bytes("a,b\n"))
    assert [c.name for c in table.columns] == ["a", "b"]
    assert table.sampled_rows == 0


def test_a_file_with_no_header_is_rejected() -> None:
    with pytest.raises(ValueError, match="no columns"):
        infer_table("f.csv", b"")


@pytest.mark.parametrize(
    ("raw", "column_type", "expected"),
    [
        ("42", ColumnType.integer, 42),
        ("10.50", ColumnType.numeric, Decimal("10.50")),
        ("yes", ColumnType.boolean, True),
        ("f", ColumnType.boolean, False),
        ("2024-01-15", ColumnType.date, date(2024, 1, 15)),
        ("2024-01-15 09:30:00", ColumnType.timestamp, datetime(2024, 1, 15, 9, 30)),
        ("hello", ColumnType.text, "hello"),
        ("", ColumnType.integer, None),
        ("   ", ColumnType.text, None),
    ],
)
def test_coerce(raw: str, column_type: ColumnType, expected: object) -> None:
    assert coerce(raw, column_type) == expected


def test_iter_rows_yields_python_values_not_strings() -> None:
    rows = list(iter_rows(csv_bytes("a,b\n1,x\n2,\n"), [ColumnType.integer, ColumnType.text]))
    assert rows == [(1, "x"), (2, None)]


def test_iter_rows_pads_a_short_row_rather_than_failing() -> None:
    rows = list(iter_rows(csv_bytes("a,b\n1\n"), [ColumnType.integer, ColumnType.text]))
    assert rows == [(1, None)]


def test_iter_rows_drops_cells_beyond_the_declared_columns() -> None:
    rows = list(iter_rows(csv_bytes("a\n1,extra\n"), [ColumnType.integer]))
    assert rows == [(1,)]
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_inference.py -q`
Expected: `ModuleNotFoundError: No module named 'app.services.inference'`

- [ ] **Step 3: Implement**

Write `app/services/inference.py` to satisfy every assertion above. Required shape:

```python
"""CSV sampling and the type ladder. Pure — no database, no filesystem."""

import csv
import enum
import io
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath

from app.services.identifiers import normalise, unique_names

SAMPLE_ROWS = 1000
SAMPLE_VALUES = 3          # what the review screen shows per column
_TRUE = frozenset({"true", "t", "yes", "y", "1"})
_FALSE = frozenset({"false", "f", "no", "n", "0"})


class ColumnType(enum.StrEnum):
    integer = "integer"
    numeric = "numeric"
    boolean = "boolean"
    date = "date"
    timestamp = "timestamp"
    text = "text"


# Design document §7: first match wins, checked in this order.
LADDER = (
    ColumnType.integer, ColumnType.numeric, ColumnType.boolean,
    ColumnType.date, ColumnType.timestamp,
)
```

Implementation notes that the tests pin down:

- `_decode(data)` tries `utf-8-sig` then falls back to `latin-1`, so a Windows-exported CSV never explodes.
- `_matches(value, column_type)` returns a bool; `coerce` returns the Python value or `None`. Both treat a whitespace-only cell as absent.
- `integer` must reject `"1.0"` and anything outside `bigint` range; `numeric` accepts what `Decimal` accepts but rejects `nan`/`inf`.
- `date` uses `date.fromisoformat`; `timestamp` uses `datetime.fromisoformat` after replacing a `T` separator with a space is *not* needed — `fromisoformat` handles both in 3.11.
- A column whose sampled cells are all empty infers as nullable `text`.
- `infer_table` derives the table name from `PurePosixPath(filename).stem` through `normalise`, and the column names through `unique_names`.
- `iter_rows` pads short rows with `None` and truncates long ones, so one ragged line cannot abort a 100k-row import.

- [ ] **Step 4: Run it and confirm it passes**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_inference.py -q`
Expected: 24 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/inference.py backend/tests/test_inference.py
git commit -m "feat(ingest): infer CSV column types by sampling
...attribution..."
```

---

## Task 3: The analyse endpoint

**Files:**
- Create: `backend/app/schemas/upload.py`, `backend/app/api/uploads.py`
- Modify: `backend/app/main.py` (register the router)
- Test: `backend/tests/test_uploads_api.py`

**Interfaces:**
- Consumes: `infer_table`, `OwnedProject`, `settings.max_upload_bytes`
- Produces: `POST /projects/{id}/upload` → `UploadAnalysis{tables: [TableProposal]}`; `read_upload(file: UploadFile, limit: int) -> bytes` raising `PayloadTooLargeError`

- [ ] **Step 1: Write the failing test**

```python
async def test_analysis_returns_a_proposal_without_creating_anything(
    client, auth_headers, project
):
    response = await client.post(
        f"/projects/{project['id']}/upload",
        headers=auth_headers,
        files={"files": ("sales.csv", b"Order ID,Amount\n1,10.50\n", "text/csv")},
    )
    assert response.status_code == 200
    table = response.json()["tables"][0]
    assert table["name"] == "sales"
    assert [c["name"] for c in table["columns"]] == ["order_id", "amount"]
    assert [c["type"] for c in table["columns"]] == ["integer", "numeric"]


async def test_analysis_does_not_create_a_schema(client, auth_headers, project, session):
    await client.post(...)  # as above
    row = await session.scalar(text(
        "SELECT count(*) FROM information_schema.schemata WHERE schema_name LIKE 'user_%'"
    ))
    assert row == 0


async def test_a_file_over_the_limit_is_refused(client, auth_headers, project, monkeypatch):
    # 413 with the limit named, not a truncated import.
    ...


async def test_another_users_project_is_a_404(client, other_headers, project): ...
async def test_a_non_csv_extension_is_refused(client, auth_headers, project): ...
async def test_an_empty_file_names_the_file_that_failed(client, auth_headers, project): ...
```

Add to `backend/tests/conftest.py` the fixtures these need: `auth_headers` (register + login, returns the bearer header), `other_headers` (a second user), `project` (a created project dict).

- [ ] **Step 2: Run and confirm it fails** — `404 Not Found` for the upload route.

- [ ] **Step 3: Implement**

`app/schemas/upload.py`:

```python
class ColumnProposal(BaseModel):
    name: str
    source_name: str
    type: ColumnType
    nullable: bool
    samples: list[str]

class TableProposal(BaseModel):
    name: str
    source_filename: str
    sampled_rows: int
    columns: list[ColumnProposal]

class UploadAnalysis(BaseModel):
    tables: list[TableProposal]
```

`app/api/uploads.py` streams each `UploadFile` in 64 KiB chunks, aborting the moment the running total passes `settings.max_upload_bytes`, and raises a new `PayloadTooLargeError` (413) added to `app/core/errors.py`. Reject any filename whose suffix is not `.csv`.

- [ ] **Step 4: Run and confirm it passes.**
- [ ] **Step 5: Commit.**

---

## Task 4: Raw-connection helpers and provisioning (safety layer 4)

**Files:**
- Create: `backend/app/db/raw.py`, `backend/app/services/provisioning.py`
- Test: `backend/tests/test_provisioning.py`

**Interfaces:**
- Produces: `raw.driver_of(connection) -> psycopg.AsyncConnection`, `raw.execute(connection, statement: Composable) -> None`, `raw.fetch_all(connection, statement, params=None) -> list[tuple]`; `provisioning.provision(session, project) -> tuple[str, str]` returning `(schema_name, role_name)`, `provisioning.deprovision(session, project) -> None`

- [ ] **Step 1: Write the failing test**

```python
async def test_provision_creates_the_schema_and_role(session, user, project):
    schema, role = await provision(session, project)
    assert schema == f"user_{user.id}_sales"
    assert role == f"ro_p{project.id}"
    assert await _exists(session, "information_schema.schemata", "schema_name", schema)
    assert await _exists(session, "pg_roles", "rolname", role)


async def test_provision_is_idempotent(session, project):
    first = await provision(session, project)
    assert await provision(session, project) == first


async def test_provision_records_both_names_on_the_project(session, project):
    schema, role = await provision(session, project)
    assert project.schema_name == schema
    assert project.readonly_role == role


async def test_the_role_can_read_the_schema_and_nothing_else(session, project): ...
async def test_deprovision_removes_the_schema_and_the_role(session, project): ...
async def test_deprovision_on_a_project_that_was_never_provisioned_is_a_no_op(session, project): ...
async def test_a_project_name_that_needs_quoting_is_still_safe(session, user):
    # A project literally called `sales"; DROP SCHEMA public; --`
    ...
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement**

`app/db/raw.py` — the one place that reaches psycopg:

```python
"""Reach psycopg from SQLAlchemy, for the two jobs SQLAlchemy cannot do:
composing DDL from user-derived identifiers, and COPY."""

from typing import cast

import psycopg
from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncConnection


async def driver_of(connection: AsyncConnection) -> psycopg.AsyncConnection:
    raw = await connection.get_raw_connection()
    return cast(psycopg.AsyncConnection, raw.driver_connection)


async def execute(connection: AsyncConnection, statement: sql.Composable) -> None:
    driver = await driver_of(connection)
    await driver.execute(statement)
```

`app/services/provisioning.py` composes exactly the statements in design §6 layer 4, every name through `sql.Identifier`:

```python
CREATE SCHEMA IF NOT EXISTS {schema}
CREATE ROLE {role} NOLOGIN                     -- guarded by a pg_roles lookup
GRANT USAGE ON SCHEMA {schema} TO {role}
GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {role}
ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO {role}
GRANT {role} TO CURRENT_USER                   -- so the app may SET ROLE to it
```

and `deprovision` runs, in this order and in one transaction:

```python
DROP SCHEMA IF EXISTS {schema} CASCADE
DROP OWNED BY {role}      -- removes grants and default privileges elsewhere
DROP ROLE IF EXISTS {role}
```

`DROP OWNED BY` is not optional: `ALTER DEFAULT PRIVILEGES` leaves catalog entries that outlive the schema and would block `DROP ROLE`. This is the leak flagged in design §16.

- [ ] **Step 4: Run and confirm it passes.**
- [ ] **Step 5: Commit.**

---

## Task 5: Ingestion — tables, COPY, uploads rows

**Files:**
- Create: `backend/app/services/ingestion.py`
- Test: `backend/tests/test_ingestion.py`

**Interfaces:**
- Consumes: `provisioning.provision`, `inference.iter_rows`, `raw.execute`
- Produces: frozen `ColumnSpec(name, source_name, type, nullable)`, `ForeignKeySpec(column, references_table, references_column)`, `TableSpec(name, source_filename, columns, primary_key, foreign_keys)`, `CommittedTable(name, row_count)`, `commit_upload(session, project, specs: Sequence[TableSpec], files: Mapping[str, bytes]) -> list[CommittedTable]`

- [ ] **Step 1: Write the failing test**

```python
async def test_commit_creates_the_table_and_copies_every_row(session, project): ...
async def test_a_nominated_primary_key_becomes_the_constraint(session, project): ...
async def test_no_nominated_key_generates_a_surrogate_id(session, project): ...
async def test_a_declared_foreign_key_is_created(session, project): ...
async def test_a_foreign_key_to_a_table_not_in_the_batch_is_refused(session, project): ...
async def test_a_failure_part_way_leaves_no_tables_behind(session, project):
    # Two tables; the second references a column that does not exist.
    # Design §7: commit is transactional.
async def test_table_count_is_refreshed_on_the_project(session, project): ...
async def test_an_uploads_row_records_the_filename_and_size(session, project): ...
async def test_a_header_that_looks_like_sql_is_stored_as_a_column_name(session, project):
    # Header: `x"); DROP TABLE users; --`  →  a column, not an incident.
async def test_committing_twice_replaces_the_table(session, project): ...
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement**

`commit_upload` runs entirely inside the caller's transaction:

1. `provision(session, project)`.
2. Validate: every `TableSpec.name` unique; every FK target inside the batch; every FK column present; `primary_key`, when given, names a real column *and* that column is not nullable.
3. For each table, `DROP TABLE IF EXISTS {schema}.{table}` then `CREATE TABLE`, composed with `sql.Identifier` per name and `sql.SQL` per type keyword from a fixed `_PG_TYPE` map (`integer→BIGINT`, `numeric→NUMERIC`, `boolean→BOOLEAN`, `date→DATE`, `timestamp→TIMESTAMP`, `text→TEXT`). A surrogate key is `id BIGSERIAL PRIMARY KEY`.
4. `COPY {schema}.{table} ({cols}) FROM STDIN` and `await copy.write_row(row)` for each row from `iter_rows`. psycopg adapts and escapes each Python value, so no cell content can break out.
5. `ALTER TABLE ... ADD FOREIGN KEY` for every declared FK, after all tables exist.
6. `ANALYZE` each table so the explorer's planner estimates are sane.
7. Re-run the grants from Task 4 — `GRANT SELECT ON ALL TABLES` only covers tables that existed when it ran.
8. Insert one `Upload` row per file; set `project.table_count`.

- [ ] **Step 4: Run and confirm it passes.**
- [ ] **Step 5: Commit.**

---

## Task 6: The commit endpoint

**Files:**
- Modify: `backend/app/api/uploads.py`, `backend/app/schemas/upload.py`
- Test: `backend/tests/test_uploads_api.py`

`POST /projects/{id}/upload/commit` is multipart: the same `files`, plus a `spec` form field carrying JSON that parses into `UploadCommit{tables: [TableSpecIn]}`.

The client re-sends the files rather than the server stashing them between the two calls. That trade is deliberate: a stash needs a temp store, a key, an expiry and a cleanup job, and the design (§2) rules out a scheduler. Re-reading a ≤25 MB file is cheaper than all of that.

- [ ] Tests: a full round trip (analyse → correct a type → commit → the column really is `TEXT`); a `spec` naming a file that was not uploaded is a 422 that says which; another user's project is 404; committing sets `schema_name`, `readonly_role` and `table_count` on the project row.
- [ ] Implement, run, commit.

---

## Task 7: Deleting a project drops its schema, grants and role

**Files:**
- Modify: `backend/app/services/projects.py` (`delete_project`)
- Test: `backend/tests/test_projects_api.py`

This is the risk design §16 carries forward.

- [ ] **Step 1: Write the failing test**

```python
async def test_deleting_a_project_drops_its_schema(session, project_with_data): ...
async def test_deleting_a_project_drops_its_readonly_role(session, project_with_data):
    # Without this, roles accumulate in the cluster forever.
async def test_deleting_a_project_leaves_another_projects_schema_alone(session): ...
async def test_deleting_a_never_provisioned_project_still_works(session, project): ...
```

- [ ] **Step 2: Run and confirm the role test fails** (the role survives).
- [ ] **Step 3:** `delete_project` calls `deprovision(session, project)` before `session.delete(project)`, in the same transaction. Replace the "Phase 3 extends this" docstring with what it now does.
- [ ] **Step 4: Run and confirm it passes.**
- [ ] **Step 5: Commit.**

---

## Task 8: Introspection and the schema endpoint

**Files:**
- Create: `backend/app/services/introspection.py`, `backend/app/schemas/schema.py`, `backend/app/api/schema.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_introspection.py`, `backend/tests/test_schema_api.py`

**Interfaces:**
- Produces: `describe_schema(session, schema_name) -> list[TableDescription]` where `TableDescription(name, row_count, columns, indexes)`, `ColumnDescription(name, data_type, nullable, default, is_primary_key, references)`, `IndexDescription(name, definition)`; `GET /projects/{id}/schema -> ProjectSchema`

Introspection reads `information_schema` and `pg_catalog` **as `dbpilot_app`** (design §8) — this is our own query, never the user's, which is why the gate can later forbid catalog access from user SQL without breaking the explorer.

Row counts are exact `count(*)`, gathered in one round trip via a composed `UNION ALL`, because uploads are ≤25 MB and `reltuples` is `-1` until the first `ANALYZE`.

- [ ] Tests: columns come back in ordinal order with correct types and nullability; the primary key is flagged; a foreign key reports `table.column`; indexes are listed; row counts are exact; a project with no schema yet returns `{schema_name: null, tables: []}` rather than an error; another user's project is 404.
- [ ] Implement, run, commit.

---

## Task 9: The read-only connection and the preview endpoint

**Files:**
- Create: `backend/app/db/readonly.py`
- Modify: `backend/app/api/schema.py`, `backend/app/schemas/schema.py`
- Test: `backend/tests/test_readonly.py`, `backend/tests/test_schema_api.py`

**Interfaces:**
- Produces: `readonly_connection(project) -> AsyncIterator[AsyncConnection]` (async context manager); `GET /projects/{id}/tables/{table}/preview?limit&offset&sort&direction -> TablePreview{columns, rows, total}`

This is safety layer 3, arriving one phase early because the preview is the first thing that runs a query against user data.

```python
@asynccontextmanager
async def readonly_connection(project: Project) -> AsyncIterator[AsyncConnection]:
    """A connection that cannot write, scoped to one project's role.

    Deliberately NOT the request's metadata session: `SET LOCAL ROLE` lasts for
    the whole transaction, so sharing one would leave the rest of the request
    running as the read-only role. This borrows its own connection from the same
    pool and always rolls back.
    """
    async with get_engine().connect() as connection:
        transaction = await connection.begin()
        try:
            await raw.execute(connection, sql.SQL("SET LOCAL ROLE {}").format(
                sql.Identifier(project.readonly_role)))
            # SET TRANSACTION READ ONLY, not default_transaction_read_only —
            # the latter does not constrain the transaction already open.
            await raw.execute(connection, sql.SQL("SET TRANSACTION READ ONLY"))
            await raw.execute(connection, sql.SQL("SET LOCAL statement_timeout = {}").format(
                sql.Literal(f"{get_settings().statement_timeout_seconds}s")))
            await raw.execute(connection, sql.SQL("SET LOCAL search_path = {}").format(
                sql.Identifier(project.schema_name)))
            yield connection
        finally:
            await transaction.rollback()
```

The preview names its table and sort column from **an allowlist built by introspection**, never from the query string directly. `limit` is clamped to 100 (PRD F3), `offset` to ≥ 0, `direction` to `asc`/`desc`.

- [ ] Tests: `test_readonly.py` proves an `INSERT` on the read-only connection raises, that a query against *another* project's schema raises `InsufficientPrivilege`, and that the outer session's `current_user` is unaffected afterwards. `test_schema_api.py` covers pagination, sorting, an unknown table → 404, an unknown sort column → 422, and `limit=999` clamping to 100.
- [ ] These need committed data, so add a `provisioned_project` fixture that commits and tears down explicitly — a rolled-back transaction is invisible to a second connection.
- [ ] Implement, run, commit.

---

## Task 10: Cross-user isolation, proved

**Files:**
- Create: `backend/tests/test_isolation_roles.py`

The PRD §12 claim is "no cross-user reads at any layer". Task 9 tests the mechanism; this task tests the claim.

- [ ] Two users, two projects, two schemas, each with a table holding a distinguishable row.
- [ ] Assert user A's role cannot read user B's table **by fully-qualified name** — `permission denied for schema`, not an empty result.
- [ ] Assert the API returns 404 (not 403, not 200) for every Phase 3 route when the caller does not own the project: upload, commit, schema, preview.
- [ ] Assert a project's role holds no privilege on the `dbpilot` metadata schema — a read of `dbpilot.users` from the role fails.
- [ ] Run, commit.

---

## Task 11: Frontend — upload and review

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/components/Select.tsx`, `frontend/src/features/upload/UploadPanel.tsx`, `frontend/src/features/upload/SchemaReview.tsx`
- Test: `frontend/src/features/upload/__tests__/SchemaReview.test.tsx`, `frontend/src/lib/__tests__/api.test.ts`

The first change is a bug fix. `request()` sets `Content-Type: application/json` whenever a body is present; with `FormData` that overrides the browser's own multipart boundary and the server sees a malformed body. Skip the header when the body is `FormData`.

```typescript
if (
  !headers.has('Content-Type') &&
  options.body !== undefined &&
  !(options.body instanceof FormData)
) {
  headers.set('Content-Type', 'application/json')
}
```

- [ ] Test that fix first: `apiFetch` with a `FormData` body sets no `Content-Type`; with a JSON string it still does.
- [ ] `UploadPanel` accepts `.csv` files, calls the analyse endpoint, and holds both the proposal and the original `File` objects (the commit re-sends them).
- [ ] `SchemaReview` renders one row per column with a type `<select>`, a primary-key radio group per table including an "Add an `id` column" option, and a foreign-key picker restricted to tables in the same batch. Tests: changing a type sends the changed type; the PK radio sends `primary_key`; a nullable column cannot be chosen as the primary key; the commit button is disabled while a request is in flight.
- [ ] Run `npm test`, commit.

---

## Task 12: Frontend — schema explorer, preview, routing

**Files:**
- Create: `frontend/src/components/Badge.tsx`, `frontend/src/features/schema/SchemaExplorer.tsx`, `frontend/src/features/schema/TablePreview.tsx`, `frontend/src/routes/ProjectDetail.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/routes/Projects.tsx`
- Test: `frontend/src/features/schema/__tests__/SchemaExplorer.test.tsx`, `frontend/src/routes/__tests__/ProjectDetail.test.tsx`

PRD §10.9 for this screen: **rail + detail table, no cards**, distinguished from the workspace by layout rather than colour, with **PK badges as lime outline pills**. That is the whole accent budget for the screen — the rail selection uses a border, not lime fill.

- [ ] `SchemaExplorer`: 240px rail listing tables with row counts, a search input filtering across table *and* column names (PRD F3), and a detail table of columns with type, nullability, default and PK/FK badges.
- [ ] `TablePreview`: first 100 rows, `Prev`/`Next` paging against `offset`, and a sortable header that sets `sort` and toggles `direction`.
- [ ] `ProjectDetail` at `/projects/:id` shows `UploadPanel` when the project has no schema yet and `SchemaExplorer` once it does — the empty state is an invitation (PRD §10.9): "No data yet. Upload a CSV to get started."
- [ ] `Projects.tsx` links each row to its detail page.
- [ ] Run `npm test`, commit.

---

## Verification before the phase tag

- [ ] `cd backend && ./.venv/Scripts/python -m pytest -q` — all green, and report the count.
- [ ] `./.venv/Scripts/python -m ruff check . && ./.venv/Scripts/python -m mypy app`
- [ ] `./.venv/Scripts/python -m alembic check` — no drift.
- [ ] `cd frontend && npm test -- --run && npm run build`
- [ ] Start `python run.py`, and drive the real browser: create a project, upload a CSV, change one inferred type, commit, and confirm the explorer shows the table with the corrected type and a working preview. The StrictMode refresh race and the uvicorn loop factory were both invisible to the test harness — exercise the real thing.
- [ ] `git tag phase-3 && git push origin main --tags`, then confirm CI is green.

---

## Self-review notes

- **Spec coverage.** PRD F2.1 → Tasks 2, 3, 5, 6, 11. F3 → Tasks 8, 9, 12. Design §6 layer 3 → Task 9; layer 4 → Task 4; §7 ingestion → Tasks 2–6; §8 introspection → Task 8; §16 role leak → Task 7. PRD §7 paths `/upload`, `/schema`, `/tables/{t}/preview` → Tasks 3, 6, 8, 9. F2.2 (external connections) is **not** in this phase — design §15 places it in Phase 6.
- **Deferred deliberately.** The ER diagram (F4) is Phase 5; it reuses `describe_schema` from Task 8 unchanged, which is why introspection returns foreign keys even though nothing in Phase 3 draws them.
- **Type consistency.** `ColumnType` is defined once in `inference.py` and imported by `schemas/upload.py` and `services/ingestion.py`. `schema_name_for`/`role_name_for` are called only by `provisioning.py`. `raw.execute` is the only path from a service to psycopg.
