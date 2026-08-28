"""M1 auth foundation tests: login, JWT protection, health exemption, WS token."""
from __future__ import annotations

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import JWT_EXPIRE_SECONDS, create_access_token, get_jwt_secret
from app.db.base import Base
import app.db.models  # noqa: F401
from app.db.user_model import UserEntity
from app.main import app
from app.services.user_service import hash_password


@pytest.fixture()
def auth_client(tmp_path):
    """独立 SQLite 库的 app 实例 + 已种子 admin。"""
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'auth.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        session.add(
            UserEntity(
                username="admin",
                password_hash=hash_password("correct-password-123"),
                is_admin=True,
                display_name="Administrator",
            )
        )
        session.commit()

    app.state.auth_session_factory = factory
    # 不带自动注入的 Authorization 头 —— 显式构造裸 client
    client = TestClient(app, headers={})
    try:
        yield client
    finally:
        app.state.auth_session_factory = None


def test_login_success(auth_client):
    resp = auth_client.post("/api/auth/login", json={"username": "admin", "password": "correct-password-123"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == JWT_EXPIRE_SECONDS
    assert payload["username"] == "admin"
    claims = pyjwt.decode(payload["access_token"], get_jwt_secret(), algorithms=["HS256"], issuer="shujietai")
    assert claims["sub"] == "admin"
    assert claims["is_admin"] is True


def test_login_wrong_password_401(auth_client):
    resp = auth_client.post("/api/auth/login", json={"username": "admin", "password": "wrong-password"})
    assert resp.status_code == 401


def test_login_unknown_user_401_same_error(auth_client):
    resp = auth_client.post("/api/auth/login", json={"username": "nobody", "password": "whatever"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid_credentials"


def test_api_without_token_401(auth_client):
    resp = auth_client.get("/api/v1/sessions")
    assert resp.status_code == 401


def test_api_with_garbage_token_401(auth_client):
    resp = auth_client.get("/api/v1/sessions", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401


def test_health_exempt_from_auth(auth_client):
    resp = auth_client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_me_with_valid_token(auth_client):
    login = auth_client.post("/api/auth/login", json={"username": "admin", "password": "correct-password-123"})
    token = login.json()["access_token"]
    resp = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


def test_expired_token_401(auth_client):
    expired = create_access_token("admin", is_admin=True, expires_seconds=-10)
    resp = auth_client.get("/api/v1/sessions", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401


def test_ws_without_token_rejected(auth_client):
    with pytest.raises(Exception):
        # 无 token：服务端 accept 后立即 close(4401)，客户端在 receive 时会抛错
        with auth_client.websocket_connect("/api/v1/ws"):
            pass


def test_ws_with_garbage_token_rejected(auth_client):
    with pytest.raises(Exception):
        with auth_client.websocket_connect("/api/v1/ws?token=garbage.token.here"):
            pass


def test_ws_with_valid_token_accepted(auth_client):
    token = create_access_token("admin", is_admin=True)
    with auth_client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        ws.send_text('{"action": "subscribe_task", "task_id": "dt_probe"}')
        # 无异常即视为连接建立并被接受（task 不存在时服务端回复 error 也属正常业务）


def test_logout_endpoint_requires_token(auth_client):
    resp = auth_client.post("/api/auth/logout")
    assert resp.status_code == 401
