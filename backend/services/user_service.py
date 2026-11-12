"""用户管理服务：last-admin 安全规则与用户 CRUD。

安全规则（assert_admin_left）内置于 update 与 deactivate，
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.security import hash_password
from models import User
from schemas import Role, UserCreate, UserResponse, UserUpdate


def assert_admin_left(
    db: Session,
    target: User,
    next_role: Role | str | None = None,
    next_active: bool | None = None,
) -> None:
    """保证变更后系统里仍有至少一名启用的管理员，避免把自己锁在门外。"""
    role = next_role.value if isinstance(next_role, Role) else (next_role or target.role)
    active = target.is_active if next_active is None else next_active
    if role == Role.ADMIN.value and active:
        return
    others = (
        db.query(User)
        .filter(
            User.id != target.id,
            User.role == Role.ADMIN.value,
            User.is_active.is_(True),
        )
        .count()
    )
    if others == 0:
        raise HTTPException(status_code=400, detail="系统至少需要保留一名启用的管理员")


class UserService:
    """用户的增删改查；停用是软删除（is_active=False）。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_users(self, search: str | None = None) -> list[UserResponse]:
        """列出平台用户，支持按用户名搜索。"""
        query = self.db.query(User)
        if search:
            query = query.filter(User.username.like(f"%{search}%"))
        items = query.order_by(User.id.desc()).all()
        return [UserResponse.model_validate(item) for item in items]

    def create(self, payload: UserCreate) -> UserResponse:
        """创建用户账号，密码在入库前哈希。"""
        user = User(
            username=payload.username,
            email=payload.email,
            hashed_password=hash_password(payload.password),
            role=payload.role.value,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return UserResponse.model_validate(user)

    def update(self, user_id: int, payload: UserUpdate) -> UserResponse:
        """修改用户属性，支持部分更新；受 last-admin 规则保护。"""
        user = self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        data = payload.model_dump(exclude_unset=True)
        assert_admin_left(self.db, user, data.get("role"), data.get("is_active"))
        if password := data.pop("password", None):
            user.hashed_password = hash_password(password)
        for key, value in data.items():
            setattr(user, key, value.value if hasattr(value, "value") else value)
        self.db.commit()
        self.db.refresh(user)
        return UserResponse.model_validate(user)

    def deactivate(self, user_id: int) -> None:
        """停用用户账号（软删除）；受 last-admin 规则保护。"""
        user = self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        assert_admin_left(self.db, user, next_active=False)
        user.is_active = False
        self.db.commit()
