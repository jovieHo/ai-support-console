"""商务数据服务：CRUD 与归档语义。

DELETE 在领域语义上是归档（status=archived）而非物理删除，
这层语义通过方法名 archive。
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import BusinessData
from schemas import BusinessCreate, BusinessResponse, BusinessStatus, BusinessUpdate


class BusinessService:
    """商务数据的增删改查。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_items(self, status: str | None = None, search: str | None = None) -> list[BusinessResponse]:
        """列出商务数据，支持按状态筛选和标题搜索。"""
        query = self.db.query(BusinessData)
        if status:
            query = query.filter(BusinessData.status == status)
        if search:
            query = query.filter(BusinessData.title.like(f"%{search}%"))
        items = query.order_by(BusinessData.id.desc()).all()
        return [BusinessResponse.model_validate(item) for item in items]

    def create(self, payload: BusinessCreate, owner_id: int) -> BusinessResponse:
        """创建商务数据记录，关联所有者。"""
        item = BusinessData(**payload.model_dump(mode="json"), owner_id=owner_id)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return BusinessResponse.model_validate(item)

    def update(self, item_id: int, payload: BusinessUpdate) -> BusinessResponse:
        """更新商务数据记录，支持部分字段更新。"""
        item = self.db.get(BusinessData, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="商务数据不存在")
        for key, value in payload.model_dump(exclude_unset=True, mode="json").items():
            setattr(item, key, value)
        self.db.commit()
        self.db.refresh(item)
        return BusinessResponse.model_validate(item)

    def archive(self, item_id: int) -> None:
        """归档商务数据记录（软删除）。"""
        item = self.db.get(BusinessData, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="商务数据不存在")
        item.status = BusinessStatus.ARCHIVED.value
        self.db.commit()
