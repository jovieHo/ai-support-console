"""FastAPI 依赖注入：数据库会话 + 当前用户认证。

- DbSession：每个请求的数据库会话，通过FastAPI的Depends注入
- CurrentUser：从Authorization Header解析JWT获取当前登录用户，自动验证身份
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from core.security import decode_access_token
from database import get_db
from models import User
from schemas import Role

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """从 Bearer Token 中解析并验证当前登录用户，无效时抛 401。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效") from exc
    user = db.query(User).filter(User.username == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: Role):
    """生成"限定角色"的依赖函数：当前用户角色不在允许列表时拒绝（403）。

    参数:
        roles: 允许访问的角色枚举，如 Role.CUSTOMER_SERVICE, Role.ADMIN
    """

    def checker(user: CurrentUser) -> User:
        if user.role not in {role.value for role in roles}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该资源")
        return user

    return checker


# 角色受限依赖别名：与前端路由 meta.roles 的映射保持一致
# StaffUser —— 客服工作台 / 知识库 / 决策大屏（客服、管理员）
# AdminUser —— 商务数据 / 用户管理等管理员专属接口
StaffUser = Annotated[User, Depends(require_role(Role.CUSTOMER_SERVICE, Role.ADMIN))]
AdminUser = Annotated[User, Depends(require_role(Role.ADMIN))]
