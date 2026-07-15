import jieba.analyse
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def extract_keywords(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    # 流写入器
    writer = get_stream_writer()
    writer({"type": "progress", "step": "抽取关键字", "status": "running"})
    try:
        # 1.获取用户问题
        query = state["query"]

        # 2.使用jieba对关键词进行分词，得到关键词列表 只提取指定词性的词
        allow_pos = (
            "n",  # 名词: 数据、服务器、表格
            "nr",  # 人名: 张三、李四
            "ns",  # 地名: 北京、上海
            "nt",  # 机构团体名: 政府、学校、某公司
            "nz",  # 其他专有名词: Unicode、哈希算法、诺贝尔奖
            "v",  # 动词: 运行、开发
            "vn",  # 名动词: 工作、研究
            "a",  # 形容词: 美丽、快速
            "an",  # 名形词: 难度、合法性、复杂度
            "eng",  # 英文
            "i",  # 成语
            "l",  # 常用固定短语
        )
        keywords = jieba.analyse.extract_tags(query, allowPOS=allow_pos)
        keywords = list(set(keywords + [query]))
        writer({"type": "progress", "step": "抽取关键字", "status": "success"})
        logger.info(f"抽取关键字成功, 关键字列表: {keywords}")
        # 3.返回结果
        return {"keywords": keywords}
    except Exception as e:
        writer({"type": "progress", "step": "抽取关键字", "status": "error"})
        logger.error(f"抽取关键字失败, 错误信息: {str(e)}")
        raise