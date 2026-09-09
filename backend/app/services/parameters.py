"""Saved queries with :name placeholders. Design document section 11.

Values reach PostgreSQL as bound parameters, never as string interpolation, so a
parameter can supply a value but never SQL structure. The gate still runs on the
template before anything is bound, which is the part that keeps every layer-2
rule in force for parameterised queries too.

sqlglot cannot parse a placeholder in every position a user might put one (a
bare `:limit` after LIMIT, say), so for *parsing only* the placeholders are
replaced with type-appropriate sentinel literals. The original template is what
gets bound and executed — the substitution never leaves this module.
"""

import enum
import re
from dataclasses import dataclass
from typing import Any

# :name, but not ::cast and not inside a string literal (handled by _spans).
_PLACEHOLDER = re.compile(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)")
_STRING = re.compile(r"'(?:[^']|'')*'")


class ParameterType(enum.StrEnum):
    text = "text"
    integer = "integer"
    numeric = "numeric"
    boolean = "boolean"
    date = "date"


_SENTINELS = {
    ParameterType.text: "'dbpilot'",
    ParameterType.integer: "1",
    ParameterType.numeric: "1",
    ParameterType.boolean: "TRUE",
    ParameterType.date: "DATE '2000-01-01'",
}


@dataclass(frozen=True)
class Parameter:
    name: str
    type: ParameterType = ParameterType.text
    label: str = ""
    default: str | None = None


def _string_spans(sql: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _STRING.finditer(sql)]


def _outside_strings(sql: str) -> list[re.Match[str]]:
    spans = _string_spans(sql)
    return [
        match
        for match in _PLACEHOLDER.finditer(sql)
        if not any(start <= match.start() < end for start, end in spans)
    ]


def extract_parameters(template: str) -> list[Parameter]:
    """The placeholders in `template`, in order, without duplicates.

    A placeholder inside a string literal is text, not a parameter: a query
    filtering on the literal ':00' must not sprout a parameter called `00`.
    """
    seen: list[str] = []
    for match in _outside_strings(template):
        name = match.group(1)
        if name not in seen:
            seen.append(name)
    return [Parameter(name=name, label=name.replace("_", " ")) for name in seen]


def for_parsing(template: str, parameters: list[Parameter]) -> str:
    """The template with sentinels in place of placeholders, for the gate only."""
    types = {parameter.name: parameter.type for parameter in parameters}
    matches = _outside_strings(template)
    result = template
    for match in reversed(matches):
        sentinel = _SENTINELS[types.get(match.group(1), ParameterType.text)]
        result = result[: match.start()] + sentinel + result[match.end() :]
    return result


def _coerce(value: Any, parameter_type: ParameterType) -> Any:
    """Values arrive as JSON strings from a form; PostgreSQL wants types."""
    from datetime import date
    from decimal import Decimal

    if value is None or value == "":
        return None
    text = str(value)
    if parameter_type is ParameterType.integer:
        return int(text)
    if parameter_type is ParameterType.numeric:
        return Decimal(text)
    if parameter_type is ParameterType.boolean:
        return text.strip().lower() in {"true", "t", "yes", "y", "1"}
    if parameter_type is ParameterType.date:
        return date.fromisoformat(text.strip())
    return text


def bind(
    template: str, parameters: list[Parameter], values: dict[str, Any]
) -> tuple[str, list[Any]]:
    """Rewrite :name to %s and return the values in matching order.

    psycopg's own parameter binding does the escaping, so a value containing
    `'; DROP TABLE users; --` arrives as a string comparison and nothing else.
    """
    types = {parameter.name: parameter.type for parameter in parameters}
    defaults = {
        parameter.name: parameter.default
        for parameter in parameters
        if parameter.default is not None
    }

    ordered: list[Any] = []
    matches = _outside_strings(template)
    result = template
    for match in reversed(matches):
        result = result[: match.start()] + "%s" + result[match.end() :]

    for match in matches:
        name = match.group(1)
        if name in values:
            raw = values[name]
        elif name in defaults:
            raw = defaults[name]
        else:
            raise ValueError(f"{name!r} has no value.")
        ordered.append(_coerce(raw, types.get(name, ParameterType.text)))

    return result, ordered
