#!/bin/sh
# ShuJieTai 后端容器入口：SHUJIE_RUN_MIGRATIONS=1 时先跑 alembic 迁移再启动服务。
# 生产 compose 置 1（空库自动建表、发版自动升级 schema）；本地 dev compose 不设，保持手动迁移习惯。
set -e

if [ "${SHUJIE_RUN_MIGRATIONS:-0}" = "1" ]; then
    echo "[entrypoint] running alembic upgrade head"
    alembic upgrade head
fi

exec "$@"
