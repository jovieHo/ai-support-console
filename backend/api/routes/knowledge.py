"""知识库路由：文档上传、分块管理、FAQ 维护、知识库问答。"""

from fastapi import APIRouter, File, Form, Query, UploadFile

from api.deps import CurrentUser, DbSession, StaffUser
from schemas import FAQCreate, FAQResponse, FAQUpdate, KnowledgeOverviewResponse, KnowledgeQuery, KnowledgeQueryResponse, ListResponse
from services.knowledge_service import KnowledgeService
from services.rag_service import RAGService
from tools.chunking import DEFAULT_CHUNK_SIZE

router = APIRouter(prefix="/knowledge", tags=["知识库"])


@router.post("/upload")
async def upload_document(
    _: StaffUser,
    db: DbSession,
    file: UploadFile = File(...),
    chunk_size: int = Form(DEFAULT_CHUNK_SIZE),
) -> dict:
    """上传文件（支持 txt/pdf/docx 等），自动解析、按段落分块并建立向量索引。"""
    document = await RAGService(db).ingest_upload(file, chunk_size)
    return {
        "id": document.id,
        "filename": document.filename,
        "chunk_count": document.chunk_count,
        "parse_status": document.parse_status,
        "parse_message": document.parse_message,
        "parsed_at": document.parsed_at,
        "persisted": True,
        "message": document.parse_message,
    }


@router.post("/query", response_model=KnowledgeQueryResponse)
async def query_knowledge(payload: KnowledgeQuery, _: CurrentUser, db: DbSession) -> KnowledgeQueryResponse:
    """对知识库进行语义搜索，返回相关文档片段及 AI 生成的回答。"""
    return await RAGService(db).query(payload.question, payload.top_k)


@router.get("/documents", response_model=ListResponse)
def list_documents(_: CurrentUser, db: DbSession) -> ListResponse:
    """查看知识库中所有已上传文档的列表。"""
    documents = KnowledgeService(db).list_documents()
    return ListResponse(total=len(documents), items=documents)


@router.get("/chunks", response_model=ListResponse)
def list_chunks(
    _: StaffUser,
    db: DbSession,
    document_id: int | None = Query(None, ge=1),
    search: str | None = None,
    limit: int | None = Query(None, ge=1, le=5000),
) -> ListResponse:
    """查看文档解析后的知识分块，支持按文档筛选、内容搜索和数量限制。"""
    total, chunks = KnowledgeService(db).list_chunks(document_id, search, limit)
    return ListResponse(total=total, items=chunks)


@router.get("/overview", response_model=KnowledgeOverviewResponse)
def overview(_: StaffUser, db: DbSession) -> KnowledgeOverviewResponse:
    """返回知识库的整体概览，包括所有文档、分块、FAQ 及统计信息。"""
    return KnowledgeService(db).overview()


# FAQ 管理

@router.get("/faqs", response_model=ListResponse)
def list_faqs(_: StaffUser, db: DbSession, search: str | None = None) -> ListResponse:
    """获取知识库中的所有 FAQ，支持按问题模糊搜索。"""
    faqs = KnowledgeService(db).list_faqs(search)
    return ListResponse(total=len(faqs), items=faqs)


@router.post("/faqs", response_model=FAQResponse)
def create_faq(payload: FAQCreate, _: StaffUser, db: DbSession) -> FAQResponse:
    """向知识库添加新的 FAQ 问答对。"""
    return KnowledgeService(db).create_faq(payload)


@router.put("/faqs/{faq_id}", response_model=FAQResponse)
def update_faq(faq_id: int, payload: FAQUpdate, _: StaffUser, db: DbSession) -> FAQResponse:
    """修改指定 FAQ 的内容，支持部分字段更新。"""
    return KnowledgeService(db).update_faq(faq_id, payload)


@router.delete("/faqs/{faq_id}")
def delete_faq(faq_id: int, _: StaffUser, db: DbSession) -> dict[str, str]:
    """停用指定 FAQ（软删除：将 is_active 设为 False 而非物理删除）。"""
    KnowledgeService(db).deactivate_faq(faq_id)
    return {"message": "FAQ 已停用"}


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, _: StaffUser, db: DbSession) -> dict:
    """删除指定文档及其向量与原始文件（物理删除）。"""
    service = KnowledgeService(db)
    document = service.get_document(document_id)
    RAGService(db).delete_document(document)
    return {"ok": True, "message": f"文档「{document.filename}」已删除"}
