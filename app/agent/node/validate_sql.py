from langgraph.runtime import Runtime
from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger
from app.core.sql_guard import guard_sql


async def validate_sql(state:DataAgentState,runtime:Runtime[DataAgentContext]):
	writer = runtime.stream_writer
	writer({"type": "progress", "step": "校验SQL", "status": "running"})

	# 1.获取状态中SQL
	try:
		sql=state["sql"]
		# Reject hallucinated tables/fields before sending generated SQL to MySQL.
		recalled_schema = {
			table["name"]: {column["name"] for column in table.get("columns", [])}
			for table in state.get("table_infos", [])
		}
		guard_result = guard_sql(sql, recalled_schema)
		if not guard_result.safe:
			raise ValueError("; ".join(guard_result.errors))
		# 2.验证SQL
		dw_mysql_repository = runtime.context["dw_mysql_repository"]
		await dw_mysql_repository.validate_sql(sql)

		writer({"type": "progress", "step": "校验SQL", "status": "success"})
		return {"error": None}
	except Exception as e:
		writer({"type": "progress", "step": "校验SQL", "status": "error"})
		logger.error(f"校验SQL失败, 错误信息: {str(e)}")
		return {"error": str(e)}

