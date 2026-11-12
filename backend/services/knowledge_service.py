"""知识库服务：文档、分块、FAQ 的查询与 FAQ 维护。

从路由层抽出，承载 knowledge.py 里的数据访问。上传/删除文档/问答等
有编排语义的操作仍留在 RAGService，这里负责纯查询与 FAQ 增改停。
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import FAQ, KnowledgeChunk, KnowledgeDocument
from schemas import (
    FAQCreate,
    FAQResponse,
    FAQUpdate,
    KnowledgeChunkResponse,
    KnowledgeDocumentResponse,
    KnowledgeOverviewResponse,
)


class KnowledgeService:
    """知识库文档/分块/FAQ 的纯查询。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def document_response(self, item: KnowledgeDocument) -> KnowledgeDocumentResponse:
        """将知识库文档数据库对象转换为响应模型，根据 chunk_count 推断解析状态。"""
        status = item.parse_status or ("indexed" if item.chunk_count else "empty")
        message = item.parse_message or (
            "已完成解析并建立知识分块" if item.chunk_count else "未生成知识分块，请检查文档内容"
        )
        return KnowledgeDocumentResponse(
            id=item.id,
            filename=item.filename,
            content_type=item.content_type,
            chunk_count=item.chunk_count,
            segment_rule=item.segment_rule,
            parse_status=status,
            parse_message=message,
            parsed_at=item.parsed_at,
            created_at=item.created_at,
        )

    def list_documents(self) -> list[KnowledgeDocumentResponse]:
        """按创建时间倒序列出所有文档。"""
        documents = self.db.query(KnowledgeDocument).order_by(KnowledgeDocument.id.desc()).all()
        return [self.document_response(item) for item in documents]

    def list_chunks(
        self,
        document_id: int | None = None,
        search: str | None = None,
        limit: int | None = None,
    ) -> tuple[int, list[KnowledgeChunkResponse]]:
        """列出知识分块，支持按文档筛选、内容搜索和数量限制，返回 (总数, 结果)。"""
        query = self.db.query(KnowledgeChunk)
        if document_id:
            query = query.filter(KnowledgeChunk.document_id == document_id)
        if search:
            query = query.filter(KnowledgeChunk.content.like(f"%{search}%"))
        total = query.count()
        query = query.order_by(KnowledgeChunk.id.desc())
        if limit:
            query = query.limit(limit)
        chunks = query.all()
        return total, [KnowledgeChunkResponse.model_validate(item) for item in chunks]

    def list_faqs(self, search: str | None = None) -> list[FAQResponse]:
        """列出所有 FAQ，支持按问题模糊搜索。"""
        query = self.db.query(FAQ)
        if search:
            query = query.filter(FAQ.question.like(f"%{search}%"))
        items = query.order_by(FAQ.id.desc()).all()
        return [FAQResponse.model_validate(item) for item in items]

    def overview(self) -> KnowledgeOverviewResponse:
        """返回知识库整体概览：所有文档、分块、FAQ 及统计信息。"""
        documents = self.db.query(KnowledgeDocument).order_by(KnowledgeDocument.id.desc()).all()
        chunks = self.db.query(KnowledgeChunk).order_by(KnowledgeChunk.id.desc()).all()
        faqs = self.db.query(FAQ).order_by(FAQ.id.desc()).all()
        return KnowledgeOverviewResponse(
            documents=[self.document_response(item) for item in documents],
            chunks=[KnowledgeChunkResponse.model_validate(item) for item in chunks],
            faqs=[FAQResponse.model_validate(item) for item in faqs],
            stats={
                "document_count": len(documents),
                "chunk_count": self.db.query(KnowledgeChunk).count(),
                "faq_count": len(faqs),
            },
        )

    # FAQ 维护
    def _get_faq(self, faq_id: int) -> FAQ:
        """取 FAQ，不存在则 404。"""
        item = self.db.get(FAQ, faq_id)
        if not item:
            raise HTTPException(status_code=404, detail="FAQ 不存在")
        return item

    def create_faq(self, payload: FAQCreate) -> FAQResponse:
        """新增 FAQ 问答对。"""
        item = FAQ(**payload.model_dump())
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return FAQResponse.model_validate(item)

    def update_faq(self, faq_id: int, payload: FAQUpdate) -> FAQResponse:
        """修改 FAQ，支持部分字段更新。"""
        item = self._get_faq(faq_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        self.db.commit()
        self.db.refresh(item)
        return FAQResponse.model_validate(item)

    def deactivate_faq(self, faq_id: int) -> None:
        """停用 FAQ（软删除：is_active=False）。"""
        item = self._get_faq(faq_id)
        item.is_active = False
        self.db.commit()

    # 文档
    def get_document(self, document_id: int) -> KnowledgeDocument:
        """取文档，不存在则 404。"""
        document = self.db.get(KnowledgeDocument, document_id)
        if not document:
            raise HTTPException(status_code=404, detail="文档不存在")
        return document
