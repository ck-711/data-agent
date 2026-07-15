from typing import TypedDict

from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.entities.value_info import ValueInfo

# 列信息封装实体
class ColumnInfoState(TypedDict):
    name: str
    type: str
    role: str
    examples: list
    description: str
    alias: list[str]

# 表信息封装实体
class TableInfoState(TypedDict):
    name: str
    role: str
    description: str
    columns: list[ColumnInfoState]

# 指标信息封装实体
class MetricInfoState(TypedDict):
    name: str
    description: str
    relevant_columns: list[str]
    alias: list[str]


class DateInfoState(TypedDict):
    date: str
    weekday: str
    quarter: str


class DBInfoState(TypedDict):
    version: str
    dialect: str


class DataAgentState(TypedDict):
    query: str  # 用户的查询
    keywords: list[str]  # 提取关键字列表
    retrieved_columns: list[ColumnInfo]  # 召回列信息列表
    retrieved_metrics:list[MetricInfo] # 召回指标信息列表
    retrieved_values:list[ValueInfo] # 召回字段取值信息列表
    table_infos: list[TableInfoState]  # 封装表信息列表
    metric_infos: list[MetricInfoState]  # 封装指标信息列表
    date_info: DateInfoState
    db_info: DBInfoState
    error:str
    sql:str
