"""认证路由：用户注册与登录，返回 JWT token。"""

from fastapi import APIRouter

from api.deps import DbSession
from schemas import RegisterRequest, TokenResponse, UserLogin
from services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=TokenResponse)
def register(payload: RegisterRequest, db: DbSession) -> TokenResponse:
    """新用户注册，创建账号并返回 JWT 访问令牌。

    公开注册一律发放企业用户角色，角色提升只能由管理员在用户管理接口操作。
    """
    return AuthService(db).register(payload)


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: DbSession) -> TokenResponse:
    """验证用户凭据，登录成功返回 JWT 访问令牌。"""
    return AuthService(db).login(payload)
