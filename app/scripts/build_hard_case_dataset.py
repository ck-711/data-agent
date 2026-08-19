"""Build a V3 training set with reviewed hard cases, preserving the V2 test split."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


HARD_CASES = [
    ("aggregate_month_filtered", "统计 2025 年 1 月的订单数和销售金额，结果只保留汇总值", "SELECT COUNT(DISTINCT o.order_id) AS 订单数, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id WHERE d.year = 2025 AND d.month = 1;", ["fact_order", "dim_date"]),
    ("aggregate_month_filtered", "汇总 2025 年 2 月订单数和销售金额，不要返回订单明细", "SELECT COUNT(DISTINCT o.order_id) AS 订单数, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id WHERE d.year = 2025 AND d.month = 2;", ["fact_order", "dim_date"]),
    ("aggregate_month_filtered", "只统计 2025 年 3 月的订单数量和销售总额", "SELECT COUNT(DISTINCT o.order_id) AS 订单数, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id WHERE d.year = 2025 AND d.month = 3;", ["fact_order", "dim_date"]),
    ("aggregate_month_filtered", "查询 2025 年 1 月的订单总数及销售金额，输出一行", "SELECT COUNT(DISTINCT o.order_id) AS 订单数, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id WHERE d.year = 2025 AND d.month = 1;", ["fact_order", "dim_date"]),
    ("projection_real_fields", "列出订单编号和订单金额，不能遗漏订单编号", "SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order WHERE order_amount IS NOT NULL;", ["fact_order"]),
    ("projection_real_fields", "查询真实存在的订单编号、订单金额字段", "SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order WHERE 1 = 1;", ["fact_order"]),
    ("projection_real_fields", "返回订单编号和非空订单金额两列", "SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order WHERE order_amount IS NOT NULL;", ["fact_order"]),
    ("projection_real_fields", "查询订单金额时同时返回对应订单编号", "SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order WHERE 1 = 1;", ["fact_order"]),
    ("limited_dimension", "查询日期维度的日期编号、年份和月份，最多返回 10 条", "SELECT date_id AS 日期编号, year AS 年份, month AS 月份 FROM dim_date ORDER BY date_id LIMIT 10;", ["dim_date"]),
    ("limited_dimension", "只返回前 10 条日期维度记录及日期编号", "SELECT date_id AS 日期编号, year AS 年份, month AS 月份 FROM dim_date ORDER BY date_id LIMIT 10;", ["dim_date"]),
    ("limited_dimension", "查询日期表的年份月份，结果限制为十行", "SELECT date_id AS 日期编号, year AS 年份, month AS 月份 FROM dim_date ORDER BY date_id LIMIT 10;", ["dim_date"]),
    ("limited_dimension", "读取日期维度前三个字段并限制十条记录", "SELECT date_id AS 日期编号, year AS 年份, month AS 月份 FROM dim_date ORDER BY date_id LIMIT 10;", ["dim_date"]),
    ("schema_member_level", "只返回客户姓名和会员等级，使用客户维度真实字段", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10;", ["dim_customer"]),
    ("schema_member_level", "查询客户姓名及会员等级，不要连接不存在的会员表", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10;", ["dim_customer"]),
    ("schema_member_level", "从 dim_customer 返回客户姓名和会员等级各十条", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10;", ["dim_customer"]),
    ("schema_member_level", "查询真实存在的 customer_name 与 member_level 字段", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10;", ["dim_customer"]),
    ("grouping_scope", "按月份汇总销售金额，每个月只返回一行", "SELECT d.month AS 月份, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id GROUP BY d.month ORDER BY d.month;", ["fact_order", "dim_date"]),
    ("grouping_scope", "按季度汇总销售数量，不要展开订单明细", "SELECT d.quarter AS 季度, SUM(o.order_quantity) AS 销售数量 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id GROUP BY d.quarter ORDER BY d.quarter;", ["fact_order", "dim_date"]),
    ("grouping_scope", "按地区统计订单数，每个地区一行", "SELECT r.region_name AS 地区, COUNT(DISTINCT o.order_id) AS 订单数 FROM fact_order AS o JOIN dim_region AS r ON o.region_id = r.region_id GROUP BY r.region_name ORDER BY r.region_name;", ["fact_order", "dim_region"]),
    ("grouping_scope", "按会员等级汇总销售金额，每个等级一行", "SELECT c.member_level AS 会员等级, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_customer AS c ON o.customer_id = c.customer_id GROUP BY c.member_level ORDER BY c.member_level;", ["fact_order", "dim_customer"]),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("data/finetuning_v2"))
    parser.add_argument("--output", type=Path, default=Path("data/finetuning_v3"))
    args = parser.parse_args()
    source_records = [json.loads(line) for line in (args.source / "approved.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    train = [r for r in source_records if r["metadata"]["split"] == "train"]
    val = [r for r in source_records if r["metadata"]["split"] == "val"]
    test = [r for r in source_records if r["metadata"]["split"] == "test"]
    template = copy.deepcopy(train[0])
    hard = []
    for index, (template_id, query, sql, tables) in enumerate(HARD_CASES, start=1):
        record = copy.deepcopy(template)
        record["id"] = f"hard_{index:04d}"
        record["query_family"] = "hard_case"
        record["messages"][1]["content"] = record["messages"][1]["content"].split("\n\n", 1)[0] + "\n\n召回上下文：\n" + record["messages"][1]["content"].split("召回上下文：\n", 1)[1]
        record["messages"][1]["content"] = record["messages"][1]["content"].replace(record["messages"][1]["content"].splitlines()[0], f"用户查询：{query}", 1)
        record["messages"][2]["content"] = sql
        metadata = record["metadata"]
        metadata.update({"tables": tables, "base_template_id": template_id, "template_id": f"{template_id}_hard_{index:04d}", "split": "train", "sql_sha256": hashlib.sha256(" ".join(sql.lower().split()).encode()).hexdigest(), "source": "manually-authored hard-case augmentation"})
        hard.append(record)
    records = train + hard + val + test
    args.output.mkdir(parents=True, exist_ok=True)
    for name, rows in (("approved.jsonl", records), ("train.jsonl", train + hard), ("val.jsonl", val), ("test.jsonl", test)):
        (args.output / name).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(records), "train": len(train) + len(hard), "val": len(val), "test": len(test)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
