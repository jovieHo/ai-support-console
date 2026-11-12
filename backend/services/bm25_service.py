"""BM25 词法检索：rank_bm25 实现的稀疏检索路。

BM25 与向量检索互补，错误模式几乎不重叠：向量把文本压成一个稠密向量，
擅长语义近义。（错误码、产品名、型号）是模糊的——E4021 和 E4022 的向量可能几乎一样；
BM25 是字面匹配，看见 E4021 就只给含 E4021 的块高分，且 IDF 项会给
低频高区分度的 token 更高权重。

索引是进程级缓存，按「分块总数 + 最大 id」失效——与 RAG 查询缓存键含
chunk_count 是同一个思路：库一变，旧索引作废。只看总数不够：删一份旧
文档再传一份新文档时总数不变，旧索引会继续召回已删除的内容，max(id)
在新增时必然变大，正好补上这个口子。缓存里存不可变快照（ChunkRef）而非
ORM 对象，避免跨请求复用时撞上 Session 分离问题。
"""

from __future__ import annotations

from dataclasses import dataclass

from rank_bm25 import BM25Okapi
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import KnowledgeChunk
from tools.tokenize import tokenize


@dataclass(frozen=True)
class ChunkRef:
    """知识分块的检索快照：BM25 索引只依赖这三个字段。"""

    chunk_id: int
    source: str
    content: str


class BM25Service:
    """对 knowledge_chunks 建 BM25 索引并执行词法检索。"""

    _bm25: BM25Okapi | None = None
    _refs: list[ChunkRef] = []
    _token_sets: list[set[str]] = []
    _indexed_signature: tuple | None = None

    def __init__(self, db: Session) -> None:
        self.db = db

    def search(self, query: str, top_k: int = 4) -> list[ChunkRef]:
        """按 BM25 相关度返回前 top_k 个分块快照，排名即列表顺序。

        「是否命中」用词面交集判断，不用分数 > 0：rank_bm25 的 BM25Okapi
        IDF 形如 log((N-df+0.5)/(df+0.5))，语料很小或某词出现在过半文档时
        IDF 会退化到 0 甚至为负，真实命中的分数同样变成 0/负数，按分数过滤。分数只负责排序，匹配与否交给词表交集。
        """
        bm25, refs, token_sets = self._get_index()
        if bm25 is None:
            return []
        query_tokens = tokenize(query)
        query_set = set(query_tokens)
        if not query_set:
            return []
        scores = bm25.get_scores(query_tokens)
        matched = [index for index, tokens in enumerate(token_sets) if tokens & query_set]
        matched.sort(key=lambda index: scores[index], reverse=True)
        return [refs[index] for index in matched[:top_k]]

    def _get_index(self) -> tuple[BM25Okapi | None, list[ChunkRef], list[set[str]]]:
        """取进程级索引；(count, max_id) 签名变化时整库重建。"""
        signature = self.db.query(
            func.count(KnowledgeChunk.id), func.max(KnowledgeChunk.id)
        ).one()
        if type(self)._bm25 is not None and type(self)._indexed_signature == signature:
            return type(self)._bm25, type(self)._refs, type(self)._token_sets

        rows = (
            self.db.query(KnowledgeChunk.id, KnowledgeChunk.source, KnowledgeChunk.content)
            .all()
        )
        if not rows:
            type(self)._bm25, type(self)._refs = None, []
            type(self)._token_sets, type(self)._indexed_signature = [], signature
            return None, [], []

        refs = [ChunkRef(row.id, row.source or "未知", row.content) for row in rows]
        corpus = [tokenize(ref.content) for ref in refs]
        type(self)._bm25 = BM25Okapi(corpus)
        type(self)._refs = refs
        type(self)._token_sets = [set(tokens) for tokens in corpus]
        type(self)._indexed_signature = signature
        return type(self)._bm25, type(self)._refs, type(self)._token_sets
