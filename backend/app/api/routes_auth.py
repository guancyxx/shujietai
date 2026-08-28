from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import create_access_token, require_user
from app.services.user_service import authenticate, get_user_by_username

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    username: str
    display_name: str
    is_admin: bool


class MeResponse(BaseModel):
    username: str
    display_name: str
    is_admin: bool


def _db_session(request: Request) -> Session:
    factory = getattr(request.app.state, "auth_session_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="auth_unavailable")
    return factory()


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request) -> LoginResponse:
    from app.auth import JWT_EXPIRE_SECONDS

    session = _db_session(request)
    try:
        user = authenticate(session, payload.username, payload.password)
    finally:
        session.close()
    if user is None:
        # 统一 401，不区分用户不存在/密码错误
        raise HTTPException(status_code=401, detail="invalid_credentials")
    token = create_access_token(user.username, is_admin=user.is_admin)
    return LoginResponse(
        access_token=token,
        expires_in=JWT_EXPIRE_SECONDS,
        username=user.username,
        display_name=user.display_name or user.username,
        is_admin=user.is_admin,
    )


@router.get("/me", response_model=MeResponse)
def me(request: Request, claims: dict = Depends(require_user)) -> MeResponse:
    session = _db_session(request)
    try:
        user = get_user_by_username(session, claims["sub"])
    finally:
        session.close()
    if user is None:
        raise HTTPException(status_code=401, detail="invalid_token")
    return MeResponse(
        username=user.username,
        display_name=user.display_name or user.username,
        is_admin=user.is_admin,
    )


@router.post("/logout")
def logout(claims: dict = Depends(require_user)) -> dict[str, object]:
    """JWT 无状态：后端不做吊销，前端删除 token 即登出。保留端点供前端语义化调用。"""
    return {"detail": "logged_out", "username": claims.get("sub")}
