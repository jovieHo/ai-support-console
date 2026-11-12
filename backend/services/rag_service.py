"""文档入库、FAQ/文档联合检索和 RAG 问答。

检索链路：文档解析 → 段落切分（ParagraphSplitter）→ 向量 + BM25 双路
→ RRF 融合 → FAQ 强命中直出 → 带来源的答案生成。
"""

from __future__ import annotations

import asyncio
import difflib
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session

from core.cache import Cache
from core.config import get_settings
from models import FAQ, KnowledgeChunk, KnowledgeDocument
from prompts.templates import KNOWLEDGE_QUERY_PROMPT
from schemas import KnowledgeQueryResponse, SourceSnippet
from services.bm25_service import BM25Service
from services.embedding_service import EmbeddingService
from services.llm_service import LLMService
from tools.chunking import DEFAULT_CHUNK_SIZE, STRATEGY, ParagraphSplitter
from tools.tokenize import tokenize


class RAGService:
    """RAG 服务：文档入库、混合检索（向量 + BM25 → RRF 融合）与缓存。"""

    # RRF 融合的平滑常数：rank 越靠后贡献越小，60 是论文推荐的经验值
    RRF_K = 60

    # FAQ 直出阈值：比对 faq_score（不含 +0.05 展示加分的原始命中分）。
    # 达到该值即视为提问与标准问法同义，跳过模型直接采用人工答案
    FAQ_DIRECT_THRESHOLD = 0.85
    # 字符相似度阈值：提问与 FAQ 问句的字符级相似度达到该值视为同义问法。
    # 定在 0.75 而不是更低：0.65 会把「企业版多少钱」判成「专业版一年多少钱」
    FAQ_SIMILARITY_THRESHOLD = 0.75

    def __init__(self, db: Session) -> None:
        self.db = db
        self.llm = LLMService()
        self.embedding = EmbeddingService()
        self.bm25 = BM25Service(db)
        self.cache = Cache()
        # 上一次 retrieve() 走通的检索路：hybrid / vector / bm25 / faq / none，仅供埋点读取。
        # RAGService 每次请求新建，实例级状态不会跨请求串味。
        self.last_retrieval_mode = "none"
        # 上一次 retrieve() 判定出的可直出 FAQ 片段。判定发生在 top_k 截断
        # 之前（文档路归一化后展示分恒有 1.0，会把 FAQ 挤出 top_k，截断后再
        # 判等于永远判不到），调用方直接读它，不再自己扫检索结果。
        self.direct_faq_hit = None
        # 生成链：ChatPromptTemplate 组装消息 → llm.as_runnable() 适配裸 httpx 的 LLMService
        self._qa_chain = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", KNOWLEDGE_QUERY_PROMPT),
                    ("human", "问题：{question}\n\n知识片段：\n{context}"),
                ]
            )
            | self.llm.as_runnable()
            | StrOutputParser()
        )

    # 文档入库

    async def ingest_upload(self, upload: UploadFile, chunk_size: int = DEFAULT_CHUNK_SIZE) -> KnowledgeDocument:
        """解析上传文件，保存原文、分块和向量。"""
        raw = await upload.read()
        text = self._extract_text(upload.filename, raw)
        source = upload.filename or "upload.txt"
        docs = ParagraphSplitter(chunk_size).split_to_documents(text, source)
        chunks = [doc.page_content for doc in docs]
        longest = max((len(chunk) for chunk in chunks), default=0)
        if chunks:
            message = f"已解析 {len(text)} 个字符，按段落生成 {len(chunks)} 个知识分块（最长 {longest} 字）"
            if longest > chunk_size:
                message += f"；有段落超过 {chunk_size} 字上限，已让它独占一块而非拦腰截断"
        else:
            message = "未从文件中解析到文本内容，未生成知识分块"
        document = KnowledgeDocument(
            filename=source,
            content_type=upload.content_type or "text/plain",
            chunk_count=len(chunks),
            segment_rule=f"{STRATEGY}-{chunk_size}",
            parse_status="indexed" if chunks else "empty",
            parse_message=message,
            parsed_at=datetime.now(timezone.utc),
        )
        self.db.add(document)
        self.db.flush()
        self._save_original_file(document.id, source, raw)
        chunk_objs = [
            KnowledgeChunk(
                document_id=document.id,
                content=chunk,
                source=source,
                embedding_text=chunk,
            )
            for chunk in chunks
        ]
        for obj in chunk_objs:
            self.db.add(obj)
        self.db.commit()
        self.db.refresh(document)

        # 同步写入 Chroma（chunk_id 作 id，重复上传不产生副本）；失败静默，BM25 词法路仍在
        if chunk_objs:
            try:
                await self.embedding.add_documents(
                    texts=[c.embedding_text for c in chunk_objs],
                    metadatas=[{"chunk_id": c.id, "document_id": document.id, "source": c.source} for c in chunk_objs],
                    ids=[str(c.id) for c in chunk_objs],
                )
            except Exception:
                pass
        return document

    def delete_document(self, document: KnowledgeDocument) -> None:
        """删除文档：先清向量再删 SQL，避免遗留无法定位的孤儿向量。"""
        doc_id = document.id
        chunk_ids = [
            row[0]
            for row in self.db.query(KnowledgeChunk.id)
            .filter(KnowledgeChunk.document_id == doc_id)
            .all()
        ]
        self.embedding.delete_chunks(chunk_ids)
        self.db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).delete()
        self.db.delete(document)
        self.db.commit()
        for path in (get_settings().base_dir / "storage" / "knowledge").glob(f"{doc_id}_*"):
            path.unlink(missing_ok=True)

    def _save_original_file(self, document_id: int, filename: str, raw: bytes) -> None:
        """
        将原始上传文件保存到本地存储目录。

        参数:
            document_id: 文档数据库 ID
            filename: 原始文件名
            raw: 文件原始字节
        """
        # 清理文件名中的不安全字符，保留中文、字母、数字和下划线
        safe_name = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", filename).strip("_") or "upload.txt"
        storage_dir = get_settings().base_dir / "storage" / "knowledge"
        storage_dir.mkdir(parents=True, exist_ok=True)
        target = storage_dir / f"{document_id}_{safe_name}"
        target.write_bytes(raw)

    # FAQ 直出判定
    @classmethod
    def pick_direct_faq(cls, sources: list[SourceSnippet]) -> SourceSnippet | None:
        """
        从检索结果中挑出可直出的 FAQ 片段，无可直出项返回 None。

        只认高分（>= FAQ_DIRECT_THRESHOLD），弱命中仍交给模型，
        让模型参考片段组织措辞。
        输入用 FAQ 检索路的完整结果（retrieve() 在 top_k 截断前调用），
        避免为判定再扫一遍 FAQ 全表。

        阈值比对的是 faq_score（不含 +0.05 展示加分的原始命中分）

        参数:
            sources: retrieve() 返回的检索结果

        返回:
            SourceSnippet | None: 可直出的 FAQ 片段
        """
        for item in sources:
            if item.source.startswith("FAQ：") and (item.faq_score or 0.0) >= cls.FAQ_DIRECT_THRESHOLD and cls.faq_answer_text(item):
                return item
        return None

    @staticmethod
    def faq_answer_text(snippet: SourceSnippet) -> str:
        """
        从 FAQ 片段的「问：…\\n答：…」文本中取出答案部分。

        参数:
            snippet: FAQ 检索产出的片段

        返回:
            str: 纯答案文本；格式异常时返回空串（调用方据此放弃直出）
        """
        return snippet.content.partition("\n答：")[2].strip()

    # RAG 查询入口

    async def query(self, question: str, top_k: int = 4) -> KnowledgeQueryResponse:
        """
        RAG 查询：检索相关知识片段；FAQ 强命中直接采用人工答案，否则交由 LLM 生成，结果带缓存。

        参数:
            question: 用户问题
            top_k: 返回的 Top-K 相关片段数，默认 4

        返回:
            KnowledgeQueryResponse: 包含答案和引用来源列表
        """
        # 计算知识库规模用于缓存键
        chunk_count = self.db.query(KnowledgeChunk).count()
        faq_count = self.db.query(FAQ).filter(FAQ.is_active.is_(True)).count()
        cache_key = f"rag:v4:{chunk_count}:{faq_count}:{top_k}:{question}"
        cached = self.cache.get_json(cache_key)
        if cached:
            return KnowledgeQueryResponse(**cached)

        sources = await self.retrieve(question, top_k)
        if not sources:
            return KnowledgeQueryResponse(
                answer="暂未在企业知识库中检索到高相关内容。请上传文档、维护 FAQ，或换一种更具体的问法。",
                sources=[],
            )

        # FAQ 强命中直接返回人工答案，不经过模型改写：
        hit = self.direct_faq_hit
        if hit:
            result = KnowledgeQueryResponse(answer=self.faq_answer_text(hit), sources=[hit])
            self.cache.set_json(cache_key, result.model_dump(), ttl_seconds=180)
            return result

        context = "\n\n".join(
            f"来源 {index + 1}：{item.source}\n片段：{item.content}"
            for index, item in enumerate(sources)
        )
        try:
            answer = await self._qa_chain.ainvoke({"question": question, "context": context})
        except Exception:
            # LLM 调用失败时使用本地兜底回答
            answer = self._fallback_answer(question, sources)
        result = KnowledgeQueryResponse(answer=answer, sources=sources)
        self.cache.set_json(cache_key, result.model_dump(), ttl_seconds=180)
        return result

    def _fallback_answer(self, question: str, sources: list[SourceSnippet]) -> str:
        """
        LLM 不可用时的兜底回答，直接返回最高相关片段的原文内容。

        参数:
            question: 用户问题
            sources: 检索到的相关片段列表

        返回:
            str: 兜底回复文本
        """
        top = sources[0]
        return (
            f"已根据企业知识库检索到与「{question}」相关的内容。\n\n"
            f"结论：{top.content}\n\n"
            "说明：当前大模型服务暂时不可用，以上为基于最高相关知识片段的兜底回答。"
        )

    # 检索核心：向量（Chroma retriever）+ BM25 双路 RRF 融合，FAQ 独立并行
    async def retrieve(self, question: str, top_k: int = 4) -> list[SourceSnippet]:
        """文档双路 RRF 融合 + FAQ 独立竞争，按展示分返回前 top_k 条。

        文档路内部按 RRF 原始分排序，展示分按本次结果集的最高原始分归一化
        （最高分恒为 1.0，不假设「两路都排第一」）；FAQ 保持 0~1 自有分数，
        因此两类片段在前端是同一尺度。阈值判定只用 faq_score，不看展示分。
        """
        vector_docs = await self._vector_retrieve(question, top_k)
        # to_thread：BM25 打分是同步 CPU 计算，直接调用会阻塞事件循环，
        # 与 assist 并行段里分类 LLM 的 HTTP 响应处理互相卡
        bm25_refs = await asyncio.to_thread(self.bm25.search, question, top_k)
        doc_snippets = self._rrf_fuse(vector_docs, bm25_refs, top_k)
        faq_snippets = self._faq_retrieve(question, top_k)

        # 直出判定必须在 top_k 截断之前：文档展示分归一化后恒有 1.0，
        # FAQ 的 0.95 会被挤出 top_k，截断后再判定等于永远判不到
        self.direct_faq_hit = self.pick_direct_faq(faq_snippets)

        merged = doc_snippets + faq_snippets
        merged.sort(key=lambda item: item.score, reverse=True)
        # 检索路径口径：FAQ 直出优先
        # 垃圾命中抢记成 hybrid/vector，否则埋点饼图里 FAQ 命中永远接近 0。
        self.last_retrieval_mode = (
            "faq" if self.direct_faq_hit else self._retrieval_mode(vector_docs, bm25_refs, faq_snippets)
        )
        return merged[:top_k]

    @staticmethod
    def _retrieval_mode(
        vector_docs: list[Document], bm25_refs: list, faq_snippets: list[SourceSnippet]
    ) -> str:
        if vector_docs and bm25_refs:
            return "hybrid"
        if vector_docs:
            return "vector"
        if bm25_refs:
            return "bm25"
        return "faq" if faq_snippets else "none"

    def _rrf_fuse(self, vector_docs: list[Document], bm25_refs: list, top_k: int) -> list[SourceSnippet]:
        """RRF 融合：不比分数、只比排名。

        余弦相似度与 BM25 分数量纲不同（一个 0~1、一个无上限）
        排名是无量纲的。某块总分 = Σ 1/(k + rank_i)，同时被
        两路排到前面的块两项相加自然冒头——共识优先。

        排序用原始 RRF 分；展示分按本次结果集最高原始分归一化，最高分恒为
        1.0。不用固定分母 2/(k+1)：那只在「两路都排第一」时成立，只命中
        一路时最高只有 0.5，会让文档分和 FAQ 分无法比较。
        """
        contributions: dict = {}
        info: dict = {}  # key -> (source, content)
        for rank, doc in enumerate(vector_docs, start=1):
            meta = doc.metadata or {}
            key = meta.get("chunk_id", f"raw:{doc.page_content}")
            contributions[key] = contributions.get(key, 0.0) + 1.0 / (self.RRF_K + rank)
            info.setdefault(key, (meta.get("source", "未知"), doc.page_content))
        for rank, ref in enumerate(bm25_refs, start=1):
            contributions[ref.chunk_id] = contributions.get(ref.chunk_id, 0.0) + 1.0 / (self.RRF_K + rank)
            info.setdefault(ref.chunk_id, (ref.source, ref.content))

        ordered = sorted(contributions.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        if not ordered:
            return []
        top_raw = ordered[0][1]
        return [
            SourceSnippet(
                source=f"文档：{info[key][0]}",
                content=info[key][1][:600],
                score=round(rrf / top_raw, 4),
            )
            for key, rrf in ordered
        ]

    async def _vector_retrieve(self, question: str, top_k: int) -> list[Document]:
        """Chroma 不可用、为空或查询失败时返回空列表，由 BM25 词法路兜底。

        RRF 只看排名不看分数，因此走 as_retriever() 标准检索接口即可，
        不需要 similarity_search_with_score 的距离值。
        """
        if self.embedding.vector_store is None:
            return []
        try:
            retriever = self.embedding.vector_store.as_retriever(search_kwargs={"k": top_k})
            return await retriever.ainvoke(question)
        except Exception:
            return []

    def _faq_retrieve(self, question: str, top_k: int = 4) -> list[SourceSnippet]:
        """独立检索 FAQ，使其在文档双路有结果时仍参与排序。"""
        query_tokens = Counter(tokenize(question))
        scored: list[SourceSnippet] = []
        faqs = self.db.query(FAQ).filter(FAQ.is_active.is_(True)).all()
        for faq in faqs:
            text = f"{faq.question}\n{faq.answer}"
            score = self._cosine(query_tokens, Counter(tokenize(text)))
            if question.strip() and (question.strip() in faq.question or faq.question in question.strip()):
                score = max(score, 0.95)
            elif self._similarity(question, faq.question) >= self.FAQ_SIMILARITY_THRESHOLD:
                score = max(score, 0.9)
            if score > 0:
                final_score = round(score + 0.05, 4)  # FAQ 结果额外加分
                scored.append(
                    SourceSnippet(
                        source=f"FAQ：{faq.category} #{faq.id}",
                        content=f"问：{faq.question}\n答：{faq.answer}",
                        score=final_score,
                        # 原始命中分（不含展示加分）单独留给直出阈值，与展示口径解耦
                        faq_score=round(score, 4),
                    )
                )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]

    # 文本处理工具方法
    def _extract_text(self, filename: str | None, raw: bytes) -> str:
        """从 PDF、DOCX 或纯文本中提取内容。"""
        suffix = Path(filename or "").suffix.lower()
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
                import io

                reader = PdfReader(io.BytesIO(raw))
                return "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception:
                return raw.decode("utf-8", errors="ignore")
        if suffix in {".docx", ".doc"}:
            try:
                from docx import Document as DocxDocument
                import io

                doc = DocxDocument(io.BytesIO(raw))
                return "\n".join(paragraph.text for paragraph in doc.paragraphs)
            except Exception:
                return raw.decode("utf-8", errors="ignore")
        return raw.decode("utf-8", errors="ignore")

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        """字符序列匹配可保留“企业版/专业版”等定语差异。"""
        return difflib.SequenceMatcher(None, left.strip(), right.strip()).ratio()

    def _cosine(self, left: Counter[str], right: Counter[str]) -> float:
        """计算两个词频向量的余弦相似度。"""
        common = set(left) & set(right)
        numerator = sum(left[token] * right[token] for token in common)
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if not left_norm or not right_norm:
            return 0.0
        return numerator / (left_norm * right_norm)
