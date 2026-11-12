"""客服流水线的数据查询函数：给生成阶段提供真实的平台运营数据。"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import BusinessData, CustomerConsultation


def query_business_summary(db: Session) -> dict[str, float | int]:
    """查询平台商务数据总览。

    统计三个核心指标：
    - business_count: 商务数据记录总数
    - consultation_count: 客户咨询记录总数
    - total_amount: 所有商务项目的金额总和（使用 COALESCE 处理空表情况）

    参数:
        db: SQLAlchemy 数据库会话

    返回:
        dict: 包含 business_count（int）、consultation_count（int）、
              total_amount（float）的字典
    """
    # 使用 COALESCE 确保空表时 SUM 返回 0 而非 None
    total_amount = db.query(func.coalesce(func.sum(BusinessData.amount), 0)).scalar()
    business_count = db.query(BusinessData).count()
    consultation_count = db.query(CustomerConsultation).count()
    return {
        "business_count": business_count,
        "consultation_count": consultation_count,
        "total_amount": float(total_amount or 0),
    }
