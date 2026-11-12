"""EmbeddingService 的异步调用路径测试。"""

import unittest
from unittest.mock import AsyncMock, Mock

from langchain_core.documents import Document

from services.embedding_service import EmbeddingService


class EmbeddingServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = EmbeddingService.__new__(EmbeddingService)
        self.service.vector_store = Mock()

    async def test_add_documents_uses_async_vector_store_api(self) -> None:
        self.service.vector_store.aadd_texts = AsyncMock(return_value=["chunk-1"])

        result = await self.service.add_documents(
            texts=["示例内容"],
            metadatas=[{"source": "demo.txt"}],
            ids=["chunk-1"],
        )

        self.assertEqual(result, ["chunk-1"])
        self.service.vector_store.aadd_texts.assert_awaited_once_with(
            texts=["示例内容"],
            metadatas=[{"source": "demo.txt"}],
            ids=["chunk-1"],
        )

    async def test_search_with_score_uses_async_vector_store_api(self) -> None:
        expected = [(Document(page_content="示例内容"), 0.25)]
        self.service.vector_store.asimilarity_search_with_score = AsyncMock(return_value=expected)

        result = await self.service.search_with_score("示例问题", k=3)

        self.assertEqual(result, expected)
        self.service.vector_store.asimilarity_search_with_score.assert_awaited_once_with("示例问题", k=3)


if __name__ == "__main__":
    unittest.main()
