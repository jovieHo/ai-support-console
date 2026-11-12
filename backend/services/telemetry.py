"""AI 调用埋点

/chat 与 /support/assist 共用同一份写入逻辑：一次请求记一行，字段口径一致，

写失败只回滚自己，不影响已经返回给用户的答案——埋点是旁路，不是主链路。
"""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from models import AiInvocation
from schemas import SourceSnippet

# 请求入口码值，与前端展示一一对应
ENTRY_CHAT = "chat"
ENTRY_ASSIST = "assist"


def elapsed_ms(started: float) -> int:
    """从计时起点到现在的毫秒数。"""
    return int((time.perf_counter() - started) * 1000)


def record_invocation(
    db: Session,
    *,
    entry: str,
    retrieval_mode: str,
    sources: list[SourceSnippet],
    retrieval_ms: int,
    llm_ms: int,
    prompt_chars: int = 0,
    ttft_ms: int | None = None,
    is_faq_direct: bool = False,
    is_success: bool = True,
    is_escalated: bool = False,
    conversation_id: int | None = None,
) -> None:
    """记录一次 AI 请求。

    参数:
        db: 数据库会话
        entry: 请求入口，chat / assist
        retrieval_mode: 检索路径，取 RAGService.last_retrieval_mode
        sources: 本次回复引用的片段，命中数与最高分从这里算
        retrieval_ms: 检索耗时（assist 含分类并行段）
        llm_ms: 模型生成耗时，FAQ 直出未调模型时传 0
        prompt_chars: 拼给模型的上下文总字符数
        ttft_ms: 首字延迟，仅流式请求有值
        is_faq_direct: 是否 FAQ 强命中跳过模型
        is_success: 本次请求是否成功
        is_escalated: Agent 是否建议转人工（不是客服实际接管）
        conversation_id: 所属会话，assist 无会话时为 None
    """
    try:
        db.add(
            AiInvocation(
                conversation_id=conversation_id,
                entry=entry,
                retrieval_mode=retrieval_mode,
                hit_count=len(sources),
                top_score=max((item.score for item in sources), default=0.0),
                is_faq_direct=is_faq_direct,
                is_escalated=is_escalated,
                prompt_chars=prompt_chars,
                latency_retrieval_ms=retrieval_ms,
                latency_llm_ms=llm_ms,
                ttft_ms=ttft_ms,
                is_success=is_success,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
