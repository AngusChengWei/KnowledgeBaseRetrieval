"""
FastAPI 入口：创建应用、注册路由、启动/关闭事件。

启动流程:
  1. startup 事件 → 初始化数据库表（建表/迁移/默认数据）
  2. 注册 5 个路由模块（auth / chat / admin / export / analysis）
  3. 跨域中间件从环境变量读取允许的来源
  4. uvicorn 监听 0.0.0.0:8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from logger import get_logger
from models import HealthResponse
from routes.auth import router as auth_router
from routes.chat import router as chat_router
from routes.admin import router as admin_router
from routes.export_routes import router as export_router
from routes.analysis import router as analysis_router

_logger = get_logger(__name__)
app = FastAPI(title="企业AI知识助手系统", version="2.0.0")


@app.on_event("startup")
def startup():
    """应用启动时自动建表、执行数据库迁移、初始化默认数据"""
    from db import init_db
    init_db()


@app.on_event("shutdown")
def shutdown():
    """关闭 SQLite 连接，ChromaDB 的 PersistentClient 随进程退出自动清理"""
    from db import _conn
    if _conn:
        try:
            _conn.close()
            _logger.info("SQLite 连接已关闭")
        except Exception as e:
            _logger.error(f"关闭 SQLite 连接失败: {e}")


# 跨域配置 — 来源列表从 .env 的 CORS_ORIGINS 读取（逗号分隔）
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 各功能模块的路由注册
app.include_router(auth_router)       # /auth/*, /departments
app.include_router(chat_router)       # /sessions/*, /ask, /upload, /documents/*, /rebuild, /import-url
app.include_router(admin_router)      # /admin/*, /audit/*
app.include_router(export_router)     # /pdf/*, /export/*
app.include_router(analysis_router)   # /analyze/*


@app.get("/health")
async def health_check():
    """
    健康检查 — 验证 SQLite 和 ChromaDB 是否可用。
    返回 status="ok" 表示全正常，"degraded" 表示部分异常。
    """
    checks = {"database": "ok", "chromadb": "ok"}
    healthy = True

    try:
        from db import get_db
        db = get_db()
        db.execute("SELECT 1")
    except Exception as e:
        checks["database"] = f"error: {e}"
        healthy = False

    try:
        from vector_store import _client
        _client.list_collections()
    except Exception as e:
        checks["chromadb"] = f"error: {e}"
        healthy = False

    return {"status": "ok" if healthy else "degraded", "checks": checks}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
