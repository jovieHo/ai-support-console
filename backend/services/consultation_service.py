"""咨询记录服务：客服工作台的工单 CRUD。"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import CustomerConsultation
from schemas import CustomerConsultationCreate, CustomerConsultationResponse, CustomerConsultationUpdate


class ConsultationService:
    """客户咨询工单的增删改查。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_items(
        self,
        status: str | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> list[CustomerConsultationResponse]:
        """列出咨询记录，支持按状态、分类和问题内容筛选。"""
        query = self.db.query(CustomerConsultation)
        if status:
            query = query.filter(CustomerConsultation.status == status)
        if category:
            query = query.filter(CustomerConsultation.category == category)
        if search:
            query = query.filter(CustomerConsultation.question.like(f"%{search}%"))
        items = query.order_by(CustomerConsultation.id.desc()).all()
        return [CustomerConsultationResponse.model_validate(item) for item in items]

    def create(self, payload: CustomerConsultationCreate) -> CustomerConsultationResponse:
        """创建一条客户咨询记录。"""
        item = CustomerConsultation(**payload.model_dump(mode="json"))
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return CustomerConsultationResponse.model_validate(item)

    def update(self, item_id: int, payload: CustomerConsultationUpdate) -> CustomerConsultationResponse:
        """修改指定咨询记录，支持部分字段更新。"""
        item = self.db.get(CustomerConsultation, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="咨询记录不存在")
        for key, value in payload.model_dump(exclude_unset=True, mode="json").items():
            setattr(item, key, value)
        self.db.commit()
        self.db.refresh(item)
        return CustomerConsultationResponse.model_validate(item)

    def delete(self, item_id: int) -> None:
        """物理删除咨询记录。"""
        item = self.db.get(CustomerConsultation, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="咨询记录不存在")
        self.db.delete(item)
        self.db.commit()
