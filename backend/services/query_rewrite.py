"""多轮检索的查询改写。

历史消息只喂给生成模型，检索拿到的仍是当前这句原文；「那它呢」这类
指代型问题直接进向量库必然召回偏。这里在检索前把问题补全成独立问句。
只在多轮、且当前问题确实是指代/省略时才改写：改写要多一次模型调用，

"""

from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from prompts.templates import REWRITE_PROMPT
from services.llm_service import LLMService

# 少于这个长度的问题大概率省略了主语
SHORT_QUESTION_CHARS = 8

# 显式指代/追问标记
FOLLOW_UP_MARKERS = ("它", "这个", "那个", "那", "还有", "呢", "上述", "刚才", "前面", "同一个")

# 改写结果异常长时按失败处理，避免把解释性文字塞进检索
MAX_REWRITE_CHARS = 60


def needs_rewrite(question: str) -> bool:
    """判断当前问题是否依赖上下文才能看懂。"""
    text = question.strip()
    return len(text) <= SHORT_QUESTION_CHARS or any(marker in text for marker in FOLLOW_UP_MARKERS)


class QueryRewriter:
    """把指代型问题改写成独立问句；任何异常都退回原问题。"""

    def __init__(self) -> None:
        self.llm = LLMService()
        self._chain = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", REWRITE_PROMPT),
                    ("human", "最近对话：\n{history}\n\n当前问题：{question}"),
                ]
            )
            | self.llm.as_runnable()
            | StrOutputParser()
        )

    async def rewrite(self, question: str, history: list[str]) -> str:
        """history 为空（首轮）或不需改写时原样返回。"""
        # 没有 key 时 chat() 返回的是本地降级话术，不能当检索词用
        if not history or not self.llm.settings.llm_api_key or not needs_rewrite(question):
            return question
        try:
            text = await self._chain.ainvoke({"history": "\n".join(history), "question": question})
        except Exception:
            return question
        text = text.strip().strip('"').strip()
        if not text or len(text) > MAX_REWRITE_CHARS:
            return question
        return text
