from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv
from omegaconf import OmegaConf


# 日志配置
@dataclass
class File:
    enable: bool
    level: str
    path: str
    rotation: str
    retention: str


@dataclass
class Console:
    enable: bool
    level: str


@dataclass
class LoggingConfig:
    file: File
    console: Console


# 数据库配置
@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass
class QdrantConfig:
    host: str
    port: int
    embedding_size: int


@dataclass
class EmbeddingConfig:
    host: str
    port: int
    model: str


@dataclass
class ESConfig:
    host: str
    port: int
    index_name: str


@dataclass
class LLMConfig:
    model_name: str
    api_key: str
    base_url: str = ""
    correction_model_name: str = ""
    correction_api_key: str = ""
    correction_base_url: str = ""
    correction_proxy: str = ""


@dataclass
class AppConfig:
    logging: LoggingConfig
    db_meta: DBConfig
    db_dw: DBConfig
    qdrant: QdrantConfig
    embedding: EmbeddingConfig
    es: ESConfig
    llm: LLMConfig


project_root = Path(__file__).parents[2]
load_dotenv(project_root / ".env", override=False)
config_file = project_root / 'conf' / 'app_config.yaml'
context = OmegaConf.load(config_file)
schema = OmegaConf.structured(AppConfig)
app_config: AppConfig = OmegaConf.to_object(OmegaConf.merge(schema, context))
app_config.llm.model_name = os.getenv("DATA_AGENT_LLM_MODEL", app_config.llm.model_name)
app_config.llm.api_key = os.getenv("DATA_AGENT_LLM_API_KEY", app_config.llm.api_key or "")
app_config.llm.base_url = os.getenv("DATA_AGENT_LLM_BASE_URL", app_config.llm.base_url or "")
app_config.llm.correction_model_name = os.getenv(
    "DATA_AGENT_LLM_CORRECTION_MODEL", app_config.llm.correction_model_name or ""
)
app_config.llm.correction_api_key = os.getenv(
    "DATA_AGENT_LLM_CORRECTION_API_KEY", app_config.llm.correction_api_key or app_config.llm.api_key or ""
)
app_config.llm.correction_base_url = os.getenv(
    "DATA_AGENT_LLM_CORRECTION_BASE_URL", app_config.llm.correction_base_url or ""
)
app_config.llm.correction_proxy = os.getenv(
    "DATA_AGENT_LLM_CORRECTION_PROXY", app_config.llm.correction_proxy or ""
)
