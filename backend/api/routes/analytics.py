from fastapi import APIRouter

from api.deps import AdminUser, DbSession
from schemas import AnalyticsReport
from services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["决策大屏"])


@router.get("/report", response_model=AnalyticsReport)
async def report(_: AdminUser, db: DbSession) -> AnalyticsReport:
    """生成决策大屏所需的 AI 系统效果分析报告，仅管理员可见。"""
    return await AnalyticsService(db).build_report()
