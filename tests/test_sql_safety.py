from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from app.agent.node.validate_sql import validate_sql
from app.agent.node.correct_sql import correct_sql
from app.core.sql_guard import guard_sql


SCHEMA = {
    "fact_order": {"order_id", "order_amount"},
    "dim_customer": {"customer_id", "customer_name", "member_level"},
}


class FakeRepository:
    def __init__(self) -> None:
        self.validated: list[str] = []

    async def validate_sql(self, sql: str) -> None:
        self.validated.append(sql)


class SQLSafetyTests(unittest.TestCase):
    def test_guard_rejects_markdown_fence(self) -> None:
        result = guard_sql("```sql\nSELECT order_id FROM fact_order;\n```", SCHEMA)
        self.assertFalse(result.safe)
        self.assertIn("Markdown code fences are not allowed", result.errors)

    def test_guard_rejects_unknown_table(self) -> None:
        result = guard_sql(
            "SELECT c.customer_name FROM dim_customer AS c JOIN dim_member AS m ON c.customer_id = m.customer_id;",
            SCHEMA,
        )
        self.assertFalse(result.safe)
        self.assertIn("unknown table: dim_member", result.errors)

    def test_validate_node_blocks_before_database(self) -> None:
        repository = FakeRepository()
        events: list[dict] = []
        runtime = SimpleNamespace(stream_writer=events.append, context={"dw_mysql_repository": repository})
        state = {
            "sql": "SELECT c.customer_name FROM dim_customer AS c JOIN dim_member AS m ON c.customer_id = m.customer_id;",
            "table_infos": [
                {"name": "dim_customer", "columns": [{"name": "customer_id"}, {"name": "customer_name"}]}
            ],
        }
        result = asyncio.run(validate_sql(state, runtime))
        self.assertIsNotNone(result["error"])
        self.assertEqual(repository.validated, [])

    def test_validate_node_allows_recalled_schema(self) -> None:
        repository = FakeRepository()
        runtime = SimpleNamespace(stream_writer=lambda event: None, context={"dw_mysql_repository": repository})
        state = {
            "sql": "SELECT o.order_id AS 订单编号 FROM fact_order AS o;",
            "table_infos": [
                {"name": "fact_order", "columns": [{"name": "order_id"}]}
            ],
        }
        result = asyncio.run(validate_sql(state, runtime))
        self.assertIsNone(result["error"])
        self.assertEqual(repository.validated, [state["sql"]])

    def test_correction_failure_is_fail_closed(self) -> None:
        class FailingChain:
            async def ainvoke(self, _payload):
                raise ConnectionError("correction endpoint unavailable")

        # The node imports the chain dependency at module scope; replace it
        # with a deterministic failing model for this regression test.
        import app.agent.node.correct_sql as module

        original = module.correction_llm
        module.correction_llm = FailingChain()
        try:
            runtime = SimpleNamespace(stream_writer=lambda _event: None, context={})
            state = {
                "query": "统计订单总数",
                "table_infos": [],
                "metric_infos": [],
                "db_info": {},
                "date_info": {},
                "error": "unknown table",
                "sql": "SELECT * FROM missing_table;",
                "correction_attempts": 0,
            }
            result = asyncio.run(correct_sql(state, runtime))
            self.assertEqual(result["correction_attempts"], 2)
            self.assertIn("已拒绝执行", result["error"])
        finally:
            module.correction_llm = original


if __name__ == "__main__":
    unittest.main()
