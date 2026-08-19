"""Evaluate SQL safety, executability, and result equivalence on MySQL 8."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncmy
import yaml

from app.scripts.validate_seed_dataset import FORBIDDEN, validate


ORDER_INTENT = re.compile(r"(排序|升序|降序|最高|最低|最多|最少|前\s*\d+|top\s*\d+)", re.I)


def read_only_errors(sql: str) -> list[str]:
    sql = sql.strip()
    errors = []
    if not sql.upper().startswith(("SELECT", "WITH")):
        errors.append("not a SELECT/CTE query")
    if sql.count(";") > 1 or (";" in sql and not sql.endswith(";")):
        errors.append("contains more than one statement")
    if FORBIDDEN.search(sql):
        errors.append("contains a write/DDL keyword")
    return errors


def normalize_value(value: Any) -> Any:
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def values_equal(left: Any, right: Any) -> bool:
    left, right = normalize_value(left), normalize_value(right)
    if isinstance(left, float) and isinstance(right, float):
        return math.isclose(left, right, rel_tol=1e-6, abs_tol=1e-6)
    return left == right


def rows_equal(left: list[tuple], right: list[tuple], ordered: bool) -> bool:
    if len(left) != len(right):
        return False
    if left and right and len(left[0]) != len(right[0]):
        return False
    if not ordered:
        key = lambda row: json.dumps([normalize_value(value) for value in row], ensure_ascii=False)
        left, right = sorted(left, key=key), sorted(right, key=key)
    return all(
        all(values_equal(a, b) for a, b in zip(left_row, right_row, strict=True))
        for left_row, right_row in zip(left, right, strict=True)
    )


async def execute(cursor: Any, sql: str) -> tuple[list[str], list[tuple]]:
    await cursor.execute(sql)
    columns = [item[0] for item in cursor.description or []]
    rows = list(await cursor.fetchall())
    if len(rows) > 10_000:
        raise ValueError("result exceeds 10,000 rows")
    return columns, rows


async def evaluate(args: argparse.Namespace) -> dict:
    references = {
        record["id"]: record
        for line in args.references.read_text(encoding="utf-8").splitlines()
        if line.strip() and (record := json.loads(line))
    }
    predictions = [json.loads(line) for line in args.predictions.read_text(encoding="utf-8").splitlines() if line.strip()]
    model_name = predictions[0].get("model", "unspecified") if predictions else "unspecified"
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))["db_dw"]
    connection = await asyncmy.connect(
        host=config["host"], port=config["port"], user=config["user"], password=config["password"],
        db=config["database"], autocommit=False, connect_timeout=5, read_timeout=15,
    )
    cursor = connection.cursor()
    await cursor.execute("SET SESSION TRANSACTION READ ONLY")
    evaluated = []
    try:
        for prediction in predictions:
            reference = references.get(prediction.get("id"))
            if not reference:
                continue
            predicted_sql = prediction.get("predicted_sql", "").strip()
            reference_sql = next(message["content"] for message in reference["messages"] if message["role"] == "assistant").strip()
            user_text = next(message["content"] for message in reference["messages"] if message["role"] == "user")
            query = user_text.splitlines()[0].removeprefix("用户查询：")
            safety_errors = read_only_errors(predicted_sql)
            contract_errors = validate({"messages": [{"role": "assistant", "content": predicted_sql}]})
            item = {
                "id": prediction["id"], "query": query, "predicted_sql": predicted_sql,
                "reference_sql": reference_sql, "read_only_safe": not safety_errors,
                "safety_errors": safety_errors, "contract_valid": not contract_errors,
                "contract_errors": contract_errors, "executable": False, "result_correct": False,
                "execution_error": None, "reference_row_count": None, "predicted_row_count": None,
            }
            try:
                _, reference_rows = await execute(cursor, reference_sql)
                item["reference_row_count"] = len(reference_rows)
                if safety_errors:
                    item["execution_error"] = "blocked by read-only safety gate"
                else:
                    _, predicted_rows = await execute(cursor, predicted_sql)
                    item["predicted_row_count"] = len(predicted_rows)
                    item["executable"] = True
                    item["result_correct"] = rows_equal(reference_rows, predicted_rows, bool(ORDER_INTENT.search(query)))
            except Exception as exc:
                item["execution_error"] = f"{type(exc).__name__}: {exc}"
                await connection.rollback()
                await cursor.execute("SET SESSION TRANSACTION READ ONLY")
            evaluated.append(item)
    finally:
        await connection.rollback()
        await cursor.close()
        connection.close()

    count = len(evaluated)
    safe_count = sum(row["read_only_safe"] for row in evaluated)
    contract_count = sum(row["contract_valid"] for row in evaluated)
    executable_count = sum(row["executable"] for row in evaluated)
    correct_count = sum(row["result_correct"] for row in evaluated)
    unique_rows = list({row["query"]: row for row in evaluated}.values())
    unique_count = len(unique_rows)
    unique_summary = {
        "sample_count": unique_count,
        "read_only_safety_rate": sum(row["read_only_safe"] for row in unique_rows) / unique_count if unique_count else 0.0,
        "contract_valid_rate": sum(row["contract_valid"] for row in unique_rows) / unique_count if unique_count else 0.0,
        "executability_rate": sum(row["executable"] for row in unique_rows) / unique_count if unique_count else 0.0,
        "result_correctness": sum(row["result_correct"] for row in unique_rows) / unique_count if unique_count else 0.0,
    }
    return {
        "model": model_name, "dataset": str(args.references),
        "database": f"{config['host']}:{config['port']}/{config['database']}",
        "review_scope": "代理审核（非业务签字）", "sample_count": count,
        "counts": {"read_only_safe": safe_count, "contract_valid": contract_count, "executable": executable_count, "result_correct": correct_count},
        "read_only_safety_rate": safe_count / count if count else 0.0,
        "contract_valid_rate": contract_count / count if count else 0.0,
        "executability_rate": executable_count / count if count else 0.0,
        "result_correctness": correct_count / count if count else 0.0,
        "evaluation_policy": {
            "database_transaction": "SET SESSION TRANSACTION READ ONLY",
            "numeric_tolerance": {"relative": 1e-6, "absolute": 1e-6},
            "row_order": "Compared only when the natural-language question explicitly requests ordering or ranking.",
            "column_aliases": "Ignored; row value shape and values must match.",
        },
        "unique_question_summary": unique_summary,
        "rows": evaluated,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--references", type=Path, default=Path("data/finetuning/test.jsonl"))
    parser.add_argument("--config", type=Path, default=Path("conf/app_config.yaml"))
    parser.add_argument("--output", type=Path, default=Path("data/finetuning/qwen_evaluation_report.json"))
    args = parser.parse_args()
    report = asyncio.run(evaluate(args))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    keys = ("sample_count", "read_only_safety_rate", "contract_valid_rate", "executability_rate", "result_correctness")
    print(json.dumps({key: report[key] for key in keys}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
