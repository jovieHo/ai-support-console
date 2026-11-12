"""商务数据路由：CRUD 操作，支持按状态筛选和标题搜索。"""

from fastapi import APIRouter, Query, status

from api.deps import AdminUser, DbSession
from schemas import BusinessCreate, BusinessResponse, BusinessStatus, BusinessUpdate, ListResponse
from services.business_service import BusinessService

router = APIRouter(prefix="/business", tags=["商务数据"])


@router.get("", response_model=ListResponse)
def list_business(
    _: AdminUser,
    db: DbSession,
    status_filter: BusinessStatus | None = Query(None, alias="status"),
    search: str | None = None,
) -> ListResponse:
    """获取商务数据列表，支持按状态筛选和标题搜索。"""
    items = BusinessService(db).list_items(
        status=status_filter.value if status_filter else None,
        search=search,
    )
    return ListResponse(total=len(items), items=items)


@router.post("", response_model=BusinessResponse, status_code=status.HTTP_201_CREATED)
def create_business(payload: BusinessCreate, current_user: AdminUser, db: DbSession) -> BusinessResponse:
    """创建商务数据记录，关联当前登录用户为所有者。"""
    return BusinessService(db).create(payload, current_user.id)


@router.put("/{item_id}", response_model=BusinessResponse)
def update_business(item_id: int, payload: BusinessUpdate, _: AdminUser, db: DbSession) -> BusinessResponse:
    """更新商务数据记录，支持部分字段更新。"""
    return BusinessService(db).update(item_id, payload)


@router.delete("/{item_id}")
def delete_business(item_id: int, _: AdminUser, db: DbSession) -> dict[str, str]:
    """归档商务数据记录（软删除：将状态设为 archived 而非物理删除）。"""
    BusinessService(db).archive(item_id)
    return {"message": "商务数据已归档"}
