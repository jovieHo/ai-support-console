"""数据库初始化脚本：建表、迁移缺失列、写入演示种子数据。

该脚本在应用启动时自动执行，也可以在命令行独立运行以重建数据库。
"""

import models
from core.security import hash_password
from database import Base, SessionLocal, engine
from tools.migrate_schema import apply_migrations


def init_db() -> None:
    """初始化数据库：建表、列迁移、种子数据写入。

    三步操作按顺序执行：
    1. 根据 ORM 模型创建不存在的表
    2. 补齐已有表中可能缺失的列（渐进式迁移）
    3. 仅在空表时写入演示种子数据
    """
    Base.metadata.create_all(bind=engine)
    ensure_schema_columns()
    seed_demo_data()


def ensure_schema_columns() -> None:
    """渐进式数据库迁移：检查并补齐已有表中缺失的列和索引。

    列/索引迁移清单统一收敛在 tools/migrate_schema.py，
    这里复用同一份清单，保证本地 uvicorn 与 Docker 走同一条迁移路径。
    """
    apply_migrations(engine)


def seed_demo_data() -> None:
    """写入演示种子数据：仅在对应表为空时填充示例记录。

    包含以下演示数据：
    - 3 个用户账号：admin、service、user
    - 3 条 FAQ 问答
    - 3 条客户咨询记录
    - 2 条商务数据记录

    所有插入操作在同一个事务中完成，如果任意一条失败则整体回滚。
    """
    db = SessionLocal()
    try:
        if db.query(models.User).count() == 0:
            db.add_all(
                [
                    models.User(username="admin", email="admin@zhiqitong.demo", hashed_password=hash_password("admin123"), role="admin"),
                    models.User(username="service", email="service@zhiqitong.demo", hashed_password=hash_password("service123"), role="customer_service"),
                    models.User(username="user", email="user@zhiqitong.demo", hashed_password=hash_password("user123"), role="enterprise_user"),
                ]
            )
        if db.query(models.FAQ).count() == 0:
            db.add_all(
                [
                    models.FAQ(question="平台是否支持私有化部署？", answer="支持 Docker Compose 私有化部署，可按企业网络与安全要求配置。", category="product"),
                    models.FAQ(question="模型可以切换吗？", answer="支持 DeepSeek、通义千问、OpenAI 等兼容 OpenAI 协议的大模型。", category="ai"),
                    models.FAQ(question="知识库支持哪些文档？", answer="当前支持 PDF、Word、CSV、TXT 上传解析，并可配置分块参数。", category="knowledge"),
                ]
            )
        if db.query(models.CustomerConsultation).count() == 0:
            db.add_all(
                [
                    models.CustomerConsultation(customer_name="张三", question="这个产品支持企业私有化部署吗？", category="product", priority=4, status="pending", ai_reply="支持，可提供 Docker Compose 部署方案。", satisfaction=5),
                    models.CustomerConsultation(customer_name="李四", question="售后服务响应时间是多久？", category="service", priority=3, status="replied", ai_reply="标准服务为工作日 4 小时内响应。", satisfaction=4),
                    models.CustomerConsultation(customer_name="王五", question="知识库上传 PDF 后如何检索？", category="technical", priority=2, status="closed", ai_reply="上传后系统会分块并建立向量索引，可通过知识库问答检索。", satisfaction=5),
                ]
            )
        if db.query(models.BusinessData).count() == 0:
            db.add_all(
                [
                    models.BusinessData(title="智慧客服升级项目", content="面向企业客户服务中心的 AI 辅助答复与质检。", amount=860000, status="published"),
                    models.BusinessData(title="企业知识库建设", content="建设统一文档上传、分段、检索和问答流程。", amount=420000, status="draft"),
                ]
            )
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
