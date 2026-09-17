# ShuJieTai 生产部署（sjt.guancyxx.cn）

> 任务卡 #272（M4）。拓扑对齐 taskdeck / 博客现行模式（2026-09-16 迁移后）：
> **容器全部跑在 NAS，云服务器只做 TLS 入口**。
> 分工红线：服务器 132.232.249.122 禁 agent SSH——DNS、证书、云 nginx 命令由 galen 执行；
> 本目录所有配置入仓，NAS 侧操作可由 agent 协助。

## 拓扑

```
手机/浏览器
  │ https://sjt.guancyxx.cn
  ▼
腾讯云 nginx (132.232.249.122, 443 TLS 终结, TrustAsia)
  │ proxy_pass http://100.117.242.15:8400   （Tailscale 隧道）
  ▼
NAS (群晖 DS923+, /volume1/docker/shujietai)
  └─ docker compose（deploy/docker-compose.prod.yml）
      ├─ frontend  nginx:alpine ─ 0.0.0.0:8400→80 ─ vite build 静态托管 + /api 反代
      ├─ backend   uvicorn（启动前自动 alembic upgrade head）
      ├─ postgres  16-alpine（数据卷 shujietai_postgres_data）
      └─ redis     7-alpine
```

同域反代（页面与 API 都从 sjt.guancyxx.cn 出）顺带解决了 CORS 与后续 M3 iframe
的存储隔离问题。NAS 端口占用参考：8321=taskdeck、3005=blog、3300/2222=forgejo，
ShuJieTai 取 **8400**。

## 一、首次部署 — NAS 侧

```bash
ssh nas   # 或 ssh nas-lan 兜底

# 1) 部署副本（纯部署目标；只读 deploy key 可选）
git clone git@github.com:guancyxx/shujietai.git /volume1/docker/shujietai
cd /volume1/docker/shujietai

# 2) 生产秘钥（生成后 chmod 600，不入任何仓库/卡片/日志）
cp deploy/.env.prod.example deploy/.env.prod
chmod 600 deploy/.env.prod
vi deploy/.env.prod    # 填 POSTGRES_PASSWORD / SHUJIE_JWT_SECRET / SHUJIE_ADMIN_PASSWORD
#   生成：openssl rand -hex 24（PG密码）/ openssl rand -hex 48（JWT）

# 3) 首次拉起（之后交给 cron 自动部署）
sudo -n /usr/local/bin/docker compose --env-file deploy/.env.prod \
    -f deploy/docker-compose.prod.yml up -d --build

# 4) 验证（NAS 本机）
curl -s http://127.0.0.1:8400/api/v1/health
curl -s http://100.117.242.15:8400/api/v1/health   # 经 Tailscale，云侧反代依赖这条通
```

首启自动完成：alembic 建全表 + 种子 admin 用户（密码取
`SHUJIE_ADMIN_PASSWORD`；缺省则随机生成并打进 backend 日志，首登后建议改掉）。

### 自动部署 cron（galen，需 root）

NAS `/etc/crontab` 追加（DSM 升级可能重写 crontab，丢了按此重建）：

```
*/15 * * * * guancyxx flock -xn /tmp/shujietai-deploy.lock /volume1/docker/shujietai/deploy/nas-deploy.sh >> /volume1/docker/shujietai/nas-deploy.log 2>&1
```

`nas-deploy.sh` 与 taskdeck 同款纪律：marker 门控
（`.deployed-commit` 只记录部署且健康检查通过的 commit）→ reset → build →
`up -d` → 30×2s 健康检查 → 全绿才推进 marker；失败 marker 不动下轮重试。
**merged ≈ live（≤15 分钟）**。

## 二、首次部署 — galen 侧（云服务器，红线内）

1. **DNS**：`sjt.guancyxx.cn` A 记录 → `132.232.249.122`
2. **证书**：TrustAsia 给 `sjt.guancyxx.cn` 签发（流程同 tasks.guancyxx.cn），
   放到 `/etc/nginx/ssl/sjt.guancyxx.cn/{fullchain,privkey}.pem`
   （路径不同则同步改 `deploy/nginx/sjt.guancyxx.cn.conf`）
3. **vhost**（配置已在仓 `deploy/nginx/sjt.guancyxx.cn.conf`）：

```bash
sudo cp deploy/nginx/sjt.guancyxx.cn.conf /etc/nginx/sites-available/sjt.guancyxx.cn
sudo ln -s /etc/nginx/sites-available/sjt.guancyxx.cn /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

4. **验收**：手机蜂窝网络（非内网）打开 `https://sjt.guancyxx.cn` →
   登录 → 任务面板可用、会话/派发页无 401、WS 实时事件正常（页面顶部连接状态）。

## 三、fetch-all cron 恢复（Mac 本机）

原 cron `c72c6c2f12af`（Shujietai Git Fetch All，每日 05:00，2026-08-28 因本地服务
停摆暂停）。恢复三步（**等 sjt.guancyxx.cn 上线后**）：

```bash
# 1) 用仓内新版覆盖 hermes 脚本（API 指向新域名 + M1 登录换 JWT）
cp deploy/scripts/shujietai-fetch-all.py ~/.hermes/scripts/shujietai-fetch-all.py

# 2) 写凭据（建一个专用账号或直接用 admin；chmod 600）
cat > ~/.hermes/.shujietai-fetch-all.env <<'EOF'
SJT_API_USER=admin
SJT_API_PASSWORD=<密码>
EOF
chmod 600 ~/.hermes/.shujietai-fetch-all.env

# 3) 手跑一次验证，再启用 cron（hermes cron enable c72c6c2f12af）
python3 ~/.hermes/scripts/shujietai-fetch-all.py
```

## 四、日常运维

```bash
ssh nas
bash /volume1/docker/shujietai/deploy/nas-deploy.sh      # 不等 cron 立即部署（几乎无 stdout）
tail -50 /volume1/docker/shujietai/nas-deploy.log         # 部署日志（看 "deployed <hash>"）
cat /volume1/docker/shujietai/.deployed-commit            # 线上版本
sudo -n /usr/local/bin/docker logs shujietai-backend --tail 50
sudo -n /usr/local/bin/docker compose --env-file /volume1/docker/shujietai/deploy/.env.prod \
    -f /volume1/docker/shujietai/deploy/docker-compose.prod.yml ps
```

**回滚**（无自动化，与 taskdeck 相同）：`git reset --hard <旧commit>` 后重跑
nas-deploy.sh（健康检查过了 marker 自动写）。

**不登服务器判断线上版本**：

```bash
curl -s https://sjt.guancyxx.cn/api/v1/health
```

## 五、边界与已知事项

- **M2/M3 尚未合并**（#270/#271 inbox）：本部署上线的是 M1 认证地基 +
  旧任务面板/派发功能；OIDC 与应用中心合并后经同一 cron 自动上线，无需改部署。
- **Hermes 桥默认禁用**：`HERMES_API_BASE_URL` 留空时派发到 hermes 的功能
  不可用但不影响服务启动。要启用：填 Mac 的 Tailscale 地址
  （`tailscale status` 查 Mac 的 100.x IP）+ 对应 API key，改 `.env.prod` 后重跑部署。
- **WS 单 worker**：dispatch 事件广播走进程内存，backend 不能加 `--workers N`，
  否则 WS 订阅断流。
- **admin 密码重置**：`docker exec -it shujietai-backend python -m app.set_password <user>`。
- 本地开发仍用根目录 `docker-compose.yml`（vite dev + bind mount + --reload），
  与本生产栈互不影响。
