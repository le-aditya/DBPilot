"""Question in, validated SQL out. PRD F5, design section 9.

The pipeline validates every identifier the model returns against the live
schema and retries exactly once with the specific error appended. A second
failure returns the model's own account of what is missing rather than an
invented query — PRD F5 is explicit that a wrong table name is worse than an
honest "I cannot answer that".
"""

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.ai.models import GeneratedSQL
from app.ai.prompts import build_prompt, select_tables
from app.ai.provider import LLMProvider
from app.services.introspection import TableDescription

MAX_CACHE_ENTRIES = 256


class SchemaTooLarge(Exception):
    """Design section 9: say so rather than truncate the schema silently."""


@dataclass(frozen=True)
class Generation:
    result: GeneratedSQL
    attempts: int
    cached: bool


def schema_fingerprint(tables: Sequence[TableDescription]) -> str:
    """Identity of a schema's shape, for the cache key.

    Row counts are deliberately excluded: adding rows does not change which SQL
    answers a question, and including them would evict the cache on every import.
    """
    shape = ";".join(
        f"{table.name}:" + ",".join(f"{c.name}.{c.data_type}" for c in table.columns)
        for table in tables
    )
    return hashlib.sha256(shape.encode()).hexdigest()[:16]


def unknown_identifiers(
    sql: str, tables: Sequence[TableDescription]
) -> list[str]:
    """Names in `sql` that the schema does not have. Empty means it checks out.

    Aliases are resolved first, so `SELECT c.name FROM customers c` does not
    report `c` as an unknown table.
    """
    try:
        tree = sqlglot.parse_one(sql, dialect="postgres")
    except SqlglotError:
        return []  # the gate reports unparseable SQL; not this function's job

    known_tables = {table.name.lower() for table in tables}
    known_columns = {
        column.name.lower() for table in tables for column in table.columns
    }
    # CTE names are legitimate table references the schema will not contain.
    known_tables |= {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}

    aliases: set[str] = set()
    problems: list[str] = []
    for table in tree.find_all(exp.Table):
        if table.alias:
            aliases.add(table.alias.lower())
        name = table.name.lower()
        if name and name not in known_tables:
            problems.append(f"table {table.name!r} does not exist")

    for column in tree.find_all(exp.Column):
        qualifier = column.table.lower()
        if qualifier and qualifier not in known_tables and qualifier not in aliases:
            problems.append(f"table {column.table!r} does not exist")
        name = column.name.lower()
        if name and name != "*" and name not in known_columns:
            problems.append(f"column {column.name!r} does not exist")

    seen: list[str] = []
    for problem in problems:
        if problem not in seen:
            seen.append(problem)
    return seen


class GenerationCache:
    """Identical (question, schema) pairs answered from memory.

    Addresses the PRD section 13 quota risk directly: a demo where the same
    question is asked repeatedly costs one call, not ten.
    """

    def __init__(self, limit: int = MAX_CACHE_ENTRIES) -> None:
        self._entries: dict[tuple[str, str], GeneratedSQL] = {}
        self._limit = limit

    def get(self, question: str, fingerprint: str) -> GeneratedSQL | None:
        return self._entries.get((question.strip().lower(), fingerprint))

    def put(self, question: str, fingerprint: str, result: GeneratedSQL) -> None:
        if len(self._entries) >= self._limit:
            self._entries.pop(next(iter(self._entries)))
        self._entries[(question.strip().lower(), fingerprint)] = result

    def clear(self) -> None:
        self._entries.clear()


_cache = GenerationCache()


def get_cache() -> GenerationCache:
    return _cache


async def generate_sql(
    provider: LLMProvider,
    *,
    question: str,
    tables: Sequence[TableDescription],
    samples: Mapping[str, Sequence[Sequence[object]]] | None = None,
    cache: GenerationCache | None = None,
) -> Generation:
    """Ask the model, check its answer against the schema, retry once if wrong."""
    if not tables:
        raise SchemaTooLarge("This project has no tables to query yet.")

    chosen = select_tables(tables, question)
    fingerprint = schema_fingerprint(chosen)
    store = cache if cache is not None else _cache

    hit = store.get(question, fingerprint)
    if hit is not None:
        return Generation(result=hit, attempts=0, cached=True)

    prompt = build_prompt(question, chosen, samples)
    result = await provider.generate(prompt, schema=GeneratedSQL)
    attempts = 1

    if result.sql.strip():
        problems = unknown_identifiers(result.sql, chosen)
        if problems:
            retry = build_prompt(
                question,
                chosen,
                samples,
                retry_error="; ".join(problems),
            )
            result = await provider.generate(retry, schema=GeneratedSQL)
            attempts = 2

            if result.sql.strip() and unknown_identifiers(result.sql, chosen):
                # Twice wrong. Return the model's own account rather than SQL
                # that names something the database does not have.
                result = GeneratedSQL(
                    sql="",
                    assumptions=result.assumptions,
                    confidence="low",
                    missing=result.missing
                    or "The schema does not contain the data this question needs.",
                )

    if result.sql.strip():
        store.put(question, fingerprint, result)
    return Generation(result=result, attempts=attempts, cached=False)
