"""Embedding + 向量库服务：基于 OpenAI 兼容协议与 Chroma 持久化向量。"""

from __future__ import annotations

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from core.config import get_settings


class EmbeddingService:
    """文本转向量、入库 Chroma、相似度检索。

    未配置 embed_api_key 时 vector_store 为 None，调用方据此只走 BM25 词法检索；
    其余方法需调用方先确认 vector_store 可用。
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.embed_api_key:
            self._embeddings = None
            self.vector_store = None
            return
        self._embeddings = OpenAIEmbeddings(
            base_url=self.settings.embed_base_url,
            api_key=self.settings.embed_api_key,
            model=self.settings.embed_model,
            # 阿里云百炼只接受原始字符串，不接受 token id 数组；
            # langchain 默认会用 tiktoken 预分词，导致 contents 参数校验报错
            check_embedding_ctx_length=False,
        )
        self.vector_store = Chroma(
            embedding_function=self._embeddings,
            persist_directory=self.settings.chroma_persist_dir,
            collection_name=self.settings.chroma_collection_name,
            # 显式声明余弦空间：Chroma 默认是 L2，会导致上层 1 - distance 出现负数；
            # 使用 configuration 写法
            collection_configuration={"hnsw": {"space": "cosine"}},
        )

    async def add_documents(
        self,
        texts: list[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        """入库到 Chroma，返回 id 列表；调用前需确认 vector_store 可用。"""
        return await self.vector_store.aadd_texts(texts=texts, metadatas=metadatas, ids=ids)

    async def search_with_score(self, query: str, k: int = 4) -> list[tuple[Document, float]]:
        return await self.vector_store.asimilarity_search_with_score(query, k=k)

    def delete_chunks(self, chunk_ids: list[int]) -> None:
        """按 chunk id 删除向量；vector_store 不可用时跳过。"""
        if self.vector_store is not None and chunk_ids:
            self.vector_store.delete(ids=[str(cid) for cid in chunk_ids])
