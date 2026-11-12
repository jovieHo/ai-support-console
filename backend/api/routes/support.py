"""客服工作台路由：咨询记录管理 + AI 智能辅助回复。"""

from fastapi import APIRouter, Query, status

from api.deps import DbSession, StaffUser
from schemas import AgentRequest, CustomerConsultationCreate, CustomerConsultationResponse, CustomerConsultationUpdate, ListResponse
from services.agent_service import AgentService
from services.consultation_service import ConsultationService
from services.telemetry import ENTRY_ASSIST, record_invocation

router = APIRouter(prefix="/support", tags=["客服工作台"])


@router.post("/assist")
async def assist(payload: AgentRequest, _: StaffUser, db: DbSession):
    """调用客服应答流水线，根据客户问题生成辅助回复建议。"""
    service = AgentService(db)
    try:
        return await service.run_customer_workflow(payload.question, payload.customer_name)
    finally:
        # 成功失败都留痕：这条埋点是「建议转人工率」唯一的数据源
        metrics = service.telemetry
        record_invocation(
            db,
            entry=ENTRY_ASSIST,
            retrieval_mode=metrics["retrieval_mode"],
            sources=metrics["sources"],
            retrieval_ms=metrics["retrieval_ms"],
            llm_ms=metrics["llm_ms"],
            prompt_chars=metrics["prompt_chars"],
            is_faq_direct=metrics["is_faq_direct"],
            is_success=metrics["is_success"],
            is_escalated=metrics["is_escalated"],
        )


@router.get("/consultations", response_model=ListResponse)
def list_consultations(
    _: StaffUser,
    db: DbSession,
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = None,
    search: str | None = None,
) -> ListResponse:
    """获取咨询记录列表，支持按状态、分类和问题内容筛选。"""
    items = ConsultationService(db).list_items(status=status_filter, category=category, search=search)
    return ListResponse(total=len(items), items=items)


@router.post("/consultations", response_model=CustomerConsultationResponse, status_code=status.HTTP_201_CREATED)
def create_consultation(payload: CustomerConsultationCreate, _: StaffUser, db: DbSession) -> CustomerConsultationResponse:
    """创建一条新的客户咨询记录。"""
    return ConsultationService(db).create(payload)


@router.put("/consultations/{item_id}", response_model=CustomerConsultationResponse)
def update_consultation(item_id: int, payload: CustomerConsultationUpdate, _: StaffUser, db: DbSession) -> CustomerConsultationResponse:
    """修改指定咨询记录的信息，支持部分字段更新。"""
    return ConsultationService(db).update(item_id, payload)


@router.delete("/consultations/{item_id}")
def delete_consultation(item_id: int, _: StaffUser, db: DbSession) -> dict[str, str]:
    """删除咨询记录（物理删除）。"""
    ConsultationService(db).delete(item_id)
    return {"message": "咨询记录已删除"}
