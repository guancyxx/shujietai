"""CLI: 交互式为用户设置/重置密码。

用法（backend 目录下）:
    python -m app.set_password <username> [new_password]

new_password 缺省时交互提示输入（getpass，不回显）。用户不存在则创建。
"""
from __future__ import annotations

import getpass
import sys

from sqlalchemy.orm import Session

from app.container import store
from app.db.user_model import UserEntity
from app.services.user_service import get_user_by_username, hash_password


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m app.set_password <username> [new_password]", file=sys.stderr)
        return 2
    username = argv[0]

    password = argv[1] if len(argv) > 1 else ""
    if not password:
        password = getpass.getpass(f"New password for '{username}': ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("passwords do not match", file=sys.stderr)
            return 2
    if len(password) < 8:
        print("password must be at least 8 characters", file=sys.stderr)
        return 2

    factory = getattr(store, "session_factory", None)
    if factory is None:
        print("no SQL session factory available (SESSION_STORE_BACKEND=memory?)", file=sys.stderr)
        return 1

    with Session(bind=factory.kw["bind"]) as session:
        user = get_user_by_username(session, username)
        if user is None:
            session.add(
                UserEntity(
                    username=username,
                    password_hash=hash_password(password),
                    is_admin=False,
                    display_name=username,
                )
            )
            action = "created"
        else:
            user.password_hash = hash_password(password)
            action = "updated"
        session.commit()
    print(f"password {action} for user '{username}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
