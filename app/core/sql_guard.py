"""Static, schema-aware safety checks for generated read-only SQL."""

from __future__ import annotations

import re
from dataclasses import dataclass


FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|create|replace|call|load|into\s+outfile)\b", re.I)
TABLE_REF = re.compile(
    r"\b(?:from|join)\s+(?:(?P<schema>[a-z_][\w]*)\.)?(?P<table>[a-z_][\w]*)"
    r"(?:\s+(?:as\s+)?(?P<alias>[a-z_][\w]*))?",
    re.I,
)
QUALIFIED = re.compile(r"\b(?P<alias>[a-z_][\w]*)\.(?P<column>[a-z_][\w]*)\b", re.I)
KEYWORDS = {"where", "group", "order", "limit", "having", "on", "join", "left", "right", "inner", "outer", "cross", "union"}


@dataclass(frozen=True)
class SQLGuardResult:
    safe: bool
    errors: tuple[str, ...]


def guard_sql(sql: str, schema: dict[str, set[str]], *, database: str | None = None) -> SQLGuardResult:
    """Validate one generated query against the recalled schema.

    This intentionally checks only deterministic properties. SQL execution and
    result correctness remain separate gates in ``evaluate_sql.py``.
    """
    text = sql.strip()
    errors: list[str] = []
    if not text.upper().startswith(("SELECT", "WITH")):
        errors.append("query must start with SELECT or WITH")
    if text.count(";") > 1 or (";" in text and not text.endswith(";")):
        errors.append("query must contain one statement")
    if "--" in text or "/*" in text or "*/" in text:
        errors.append("SQL comments are not allowed")
    if "```" in text:
        errors.append("Markdown code fences are not allowed")
    if FORBIDDEN.search(text):
        errors.append("query contains a write, DDL, or export keyword")

    normalized_schema = {name.lower(): {column.lower() for column in columns} for name, columns in schema.items()}
    aliases: dict[str, str] = {}
    for match in TABLE_REF.finditer(text):
        table = match.group("table").lower()
        alias = (match.group("alias") or "").lower()
        if alias in KEYWORDS:
            alias = ""
        if table not in normalized_schema:
            errors.append(f"unknown table: {table}")
            continue
        aliases[alias or table] = table
        if database and match.group("schema") and match.group("schema").lower() != database.lower():
            errors.append(f"unexpected database qualifier: {match.group('schema')}")

    for match in QUALIFIED.finditer(text):
        alias, column = match.group("alias").lower(), match.group("column").lower()
        table = aliases.get(alias)
        if table and column not in normalized_schema[table]:
            errors.append(f"unknown column: {alias}.{column}")

    return SQLGuardResult(safe=not errors, errors=tuple(dict.fromkeys(errors)))
