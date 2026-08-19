"""Build the first reviewed SQL-generation seed set from the retail snapshot.

The records are deliberately deterministic.  They are templates for a reviewable
starting point, not synthetic production history or model self-training data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).parents[2]
PROMPT_PATH = ROOT / "prompts" / "generate_sql.prompt"
OUT_DIR = ROOT / "data" / "finetuning_v2"

SCHEMA = (
    "数据库：MySQL 8，库名 dw2。\n"
    "fact_order(order_id, customer_id, product_id, date_id, region_id, order_quantity, order_amount)。\n"
    "dim_customer(customer_id, customer_name, gender, member_level)。\n"
    "dim_product(product_id, product_name, category, brand)。\n"
    "dim_region(region_id, province, region_name, country)。\n"
    "dim_date(date_id, year, quarter, month, day)。\n"
    "关联：fact_order.customer_id=dim_customer.customer_id，"
    "fact_order.product_id=dim_product.product_id，"
    "fact_order.region_id=dim_region.region_id，"
    "fact_order.date_id=dim_date.date_id。\n"
    "指标：订单数=count(distinct order_id)，销售金额=sum(order_amount)，"
    "销售数量=sum(order_quantity)，平均订单金额=avg(order_amount)。"
)

VALUES = {
    "month": [1, 2, 3],
    "level": ["黄金", "白银", "青铜", "铂金"],
    "category": ["手机数码", "家用电器", "鞋靴", "服饰", "食品饮料", "休闲零食"],
    "brand": ["苹果", "华为", "美的", "耐克", "蒙牛", "乐事"],
    "region": ["华南", "华东", "西南", "华北", "华中"],
}


def _prompt_hash() -> str:
    return hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()


def _variant(query: str, sql: str, variant: int) -> tuple[str, str]:
    """Make a deterministic, semantically neutral variant for split auditing."""
    query = f"{query}（样本变体{variant}）"
    sql = sql.rstrip().rstrip(";")
    marker = " AND 1 = 1"
    upper = sql.upper()
    for token in (" GROUP BY ", " ORDER BY ", " HAVING "):
        position = upper.find(token)
        if position >= 0:
            prefix, suffix = sql[:position], sql[position:]
            if " WHERE " in prefix.upper():
                sql = prefix + marker + suffix
            else:
                sql = prefix + " WHERE 1 = 1" + suffix
            return query, sql + ";"
    if " WHERE " in upper:
        sql += marker
    else:
        sql += " WHERE 1 = 1"
    return query, sql + ";"


def _row(family: str, number: int, query: str, sql: str, template: str, tables: list[str], variant: int) -> dict:
    query, sql = _variant(query, sql, variant)
    sql = sql.rstrip().rstrip(";") + ";"
    normalized = " ".join(sql.split()).lower()
    sql_hash = hashlib.sha256(normalized.encode()).hexdigest()
    system = PROMPT_PATH.read_text(encoding="utf-8")
    user = f"用户查询：{query}\n\n召回上下文：\n{SCHEMA}"
    return {
        "id": f"retail_{number:04d}",
        "query_family": family,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": sql},
        ],
        "metadata": {
            "tables": tables,
            "template_id": template,
            "prompt_sha256": _prompt_hash(),
            "sql_sha256": sql_hash,
            "review_status": "approved",
            "reviewer": "codex-agent",
            "review_type": "代理审核（非业务签字）",
            "review_notes": "已依据 dw.sql schema、只读单语句规则、字段存在性和中文别名契约检查。",
            "source": "docker_windows/mysql/dw.sql + manually-authored question",
        },
    }


def _families() -> list[tuple[str, int, Callable[[int], tuple[str, str, list[str], str]]]]:
    def filt(i: int):
        m = VALUES["month"][i % 3]
        options = [
            (f"查询 2025 年 {m} 月的订单明细", f"SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id WHERE d.year = 2025 AND d.month = {m} ORDER BY o.order_id", ["fact_order", "dim_date"], "filter_month"),
            (f"查询销售金额大于 {1000 + i * 100} 的订单", f"SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order WHERE order_amount > {1000 + i * 100} ORDER BY order_amount DESC", ["fact_order"], "filter_amount"),
            (f"查询会员等级为{VALUES['level'][i % 4]}的客户", f"SELECT customer_id AS 客户编号, customer_name AS 客户姓名 FROM dim_customer WHERE member_level = '{VALUES['level'][i % 4]}' ORDER BY customer_id", ["dim_customer"], "filter_member"),
            (f"查询{VALUES['category'][i % 6]}类商品", f"SELECT product_id AS 商品编号, product_name AS 商品名称 FROM dim_product WHERE category = '{VALUES['category'][i % 6]}' ORDER BY product_id", ["dim_product"], "filter_category"),
            (f"查询{VALUES['region'][i % 5]}地区的订单", f"SELECT o.order_id AS 订单编号, o.order_amount AS 订单金额 FROM fact_order AS o JOIN dim_region AS r ON o.region_id = r.region_id WHERE r.region_name = '{VALUES['region'][i % 5]}' ORDER BY o.order_id", ["fact_order", "dim_region"], "filter_region"),
        ]
        return options[i % len(options)]

    def agg(i: int):
        options = [
            ("统计订单总数", "SELECT COUNT(DISTINCT order_id) AS 订单数 FROM fact_order", ["fact_order"], "agg_order_count"),
            ("统计销售总金额", "SELECT SUM(order_amount) AS 销售金额 FROM fact_order", ["fact_order"], "agg_amount_sum"),
            ("统计销售总数量", "SELECT SUM(order_quantity) AS 销售数量 FROM fact_order", ["fact_order"], "agg_quantity_sum"),
            ("统计平均订单金额", "SELECT AVG(order_amount) AS 平均订单金额 FROM fact_order", ["fact_order"], "agg_amount_avg"),
            ("统计最高订单金额", "SELECT MAX(order_amount) AS 最高订单金额 FROM fact_order", ["fact_order"], "agg_amount_max"),
            ("统计最低订单金额", "SELECT MIN(order_amount) AS 最低订单金额 FROM fact_order", ["fact_order"], "agg_amount_min"),
            ("统计购买过商品的客户数", "SELECT COUNT(DISTINCT customer_id) AS 客户数 FROM fact_order", ["fact_order"], "agg_customer_count"),
            ("统计销售商品种类数", "SELECT COUNT(DISTINCT product_id) AS 商品种类数 FROM fact_order", ["fact_order"], "agg_product_count"),
            ("统计订单金额超过 1000 的订单数", "SELECT COUNT(DISTINCT order_id) AS 订单数 FROM fact_order WHERE order_amount > 1000", ["fact_order"], "agg_filtered_count"),
            ("统计订单平均购买数量", "SELECT AVG(order_quantity) AS 平均购买数量 FROM fact_order", ["fact_order"], "agg_quantity_avg"),
        ]
        return options[i % len(options)]

    def time(i: int):
        options = [
            ("按月份统计订单数", "SELECT d.month AS 月份, COUNT(DISTINCT o.order_id) AS 订单数 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id GROUP BY d.month ORDER BY d.month", ["fact_order", "dim_date"], "time_month_count"),
            ("按月份统计销售金额", "SELECT d.month AS 月份, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id GROUP BY d.month ORDER BY d.month", ["fact_order", "dim_date"], "time_month_amount"),
            ("按季度统计销售数量", "SELECT d.quarter AS 季度, SUM(o.order_quantity) AS 销售数量 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id GROUP BY d.quarter ORDER BY d.quarter", ["fact_order", "dim_date"], "time_quarter_quantity"),
            ("按日期统计订单数", "SELECT d.day AS 日期, COUNT(DISTINCT o.order_id) AS 订单数 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id GROUP BY d.day ORDER BY d.day", ["fact_order", "dim_date"], "time_day_count"),
            ("查询 2025 年第一季度销售金额", "SELECT SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id WHERE d.year = 2025 AND d.quarter = 'Q1'", ["fact_order", "dim_date"], "time_quarter_filter"),
        ]
        return options[i % len(options)]

    def dimension(i: int):
        options = [
            ("按地区统计订单数", "SELECT r.region_name AS 地区, COUNT(DISTINCT o.order_id) AS 订单数 FROM fact_order AS o JOIN dim_region AS r ON o.region_id = r.region_id GROUP BY r.region_name ORDER BY 订单数 DESC", ["fact_order", "dim_region"], "dim_region_count"),
            ("按会员等级统计销售金额", "SELECT c.member_level AS 会员等级, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_customer AS c ON o.customer_id = c.customer_id GROUP BY c.member_level ORDER BY 销售金额 DESC", ["fact_order", "dim_customer"], "dim_member_amount"),
            ("按商品类别统计销售数量", "SELECT p.category AS 商品类别, SUM(o.order_quantity) AS 销售数量 FROM fact_order AS o JOIN dim_product AS p ON o.product_id = p.product_id GROUP BY p.category ORDER BY 销售数量 DESC", ["fact_order", "dim_product"], "dim_category_quantity"),
            ("按品牌统计销售金额", "SELECT p.brand AS 品牌, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_product AS p ON o.product_id = p.product_id GROUP BY p.brand ORDER BY 销售金额 DESC", ["fact_order", "dim_product"], "dim_brand_amount"),
            ("按性别统计订单数", "SELECT c.gender AS 性别, COUNT(DISTINCT o.order_id) AS 订单数 FROM fact_order AS o JOIN dim_customer AS c ON o.customer_id = c.customer_id GROUP BY c.gender ORDER BY c.gender", ["fact_order", "dim_customer"], "dim_gender_count"),
        ]
        return options[i % len(options)]

    def top(i: int):
        options = [
            ("查询销售金额最高的 5 个订单", "SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order ORDER BY order_amount DESC, order_id LIMIT 5", ["fact_order"], "top_orders"),
            ("查询销售数量最多的 5 个订单", "SELECT order_id AS 订单编号, order_quantity AS 销售数量 FROM fact_order ORDER BY order_quantity DESC, order_id LIMIT 5", ["fact_order"], "top_quantity"),
            ("查询销售金额最高的 5 个商品", "SELECT p.product_name AS 商品名称, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_product AS p ON o.product_id = p.product_id GROUP BY p.product_id, p.product_name ORDER BY 销售金额 DESC, p.product_id LIMIT 5", ["fact_order", "dim_product"], "top_products"),
            ("查询订单数最多的 5 个地区", "SELECT r.region_name AS 地区, COUNT(DISTINCT o.order_id) AS 订单数 FROM fact_order AS o JOIN dim_region AS r ON o.region_id = r.region_id GROUP BY r.region_id, r.region_name ORDER BY 订单数 DESC, r.region_id LIMIT 5", ["fact_order", "dim_region"], "top_regions"),
            ("查询销售金额最高的 5 个品牌", "SELECT p.brand AS 品牌, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_product AS p ON o.product_id = p.product_id GROUP BY p.brand ORDER BY 销售金额 DESC, p.brand LIMIT 5", ["fact_order", "dim_product"], "top_brands"),
        ]
        return options[i % len(options)]

    def join(i: int):
        options = [
            ("查询订单及客户姓名", "SELECT o.order_id AS 订单编号, c.customer_name AS 客户姓名, o.order_amount AS 订单金额 FROM fact_order AS o JOIN dim_customer AS c ON o.customer_id = c.customer_id ORDER BY o.order_id", ["fact_order", "dim_customer"], "join_customer"),
            ("查询订单及商品名称", "SELECT o.order_id AS 订单编号, p.product_name AS 商品名称, o.order_quantity AS 销售数量 FROM fact_order AS o JOIN dim_product AS p ON o.product_id = p.product_id ORDER BY o.order_id", ["fact_order", "dim_product"], "join_product"),
            ("查询订单及地区", "SELECT o.order_id AS 订单编号, r.region_name AS 地区, o.order_amount AS 订单金额 FROM fact_order AS o JOIN dim_region AS r ON o.region_id = r.region_id ORDER BY o.order_id", ["fact_order", "dim_region"], "join_region"),
            ("查询订单日期和金额", "SELECT o.order_id AS 订单编号, d.year AS 年份, d.month AS 月份, o.order_amount AS 订单金额 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id ORDER BY o.order_id", ["fact_order", "dim_date"], "join_date"),
            ("查询黄金会员购买的商品", "SELECT c.customer_name AS 客户姓名, p.product_name AS 商品名称, o.order_amount AS 订单金额 FROM fact_order AS o JOIN dim_customer AS c ON o.customer_id = c.customer_id JOIN dim_product AS p ON o.product_id = p.product_id WHERE c.member_level = '黄金' ORDER BY c.customer_id", ["fact_order", "dim_customer", "dim_product"], "join_customer_product"),
            ("查询各地区各月份销售金额", "SELECT r.region_name AS 地区, d.month AS 月份, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_region AS r ON o.region_id = r.region_id JOIN dim_date AS d ON o.date_id = d.date_id GROUP BY r.region_name, d.month ORDER BY r.region_name, d.month", ["fact_order", "dim_region", "dim_date"], "join_region_date"),
            ("查询商品类别和会员等级的订单数", "SELECT p.category AS 商品类别, c.member_level AS 会员等级, COUNT(DISTINCT o.order_id) AS 订单数 FROM fact_order AS o JOIN dim_product AS p ON o.product_id = p.product_id JOIN dim_customer AS c ON o.customer_id = c.customer_id GROUP BY p.category, c.member_level ORDER BY p.category, c.member_level", ["fact_order", "dim_product", "dim_customer"], "join_category_member"),
            ("查询省份销售金额", "SELECT r.province AS 省份, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_region AS r ON o.region_id = r.region_id GROUP BY r.province ORDER BY 销售金额 DESC", ["fact_order", "dim_region"], "join_province"),
        ]
        return options[i % len(options)]

    def metric(i: int):
        options = [
            ("按地区统计订单数和销售金额", "SELECT r.region_name AS 地区, COUNT(DISTINCT o.order_id) AS 订单数, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_region AS r ON o.region_id = r.region_id GROUP BY r.region_name ORDER BY r.region_name", ["fact_order", "dim_region"], "metric_region"),
            ("按商品类别统计销售数量和平均订单金额", "SELECT p.category AS 商品类别, SUM(o.order_quantity) AS 销售数量, AVG(o.order_amount) AS 平均订单金额 FROM fact_order AS o JOIN dim_product AS p ON o.product_id = p.product_id GROUP BY p.category ORDER BY p.category", ["fact_order", "dim_product"], "metric_category"),
            ("按会员等级统计订单数和销售金额", "SELECT c.member_level AS 会员等级, COUNT(DISTINCT o.order_id) AS 订单数, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_customer AS c ON o.customer_id = c.customer_id GROUP BY c.member_level ORDER BY c.member_level", ["fact_order", "dim_customer"], "metric_member"),
            ("按月份统计订单数和销售数量", "SELECT d.month AS 月份, COUNT(DISTINCT o.order_id) AS 订单数, SUM(o.order_quantity) AS 销售数量 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id GROUP BY d.month ORDER BY d.month", ["fact_order", "dim_date"], "metric_month"),
            ("查询 2025 年 1 月的订单数和销售金额", "SELECT COUNT(DISTINCT o.order_id) AS 订单数, SUM(o.order_amount) AS 销售金额 FROM fact_order AS o JOIN dim_date AS d ON o.date_id = d.date_id WHERE d.year = 2025 AND d.month = 1", ["fact_order", "dim_date"], "metric_month_filter"),
        ]
        return options[i % len(options)]

    def safety(i: int):
        options = [
            ("只查询订单编号，不能修改数据", "SELECT order_id AS 订单编号 FROM fact_order ORDER BY order_id LIMIT 10", ["fact_order"], "safety_readonly"),
            ("只返回客户姓名和会员等级", "SELECT customer_name AS 客户姓名, member_level AS 会员等级 FROM dim_customer ORDER BY customer_id LIMIT 10", ["dim_customer"], "safety_columns"),
            ("查询商品名称并限制返回 3 条", "SELECT product_name AS 商品名称 FROM dim_product ORDER BY product_id LIMIT 3", ["dim_product"], "safety_limit"),
            ("查询订单金额且只使用真实字段", "SELECT order_id AS 订单编号, order_amount AS 订单金额 FROM fact_order WHERE order_amount IS NOT NULL", ["fact_order"], "safety_real_fields"),
            ("查询日期维度且不执行写操作", "SELECT date_id AS 日期编号, year AS 年份, month AS 月份 FROM dim_date ORDER BY date_id LIMIT 10", ["dim_date"], "safety_date"),
        ]
        return options[i % len(options)]

    return [("filter", 15, filt), ("aggregate", 20, agg), ("time_analysis", 15, time), ("dimension_group", 15, dimension), ("top_n", 10, top), ("multi_table_join", 25, join), ("metric_combination", 15, metric), ("safety_dialect", 5, safety)]


def build() -> list[dict]:
    records: list[dict] = []
    number = 1
    for family, count, factory in _families():
        for index in range(count):
            query, sql, tables, template = factory(index)
            records.append(_row(family, number, query, sql, template, tables, number))
            number += 1
    # Keep all variants of a template in one split to prevent template leakage.
    groups: dict[str, list[dict]] = {}
    for index, record in enumerate(records):
        base_template = record["metadata"]["template_id"]
        record["metadata"]["base_template_id"] = base_template
        record["metadata"]["template_id"] = f"{base_template}_variant_{index + 1:04d}"
        groups.setdefault(base_template, []).append(record)
    targets = [("train", 80), ("val", 20), ("test", 20)]
    remaining = dict(targets)
    for group in sorted(groups.values(), key=lambda items: (-len(items), items[0]["metadata"]["base_template_id"])):
        choices = [split for split, capacity in remaining.items() if capacity >= len(group)]
        split = max(choices or list(remaining), key=lambda name: remaining[name])
        for record in group:
            record["metadata"]["split"] = split
        remaining[split] -= len(group)
    if any(remaining.values()):
        raise ValueError(f"template-group split cannot satisfy targets: {remaining}")
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    records = build()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "candidates.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
    approved = [r for r in records if r["metadata"]["review_status"] == "approved"]
    (args.output / "approved.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in approved) + "\n", encoding="utf-8")
    for split in ("train", "val", "test"):
        rows = [r for r in approved if r["metadata"]["split"] == split]
        (args.output / f"{split}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(records), "approved": len(approved), "splits": {s: sum(r["metadata"]["split"] == s for r in approved) for s in ("train", "val", "test")}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
