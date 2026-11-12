"""混合检索与结构化分类的针对性测试。

覆盖：RRF 融合与展示分归一化、BM25 术语命中、FAQ 直出阈值、
结构化分类降级与 classification_source、AI 指标聚合、埋点写入、
多轮查询改写、信息不足反问分支。

从 backend 目录执行：
    ./.venv/Scripts/python -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from langchain_core.documents import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import AiInvocation, KnowledgeChunk
from schemas import AgentClassification, SourceSnippet
from services.agent_service import AgentService
from services.analytics_service import AnalyticsService
from services.bm25_service import BM25Service, ChunkRef
from services.query_rewrite import MAX_REWRITE_CHARS, QueryRewriter, needs_rewrite
from services.rag_service import RAGService
from services.telemetry import ENTRY_ASSIST, record_invocation


def make_session():
    """建一个内存 SQLite 会话，用于检索与指标测试。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def vector_doc(chunk_id: int, content: str, source: str = "demo.txt") -> Document:
    """构造 Chroma retriever 返回的文档形态。"""
    return Document(page_content=content, metadata={"chunk_id": chunk_id, "source": source})


class RRFFusionTests(unittest.TestCase):
    """RRF 融合：排序用原始分，展示分按结果集最高分归一化。"""

    def setUp(self) -> None:
        self.rag = RAGService.__new__(RAGService)

    def test_single_path_top_score_is_one(self) -> None:
        """只命中一路时，最高展示分也必须是 1.0"""
        snippets = self.rag._rrf_fuse(
            [vector_doc(1, "甲"), vector_doc(2, "乙")],
            [],
            top_k=5,
        )
        self.assertEqual(snippets[0].score, 1.0)
        # 第二名 1/(60+2) 相对第一名 1/(60+1)
        self.assertAlmostEqual(snippets[1].score, round(61 / 62, 4), places=4)

    def test_dual_hit_accumulates_and_ranks_first(self) -> None:
        """两路都命中的分块分数相加，压过只被一路命中的分块。"""
        snippets = self.rag._rrf_fuse(
            [vector_doc(9, "两路都中"), vector_doc(3, "只命中向量")],
            [ChunkRef(9, "demo.txt", "两路都中")],
            top_k=5,
        )
        self.assertEqual(snippets[0].content, "两路都中")
        self.assertEqual(snippets[0].score, 1.0)
        # 只命中向量的分块 rank=2：1/(60+2) 相对 2/(60+1)
        self.assertAlmostEqual(snippets[1].score, round(61 / 124, 4), places=4)

    def test_scores_never_exceed_one(self) -> None:
        snippets = self.rag._rrf_fuse([vector_doc(1, "甲")], [ChunkRef(1, "demo.txt", "甲")], top_k=5)
        self.assertTrue(all(0 <= item.score <= 1.0 for item in snippets))

    def test_empty_inputs_return_empty(self) -> None:
        self.assertEqual(self.rag._rrf_fuse([], [], top_k=5), [])


class BM25Tests(unittest.TestCase):
    """BM25 词法路：错误码这类精确符号必须靠字面命中。"""

    def setUp(self) -> None:
        # 索引是进程级缓存，用例之间必须重置，否则会互相污染
        BM25Service._bm25 = None
        BM25Service._refs = []
        BM25Service._token_sets = []
        BM25Service._indexed_count = -1
        self.db = make_session()
        self.db.add_all(
            [
                KnowledgeChunk(
                    document_id=None,
                    content="错误码 E4021 表示登录凭证过期，请退出后重新登录。",
                    source="06-常见故障排查.txt",
                    embedding_text="错误码 E4021 表示登录凭证过期，请退出后重新登录。",
                ),
                KnowledgeChunk(
                    document_id=None,
                    content="企业版一年 9800 元，含专属客户成功经理。",
                    source="05-企业版差异.txt",
                    embedding_text="企业版一年 9800 元，含专属客户成功经理。",
                ),
            ]
        )
        self.db.commit()

    def test_error_code_hits_lexically(self) -> None:
        hits = BM25Service(self.db).search("E4021 报错", top_k=2)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].source, "06-常见故障排查.txt")

    def test_unrelated_query_returns_nothing(self) -> None:
        self.assertEqual(BM25Service(self.db).search("E9999", top_k=2), [])

    def test_empty_query_returns_nothing(self) -> None:
        self.assertEqual(BM25Service(self.db).search("   ", top_k=2), [])


class FaqDirectTests(unittest.TestCase):
    """FAQ 直出判定只认原始分，不认展示分。"""

    @staticmethod
    def faq_snippet(score: float, faq_score: float) -> SourceSnippet:
        return SourceSnippet(
            source="FAQ：billing #1",
            content="问：企业版多少钱\n答：一年 9800 元",
            score=score,
            faq_score=faq_score,
        )

    def test_display_score_does_not_drive_threshold(self) -> None:
        self.assertIsNone(RAGService.pick_direct_faq([self.faq_snippet(score=1.0, faq_score=0.5)]))

    def test_raw_score_above_threshold_direct_hits(self) -> None:
        hit = RAGService.pick_direct_faq([self.faq_snippet(score=0.6, faq_score=0.95)])
        self.assertIsNotNone(hit)
        self.assertEqual(RAGService.faq_answer_text(hit), "一年 9800 元")

    def test_document_snippet_never_direct_hits(self) -> None:
        doc = SourceSnippet(source="文档：x.txt", content="片段", score=1.0)
        self.assertIsNone(RAGService.pick_direct_faq([doc]))


class DirectFaqDecouplingTests(unittest.IsolatedAsyncioTestCase):
    """FAQ 直出判定与 top_k 截断解耦。

    文档路展示分归一化后恒有 1.0，会把 FAQ 的 0.95 挤出 top_k；
    判定必须发生在截断之前，否则文档命中时直出永远不触发。
    """

    async def test_faq_hit_survives_document_pressure(self) -> None:
        svc = RAGService.__new__(RAGService)
        svc.last_retrieval_mode = "none"
        svc.direct_faq_hit = None

        async def fake_vector(_question, _top_k):
            return [
                Document(page_content=f"文档片段 {index}", metadata={"chunk_id": index, "source": "doc.txt"})
                for index in range(3)
            ]

        svc._vector_retrieve = fake_vector
        svc.bm25 = SimpleNamespace(search=lambda _q, _k: [])
        svc._faq_retrieve = lambda _q, _k: [
            SourceSnippet(source="FAQ：refund #1", content="问：退款\n答：三个工作日", score=0.95, faq_score=0.95)
        ]

        result = await svc.retrieve("退款", 3)

        self.assertIsNotNone(svc.direct_faq_hit)
        # top_k 里全是文档（1.0 压过 0.95），但直出判定仍然成立
        self.assertTrue(all(item.source.startswith("文档") for item in result))
        # 直出时检索路径必须记 faq，不能被文档路的命中抢记成 hybrid/vector
        self.assertEqual(svc.last_retrieval_mode, "faq")


class ClassificationFallbackTests(unittest.IsolatedAsyncioTestCase):
    """结构化分类：LLM 成功用模型结果，任何异常降级规则分类。"""

    class _BrokenChain:
        async def ainvoke(self, _payload: dict):
            raise RuntimeError("模型超时")

    class _StubChain:
        def __init__(self, result: AgentClassification) -> None:
            self.result = result

        async def ainvoke(self, _payload: dict) -> AgentClassification:
            return self.result

    def service(self, chain) -> AgentService:
        service = AgentService.__new__(AgentService)
        service._classify_chain = chain
        return service

    async def test_llm_failure_falls_back_to_rules(self) -> None:
        result, source = await self.service(self._BrokenChain())._classify("企业版价格是多少", "张三")
        self.assertEqual(source, "rules")
        self.assertEqual(result.category, "price")
        self.assertEqual(result.urgency, "normal")
        self.assertEqual(result.missing_information, [])

    async def test_llm_success_keeps_structured_result(self) -> None:
        expected = AgentClassification(
            category="complaint",
            intent="要求退款",
            urgency="high",
            needs_human=True,
            missing_information=["订单号"],
        )
        result, source = await self.service(self._StubChain(expected))._classify("我要投诉并退款", "李四")
        self.assertEqual(source, "llm")
        self.assertIs(result, expected)


class MetricsTests(unittest.TestCase):
    """AI 指标聚合口径：FAQ 直出不计入模型耗时与首字延迟。"""

    def setUp(self) -> None:
        self.db = make_session()
        self.db.add_all(
            [
                AiInvocation(
                    retrieval_mode="hybrid",
                    is_faq_direct=True,
                    latency_retrieval_ms=100,
                    latency_llm_ms=0,
                    ttft_ms=None,
                    is_success=True,
                ),
                AiInvocation(
                    retrieval_mode="hybrid",
                    is_faq_direct=False,
                    latency_retrieval_ms=120,
                    latency_llm_ms=800,
                    ttft_ms=300,
                    is_success=True,
                ),
                AiInvocation(
                    retrieval_mode="bm25",
                    is_faq_direct=False,
                    latency_retrieval_ms=80,
                    latency_llm_ms=1000,
                    ttft_ms=500,
                    is_success=False,
                ),
            ]
        )
        self.db.commit()

    def test_aggregation(self) -> None:
        metrics = AnalyticsService(self.db)._ai_metrics()
        self.assertEqual(metrics["total_invocations"], 3)
        self.assertAlmostEqual(metrics["faq_direct_rate"], 0.3333, places=4)
        self.assertAlmostEqual(metrics["failure_rate"], 0.3333, places=4)
        self.assertEqual(metrics["avg_retrieval_ms"], 100)
        # 只统计非 FAQ 直出的两次：(800 + 1000) / 2
        self.assertEqual(metrics["avg_llm_ms"], 900)


class TelemetryRecordTests(unittest.TestCase):
    """埋点写入：命中数与最高分从 sources 算，入口与转人工标记按参数落库。"""

    def setUp(self) -> None:
        self.db = make_session()

    def test_record_assist_escalated(self) -> None:
        sources = [
            SourceSnippet(source="文档：退款规则", content="退款需 7 个工作日", score=0.62),
            SourceSnippet(source="FAQ：退款 #1", content="问：能退吗\n答：可以", score=0.91),
        ]
        record_invocation(
            self.db,
            entry=ENTRY_ASSIST,
            retrieval_mode="hybrid",
            sources=sources,
            retrieval_ms=180,
            llm_ms=640,
            prompt_chars=520,
            is_success=True,
            is_escalated=True,
        )
        row = self.db.query(AiInvocation).one()
        self.assertEqual(row.entry, ENTRY_ASSIST)
        self.assertEqual(row.retrieval_mode, "hybrid")
        self.assertEqual(row.hit_count, 2)
        self.assertAlmostEqual(row.top_score, 0.91, places=4)
        self.assertTrue(row.is_escalated)
        # assist 没有会话上下文
        self.assertIsNone(row.conversation_id)

    def test_record_without_sources(self) -> None:
        record_invocation(
            self.db,
            entry=ENTRY_ASSIST,
            retrieval_mode="none",
            sources=[],
            retrieval_ms=0,
            llm_ms=0,
            is_success=False,
        )
        row = self.db.query(AiInvocation).one()
        self.assertEqual(row.hit_count, 0)
        self.assertEqual(row.top_score, 0.0)
        self.assertFalse(row.is_escalated)
        self.assertFalse(row.is_success)


class _FakeRewriteChain:
    """记录调用次数的假链，用来验证「该不该改写」的判定。"""

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def ainvoke(self, _payload: dict) -> str:
        self.calls += 1
        return self.text


class _BrokenRewriteChain:
    async def ainvoke(self, _payload: dict) -> str:
        raise RuntimeError("llm down")


class QueryRewriteTests(unittest.IsolatedAsyncioTestCase):
    """只对指代型追问做改写，其余问题不得多花一次模型调用。"""

    @staticmethod
    def make_rewriter(chain) -> QueryRewriter:
        rewriter = QueryRewriter()
        rewriter.llm = SimpleNamespace(settings=SimpleNamespace(llm_api_key="test-key"))
        rewriter._chain = chain
        return rewriter

    def test_detects_follow_up(self) -> None:
        self.assertTrue(needs_rewrite("那它呢"))
        self.assertTrue(needs_rewrite("多少钱"))
        self.assertFalse(needs_rewrite("企业版退款要多久到账"))

    async def test_first_turn_not_rewritten(self) -> None:
        chain = _BrokenRewriteChain()
        self.assertEqual(await self.make_rewriter(chain).rewrite("那它呢", []), "那它呢")

    async def test_standalone_question_not_rewritten(self) -> None:
        chain = _FakeRewriteChain("企业版退款要多久到账")
        result = await self.make_rewriter(chain).rewrite("企业版退款要多久到账", ["客户：退款要多久"])
        self.assertEqual(result, "企业版退款要多久到账")
        self.assertEqual(chain.calls, 0)

    async def test_follow_up_uses_rewritten_question(self) -> None:
        chain = _FakeRewriteChain("企业版退款要多久到账")
        rewriter = self.make_rewriter(chain)
        result = await rewriter.rewrite("那它呢", ["客户：退款要多久", "客服：7 个工作日"])
        self.assertEqual(result, "企业版退款要多久到账")
        self.assertEqual(chain.calls, 1)

    async def test_falls_back_when_llm_fails(self) -> None:
        rewriter = self.make_rewriter(_BrokenRewriteChain())
        self.assertEqual(await rewriter.rewrite("那它呢", ["客户：退款要多久"]), "那它呢")

    async def test_rejects_overlong_output(self) -> None:
        rewriter = self.make_rewriter(_FakeRewriteChain("退" * (MAX_REWRITE_CHARS + 1)))
        self.assertEqual(await rewriter.rewrite("那它呢", ["客户：退款要多久"]), "那它呢")

    async def test_skips_without_api_key(self) -> None:
        """无 key 时 chat() 返回降级话术，绝不能当检索词。"""
        chain = _FakeRewriteChain("这是本地降级 AI 回复")
        rewriter = QueryRewriter()
        rewriter.llm = SimpleNamespace(settings=SimpleNamespace(llm_api_key=""))
        rewriter._chain = chain
        self.assertEqual(await rewriter.rewrite("那它呢", ["客户：退款要多久"]), "那它呢")
        self.assertEqual(chain.calls, 0)


class ClarifyBranchTests(unittest.IsolatedAsyncioTestCase):
    """缺关键信息时先反问，且不调模型。"""

    async def test_missing_information_clarifies_without_llm(self) -> None:
        service = AgentService.__new__(AgentService)
        service.telemetry = {
            "retrieval_mode": "none",
            "sources": [],
            "retrieval_ms": 0,
            "llm_ms": 0,
            "prompt_chars": 0,
            "is_faq_direct": False,
            "is_success": False,
            "is_escalated": False,
        }
        service.rag = SimpleNamespace(direct_faq_hit=None, last_retrieval_mode="vector")

        async def fake_classify(_question, _name):
            return AgentClassification(category="technical", missing_information=["设备型号"]), "llm"

        async def fake_retrieve(_question):
            return []

        reply_called: list[int] = []

        async def fake_reply(state):
            reply_called.append(1)
            return state

        service._classify = fake_classify
        service._timed_retrieve = fake_retrieve
        service._reply_agent = fake_reply
        service._persist = lambda _state: None

        response = await service.run_customer_workflow("我的设备坏了", "张三")

        self.assertEqual(reply_called, [])
        self.assertIn("设备型号", response.reply)
        self.assertTrue(any("信息不足" in line for line in response.trace))


if __name__ == "__main__":
    unittest.main()
