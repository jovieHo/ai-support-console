"""客服应答流水线：检索、生成、风险检查和草稿落库。

分类与检索并行执行（asyncio.gather）：两者没有数据依赖，串行会把
两次耗时叠加。分类任务在内部完成降级——LLM 结构化分类失败时直接
返回规则结果，绝不让自己的异常拖垮 gather 里的检索任务。
"""

from __future__ import annotations

import asyncio
import time
from typing import TypedDict

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session

from models import CustomerConsultation
from prompts.templates import CLASSIFICATION_PROMPT, CUSTOMER_SERVICE_PROMPT
from schemas import AgentClassification, AgentResponse, SourceSnippet
from services.llm_service import LLMService
from services.rag_service import RAGService
from services.telemetry import elapsed_ms
from tools.business_tools import query_business_summary
from tools.taxonomy import classify

# 高风险表述 -> 命中后展示给客服的可读标签
RISK_RULES: dict[str, str] = {
    "保证赚钱": "承诺收益",
    "绝对": "绝对化表述",
    "无条件赔偿": "越权承诺",
}


class AgentState(TypedDict):
    """客服流水线内部状态。"""
    question: str
    customer_name: str
    category: str
    sources: list[SourceSnippet]
    query_result: str
    reply: str
    risk_flags: list[str]
    action: str
    consultation_id: int | None
    trace: list[str]
    # 结构化分类产物（规则降级时 intent 为空、其余取默认值）
    intent: str
    urgency: str
    needs_human: bool
    missing_information: list[str]
    classification_source: str
    # 拼给模型的上下文总字符数，仅供埋点统计
    prompt_chars: int


def _rule_classification(question: str) -> AgentClassification:
    """关键词规则分类的降级结果，字段取值与结构化模型的默认口径一致。"""
    return AgentClassification(category=classify(question))


class AgentService:
    """客服应答服务：分类与检索并行，生成、风险检查顺序执行。"""

    def __init__(self, db: Session) -> None:
        """初始化服务，注入数据库会话、LLM 和 RAG 服务。"""
        self.db = db
        self.llm = LLMService()
        self.rag = RAGService(db)
        # 结构化分类链：PydanticOutputParser 负责两件事——
        # get_format_instructions() 把 JSON 格式要求注入提示词；
        # 解析时校验 category/urgency 枚举与字段类型，越界即抛错触发降级
        self._classifier_parser = PydanticOutputParser(pydantic_object=AgentClassification)
        self._classify_chain = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", CLASSIFICATION_PROMPT),
                    ("human", "客户名称：{customer_name}\n客户问题：{question}"),
                ]
            )
            .partial(format_instructions=self._classifier_parser.get_format_instructions())
            | self.llm.as_runnable()
            | self._classifier_parser
        )
        # 最近一次执行的埋点数据，由调用方读取后交给 services.telemetry 落库。
        # is_success 初始 False，跑完整条流水线才置 True——中途抛异常自然留下失败记录
        self.telemetry: dict = {
            "retrieval_mode": "none",
            "sources": [],
            "retrieval_ms": 0,
            "llm_ms": 0,
            "prompt_chars": 0,
            "is_faq_direct": False,
            "is_success": False,
            "is_escalated": False,
        }

    # ------------------------------------------------------------------
    # 流水线入口
    # ------------------------------------------------------------------
    async def run_customer_workflow(self, question: str, customer_name: str) -> AgentResponse:
        """执行客服应答流水线。"""
        state: AgentState = {
            "question": question,
            "customer_name": customer_name,
            "category": "",
            "sources": [],
            "query_result": "",
            "reply": "",
            "risk_flags": [],
            "action": "pass",
            "consultation_id": None,
            "trace": [],
            "intent": "",
            "urgency": "normal",
            "needs_human": False,
            "missing_information": [],
            "classification_source": "rules",
            "prompt_chars": 0,
        }

        # 分类与检索并行：没有数据依赖（分类只喂回复提示词），串行会白叠一跳 LLM 延迟。
        # FAQ 强命中时分类调用会白跑——已经发生的调用无法撤销，这是并行换延迟的固定成本。
        (classification, class_source), sources = await asyncio.gather(
            self._classify(question, customer_name),
            self._timed_retrieve(question),
        )
        state["sources"] = sources
        state["query_result"] = f"知识库命中：{self._format_sources(sources)}"
        state["category"] = classification.category
        state["intent"] = classification.intent
        state["urgency"] = classification.urgency
        state["needs_human"] = classification.needs_human
        state["missing_information"] = classification.missing_information
        state["classification_source"] = class_source
        state["trace"].append(
            f"检索：知识库（命中 {len(sources)} 条片段）"
            if sources
            else "检索：知识库（未命中片段）"
        )
        if class_source == "llm":
            state["trace"].append(
                f"分类：结构化输出（{classification.category} / {classification.intent or '意图未识别'}"
                f" / 紧急度 {classification.urgency}）"
            )
        else:
            state["trace"].append(
                f"分类：LLM 结构化分类失败，降级关键词规则（{classification.category}）"
            )
        if classification.missing_information:
            state["trace"].append(
                f"信息抽取：回答前还缺 {'、'.join(classification.missing_information)}"
            )

        hit = self.rag.direct_faq_hit
        if hit:
            state["sources"] = [hit]
            state["reply"] = RAGService.faq_answer_text(hit)
            state["trace"].append("生成：FAQ 强命中，直接采用标准答案，未调用大模型")
            self.telemetry["is_faq_direct"] = True
        elif state["missing_information"]:
            # 信息不全硬答会误导，先问清楚；缺什么由分类模型判定
            state["reply"] = self._clarify_reply(state["missing_information"])
            state["trace"].append(
                f"生成：信息不足，先反问需补 {len(state['missing_information'])} 项，未调用大模型"
            )
        else:
            llm_started = time.perf_counter()
            try:
                state = await self._reply_agent(state)
            except Exception:
                self.telemetry["llm_ms"] = elapsed_ms(llm_started)
                raise
            self.telemetry["llm_ms"] = elapsed_ms(llm_started)
        state = self._guard(state)
        self._persist(state)

        # 走完全流程才置成功；上面任何一步抛异常，埋点里留下的是 is_success=False
        self.telemetry.update(
            sources=state["sources"],
            prompt_chars=state["prompt_chars"],
            is_success=True,
            is_escalated=state["action"] == "escalate",
        )

        return AgentResponse(
            category=state["category"],
            reply=state["reply"],
            sources=state["sources"],
            risk_flags=state["risk_flags"],
            action=state["action"],
            consultation_id=state["consultation_id"],
            trace=state["trace"],
            classification_source=state["classification_source"],
            intent=state["intent"],
            urgency=state["urgency"],
            needs_human=state["needs_human"],
            missing_information=state["missing_information"],
        )

    # ------------------------------------------------------------------
    # 结构化分类（并行步之一，内部自带降级）
    # ------------------------------------------------------------------
    async def _classify(self, question: str, customer_name: str) -> tuple[AgentClassification, str]:
        """结构化分类；LLM 超时/接口失败/输出不符合 schema 时降级规则分类。

        异常在这里就地消化，返回 (结果, 来源)，绝不向外抛——
        gather 的另一端是检索，分类失败不能拖垮整条流水线。
        """
        try:
            result = await self._classify_chain.ainvoke(
                {"question": question, "customer_name": customer_name or "匿名客户"}
            )
            return result, "llm"
        except Exception:
            return _rule_classification(question), "rules"

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    async def _timed_retrieve(self, question: str) -> list[SourceSnippet]:
        """检索并单独计时。

        latency_retrieval_ms 只该含检索——并行段总耗时里还混着分类那次
        LLM 调用，直接记进去会让「平均检索耗时」指标虚高，也不可与 /chat 比较。
        """
        started = time.perf_counter()
        try:
            return await self.rag.retrieve(question, top_k=3)
        finally:
            self.telemetry["retrieval_ms"] = elapsed_ms(started)
            self.telemetry["retrieval_mode"] = self.rag.last_retrieval_mode

    @staticmethod
    def _format_sources(sources: list[SourceSnippet]) -> str:
        """把知识片段拼成提示词上下文。"""
        if not sources:
            return "未检索到相关片段"
        return "\n".join(f"[{item.source}] {item.content}" for item in sources)

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------
    async def _reply_agent(self, state: AgentState) -> AgentState:
        """调用 LLM 生成回复；FAQ 直出与信息不足反问两条路径不会进入这里。"""
        summary = query_business_summary(self.db)
        messages = [
            {"role": "system", "content": CUSTOMER_SERVICE_PROMPT},
            {
                "role": "user",
                "content": (
                    f"客户：{state['customer_name']}\n分类：{state['category']}\n"
                    f"问题：{state['question']}\n资料：{state['query_result']}\n平台数据：{summary}"
                ),
            },
        ]
        state["prompt_chars"] = sum(len(item["content"]) for item in messages)
        state["reply"] = await self.llm.chat(messages)
        state["trace"].append("生成：已产出回复草稿")
        return state

    @staticmethod
    def _clarify_reply(missing: list[str]) -> str:
        """信息不全时先反问，只问必要的，最多两项。"""
        return (
            "为了给您准确的处理结果，还需要您补充以下信息："
            f"{'、'.join(missing[:2])}。补齐后我再帮您确认。"
        )

    # ------------------------------------------------------------------
    # 风险检查
    # ------------------------------------------------------------------
    def _guard(self, state: AgentState) -> AgentState:
        """输出风险类型和处置动作，不伪造连续评分。"""
        flags = [label for word, label in RISK_RULES.items() if word in state["reply"]]
        state["risk_flags"] = flags
        state["action"] = "escalate" if flags else "pass"
        if flags:
            state["trace"].append(f"风险检查：命中 {'、'.join(flags)}，转人工复核")
        else:
            state["trace"].append("风险检查：未发现高风险表述")
        return state

    def _persist(self, state: AgentState) -> None:
        """保存草稿；失败时保留回复并在执行轨迹中提示人工登记。"""
        try:
            # 优先级：风险升级 5 > 分类判断需人工/高紧急 4 > 普通 3。
            # needs_human/urgency 只影响排序，转人工复核仍由风险检查把关
            priority = 5 if state["action"] == "escalate" else (
                4 if (state["needs_human"] or state["urgency"] == "high") else 3
            )
            record = CustomerConsultation(
                customer_name=state["customer_name"] or "匿名客户",
                question=state["question"],
                category=state["category"],
                priority=priority,
                status="pending" if state["action"] == "escalate" else "resolved",
                ai_reply=state["reply"],
            )
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            state["consultation_id"] = record.id
            label = "待人工复核记录" if state["action"] == "escalate" else "回复草稿"
            state["trace"].append(f"处置：已保存{label} #{record.id}")
        except Exception:
            self.db.rollback()
            state["trace"].append("处置：记录写入失败，请人工登记")
