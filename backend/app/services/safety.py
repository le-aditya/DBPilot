"""The query safety gate. PRD F7, design document section 6, layer 2.

One pure function, no I/O. That is what lets the adversarial suite be fast and
exhaustive, and it means the gate cannot be bypassed by anything that happens to
hold a database session.

The gate decides on the *parse tree*, never on string matching. A comment, a
newline, unusual casing or a CTE wrapper all change the text of a statement
without changing what it does, so text rules are defeated by cosmetics. The one
thing an attacker cannot cosmetically change is what PostgreSQL will execute,
which is what the tree represents.

Defence is in depth (PRD F7): the model is instructed, this gate validates, and
the database role enforces. This layer assumes the other two have failed.
"""

import enum
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

DEFAULT_ROW_LIMIT = 1000


class BlockRule(enum.StrEnum):
    """Why a statement was refused. PRD section 9 requires naming the rule."""

    unparseable = "unparseable"
    multiple_statements = "multiple_statements"
    not_a_select = "not_a_select"
    writes_data = "writes_data"
    catalog_access = "catalog_access"
    forbidden_function = "forbidden_function"
    locks_rows = "locks_rows"


@dataclass(frozen=True)
class Allowed:
    """The statement may run. `sql` is what to execute, not what was submitted."""

    sql: str
    limit_injected: bool


@dataclass(frozen=True)
class Blocked:
    rule: BlockRule
    detail: str


GateResult = Allowed | Blocked

# Only these may be the root of a statement. An allowlist, so a node type added
# by a future sqlglot release is refused rather than silently permitted.
_ALLOWED_ROOTS = (exp.Select, exp.Subquery, exp.SetOperation)

# Anywhere in the tree, including inside a CTE. PostgreSQL really will run
# `WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x`, and it parses with a
# SELECT at the root, so checking only the root would wave it through.
_WRITE_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Copy,
    # Anything sqlglot could not parse into a specific node — DO, VACUUM, CALL,
    # SET, and every command a future PostgreSQL adds.
    exp.Command,
)

_FORBIDDEN_SCHEMAS = frozenset({"pg_catalog", "information_schema", "pg_toast"})

# Reading files, reaching other servers, and large-object escapes. The `pg_`
# prefix check below covers most of these; they are named so the error can be
# specific about what was attempted.
_FORBIDDEN_FUNCTIONS = frozenset(
    {
        "dblink",
        "dblink_connect",
        "dblink_exec",
        "lo_import",
        "lo_export",
        "lo_get",
        "lo_put",
        "query_to_xml",
        "xmltable",
    }
)


def _function_name(node: object) -> str | None:
    if isinstance(node, exp.Anonymous):
        return str(node.this).lower()
    if isinstance(node, exp.Func):
        names = type(node).sql_names()
        return names[0].lower() if names else None
    return None


def _check_tables(tree: exp.Expression) -> Blocked | None:
    for table in tree.find_all(exp.Table):
        qualifier = (table.text("db") or table.text("catalog")).lower()
        if qualifier in _FORBIDDEN_SCHEMAS:
            return Blocked(
                BlockRule.catalog_access,
                f"Queries cannot read {qualifier}. "
                "Use the schema explorer to see the structure of your data.",
            )
        if table.name.lower().startswith("pg_"):
            return Blocked(
                BlockRule.catalog_access,
                f"{table.name} is a PostgreSQL system table and cannot be queried.",
            )
    return None


def _check_functions(tree: exp.Expression) -> Blocked | None:
    for node in tree.walk():
        name = _function_name(node)
        if name is None:
            continue
        if name in _FORBIDDEN_FUNCTIONS:
            return Blocked(
                BlockRule.forbidden_function,
                f"{name}() is not allowed: it can reach data outside this project.",
            )
        if name.startswith("pg_"):
            return Blocked(
                BlockRule.forbidden_function,
                f"{name}() is a PostgreSQL administrative function and is not allowed.",
            )
    return None


def gate(
    sql: str,
    *,
    allow_full_export: bool = False,
    row_limit: int = DEFAULT_ROW_LIMIT,
) -> GateResult:
    """Decide whether `sql` may run, and return what should run in its place.

    Checks run in PRD F7 order, and the first failure wins so the message names
    the most fundamental problem rather than an incidental one.
    """
    if not sql.strip():
        return Blocked(BlockRule.unparseable, "There is no SQL to run.")

    try:
        statements = [one for one in sqlglot.parse(sql, dialect="postgres") if one]
    except SqlglotError as error:
        # SqlglotError, not ParseError: an unterminated string raises TokenError
        # from the tokenizer, which is a sibling of ParseError rather than a
        # subclass. Catching only ParseError turned malformed input into a 500.
        first = str(error).splitlines()[0]
        return Blocked(BlockRule.unparseable, f"That is not valid SQL: {first}")

    if not statements:
        return Blocked(BlockRule.unparseable, "There is no SQL to run.")
    if len(statements) > 1:
        return Blocked(
            BlockRule.multiple_statements,
            "Only one statement can run at a time. Remove the ';' and anything after it.",
        )

    tree = statements[0]

    # A write hidden in a CTE is checked before the root type, so the message
    # says "this writes data" rather than the less useful "this is not a SELECT".
    for node in tree.walk():
        if isinstance(node, _WRITE_NODES):
            return Blocked(
                BlockRule.writes_data,
                "DBPilot only runs SELECT statements, and this one would change "
                "or administer data. Edit the SQL or rephrase your question.",
            )

    if not isinstance(tree, _ALLOWED_ROOTS):
        return Blocked(
            BlockRule.not_a_select,
            "DBPilot only runs SELECT statements. "
            "Edit the SQL or rephrase your question.",
        )

    # SELECT ... INTO creates a table, and is a SELECT everywhere else.
    if isinstance(tree, exp.Select) and tree.args.get("into"):
        return Blocked(
            BlockRule.writes_data,
            "SELECT ... INTO creates a new table, so it cannot run here.",
        )

    if tree.args.get("locks"):
        return Blocked(
            BlockRule.locks_rows,
            "FOR UPDATE and FOR SHARE lock rows for writing, so they cannot run here.",
        )

    blocked = _check_tables(tree) or _check_functions(tree)
    if blocked is not None:
        return blocked

    limit_injected = False
    if not allow_full_export and tree.args.get("limit") is None:
        tree = tree.limit(row_limit)
        limit_injected = True

    return Allowed(sql=tree.sql(dialect="postgres"), limit_injected=limit_injected)
