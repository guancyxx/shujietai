# 枢界台（ShuJieTai）MVP 设计文档

## 1. 项目定位

枢界台是一个多平台智能体会话驾驶舱：统一接入 Hermes、OpenClaw 等平台，记录任务与对话全流程，并在一个看板中完成追踪、回放与协同。

MVP 目标是先打通“统一接入 + 会话记录 + 基础驾驶舱展示”，为后续平台扩展和流程编排预留标准接口。

## 2. 目标与非目标

### 2.1 MVP 目标

1. 支持至少两个平台接入（Hermes、OpenClaw）。
2. 将平台事件标准化为统一事件与消息模型。
3. 提供会话驾驶舱三栏页面：任务栏 / 对话时间线 / 状态栏。
4. 提供会话与看板聚合查询 API。
5. 提供基础幂等、重试、审计与追溯能力。

### 2.2 非目标（MVP 不做）

1. 复杂 RBAC（先采用 workspace 级 token）。
2. 完整流程编排引擎（仅预留扩展位）。
3. 多租户计费与配额体系。

## 3. 技术栈

- Backend: FastAPI
- Frontend: Vue
- Database: PostgreSQL
- Cache/Realtime: Redis
- Deployment: Docker Compose

## 4. 架构方案（已确认 A）

采用“事件总线思路 + 平台 Connector 适配器”。

分层：
1. Connectors 层：connector-hermes / connector-openclaw
2. Normalizer 层：平台模型 -> 统一事件模型
3. Session Core 层：会话聚合、时间线、任务状态联动
4. Storage 层：PostgreSQL + Redis
5. Dashboard 层：会话驾驶舱（三栏）

关键原则：新增平台仅新增 Connector 与映射逻辑，不修改会话核心与看板核心。

## 5. 组件职责与 API 边界

### 5.1 组件职责

1. connector-hermes
   - 拉取或接收 Hermes 平台事件
   - 转发至 ingest-api

2. connector-openclaw
   - 拉取或接收 OpenClaw 平台事件
   - 转发至 ingest-api

3. normalizer
   - 将平台 payload 映射为 ConversationEvent / Message
   - 处理角色、时间戳、事件类型标准化

4. session-service
   - 会话生命周期聚合
   - 时间线回放数据组装
   - 任务状态联动

5. board-service
   - 输出三栏驾驶舱聚合结果

6. ingest-api
   - 统一写入入口
   - 幂等校验与审计记录

7. query-api
   - 会话列表、详情、时间线、驾驶舱查询

### 5.2 MVP API

- POST `/api/v1/events/ingest`
- GET `/api/v1/sessions`
- GET `/api/v1/sessions/{id}`
- GET `/api/v1/sessions/{id}/timeline`
- GET `/api/v1/board/cockpit?session_id=...`

## 6. 统一数据模型（MVP 最小集）

1. `platforms`
   - `id`, `code`, `name`, `status`

2. `sessions`
   - `id`, `platform_id`, `external_session_id`, `title`, `status`, `started_at`, `ended_at`

3. `messages`
   - `id`, `session_id`, `role`, `content`, `content_type`, `created_at`, `meta_json`

4. `events`
   - `id`, `session_id`, `event_type`, `payload_json`, `created_at`

5. `tasks`
   - `id`, `session_id`, `title`, `lane(todo|doing|done)`, `priority`, `assignee`, `updated_at`

6. `session_metrics`
   - `session_id`, `token_in`, `token_out`, `latency_ms_p50`, `error_count`, `updated_at`

设计约束：
- 平台特有字段放入 `meta_json`/`payload_json`。
- 看板查询只读聚合，不覆盖原始消息与原始事件。

## 7. 前端驾驶舱信息架构

已确认采用 A：平衡型三栏布局。

1. 左栏（任务）
   - ToDo / Doing / Done 泳道
   - 任务状态变更与优先级展示

2. 中栏（对话）
   - 跨平台统一时间线
   - 按平台/角色筛选

3. 右栏（状态）
   - 当前会话状态
   - 关键指标（token、延迟、错误）
   - 下一步建议

## 8. 容错、审计与安全

1. 幂等写入
   - 按 `(platform, event_id)` 去重

2. 失败重试
   - 指数退避：1s / 3s / 10s
   - 超阈值写入 `dead_letter_events`

3. 可追溯
   - 原始 `payload_json` 全量保留

4. 审计
   - 记录 `request_id/platform/session_id/duration`

5. 权限
   - MVP 采用 workspace 级 token

6. 安全基线
   - API key 仅通过环境变量注入
   - 敏感字段支持脱敏展示

## 9. 测试与验收标准

### 9.1 测试范围

1. 单元测试
   - normalizer 映射
   - ingest 幂等
   - session 聚合

2. 集成测试
   - ingest 写入后，sessions/timeline/cockpit 数据一致
   - 重复 event_id 不产生重复消息

3. Connector 合约测试
   - Hermes/OpenClaw 示例 payload 均可映射为统一事件

4. 前端验收
   - 三栏联动：任务更新 + 对话回放 + 状态联动

### 9.2 MVP 通过标准

1. 支持至少 2 个平台接入。
2. 单会话 1,000 条消息回放无错。
3. ingest 失败可通过 request_id/event_id 追溯。

## 10. 里程碑建议

- M1: 项目骨架 + 统一模型 + ingest/query API
- M2: Hermes/OpenClaw Connector + Normalizer
- M3: 三栏驾驶舱 UI + 会话回放
- M4: 容错审计 + 测试收口

## 11. 命名结论

项目名：枢界台（ShuJieTai）

- 中文强调“多平台边界统一的调度中枢”。
- 英文转写用于仓库目录、镜像名与服务名。