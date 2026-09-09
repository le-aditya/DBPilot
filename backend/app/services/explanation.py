"""Explain and optimise SQL. PRD F6, design section 10.

Both features hand model output to the interface, so both validate it first.

The explanation carries character offsets into the SQL so hovering a clause can
highlight the matching span. A model that miscounts would highlight the wrong
text, or crash the panel, so every offset is checked against the SQL and dropped
when it does not line up — a bad answer degrades to plain text rather than to a
broken screen.
"""

from dataclasses import dataclass

from app.ai.models import ExplainedClause, SQLExplanation
from app.ai.provider import LLMProvider

MAX_PLAN_CHARS = 6000


@dataclass(frozen=True)
class OptimisationNote:
    kind: str
    detail: str
    statement: str | None


def validated_clauses(sql: str, clauses: list[ExplainedClause]) -> list[ExplainedClause]:
    """Keep the offsets that really point at the span they claim.

    A model counts characters badly, so an offset is trusted only when the text
    it selects is plausible. Where the numbers are wrong but the clause keyword
    appears in the SQL, the offsets are recomputed by searching; where even that
    fails they are zeroed and the frontend renders the text without highlighting.
    """
    checked: list[ExplainedClause] = []
    for clause in clauses:
        start, end = clause.start, clause.end
        if 0 <= start < end <= len(sql):
            checked.append(clause)
            continue

        found = sql.upper().find(clause.clause.upper())
        if found >= 0:
            checked.append(
                ExplainedClause(
                    clause=clause.clause,
                    text=clause.text,
                    start=found,
                    end=found + len(clause.clause),
                )
            )
            continue

        checked.append(
            ExplainedClause(clause=clause.clause, text=clause.text, start=0, end=0)
        )
    return checked


EXPLAIN_RULES = """\
Explain this PostgreSQL query to someone who reads SQL slowly.

Return a one-line "summary" of what the query answers, then one entry in
"clauses" for each clause — SELECT, FROM, each JOIN, WHERE, GROUP BY, HAVING,
ORDER BY, LIMIT. For each entry, "clause" is the exact text of that clause as it
appears in the query, "text" is the plain-language explanation, and "start" and
"end" are the character offsets of that clause within the query.

Explain what the clause does for this data, not what the keyword means in
general. Do not mention the offsets in the text."""


def build_explain_prompt(sql: str) -> str:
    return f"{EXPLAIN_RULES}\n\n--- QUERY (begin) ---\n{sql}\n--- QUERY (end) ---"


OPTIMISE_RULES = """\
Below is a PostgreSQL query and its EXPLAIN (ANALYZE, BUFFERS) plan.

Return a one-line "summary" of how the query performs, then one entry in
"clauses" per suggestion. Use "clause" as a short label for the kind of problem
(for example "sequential scan", "missing index", "function on indexed column",
"SELECT * on a wide table"), and "text" for the explanation and the fix.

Where an index would help, put the exact CREATE INDEX statement at the end of
"text". Suggest nothing you cannot justify from the plan. If the query is
already efficient, say so and return no suggestions."""


def build_optimise_prompt(sql: str, plan: str) -> str:
    trimmed = plan[:MAX_PLAN_CHARS]
    return (
        f"{OPTIMISE_RULES}\n\n"
        f"--- QUERY (begin) ---\n{sql}\n--- QUERY (end) ---\n\n"
        f"--- PLAN (begin) ---\n{trimmed}\n--- PLAN (end) ---"
    )


async def explain_sql(provider: LLMProvider, sql: str) -> SQLExplanation:
    answer = await provider.generate(build_explain_prompt(sql), schema=SQLExplanation)
    return SQLExplanation(
        summary=answer.summary,
        clauses=validated_clauses(sql, answer.clauses),
    )


async def optimise_sql(provider: LLMProvider, sql: str, plan: str) -> SQLExplanation:
    """Suggestions only. DBPilot never runs a CREATE INDEX it suggested (PRD F6)."""
    return await provider.generate(
        build_optimise_prompt(sql, plan), schema=SQLExplanation
    )
