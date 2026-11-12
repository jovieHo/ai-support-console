"""认证服务：注册与登录的凭据校验、账号状态检查与令牌签发。"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.security import create_access_token, hash_password, verify_password
from models import User
from schemas import RegisterRequest, Role, TokenResponse, UserLogin, UserResponse


class AuthService:
    """注册与登录；令牌签发在此完成，路由只负责转发请求。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def register(self, payload: RegisterRequest) -> TokenResponse:
        """创建账号并返回令牌；公开注册一律发放企业用户角色。"""
        exists = (
            self.db.query(User)
            .filter((User.username == payload.username) | (User.email == payload.email))
            .first()
        )
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名或邮箱已存在")
        user = User(
            username=payload.username,
            email=payload.email,
            hashed_password=hash_password(payload.password),
            role=Role.ENTERPRISE_USER.value,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return self._token_response(user)

    def login(self, payload: UserLogin) -> TokenResponse:
        """校验凭据并返回令牌；停用账号在此拦下。"""
        user = self.db.query(User).filter(User.username == payload.username).first()
        if not user or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
        # 停用账号在登录这一步就拦下：否则会先发 token，再由后续请求的 401 把人踢出去
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被停用，请联系管理员")
        return self._token_response(user)

    def _token_response(self, user: User) -> TokenResponse:
        """签发访问令牌并组装响应。"""
        token = create_access_token(user.username, user.role)
        return TokenResponse(access_token=token, user=UserResponse.model_validate(user))
