"""User service: seeding, password hashing/verification (M1 auth foundation)."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.user_model import UserEntity

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(plain, password_hash)
    except Exception:  # noqa: BLE001 — malformed hash should not crash login
        return False


def get_user_by_username(session: Session, username: str) -> UserEntity | None:
    return session.scalar(select(UserEntity).where(UserEntity.username == username))


def seed_admin_user(engine: Engine | None, username: str = "admin") -> str | None:
    """首启无任何用户时创建 admin。密码取 SHUJIE_ADMIN_PASSWORD，缺省生成一次性
    随机密码打印到日志。返回创建的明文密码（仅随机分支），已存在用户返回 None。"""
    if engine is None:
        logger.warning("auth: no SQL engine available, skip admin seeding")
        return None
    from app.db.base import Base  # ensure metadata loaded
    import app.db.models  # noqa: F401

    Base.metadata.create_all(engine, tables=[UserEntity.__table__])  # type: ignore[arg-type]
    with Session(engine) as session:
        existing = get_user_by_username(session, username)
        if existing is not None:
            return None
        import os
        password = os.getenv("SHUJIE_ADMIN_PASSWORD", "").strip()
        generated = False
        if not password:
            password = secrets.token_urlsafe(16)
            generated = True
        session.add(
            UserEntity(
                username=username,
                password_hash=hash_password(password),
                is_admin=True,
                display_name="Administrator",
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
        if generated:
            logger.warning(
                "auth: seeded admin user '%s' with one-time random password: %s "
                "(set SHUJIE_ADMIN_PASSWORD or use `python -m app.set_password admin` to change it)",
                username,
                password,
            )
        else:
            logger.info("auth: seeded admin user '%s' from SHUJIE_ADMIN_PASSWORD", username)
        return password if generated else None


def authenticate(session: Session, username: str, password: str) -> UserEntity | None:
    user = get_user_by_username(session, username)
    if user is None:
        # 恒定时间路径：即使用户不存在也做一次 hash 比较，避免时序侧信道
        verify_password(password, hash_password("timing-equalizer"))
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
