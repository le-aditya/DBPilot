# DBPilot — Design Document

**Source PRD:** `DBPilot_PRD.md` v1.0 (Aditya Ajay, 24BLC1281)
**Design date:** 2026-09-06
**Status:** Approved for planning

This document records the design decisions the PRD leaves open, and the
architecture the implementation will follow. Where the PRD is already specific
(colour tokens, data model, API surface), this document does not restate it — it
records only what was decided on top.

---

## 1. Scope

Build the full PRD end to end: accounts, CSV ingestion, external PostgreSQL
connections, schema explorer, ER diagram, natural-language-to-SQL, the query
safety gate, explanation and optimisation, dashboard, history, saved queries,
and export.

Non-goals stay exactly as PRD §3: no writes from AI, no cross-connection joins,
no collaboration, PostgreSQL only, no fine-tuning.

## 2. Decisions taken during brainstorming

| Question | Decision | Rationale |
|---|---|---|
| Database host | Local PostgreSQL 18.6, installed natively | No Docker on the machine; a live viva demo must work offline |
| LLM | Google Gemini, key supplied by the user in `backend/.env` | Matches the PRD stack the course submission names |
| Sequencing | Six phases, runnable app at each checkpoint | Limits rework from a misread requirement |
| PRD §14.1 — CSV retention | Uploads persist indefinitely; no expiry job | Course project; avoids a scheduler dependency |
| PRD §14.2 — Saved query parameters | **In scope for v1** | User decision; see §11 |
| PRD §14.3 — Public demo project | **In scope for v1** | PRD calls it a strong yes for the portfolio case |
| Adversarial safety suite | **In scope for v1**, built explicitly | PRD §12 lists zero-writes as a success metric |
| Python runtime | 3.11.9 (verified: venv on `D:` works) | 3.14 is the machine default but lacks wheels for parts of the stack |
| PostgreSQL driver | `psycopg` v3 binary | Better 3.11 wheels than psycopg2, native async |

## 3. Architecture

Three processes and one database cluster:

```
React SPA (Vite dev server / static build)
      |  JSON over HTTP, JWT bearer
FastAPI (uvicorn, async)
      |  SQLAlchemy 2.x async + psycopg3
PostgreSQL 18
      |-- database "dbpilot"
      |     |-- schema "dbpilot"            application metadata (PRD §6)
      |     +-- schema "user_<id>_<proj>"   one per upload project
      +-- (external clusters, per user connection, read-only)
```

The FastAPI process holds **two** database identities:

- `dbpilot_app` — owns metadata, performs DDL, mints roles. Used by every
  endpoint except query execution.
- a per-project read-only role, entered via `SET LOCAL ROLE` on a connection
  borrowed from the same pool. Used **only** to execute user or AI SQL.

Query execution never runs as `dbpilot_app`.

## 4. Repository layout

```
backend/
  app/
    main.py                FastAPI app factory, middleware, exception handlers
    core/                  config, security (JWT/bcrypt), rate limiting, errors
    db/                    engine, session, base, bootstrap DDL helpers
    models/                SQLAlchemy models, one module per aggregate
    schemas/               Pydantic request/response models
    api/                   routers, one per PRD §7 resource group
    services/              ingestion, introspection, execution, safety, export
    ai/                    provider protocol, gemini, fake, prompts, pipeline
  alembic/                 migrations, checked in
  tests/                   unit, integration, adversarial, benchmark
  pyproject.toml           dependencies and tool config
frontend/
  src/
    routes/                page components, one per PRD §10.9 screen
    features/              feature-local components and hooks
    components/            shared primitives built to the design system
    lib/                   api client, query keys, formatters
    styles/                tokens.css, tailwind theme extension
docs/
  superpowers/specs/       this document
  design/                  normalisation write-up, index benchmarks, ERD export
scripts/
  bootstrap.sql            idempotent cluster setup
  seed_demo.py             public demo project data
```

Rule: a module past roughly 300 lines is a signal to split. Services are plain
functions or small classes with dependencies passed in, so they are testable
without a running server.

## 5. Application data model

PRD §6 verbatim, as SQLAlchemy 2.x typed models under Alembic. Three additions,
each a consequence of a decision in this document:

- `saved_queries` gains `sql_template TEXT NOT NULL` and
  `parameters JSONB NOT NULL DEFAULT '[]'` — see §11.
- `projects` gains `is_demo BOOLEAN NOT NULL DEFAULT false` for the public demo
  project, and `table_count INT` (the denormalisation the PRD already names).
- `projects` gains `readonly_role` so role cleanup on delete is explicit rather
  than reconstructed from a naming convention.

Migrations are split deliberately:

1. `0001_initial` — tables, constraints, foreign keys, no performance indexes.
2. `0002_performance_indexes` — the four indexes from PRD §6.

The split exists so the §12 dashboard benchmark can be measured honestly: seed
10k rows into `queries`, time the dashboard query at `0001`, upgrade to `0002`,
time it again, record both in `docs/design/index-benchmarks.md`.

## 6. Security and safety model

Four independent layers, each tested on its own.

**Layer 1 — Ownership.** Every project-scoped endpoint resolves the project
through a dependency that filters by `user_id` from the JWT. A project the
caller does not own returns 404, never 403, so project existence does not leak.

**Layer 2 — The gate.** `app/services/safety.py` exposes one pure function:

```python
def gate(sql: str, *, allow_full_export: bool = False) -> GateResult
```

`GateResult` is either `Allowed(sql)` carrying the rewritten statement, or
`Blocked(rule, detail)`. It performs no I/O, which is what makes the adversarial
suite fast and exhaustive. Checks run in PRD §F7 order:

1. Parse with `sqlglot` (postgres dialect); a parse failure is `Blocked`.
2. Reject more than one statement.
3. Allow only `SELECT` and `WITH ... SELECT`. Everything else — INSERT, UPDATE,
   DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, COPY, CALL, DO — is blocked by
   walking the parsed AST, not by matching strings.
4. Reject any reference to `pg_catalog`, `information_schema`, or a function in
   the `pg_read_file` / `pg_ls_dir` / `lo_import` class. Also reject `dblink`
   and `postgres_fdw`.
5. Inject `LIMIT 1000` when absent and `allow_full_export` is false.
6. Return the rewritten SQL.

`BlockRule` is an enum, so the interface can name the rule that fired —
PRD §9 requires a blocked query to say which rule blocked it.

Layers 3 and 4 live in `app/services/execution.py`:

**Layer 3 — Read-only transaction.**

```sql
BEGIN;
SET LOCAL ROLE ro_p<project_id>;
SET LOCAL default_transaction_read_only = on;
SET LOCAL statement_timeout = '10s';
SET LOCAL search_path = 'user_<id>_<project>';
-- gated statement
ROLLBACK;
```

The transaction always rolls back. A SELECT has nothing to commit, and rollback
makes an accidental write impossible even if every layer above failed.

The `SET LOCAL ROLE` and `search_path` lines apply to managed upload projects.
For an external connection the session is already the user's own role on their
own cluster, so those two lines are omitted and the remaining three still hold.

**Layer 4 — Role privileges.** At project creation:

```sql
CREATE ROLE ro_p42 NOLOGIN;
GRANT USAGE ON SCHEMA user_7_sales TO ro_p42;
GRANT SELECT ON ALL TABLES IN SCHEMA user_7_sales TO ro_p42;
ALTER DEFAULT PRIVILEGES IN SCHEMA user_7_sales
  GRANT SELECT ON TABLES TO ro_p42;
GRANT ro_p42 TO dbpilot_app;
```

`ro_p42` holds no grant on any other schema. A query naming another user's
schema fails on privilege inside PostgreSQL, independent of the parser. This is
the layer that makes PRD §F1 "no cross-user reads at any layer" true rather than
aspirational.

**External connections (PRD §F2.2).** Credentials are encrypted with Fernet
using `DBPILOT_ENCRYPTION_KEY` from the environment, never the repo. On save the
app connects and asserts the supplied role is read-only, by checking
`has_table_privilege` for INSERT/UPDATE/DELETE across the target schema and
`pg_roles.rolsuper`. A role holding write privileges is rejected with an
explanation rather than silently accepted. Execution against an external
connection uses layers 2 and 3; layer 4 is the user's own verified role.

**Prompt injection.** Sample rows sent to the model are truncated to 80
characters per cell, stripped of control characters, and wrapped in a delimited
block the prompt marks as data. This is mitigation, not defence — the gate runs
on model output regardless of what the model was told.

## 7. CSV ingestion

Upload to inferred schema to committed tables, in four steps with the user in
the middle:

1. **Upload.** Multipart, 25 MB per file, enforced before reading the body.
2. **Infer.** Sample the first 1000 rows. Type ladder, first match wins:
   integer, numeric, boolean, date, timestamp, text. A column is nullable if any
   sampled cell is empty. Names normalise to `snake_case` and are checked
   against PostgreSQL reserved words.
3. **Review.** The inferred schema is returned, not committed. The user corrects
   any column type, nominates a primary key or accepts a generated surrogate
   `id`, and declares foreign keys between uploaded tables.
4. **Commit.** Create the schema if new, create tables with confirmed types and
   constraints, `COPY` the data in, create the read-only role and grants, record
   an `uploads` row, refresh `projects.table_count`.

Commit is transactional: a failure part-way leaves no half-built schema.

## 8. Schema explorer and ER diagram

Introspection reads `information_schema` and `pg_catalog` **as `dbpilot_app`**,
in a service the user's SQL can never reach. This is why the gate can block
catalog access from user queries without blocking our own features.

The ERD endpoint returns nodes (tables with columns and badges) and edges
(foreign keys). Cardinality: a foreign key whose referencing column set is
unique is 1:1, otherwise 1:N. A table whose columns are covered entirely by
exactly two foreign keys plus an optional surrogate key is detected as a
junction table and rendered as N:M between its parents.

Layout: dagre computes the initial layout, the user drags nodes, positions
persist to `diagram_layouts.node_positions` on a debounce. PNG export renders
the React Flow viewport to canvas; SVG export serialises it directly.

## 9. Natural language to SQL

`app/ai/provider.py` defines a protocol:

```python
class LLMProvider(Protocol):
    async def generate(self, prompt: str, *, schema: type[T]) -> T: ...
```

Two implementations: `GeminiProvider` using structured JSON output, and
`FakeProvider` returning scripted responses keyed by prompt substring. The
protocol is what lets the pipeline be tested deterministically, and it is the
concrete mitigation for the PRD §13 outage risk — on Gemini failure the API
returns a clear "AI unavailable" error and the SQL editor stays usable.

Pipeline, in `app/ai/pipeline.py`:

1. Build schema context. Below 30 tables include all. Above, score tables by
   keyword overlap with the question, take the top matches, then expand one hop
   along foreign keys so joins stay expressible.
2. Attach three sample rows per included table, sanitised per §6.
3. Prompt with dialect, hard constraints, and the required output shape
   `{sql, assumptions[], confidence, missing}`.
4. Validate every identifier in the returned SQL against the live schema.
5. On validation failure, retry **once** with the specific error appended. A
   second failure returns the model's `missing` explanation, not an invented
   query.
6. Gate, then execute.

Identical `(question, schema_fingerprint)` pairs are cached, addressing the
quota risk. `confidence` and `assumptions` surface as chips in the interface,
never buried.

## 10. Explanation and optimisation

**Explain** asks the model for a clause-by-clause breakdown where each entry
carries `{clause, text, start, end}` character offsets into the SQL. The
frontend uses those offsets to highlight the matching span on hover, as PRD §F6
requires. Offsets are validated server-side against the SQL length and dropped
when wrong, so a bad model response degrades to plain text rather than breaking
the panel.

**Optimize** runs `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` inside the same
read-only transaction, feeds the plan to the model, and returns structured
suggestions. Index candidates render as copyable `CREATE INDEX` statements. The
app never executes them.

## 11. Saved queries with parameters

New scope, decided during brainstorming.

A saved query stores `sql_template` — SQL with `:name` placeholders — and a
`parameters` array of `{name, type, label, default}`. Parameters are extracted
from the template via `sqlglot` placeholder nodes at save time; type defaults to
text and the user can correct it.

At run time the frontend renders one typed input per parameter. The backend
binds values through SQLAlchemy `bindparams`, so values reach PostgreSQL as
**bound parameters, never string interpolation** — a parameter cannot introduce
SQL structure.

The gate runs on the template before binding. Where `sqlglot` cannot parse a
placeholder in a given position, the gate substitutes a type-appropriate literal
sentinel for parsing only; the original template is what gets bound. Every
layer-2 check therefore stays in force for parameterised queries.

## 12. Dashboard, history, export

Dashboard reads are single aggregate queries against `queries`, leaning on the
`(project_id, created_at DESC)` index. `row_count` and `duration_ms` come from
the stored columns rather than recomputation, as PRD §6 specifies.

History is append-only. Every execution writes a row, including blocked ones,
with `status` distinguishing success, error, and blocked. Blocked attempts are
part of the safety evidence, so they are never silently dropped.

Export: CSV and JSON stream from the result set. Markdown schema documentation
generates from the same introspection service that feeds the ERD, so the two
cannot disagree.

## 13. Frontend

PRD §10 is the contract and is followed exactly. Implementation notes:

- Tokens from §10.2 are declared once in `styles/tokens.css` and surfaced
  through the Tailwind theme. No component writes a raw hex value; review treats
  one as a defect.
- The §10.3 type scale becomes named utilities, so the split-colour headline is
  a component rather than a per-page improvisation.
- The accent budget is enforced per screen against the PRD §10.9 table.
- Server state: TanStack Query. Local state: component state, with a small
  Zustand store only for the query workspace panes.
- SQL editing: CodeMirror 6 with the PostgreSQL language mode, chosen because it
  is fully keyboard operable, which PRD §9 requires.
- Motion: one `useReveal` hook implementing the §10.6 fade-and-rise, disabled
  under `prefers-reduced-motion`.
- Below 768px the ERD degrades to the scrollable table list PRD §9 describes.

## 14. Testing

| Suite | Covers | Runs against |
|---|---|---|
| `tests/unit` | Gate rules, type inference, cardinality detection, prompt building | Nothing external |
| `tests/integration` | Endpoints, auth, ownership, ingestion, execution | A throwaway PostgreSQL schema |
| `tests/adversarial` | PRD §12 zero-writes metric | Real PostgreSQL, real roles |
| `tests/benchmark` | Dashboard p95 with 10k rows, before and after `0002` | Real PostgreSQL |

The adversarial suite is a stated success metric, so it is explicit about what
it proves: write statements of every kind, `;` chaining, comment-smuggled
writes, CTE-wrapped writes, catalog reads, file-reading functions, injection
strings planted in CSV cell values and column names, and a role-level test
asserting that user A's project role cannot read user B's schema even with a
fully qualified name.

A 50-question benchmark set against the seeded demo database measures the §12
valid-SQL rate. It runs on demand, not in CI, because it costs quota.

CI (GitHub Actions): lint, type-check, unit and integration suites against a
PostgreSQL service container, and a frontend build.

## 15. Phases

Each phase ends with an application that runs and a capability to demonstrate.

1. **Scaffold.** Repo, venv, FastAPI skeleton, config, Alembic wired to local
   PostgreSQL, `0001_initial`, health endpoint, CI green, Vite app rendering the
   design tokens.
2. **Identity.** Register, login, refresh with rotation, bcrypt cost 12, the
   ownership dependency, projects CRUD, auth screens.
3. **Data in.** CSV upload, inference, review-and-correct, commit, per-project
   schema and read-only role, schema explorer with preview.
4. **The core loop.** Safety gate and its adversarial suite first, then the
   execute endpoint, then Gemini NL-to-SQL, then the query workspace.
5. **Understanding.** ERD with persisted layout and export, explanation panel
   with hover mapping, optimisation with EXPLAIN.
6. **Completion.** Dashboard, history, saved queries with parameters, exports,
   external connections, demo project, benchmarks, docs, deploy.

Phase 4 builds the gate before anything that generates SQL, so no model output
ever reaches the database through an unguarded path.

## 16. Risks carried forward

PRD §13 risks stand. Two are sharpened by this design:

- **Schema context overflow** is handled by the keyword-plus-one-hop expansion
  in §9. If a schema still overflows, the pipeline returns an error naming the
  problem rather than truncating silently.
- **Model outage** is handled by the provider protocol and the always-usable SQL
  editor, so the product degrades to a manual client rather than failing.

One new risk this design introduces: per-project roles accumulate in the
cluster. Project deletion must drop the schema, revoke grants, and drop the role
in one transaction, or roles leak. That is a phase 3 test case.
