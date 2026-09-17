#!/usr/bin/env bash
# ShuJieTai NAS 自动部署（参照 taskdeck nas-deploy.sh 模式）
#
# 纪律（与 taskdeck/博客保持一致，勿单边漂移）：
#   - 门控 = .deployed-commit marker：只记录「实际部署且健康检查通过」的 commit，
#     非 git HEAD——服务器上手动 git pull 骗不过 skip 检查
#   - 失败 marker 不动，下一轮重试
#   - cron 调用方负责 flock（同锁撞车直接让位），本脚本不再加锁
#   - 手动执行几乎无 stdout：结果以日志尾部 deployed <hash> + marker 为准
#
# cron 行（NAS /etc/crontab，DSM 升级可能重写，丢了按此重建）：
#   */15 * * * * guancyxx flock -xn /tmp/shujietai-deploy.lock /volume1/docker/shujietai/deploy/nas-deploy.sh >> /volume1/docker/shujietai/nas-deploy.log 2>&1

set -euo pipefail

REPO_DIR="${SJT_REPO_DIR:-/volume1/docker/shujietai}"
ENV_FILE="$REPO_DIR/deploy/.env.prod"
COMPOSE_FILE="$REPO_DIR/deploy/docker-compose.prod.yml"
MARKER_FILE="$REPO_DIR/.deployed-commit"
# NAS 群晖：docker 不在 PATH 且 sudo 只白名单 /usr/local/bin/docker
if command -v docker >/dev/null 2>&1; then
    DOCKER=(docker)
else
    DOCKER=(sudo -n /usr/local/bin/docker)
fi

SJT_PORT="$(grep -E '^SJT_WEB_PORT=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2 | tr -d '[:space:]')"
SJT_PORT="${SJT_PORT:-8400}"
HEALTH_URL="http://127.0.0.1:${SJT_PORT}/api/v1/health"

cd "$REPO_DIR"

remote_hash="$(git fetch origin main 2>/dev/null && git rev-parse origin/main)"
marker_hash="$(cat "$MARKER_FILE" 2>/dev/null || echo none)"

if [ "$remote_hash" = "$marker_hash" ]; then
    exit 0
fi

echo "==== $(date '+%F %T') deploying $remote_hash (marker=$marker_hash) ===="

git reset --hard "$remote_hash"

"${DOCKER[@]}" compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build

# 健康检查：30 次 × 2s；失败则不动 marker（下轮 cron 重试）
for i in $(seq 1 30); do
    if curl -sf --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
        echo "$remote_hash" > "$MARKER_FILE"
        echo "==== $(date '+%F %T') deployed $remote_hash ===="
        exit 0
    fi
    sleep 2
done

echo "==== $(date '+%F %T') HEALTH CHECK FAILED for $remote_hash; marker unchanged ===="
exit 1
