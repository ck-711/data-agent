"""Static checks for the reviewed SQL seed set."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


TABLES = {
    "fact_order": {"order_id", "customer_id", "product_id", "date_id", "region_id", "order_quantity", "order_amount"},
    "dim_customer": {"customer_id", "customer_name", "gender", "member_level"},
    "dim_product": {"product_id", "product_name", "category", "brand"},
    "dim_region": {"region_id", "province", "region_name", "country"},
    "dim_date": {"date_id", "year", "quarter", "month", "day"},
}
FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|create|replace|call|load)\b", re.I)
FROM_JOIN = re.compile(
    r"\b(?:from|join)\s+(?:([a-z_][a-z0-9_]*)\.)?([a-z_][a-z0-9_]*)\s*(?:as\s+)?([a-z_][a-z0-9_]*)?",
    re.I,
)
QUALIFIED = re.compile(r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b", re.I)
SQL_KEYWORDS = {"where", "group", "order", "limit", "having", "on", "join", "left", "right", "inner", "outer"}


def validate(record: dict) -> list[str]:
    errors: list[str] = []
    messages = record.get("messages", [])
    sql = next((m.get("content", "") for m in messages if m.get("role") == "assistant"), "").strip()
    if not sql.upper().startswith(("SELECT", "WITH")):
        errors.append("SQL must start with SELECT or WITH")
    if sql.count(";") > 1 or (";" in sql and not sql.endswith(";")):
        errors.append("SQL must contain only one statement")
    if FORBIDDEN.search(sql):
        errors.append("forbidden write or DDL keyword")
    if "```" in sql or "--" in sql or "/*" in sql:
        errors.append("markdown or SQL comments are not allowed")
    aliases: dict[str, str] = {}
    for _schema, table, alias in FROM_JOIN.findall(sql):
        if table.lower() not in TABLES:
            errors.append(f"unknown table: {table}")
        else:
            effective_alias = alias if alias and alias.lower() not in SQL_KEYWORDS else table
            aliases[effective_alias.lower()] = table.lower()
    for alias, column in QUALIFIED.findall(sql):
        table = aliases.get(alias.lower())
        if table and column.lower() not in TABLES[table]:
            errors.append(f"unknown column: {alias}.{column}")
    if " AS " not in sql.upper():
        errors.append("result columns require AS aliases")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, nargs="?", default=Path("data/finetuning/approved.jsonl"))
    parser.add_argument("--expected-records", type=int, default=120)
    parser.add_argument("--expected-splits", default="train=80,val=20,test=20")
    args = parser.parse_args()
    records = [json.loads(line) for line in args.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    errors = {r["id"]: validate(r) for r in records if validate(r)}
    counts = Counter(r["query_family"] for r in records)
    splits = Counter(r["metadata"]["split"] for r in records)
    approved = Counter(r["metadata"]["review_status"] for r in records)
    report = {"records": len(records), "families": counts, "splits": splits, "review_status": approved, "errors": errors}
    print(json.dumps(report, ensure_ascii=False, indent=2, default=dict))
    expected_splits = Counter({name: int(value) for name, value in (item.split("=", 1) for item in args.expected_splits.split(","))})
    if errors or len(records) != args.expected_records or splits != expected_splits:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
