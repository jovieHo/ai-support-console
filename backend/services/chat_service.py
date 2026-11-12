"""AI 对话服务：会话存取、上下文构建与消息落库。

从路由层抽出，承载 chat.py 里的领域规则（FAQ 首轮直出判断、
上下文拼接策略、消息写库），路由只做取参与调用。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import NamedTuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Conversation, ConversationMessage
from prompts.templates import CUSTOMER_SERVICE_PROMPT
from schemas import (
    ChatRequest,
    ConversationDetail,
    ConversationMessageResponse,
    ConversationSummary,
    ConversationUpdate,
    SourceSnippet,
)
from services.query_rewrite import QueryRewriter
from services.rag_service import RAGService


class PreparedTurn(NamedTuple):
    """一轮对话请求在检索阶段产出的不可变结果，路由据此只做「怎么返回答案」。"""

    conversation_id: int
    sources: list[SourceSnippet]
    retrieval_mode: str
    retrieval_ms: int
    direct_hit: SourceSnippet | None


class ChatService:
    """会话存取与消息构建，方法均为无状态查询或纯写库操作。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # 编排：检索准备
    async def prepare(self, user_id: int, payload: ChatRequest) -> PreparedTurn:
        """一轮对话的检索编排：会话定位 → 问句改写 → 双路检索 → 首轮直出判定。
        """
        conversation = self.get_or_create_conversation(user_id, payload)
        question = await self.retrieve_question(conversation.id, payload.message)
        rag = RAGService(self.db)
        retrieve_started = time.perf_counter()
        sources = await rag.retrieve(question, top_k=3)
        retrieval_ms = int((time.perf_counter() - retrieve_started) * 1000)
        direct_hit = rag.direct_faq_hit if self.is_first_turn(conversation.id) else None
        return PreparedTurn(
            conversation_id=conversation.id,
            sources=sources,
            retrieval_mode=rag.last_retrieval_mode,
            retrieval_ms=retrieval_ms,
            direct_hit=direct_hit,
        )

    # 会话存取
    def is_first_turn(self, conversation_id: int) -> bool:
        """FAQ 仅在首轮直出，避免后续问题脱离会话上下文。"""
        return (
            self.db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation_id)
            .count()
            == 0
        )

    def get_or_create_conversation(self, user_id: int, payload: ChatRequest) -> Conversation:
        """复用 payload 中属于当前用户的会话，否则创建新会话（标题取消息前 40 字符）。"""
        conversation = self.db.get(Conversation, payload.conversation_id) if payload.conversation_id else None
        if conversation and conversation.user_id == user_id:
            return conversation

        conversation = Conversation(user_id=user_id, title=payload.message[:40])
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def get_owned_conversation(self, user_id: int, conversation_id: int) -> Conversation:
        """验证会话存在且属于当前用户，否则抛出 404。"""
        conversation = self.db.get(Conversation, conversation_id)
        if not conversation or conversation.user_id != user_id:
            raise HTTPException(status_code=404, detail="会话不存在")
        return conversation

    def list_conversations(self, user_id: int, favorite: bool | None = None) -> list[ConversationSummary]:
        """列出当前用户的会话，可按收藏状态筛选。"""
        query = self.db.query(Conversation).filter(Conversation.user_id == user_id)
        if favorite is not None:
            query = query.filter(Conversation.is_favorite.is_(favorite))
        items = query.order_by(Conversation.id.desc()).all()
        return [self.conversation_summary(item) for item in items]

    def conversation_detail(self, user_id: int, conversation_id: int) -> ConversationDetail:
        """取会话及其全部消息，按时间正序。"""
        conversation = self.get_owned_conversation(user_id, conversation_id)
        messages = (
            self.db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.id.asc())
            .all()
        )
        return ConversationDetail(
            id=conversation.id,
            title=conversation.title,
            is_favorite=bool(conversation.is_favorite),
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=[self.message_response(item) for item in messages],
        )

    def delete_conversation(self, user_id: int, conversation_id: int) -> None:
        """物理删除会话及其全部消息。"""
        conversation = self.get_owned_conversation(user_id, conversation_id)
        self.db.query(ConversationMessage).filter(
            ConversationMessage.conversation_id == conversation.id
        ).delete()
        self.db.delete(conversation)
        self.db.commit()

    def update_conversation(
        self, user_id: int, conversation_id: int, payload: ConversationUpdate
    ) -> ConversationSummary:
        """修改会话标题和/或收藏状态，支持部分更新。"""
        conversation = self.get_owned_conversation(user_id, conversation_id)
        if payload.title is not None:
            conversation.title = payload.title.strip()
        if payload.is_favorite is not None:
            conversation.is_favorite = payload.is_favorite
        conversation.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(conversation)
        return self.conversation_summary(conversation)

    # ------------------------------------------------------------------
    # 上下文构建
    # ------------------------------------------------------------------
    def build_messages(
        self,
        conversation_id: int,
        message: str,
        sources: list[SourceSnippet],
        memory_type: str,
    ) -> list[dict[str, str]]:
        """构建系统提示词、历史消息、知识上下文和当前问题。"""
        context = "\n".join(f"[{item.source}] {item.content}" for item in sources)
        history_query = self.db.query(ConversationMessage).filter(
            ConversationMessage.conversation_id == conversation_id
        )
        if memory_type == "window":
            history = history_query.order_by(ConversationMessage.id.desc()).limit(6).all()[::-1]
        elif memory_type == "recent":
            history = history_query.order_by(ConversationMessage.id.desc()).limit(3).all()[::-1]
        else:
            history = history_query.order_by(ConversationMessage.id.asc()).all()
        messages = [{"role": "system", "content": CUSTOMER_SERVICE_PROMPT}]
        messages.extend({"role": item.role, "content": item.content} for item in history)
        if context:
            content = f"{message}\n\n可引用知识片段：\n{context}"
        else:
            content = message
        messages.append({"role": "user", "content": content})
        return messages

    def recent_history(self, conversation_id: int, limit: int = 4) -> list[str]:
        """取最近若干条消息，供查询改写判断指代指向。"""
        rows = (
            self.db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.id.desc())
            .limit(limit)
            .all()
        )[::-1]
        return [f"{'客户' if row.role == 'user' else '客服'}：{row.content}" for row in rows]

    async def retrieve_question(self, conversation_id: int, message: str) -> str:
        """检索用的问句：多轮指代型问题先补全成独立问句。"""
        return await QueryRewriter().rewrite(message, self.recent_history(conversation_id))

    def save_messages(
        self,
        conversation_id: int,
        question: str,
        answer: str,
        sources: list[SourceSnippet],
    ) -> None:
        """保存一轮问答记录到数据库，并更新会话的 updated_at 时间戳。"""
        self.db.add(ConversationMessage(conversation_id=conversation_id, role="user", content=question))
        self.db.add(
            ConversationMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=answer,
                sources=json.dumps([item.model_dump() for item in sources], ensure_ascii=False),
            )
        )
        conversation = self.db.get(Conversation, conversation_id)
        if conversation:
            conversation.updated_at = datetime.now(timezone.utc)
        self.db.commit()

    # ------------------------------------------------------------------
    # 响应构建
    # ------------------------------------------------------------------
    def conversation_summary(self, conversation: Conversation) -> ConversationSummary:
        """构建会话摘要信息，包含消息总数和最后一条消息的前 120 字符。"""
        latest = (
            self.db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.id.desc())
            .first()
        )
        message_count = (
            self.db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation.id)
            .count()
        )
        return ConversationSummary(
            id=conversation.id,
            title=conversation.title,
            is_favorite=bool(conversation.is_favorite),
            message_count=message_count,
            last_message=(latest.content[:120] if latest else ""),
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    def message_response(self, message: ConversationMessage) -> ConversationMessageResponse:
        """将数据库消息对象转换为响应模型，处理 sources 字段的 JSON 反序列化。"""
        sources: list[SourceSnippet] = []
        try:
            raw_sources = json.loads(message.sources or "[]")
            sources = [SourceSnippet(**item) for item in raw_sources if isinstance(item, dict)]
        except (json.JSONDecodeError, TypeError, ValueError):
            sources = []
        return ConversationMessageResponse(
            id=message.id,
            role=message.role,
            content=message.content,
            message_type=message.message_type,
            sources=sources,
            created_at=message.created_at,
        )


def chars(messages: list[dict[str, str]]) -> int:
    """消息列表的总字符数，作为上下文规模的粗估。"""
    return sum(len(item["content"]) for item in messages)
