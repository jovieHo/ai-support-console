"""AI 对话路由：支持普通调用和 SSE 流式调用，管理会话历史。"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.deps import CurrentUser, DbSession
from schemas import (
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationSummary,
    ConversationUpdate,
)
from services.chat_service import ChatService, chars
from services.llm_service import LLMService
from services.rag_service import RAGService
from services.telemetry import ENTRY_CHAT, elapsed_ms, record_invocation

router = APIRouter(prefix="/chat", tags=["AI 对话"])


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, current_user: CurrentUser, db: DbSession) -> ChatResponse:
    """发送消息给 AI 并获取完整回复，自动关联知识库检索结果。"""
    service = ChatService(db)
    prepared = await service.prepare(current_user.id, payload)
    if prepared.direct_hit:
        answer = RAGService.faq_answer_text(prepared.direct_hit)
        service.save_messages(prepared.conversation_id, payload.message, answer, [prepared.direct_hit])
        record_invocation(db, entry=ENTRY_CHAT, conversation_id=prepared.conversation_id,
                          retrieval_mode=prepared.retrieval_mode, sources=[prepared.direct_hit],
                          retrieval_ms=prepared.retrieval_ms, llm_ms=0, is_faq_direct=True)
        return ChatResponse(conversation_id=prepared.conversation_id, answer=answer, sources=[prepared.direct_hit])
    messages = service.build_messages(prepared.conversation_id, payload.message, prepared.sources, payload.memory_type)
    llm_started = time.perf_counter()
    try:
        answer = await LLMService().chat(messages)
    except Exception:
        record_invocation(db, entry=ENTRY_CHAT, conversation_id=prepared.conversation_id,
                          retrieval_mode=prepared.retrieval_mode, sources=prepared.sources,
                          prompt_chars=chars(messages), retrieval_ms=prepared.retrieval_ms,
                          llm_ms=elapsed_ms(llm_started), is_success=False)
        raise
    service.save_messages(prepared.conversation_id, payload.message, answer, prepared.sources)
    record_invocation(db, entry=ENTRY_CHAT, conversation_id=prepared.conversation_id,
                      retrieval_mode=prepared.retrieval_mode, sources=prepared.sources,
                      prompt_chars=chars(messages), retrieval_ms=prepared.retrieval_ms,
                      llm_ms=elapsed_ms(llm_started))
    return ChatResponse(conversation_id=prepared.conversation_id, answer=answer, sources=prepared.sources)


@router.post("/stream")
async def stream_chat(payload: ChatRequest, current_user: CurrentUser, db: DbSession) -> StreamingResponse:
    """通过 Server-Sent Events 流式返回 AI 回复，实现打字机效果。"""
    started = time.perf_counter()
    service = ChatService(db)
    prepared = await service.prepare(current_user.id, payload)

    async def event_stream():
        if prepared.direct_hit:
            answer = RAGService.faq_answer_text(prepared.direct_hit)
            service.save_messages(prepared.conversation_id, payload.message, answer, [prepared.direct_hit])
            record_invocation(db, entry=ENTRY_CHAT, conversation_id=prepared.conversation_id,
                              retrieval_mode=prepared.retrieval_mode, sources=[prepared.direct_hit],
                              retrieval_ms=prepared.retrieval_ms, llm_ms=0,
                              ttft_ms=elapsed_ms(started), is_faq_direct=True)
            yield f"data: {json.dumps({'type': 'delta', 'content': answer}, ensure_ascii=False)}\n\n"
        else:
            messages = service.build_messages(prepared.conversation_id, payload.message, prepared.sources, payload.memory_type)
            answer_parts: list[str] = []
            llm_started = time.perf_counter()
            ttft_ms: int | None = None
            try:
                async for chunk in LLMService().stream_chat(messages):
                    # 首字延迟从收到请求算起，含检索，这才是用户体感的那段时间
                    if ttft_ms is None:
                        ttft_ms = elapsed_ms(started)
                    answer_parts.append(chunk)
                    yield f"data: {json.dumps({'type': 'delta', 'content': chunk}, ensure_ascii=False)}\n\n"
            except Exception:
                record_invocation(db, entry=ENTRY_CHAT, conversation_id=prepared.conversation_id,
                                  retrieval_mode=prepared.retrieval_mode, sources=prepared.sources,
                                  prompt_chars=chars(messages), retrieval_ms=prepared.retrieval_ms,
                                  llm_ms=elapsed_ms(llm_started), ttft_ms=ttft_ms, is_success=False)
                raise
            answer = "".join(answer_parts)
            service.save_messages(prepared.conversation_id, payload.message, answer, prepared.sources)
            record_invocation(db, entry=ENTRY_CHAT, conversation_id=prepared.conversation_id,
                              retrieval_mode=prepared.retrieval_mode, sources=prepared.sources,
                              prompt_chars=chars(messages), retrieval_ms=prepared.retrieval_ms,
                              llm_ms=elapsed_ms(llm_started), ttft_ms=ttft_ms)
        done_sources = [prepared.direct_hit] if prepared.direct_hit else prepared.sources
        done = {"type": "done", "conversation_id": prepared.conversation_id, "sources": [item.model_dump() for item in done_sources]}
        yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/conversations")
def conversations(current_user: CurrentUser, db: DbSession, favorite: bool | None = None) -> dict:
    """查询当前用户的所有对话会话，支持按收藏状态筛选。"""
    items = ChatService(db).list_conversations(current_user.id, favorite)
    return {"total": len(items), "items": items}


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def conversation_detail(conversation_id: int, current_user: CurrentUser, db: DbSession) -> ConversationDetail:
    """获取指定会话的完整信息，包括所有对话消息。"""
    return ChatService(db).conversation_detail(current_user.id, conversation_id)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, current_user: CurrentUser, db: DbSession) -> dict:
    """删除指定会话及其关联的所有对话消息（物理删除）。"""
    ChatService(db).delete_conversation(current_user.id, conversation_id)
    return {"ok": True, "message": "会话已删除"}


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
def update_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> ConversationSummary:
    """修改会话的标题和/或收藏状态，支持部分更新。"""
    return ChatService(db).update_conversation(current_user.id, conversation_id, payload)
