"""Turn arbitrary user text into a safe PostgreSQL identifier.

Identifiers cannot be bound as parameters, so every one of them is composed
through ``psycopg.sql.Identifier`` at the call site. This module exists so the
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
_RESERVED = frozenset(
    {
        "all", "analyse", "analyze", "and", "any", "array", "as", "asc",
        "authorization", "between", "both", "case", "cast", "check", "collate",
        "column", "constraint", "create", "cross", "current_date", "current_role",
        "current_time", "current_timestamp", "current_user", "default",
        "deferrable", "desc", "distinct", "do", "else", "end", "except", "false",
        "for", "foreign", "from", "full", "grant", "group", "having", "in",
        "initially", "inner", "intersect", "into", "is", "join", "leading",
        "left", "like", "limit", "localtime", "localtimestamp", "natural", "not",
        "null", "offset", "on", "only", "or", "order", "outer", "overlaps",
        "placing", "primary", "references", "returning", "right", "select",
        "session_user", "similar", "some", "table", "then", "to", "trailing",
        "true", "union", "unique", "user", "using", "verbose", "when", "where",
        "window", "with",
    }
)


def normalise(name: str) -> str:
    """Fold ``name`` into a legal, readable, lower-snake-case identifier."""
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
    """``user_<id>_<slug>`` — the owner is in the name, so a stray query is obvious."""
    prefix = f"user_{user_id}_"
    slug = normalise(project_name)
    return f"{prefix}{slug[: MAX_IDENTIFIER_BYTES - len(prefix)]}"


def role_name_for(project_id: int) -> str:
    """The read-only role for one project. Design document section 6, layer 4."""
    return f"ro_p{project_id}"
