import uuid
from urllib.request import Request

from app.api.routers.query_router import query_router
from fastapi import FastAPI

from app.core.context import request_id_ctx_var
from app.core.lifespan import lifespan

# 创建FastAPI应用并绑定生命周期函数
app = FastAPI(lifespan=lifespan)

# 绑定查询router
app.include_router(query_router)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    # 调用路径函数之前进行业务处理
    request_id_ctx_var.set(uuid.uuid4())
    # 调用路径函数
    response = await call_next(request)
    # 调用路径函数之后进行业务处理
    return response
