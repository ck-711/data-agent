"""Build V4 by adding schema/projection/limit coverage to the V3 training split."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


CASES = [
    ("schema_customer_projection", "从客户维度查询客户姓名和会员等级", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10;", ["dim_customer"]),
    ("schema_customer_projection", "客户表中返回 customer_name 和 member_level 两列", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10;", ["dim_customer"]),
    ("schema_customer_projection", "查询客户姓名、会员等级，数据来自 dim_customer", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10;", ["dim_customer"]),
    ("schema_customer_projection", "只读取客户维度的姓名与会员等级字段", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10;", ["dim_customer"]),
    ("schema_customer_projection", "输出十条客户姓名和会员等级记录", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10;", ["dim_customer"]),
    ("schema_customer_projection", "不要使用不存在的 dim_member 表，查询客户等级", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10;", ["dim_customer"]),
    ("schema_customer_projection", "会员等级字段在客户维度中，返回姓名和等级", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10;", ["dim_customer"]),
    ("schema_customer_projection", "从真实客户表查询姓名与等级并限制十行", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10;", ["dim_customer"]),
    ("schema_customer_projection", "列出客户表的客户姓名和会员等级", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10;", ["dim_customer"]),
    ("schema_customer_projection", "查询客户姓名和会员等级，按客户编号排序", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10;", ["dim_customer"]),
    ("projection_order_amount", "查询订单编号和订单金额两列", "SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order WHERE order_amount IS NOT NULL;", ["fact_order"]),
    ("projection_order_amount", "订单金额结果必须带订单编号", "SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order WHERE order_amount IS NOT NULL;", ["fact_order"]),
    ("projection_order_amount", "返回所有非空订单的编号及金额", "SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order WHERE order_amount IS NOT NULL;", ["fact_order"]),
    ("projection_order_amount", "真实字段 order_id 与 order_amount 一起查询", "SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order WHERE order_amount IS NOT NULL;", ["fact_order"]),
    ("projection_order_amount", "只查询订单明细中的编号和金额", "SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order WHERE order_amount IS NOT NULL;", ["fact_order"]),
    ("projection_order_amount", "订单金额不为空时显示订单编号和订单金额", "SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order WHERE order_amount IS NOT NULL;", ["fact_order"]),
    ("projection_order_amount", "查询金额字段时不能丢失 order_id", "SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order WHERE order_amount IS NOT NULL;", ["fact_order"]),
    ("projection_order_amount", "从 fact_order 返回编号和金额", "SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order WHERE order_amount IS NOT NULL;", ["fact_order"]),
    ("date_limited_projection", "查询日期编号、年份、月份，限制十条", "SELECT date_id AS 日期编号, year AS 年份, month AS 月份 FROM dim_date ORDER BY date_id LIMIT 10;", ["dim_date"]),
    ("date_limited_projection", "日期维度只返回 date_id、year、month 三列", "SELECT date_id AS 日期编号, year AS 年份, month AS 月份 FROM dim_date ORDER BY date_id LIMIT 10;", ["dim_date"]),
    ("date_limited_projection", "按日期编号排序查询十条日期记录", "SELECT date_id AS 日期编号, year AS 年份, month AS 月份 FROM dim_date ORDER BY date_id LIMIT 10;", ["dim_date"]),
    ("date_limited_projection", "读取日期表前三个业务字段并限制 10 行", "SELECT date_id AS 日期编号, year AS 年份, month AS 月份 FROM dim_date ORDER BY date_id LIMIT 10;", ["dim_date"]),
    ("date_limited_projection", "只查询日期编号年份月份，不要订单指标", "SELECT date_id AS 日期编号, year AS 年份, month AS 月份 FROM dim_date ORDER BY date_id LIMIT 10;", ["dim_date"]),
    ("date_limited_projection", "查询日期维度前十条记录", "SELECT date_id AS 日期编号, year AS 年份, month AS 月份 FROM dim_date ORDER BY date_id LIMIT 10;", ["dim_date"]),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("data/finetuning_v3"))
    parser.add_argument("--output", type=Path, default=Path("data/finetuning_v4"))
    args = parser.parse_args()
    source = [json.loads(line) for line in (args.source / "approved.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    train = [record for record in source if record["metadata"]["split"] == "train"]
    val = [record for record in source if record["metadata"]["split"] == "val"]
    test = [record for record in source if record["metadata"]["split"] == "test"]
    base = copy.deepcopy(train[0])
    extra = []
    for index, (template_id, query, sql, tables) in enumerate(CASES, start=1):
        record = copy.deepcopy(base)
        record["id"] = f"v4_hard_{index:04d}"
        record["query_family"] = "v4_hard_case"
        user_content = record["messages"][1]["content"]
        context = user_content.split("召回上下文：\n", 1)[1]
        record["messages"][1]["content"] = f"用户查询：{query}\n\n召回上下文：\n{context}"
        record["messages"][2]["content"] = sql
        metadata = record["metadata"]
        metadata.update({"tables": tables, "template_id": f"{template_id}_v4_{index:04d}", "base_template_id": template_id, "split": "train", "source": "manually-authored V4 schema coverage", "sql_sha256": hashlib.sha256(" ".join(sql.lower().split()).encode()).hexdigest()})
        extra.append(record)
    records = train + extra + val + test
    args.output.mkdir(parents=True, exist_ok=True)
    for name, rows in (("approved.jsonl", records), ("train.jsonl", train + extra), ("val.jsonl", val), ("test.jsonl", test)):
        (args.output / name).write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(records), "train": len(train) + len(extra), "val": len(val), "test": len(test)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
