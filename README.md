# DBPilot

[![CI](https://github.com/le-aditya/DBPilot/actions/workflows/ci.yml/badge.svg)](https://github.com/le-aditya/DBPilot/actions/workflows/ci.yml)

AI-powered database explorer and query assistant. Upload a CSV or connect a
PostgreSQL database, see it as an ER diagram, and query it in plain English —
the generated SQL is always shown, always explained, and **never allowed to
write**.

Built as a DBMS course project by Aditya Ajay (24BLC1281).

---

## What it does

| | |
|---|---|
| **Ingest** | Upload CSVs, correct the inferred column types, and DBPilot builds the tables |
| **Explore** | Schema explorer with row counts, keys and indexes, plus a paginated data preview |
| **Diagram** | ER diagram with cardinality, junction-table detection, drag-to-arrange, PNG/SVG export |
| **Ask** | Natural-language questions become SQL, with the assumptions the model made shown as chips |
| **Understand** | Clause-by-clause explanation that highlights the SQL as you hover it |
| **Optimise** | `EXPLAIN (ANALYZE, BUFFERS)` fed back for concrete suggestions and index candidates |
| **Track** | Dashboard, full history including blocked attempts, saved queries with `:name` parameters |
| **Export** | Results as CSV or JSON, schema documentation as Markdown |

## Safety: four independent layers

No query DBPilot generates or accepts can modify data. That is enforced four
times over, and each layer is tested on its own:

1. **Ownership** — every project-scoped route filters by the owner and returns
   **404, never 403**, so project existence cannot leak.
2. **The gate** — one pure function parses the statement with `sqlglot` and
   decides on the **parse tree, never on string matching**. It allows only
   `SELECT` / `WITH … SELECT`, rejects multiple statements, catalog access and
   file-reading functions, and injects `LIMIT 1000`.
3. **The transaction** — execution runs on its own connection with
   `SET TRANSACTION READ ONLY`, a statement timeout, and an unconditional
   `ROLLBACK`.
4. **The role** — each project gets a `NOLOGIN` PostgreSQL role holding `SELECT`
   on exactly one schema, so a query naming another user's data fails inside
   PostgreSQL regardless of what any parser upstream decided.

The adversarial suite (`backend/tests/test_adversarial.py`) proves this against
every write verb, `;` chaining, writes hidden in CTEs, catalog reads, file
functions, `SELECT … INTO`, row locks, comment smuggling, and case games.

> A write hidden in a CTE is the case that matters most: PostgreSQL really runs
> `WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x`, and it parses with a
> `SELECT` at the root. A gate that inspects only the root node waves it through.

## Requirements

- **Python 3.11** (3.12+ not yet verified against this dependency set)
- **Node 24+**
- **PostgreSQL 15 or newer** (developed against 18.6)
- A Google Gemini API key, for the natural-language features

## Setup

```bash
# 1. Create the roles and databases
psql -U postgres -h localhost -f scripts/bootstrap.sql

# 2. Backend
cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # .venv/bin/pip on macOS/Linux
cp .env.example .env                       # then fill in the CHANGE_ME values
.venv/Scripts/python -m alembic upgrade head

# 3. Frontend
cd ../frontend
npm install
```

Generate the two secrets `.env` needs:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"          # JWT_SECRET
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Running

```bash
cd backend  && .venv/Scripts/python run.py     # http://127.0.0.1:8000
cd frontend && npm run dev                     # http://localhost:5173
```

> **Use `python run.py`, not `uvicorn app.main:app`.** uvicorn ≥ 0.36 builds its
> own event loop through `get_loop_factory`, bypassing the event-loop policy —
> and psycopg 3 cannot run async on Windows' `ProactorEventLoop`. `run.py` sets
> the policy and passes `loop="none"` so it survives. There is a regression test
> that spawns a real subprocess, because an in-process test cannot catch this.

Seed the public demo project:

```bash
cd backend && .venv/Scripts/python scripts/seed_demo.py
```

## Testing

```bash
cd backend
.venv/Scripts/python -m pytest              # 398 tests
.venv/Scripts/python -m ruff check app tests scripts run.py
.venv/Scripts/python -m mypy app
.venv/Scripts/python -m alembic check       # migration drift

cd ../frontend
npm test                                     # 98 tests
npm run build
```

Integration tests need `TEST_DATABASE_URL` pointing at a throwaway database;
they are skipped without it.

## Index benchmarks

The migrations are split deliberately — `0001_initial` creates the tables with
no performance indexes, `0002_performance_indexes` adds them — so the before and
after are genuinely measured rather than reconstructed:

```bash
cd backend && .venv/Scripts/python scripts/benchmark_indexes.py --rows 100000
```

At 100,000 rows the dashboard history page goes from **4.87 ms to 0.16 ms (30×)**.
Full results, query plans and the reasoning are in
[`docs/design/index-benchmarks.md`](docs/design/index-benchmarks.md).

## Deploying

`render.yaml` is a Render blueprint that provisions the API (Docker), the static
frontend, and a PostgreSQL database in one go:

1. Push to GitHub, then **New → Blueprint** on [render.com](https://render.com)
   and select this repository.
2. Two values are not generated and must be pasted in on the first deploy:
   - `DBPILOT_ENCRYPTION_KEY` — `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   - `GEMINI_API_KEY` — from [aistudio.google.com](https://aistudio.google.com)
3. The container runs `alembic upgrade head` before starting, so the schema is
   created on first boot. Seed the demo project afterwards with
   `python scripts/seed_demo.py` from a shell on the service.

`DATABASE_URL` is normalised automatically: managed hosts hand out
`postgresql://`, and the async engine needs `postgresql+psycopg://`.

> **Not yet deployed, and the image is not yet built.** The blueprint and
> Dockerfile are committed, but Docker was not available on the build machine,
> so the container has never been built or run — treat the first deploy as the
> thing that verifies it. The live URL needs an account to publish under; once
> it is up, the demo link belongs here.

## Architecture

```
React SPA (Vite)
   │  JSON over HTTP, JWT bearer
FastAPI (uvicorn, async)
   │  SQLAlchemy 2.x async + psycopg 3
PostgreSQL
   ├── database "dbpilot"
   │     ├── schema "dbpilot"           application metadata
   │     └── schema "user_<id>_<proj>"  one per upload project
   └── external clusters, per user connection, read-only
```

The FastAPI process holds **two** database identities: `dbpilot_app`, which owns
metadata and performs DDL, and a per-project read-only role entered via
`SET LOCAL ROLE` on a borrowed connection. Query execution never runs as
`dbpilot_app`.

| Layer | Choice |
|---|---|
| Frontend | React 19, Vite, Tailwind v4, hand-rolled SVG diagram + dagre |
| Backend | FastAPI, Python 3.11, SQLAlchemy 2.x async, Alembic |
| Database | PostgreSQL, psycopg 3 |
| AI | Google Gemini, structured JSON output |
| SQL parsing | `sqlglot` |
| Auth | JWT (python-jose) + bcrypt cost 12, refresh rotation with replay detection |

The PRD names React Flow for the diagram. It is built as **hand-rolled SVG**
instead: React Flow renders nodes as HTML `div`s over an SVG edge layer, so SVG
export would have been a screenshot rather than a serialisation of what is on
screen. Dagre still does the layout.

## Documentation

- [`docs/superpowers/specs/`](docs/superpowers/specs/) — the design document
- [`docs/superpowers/plans/`](docs/superpowers/plans/) — the phase-by-phase build plans
- [`docs/design/index-benchmarks.md`](docs/design/index-benchmarks.md) — measured index impact

## Known limitations

- **NL→SQL latency is 8–22 s**, against the PRD's 6 s target. That is Gemini's
  response time, not DBPilot's; the gate, execution and database round trip are
  milliseconds. Repeat questions are served from cache instantly.
- **Model availability moves.** `gemini-2.0-flash` was retired mid-build and
  `3.6-flash` was returning 503s, so `gemini-3.5-flash` is pinned. Check this
  before a demo.
- Uploaded CSVs persist indefinitely; there is no expiry job.
- Cross-connection joins are out of scope, as the PRD specifies.
