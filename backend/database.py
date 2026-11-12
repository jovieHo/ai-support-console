"""数据库连接与会话管理。

- 支持 SQLite（本地开发）和 PostgreSQL 等关系数据库
- 提供 FastAPI 依赖注入式数据库会话
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from core.config import get_settings

settings = get_settings()

# SQLite 需要关闭同线程检测
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {},
    echo=False,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    """FastAPI 依赖注入：为每个请求创建独立的数据库会话，请求结束后自动关闭。

    使用方式（在路由函数中）:
        db: Session = Depends(get_db)

    生成器会在请求结束时执行 finally 块，确保会话被关闭和归还连接池。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
