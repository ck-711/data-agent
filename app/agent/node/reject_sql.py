from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def reject_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """Stop after bounded correction attempts without executing invalid SQL."""
    writer = runtime.stream_writer
    message = state.get("error") or "SQL 未通过校验，已拒绝执行"
    writer({"type": "progress", "step": "拒绝SQL", "status": "error"})
    logger.error("SQL 被拒绝执行：{}", message)
    return {"error": message}
