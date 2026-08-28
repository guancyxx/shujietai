from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, WebSocket
from fastapi.security.utils import get_authorization_scheme_param

logger = logging.getLogger(__name__)

# JWT 签名密钥：优先环境变量 SHUJIE_JWT_SECRET；缺省启动时随机生成并打警告
#（随机密钥重启后所有 token 失效——单机部署应显式配置）。
_generated_secret: str | None = None


def get_jwt_secret() -> str:
    global _generated_secret
    secret = os.getenv("SHUJIE_JWT_SECRET", "").strip()
    if secret:
        return secret
    if _generated_secret is None:
        _generated_secret = secrets.token_urlsafe(48)
        logger.warning(
            "SHUJIE_JWT_SECRET is not set; generated an ephemeral random secret. "
            "All sessions will be invalidated on restart. Set SHUJIE_JWT_SECRET for production."
        )
    return _generated_secret


JWT_ALGORITHM = "HS256"
JWT_EXPIRE_SECONDS = 12 * 3600  # 12h 会话
JWT_ISSUER = "shujietai"

# 无需认证的路径（docker healthcheck 依赖 health；login 本身是取 token 入口）
PUBLIC_PATHS: frozenset[str] = frozenset({"/api/v1/health", "/api/auth/login"})


def create_access_token(username: str, is_admin: bool = False, expires_seconds: int | None = None) -> str:
    now = int(time.time())
    payload = {
        "sub": username,
        "is_admin": is_admin,
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": now + (expires_seconds if expires_seconds is not None else JWT_EXPIRE_SECONDS),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """校验并解码 JWT；失败抛 jwt.InvalidTokenError 子类。"""
    return jwt.decode(
        token,
        get_jwt_secret(),
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        options={"require": ["exp", "sub"]},
    )


def _extract_bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    scheme, param = get_authorization_scheme_param(authorization)
    if scheme.lower() != "bearer" or not param:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return param


def require_user(request: Request) -> dict[str, Any]:
    """FastAPI 全局依赖：校验 Bearer JWT，返回 token claims。

    豁免路径（docker healthcheck / 登录本身）直接放行。
    """
    if request.url.path in PUBLIC_PATHS:
        return {"sub": "anonymous", "public": True}
    token = _extract_bearer_token(request)
    try:
        claims = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401, detail="token_expired", headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401, detail="invalid_token", headers={"WWW-Authenticate": "Bearer"}
        )
    return claims


# ---------- WebSocket token 校验（query param token，HMAC 时序安全的哑比较回退） ----------

_WS_REJECT_REASON_CLOSED = "unauthorized"


async def validate_ws_token(websocket: WebSocket) -> dict[str, Any] | None:
    """WS 连接前校验 query param `token`。失败时 accept 后立即以 4401 关闭，
    返回 None；成功返回 claims。"""
    token = websocket.query_params.get("token", "")
    try:
        return decode_access_token(token)
    except jwt.InvalidTokenError:
        return None


async def reject_websocket(websocket: WebSocket) -> None:
    """以受控方式拒绝未授权 WS 连接：accept → close(4401)。"""
    try:
        await websocket.accept()
        await websocket.close(code=4401, reason=_WS_REJECT_REASON_CLOSED)
    except Exception:  # noqa: BLE001 — 客户端可能已断开
        pass
