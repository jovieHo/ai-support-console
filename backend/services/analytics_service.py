"""
决策大屏分析服务
聚合 AI 调用埋点，供决策大屏展示系统效果指标。
本大屏只回答一个问题：这套 AI 系统效果怎么样。客服侧的

"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import AiInvocation
from schemas import AnalyticsReport


class AnalyticsService:
    """分析服务：聚合 AI 调用埋点，产出系统效果指标。"""

    def __init__(self, db: Session) -> None:
        """初始化服务，注入数据库会话。"""
        self.db = db

    async def build_report(self) -> AnalyticsReport:
        """构建决策大屏分析报告，仅含 AI 效果指标。"""
        return AnalyticsReport(ai_metrics=self._ai_metrics())

    def _ai_metrics(self) -> dict:
        """聚合 AI 调用埋点，覆盖 /chat 与 /support/assist 两个入口。

        口径说明：
            faq_direct_rate —— 只统计「FAQ 强命中跳过模型」的那部分；
        """
        total = self.db.query(func.count(AiInvocation.id)).scalar() or 0
        if not total:
            return {
                "total_invocations": 0,
                "faq_direct_rate": 0.0,
                "failure_rate": 0.0,
                "avg_retrieval_ms": 0,
                "avg_llm_ms": 0,
                "retrieval_modes": [],
            }

        faq_direct = (
            self.db.query(func.count(AiInvocation.id)).filter(AiInvocation.is_faq_direct.is_(True)).scalar() or 0
        )
        failed = (
            self.db.query(func.count(AiInvocation.id)).filter(AiInvocation.is_success.is_(False)).scalar() or 0
        )
        avg_retrieval = self.db.query(func.avg(AiInvocation.latency_retrieval_ms)).scalar() or 0
        # 只统计真正调过模型的请求：FAQ 直出与反问都记 0ms
        avg_llm = self.db.query(func.avg(AiInvocation.latency_llm_ms)).filter(
            AiInvocation.latency_llm_ms > 0
        ).scalar() or 0
        mode_rows = (
            self.db.query(AiInvocation.retrieval_mode, func.count(AiInvocation.id))
            .group_by(AiInvocation.retrieval_mode)
            .all()
        )

        return {
            "total_invocations": total,
            "faq_direct_rate": round(faq_direct / total, 4),
            "failure_rate": round(failed / total, 4),
            "avg_retrieval_ms": int(avg_retrieval),
            "avg_llm_ms": int(avg_llm),
            "retrieval_modes": [{"mode": mode or "none", "count": count} for mode, count in mode_rows],
        }
