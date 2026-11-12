"""智企通 AI 商务助手平台 - FastAPI 应用入口。

融合大模型、RAG 检索与可视化运营分析。
"""

import logging
import time
from contextlib import asynccontextmanager

import models  # noqa: F401  导入仅为触发 ORM 模型注册，供 init_db 建表使用
from api.routes import analytics, auth, business, chat, knowledge, support, users
from core.config import get_settings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from init_db import init_db

settings = get_settings()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 建表/迁移/种子数据只在服务真正启动时执行一次，
    # 不再随模块 import 触发——测试 import 函数时不再污染数据库。
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description="融合大模型、RAG 检索与可视化运营分析的企业级智能商务 AI 助手平台。",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
    """记录每个 HTTP 请求的方法、路径、状态码和处理耗时。"""
    start_time = time.time()
    logger.info("%s %s", request.method, request.url.path)
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info("%s %.3fs", response.status_code, process_time)
    # 将请求处理耗时暴露到响应头，便于前端监控
    response.headers["X-Process-Time"] = f"{process_time:.3f}"
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器：捕获所有未处理的异常，返回统一格式的 500 错误。"""
    logger.error("Unhandled error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试", "error_type": type(exc).__name__},
    )


for route in [auth, users, business, chat, knowledge, support, analytics]:
    app.include_router(route.router, prefix=settings.api_prefix)


@app.get("/")
def read_root() -> dict[str, str]:
    """根路径：返回平台欢迎信息与基本状态。"""
    return {
        "message": "欢迎来到智企通 AI 商务助手平台",
        "status": "running",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    """健康检查端点：供 Docker / K8s 探活使用。"""
    return {"status": "healthy", "service": "zhiqitong-business-ai-platform"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
