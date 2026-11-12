"""用户管理路由：管理员对平台的用户进行 CRUD 操作。"""

from fastapi import APIRouter, status

from api.deps import AdminUser, CurrentUser, DbSession
from schemas import ListResponse, Role, UserCreate, UserResponse, UserUpdate
from services.user_service import UserService

router = APIRouter(prefix="/users", tags=["用户管理"])


@router.get("", response_model=ListResponse)
def list_users(current_user: AdminUser, db: DbSession, search: str | None = None) -> ListResponse:
    """管理员查看平台所有用户，支持按用户名搜索。"""
    items = UserService(db).list_users(search)
    return ListResponse(total=len(items), items=items)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, current_user: AdminUser, db: DbSession) -> UserResponse:
    """管理员创建新用户账号。"""
    return UserService(db).create(payload)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, payload: UserUpdate, current_user: AdminUser, db: DbSession) -> UserResponse:
    """管理员修改指定用户的属性，支持部分更新。"""
    return UserService(db).update(user_id, payload)


@router.delete("/{user_id}")
def delete_user(user_id: int, current_user: AdminUser, db: DbSession) -> dict[str, str]:
    """管理员停用指定用户账号（软删除：将 is_active 设为 False）。"""
    UserService(db).deactivate(user_id)
    return {"message": "账号已停用"}


@router.get("/roles")
def roles(_: CurrentUser) -> list[str]:
    """返回系统中定义的所有角色枚举值。"""
    return [item.value for item in Role]
