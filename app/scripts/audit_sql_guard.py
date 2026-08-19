"""Run the schema-aware generation guard over a prediction JSONL file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.sql_guard import guard_sql


DW2_SCHEMA = {
    "fact_order": {"order_id", "customer_id", "product_id", "date_id", "region_id", "order_quantity", "order_amount"},
    "dim_customer": {"customer_id", "customer_name", "gender", "member_level"},
    "dim_product": {"product_id", "product_name", "category", "brand"},
    "dim_region": {"region_id", "province", "region_name", "country"},
    "dim_date": {"date_id", "year", "quarter", "month", "day"},
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for line in args.predictions.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        prediction = json.loads(line)
        result = guard_sql(prediction.get("predicted_sql", ""), DW2_SCHEMA, database="dw2")
        rows.append({"id": prediction.get("id"), "safe": result.safe, "errors": list(result.errors)})
    report = {
        "predictions": str(args.predictions),
        "sample_count": len(rows),
        "safe_count": sum(row["safe"] for row in rows),
        "safe_rate": sum(row["safe"] for row in rows) / len(rows) if rows else 0.0,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("sample_count", "safe_count", "safe_rate")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
