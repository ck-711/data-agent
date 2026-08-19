# Data Agent

面向中文数据分析场景的自然语言查询（NL2SQL）助手。用户通过自然语言提问，服务会结合元数据、指标、字段和值召回生成 SQL，执行查询后以 Server-Sent Events（SSE）流式返回进度与结果。

## 功能

- 基于 LangGraph 编排关键词提取、元数据召回、SQL 生成、校验与纠错流程
- 使用 MySQL 保存业务数据和元数据，Elasticsearch 召回字段值，Qdrant 召回字段与指标
- 接入 Hugging Face Text Embeddings Inference 生成中文向量
- 提供 FastAPI 流式查询接口及 Vue 3 聊天界面

## 技术栈

- 后端：Python 3.12、FastAPI、LangChain、LangGraph
- 数据服务：MySQL 8、Elasticsearch 8、Qdrant
- 向量模型：`BAAI/bge-large-zh-v1.5`
- 前端：Vue 3、Vite

## 前置条件

- Python 3.12 及 [uv](https://docs.astral.sh/uv/)
- Docker Desktop 与 Docker Compose
- Node.js 20+（运行前端时需要）
- DeepSeek API Key

## 快速开始

### 1. 配置服务

在 [conf/app_config.yaml](conf/app_config.yaml) 中确认 MySQL、Elasticsearch、Qdrant、嵌入服务以及 LLM 的连接信息。启动前请替换其中的 LLM API Key；不要将真实密钥提交到版本控制。

### 2. 启动依赖服务

首次使用时，将 `BAAI/bge-large-zh-v1.5` 模型文件放到 `docker_windows/embedding/bge-large-zh-v1.5`。随后在 `docker_windows` 目录启动容器：

```powershell
cd docker_windows
docker compose up -d --build
```

该 Compose 配置会启动：

| 服务 | 默认端口 | 用途 |
| --- | --- | --- |
| MySQL | 3306 | `meta2` 元数据与 `dw2` 数仓示例数据 |
| Elasticsearch | 9200 | 字段值检索 |
| Kibana | 5601 | Elasticsearch 管理界面 |
| Qdrant | 6333 | 字段、指标向量检索 |
| Embedding | 8081 | 文本向量化服务 |

首次创建 MySQL 容器时，会自动执行 `docker_windows/mysql` 下的初始化脚本。

### 3. 安装后端依赖并构建元数据知识库

返回项目根目录后执行：

```powershell
uv sync
uv run python -m app.scripts.build_meta_knowledge --conf conf/meta_config.yaml
```

构建脚本会将配置的表、字段和指标同步到 MySQL、Qdrant 与 Elasticsearch。修改元数据配置后，请重新运行该命令。

### 4. 启动后端

先启动受保护的本地 Qwen 端点（默认使用 V3 adapter）：

```powershell
.\.venv\Scripts\python.exe -m app.scripts.serve_qwen --adapter data/finetuning_v3/output/qwen2.5-coder-3b-sql-v3 --port 8001
```

再启动应用：

```powershell
uv run fastapi dev main.py --host 0.0.0.0 --port 8000
```

应用使用 `http://127.0.0.1:8001/v1` 作为 Qwen 主生成端点；SQL 校正继续使用 `.env` 中的 `DATA_AGENT_LLM_API_KEY` 调用 API。生成结果必须通过 schema-aware guard 和二次校验，否则会拒绝执行。

默认校正代理为 `http://127.0.0.1:10808`，可通过 `DATA_AGENT_LLM_CORRECTION_PROXY` 覆盖或置空。代理不可用时应用会返回拒绝执行事件，不会执行未通过校验的 SQL，也不会中断 SSE 响应。

服务启动后可访问 `http://localhost:8000/docs` 查看 OpenAPI 文档。

### 5. 启动前端（可选）

```powershell
cd data-agent-fronted
npm install
npm run dev
```

Vite 已将 `/api` 请求代理到 `http://localhost:8000`。在浏览器打开终端输出的本地地址即可使用聊天界面。

## 接口

### `POST /api/query`

请求体：

```json
{
  "query": "统计各地区本月销售额"
}
```

响应类型为 `text/event-stream`。每个事件的 `data` 字段是 JSON，常见类型如下：

```text
data: {"type":"progress","step":"召回字段","status":"running"}

data: {"type":"result","data":[{"region_name":"华东","sales":1000}]}
```

## 项目结构

```text
app/
  agent/          LangGraph 查询工作流与节点
  api/            FastAPI 路由、依赖和请求模型
  clients/        MySQL、ES、Qdrant、Embedding 客户端
  repositories/   数据访问层
  scripts/        元数据知识库构建脚本
  services/       查询与元数据服务
conf/             应用与元数据配置
docker_windows/   本地依赖服务及初始化 SQL
data-agent-fronted/ Vue 3 前端
prompts/          SQL 生成、校验和召回提示词
```

## 常见问题

- **连接服务失败**：确认 Docker 容器均已健康启动，并检查 `conf/app_config.yaml` 中的主机和端口。
- **查询没有召回结果**：确认已执行元数据知识库构建命令，且 `conf/meta_config.yaml` 中的数据模型与数仓表一致。
- **嵌入服务无法启动**：检查模型目录是否存在且包含完整的 `bge-large-zh-v1.5` 文件。
- **前端请求失败**：确认后端运行在 8000 端口，并通过 Vite 开发服务器访问前端以启用代理。
