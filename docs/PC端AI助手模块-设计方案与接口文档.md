# WMS 智能助手（AI Assistant）— PC 端代码设计与接口文档

> 版本：2.0.0 | 更新日期：2026-07-29 | 维护者：WMS 开发组

---

## 目录

1. [整体架构](#一整体架构)
2. [请求链路](#二请求链路)
3. [鉴权设计](#三鉴权设计)
4. [数据模型](#四数据模型)
5. [保留期策略](#五保留期策略)
6. [接口文档](#六接口文档)
7. [前端设计](#七前端设计)
8. [部署架构](#八部署架构)

---

## 一、整体架构

```
浏览器 (Vue 3 + Element Plus)
  │
  │ ① /api/ai/*  通过 nginx 代理
  ▼
Java 网关 (AiGatewayController)
  │  ② JwtAuthenticationFilter → 从 JWT 解析 currentUser
  │  ③ AiAssistantAccessService → 校验 AI_CHAT 权限 + clientType 合法性
  │  ④ AiGatewayService → 转发到 ai-backend，注入可信头
  ▼
Python AI Backend (FastAPI :8091)
  │  ⑤ auth_context → 解析可信头 → AuthContext
  │  ⑥ chat_config_resolver → 按 X-Client-Type 选 MINI/PC 配置
  │  ⑦ chat.py → 先落本地库（ai_conversation + ai_message + ai_audit_log）
  │  ⑧ dify_service / ragflow_service → 调用外部 AI 引擎
  ▼
┌──────────────┬──────────────┬──────────────┐
│   Dify       │   RAGFlow    │   MySQL 8.0  │
│ (对话/工作流) │ (知识库 RAG) │ (wms 库 5 张 │
│ :5001        │ :9380        │  ai_* 表)    │
└──────────────┴──────────────┴──────────────┘
```

### 核心设计原则

| 原则 | 说明 |
|------|------|
| **Java 鉴权，Python 信任** | Java 网关已完成 JWT 验签 + 权限校验，Python 层只消费可信头 |
| **本地先落库，再调外部** | 用户消息先写 `ai_message`，再调 Dify；回复回来后补写 ASSISTANT 消息 |
| **双端独立配置** | MINI/PC 各自独立的 Dify app key/baseUrl，通过 `X-Client-Type` 头区分 |
| **API Key 加密存储** | Fernet 对称加密，密钥来自 `AI_CONFIG_SECRET` 环境变量；日志/响应从不出现明文 |
| **主存储归 ai-backend** | 会话/消息以本地 MySQL 为权威数据源，Dify 为计算引擎 |

---

## 二、请求链路

### 2.1 SSE 流式对话（主链路）

```
用户输入 "帮我查库存"
  │
  ▼
[前端] useSSEStream.start()
  │  POST /api/ai/chat/workflow/stream
  │  Body: {"query":"帮我查库存","conversation_id":null}
  │  Header: X-Client-Type: PC, Authorization: Bearer <jwt>
  ▼
[nginx] /api/ai/ → proxy_pass wms-backend:8080
  ▼
[Java] AiGatewayController.gateway()
  │  (1) request.getAttribute("currentUser") → SysUser
  │  (2) aiAssistantAccessService.assertAssistantAccess(user, "PC")
  │       → 校验登录态 + AI_CHAT 权限 + clientType ∈ {MINI, PC}
  │  (3) aiGatewayService.forward(request, body, user, "PC")
  │       → 注入可信头：X-User-Id, X-Tenant-Id, X-Company-Id,
  │         X-Client-Type, X-Is-Super-Admin, X-Permission-Codes="AI_CHAT"
  │       → RestTemplate 转发到 http://wms-ai-backend:8091/api/ai/chat/workflow/stream
  ▼
[Python] chat.chat_workflow_stream()
  │  (1) _resolve(request) → 按 X-Client-Type=PC 取 PC 端 Dify 配置
  │  (2) _resolve_user(request, cfg) → require_trusted_context(request)
  │       → 解析 X-* 头 → AuthContext(user_id="19", tenant_id=1, client_type="PC", ...)
  │  (3) _persist_user_message(ctx, conversation_id, query)
  │       → ensure_conversation() → INSERT ai_conversation
  │       → append_message(role=USER) → INSERT ai_message
  │       → append_audit(SEND_MESSAGE) → INSERT ai_audit_log
  │  (4) dify.stream_workflow(query, user_id, conversation_id)
  │       → POST http://docker-api-1:5001/v1/workflows/run
  │       → SSE 逐行 yield 给前端
  │  (5) finally:
  │       → _persist_assistant_message() → INSERT ai_message (role=ASSISTANT)
  │       → _persist_external_ref() → UPSERT ai_external_conversation_ref
  ▼
[前端] useSSEStream 解析 SSE 事件
  │  text_chunk → 过滤 <think> 标签 → content.value += text → 实时渲染
  │  workflow_finished → callbacks.onComplete({conversationId, content})
  ▼
用户看到 AI 回复（Markdown 渲染）
```

### 2.2 会话列表查询（本地优先，Dify 兜底）

```
GET /api/ai/chat/conversations
  │
  ▼
[Python] chat.list_conversations()
  │  (1) _resolve_user(request) → AuthContext
  │  (2) get_chat_store().list_conversations(tenant_id, user_id, client_type)
  │       → SELECT * FROM ai_conversation WHERE tenant_id=? AND user_id=? AND client_type=? AND status='ACTIVE'
  │  (3) 有结果 → {"code":200, "data":[...], "source":"local"}
  │      无结果 → 回退 Dify API → {"code":200, "data":[...], "source":"dify"}
```

### 2.3 知识库检索链路

```
POST /api/ai/knowledge/retrieval
  Body: {"question":"退货流程","dataset_ids":["xxx"],"top_k":5}
  ▼
[Python] knowledge.retrieval_test()
  │  ragflow.retrieve(question, dataset_ids, top_k)
  │  → POST http://docker-ragflow-cpu-1:9380/api/v1/retrieval
  ▼
返回 Top-K 文档片段
```

---

## 三、鉴权设计

### 3.1 三种模式

| 模式 | 环境变量 | 适用场景 | 身份来源 |
|------|---------|---------|---------|
| **A. 可信头（推荐生产）** | `WMS_AI_REQUIRE_TRUSTED_HEADERS=true` | Java 网关前置的生产部署 | `X-User-Id`, `X-Tenant-Id` 等请求头 |
| **B. JWT 直连** | `WMS_AI_REQUIRE_AUTH=true` | 无 Java 网关的开发/测试环境 | `Authorization: Bearer <jwt>` |
| **C. 开发占位** | 两者均未设置 | 本地开发 | `user_id="wms-user"` 固定值 |

### 3.2 模式 A：可信头（当前生产模式）

**Java 侧注入的可信头：**

| 请求头 | 来源 | 必填 |
|--------|------|------|
| `X-User-Id` | `SysUser.getId()` | ✅ |
| `X-Tenant-Id` | `SysUser.getTenantId()` | ✅ |
| `X-Company-Id` | `SysUser.getCompanyId()` | 否 |
| `X-Client-Type` | 请求头透传，默认 `"PC"` | ✅ |
| `X-Is-Super-Admin` | `SysUser.isSuperAdmin()` | 否（默认 false） |
| `X-Role-Codes` | 当前为空字符串 | 否 |
| `X-Permission-Codes` | 固定 `"AI_CHAT"`（已在入口校验） | ✅ |

**Python 侧校验逻辑（`auth_context.py:require_trusted_context`）：**

1. 提取 `X-User-Id`、`X-Tenant-Id`、`X-Client-Type` → 归一化到 `MINI` / `PC`
2. 提取 `X-Permission-Codes` → 必须包含 `AI_CHAT`
3. 缺失必填头或权限 → `PermissionError` → 路由层转为 HTTP 401
4. `AuthContext` 是 frozen dataclass，构造后不可变

### 3.3 AuthContext 数据结构

```python
@dataclass(frozen=True)
class AuthContext:
    user_id: str              # 用户 ID（字符串形态，如 "19"）
    tenant_id: int | None     # 租户 ID
    company_id: int | None    # 公司 ID
    client_type: str          # "MINI" | "PC"
    is_super_admin: bool      # 是否超管
    role_codes: list[str]     # 角色编码列表
    permission_codes: list[str]  # 权限点列表（至少含 AI_CHAT）
    raw_claims: dict          # 原始数据，用于可观测性
```

### 3.4 端类型归一化

`chat_config_resolver.py:normalize_client_type()` 将扩展枚举收敛到基线值：

| 输入 | 归一化结果 |
|------|-----------|
| `PC`, `PC_WEB`, `PC_CLIENT`, `OPEN_PLATFORM` | `PC` |
| `MINI`, `MINI_PROGRAM`, `MINI_APP` | `MINI` |
| `null`, `""`, 非法值 | `PC`（兜底） |

---

## 四、数据模型

### 4.1 ER 图（5 张表）

```
ai_conversation (会话主表)
    │ 1:N
    ├─── ai_message (消息表)
    │      └── external_message_id → Dify 消息追溯
    │
    ├─── ai_external_conversation_ref (Dify 映射)
    │      └── (conversation_id, external_provider) UNIQUE
    │
    ├─── ai_conversation_link (跨端同步)
    │      └── source_conversation_id → target_conversation_id
    │
    └─── ai_audit_log (审计日志，append-only)
           └── operation_type: SEND_MESSAGE | CONVERSATION_DELETE | ...
```

### 4.2 ai_conversation — 本地会话主表

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT UNSIGNED PK | 本地会话 ID |
| `tenant_id` | BIGINT UNSIGNED | 租户 ID，默认 1 |
| `user_id` | BIGINT UNSIGNED | 所属用户 ID |
| `client_type` | VARCHAR(32) | MINI / PC（归一化后） |
| `source_client_type` | VARCHAR(32) | 创建时的原始请求端 |
| `primary_client_type` | VARCHAR(32) | 跨端时的代表端 |
| `title` | VARCHAR(255) | 会话标题，默认空 |
| `status` | VARCHAR(32) | ACTIVE / ARCHIVED / DELETED |
| `retention_level` | VARCHAR(32) | NORMAL / FAVORITE / PINNED |
| `external_conversation_id` | VARCHAR(128) | Dify 会话 ID 冗余 |
| `expires_at` | DATETIME | 到期时间（FAVORITE/PINNED 为 NULL） |
| `archived_at` | DATETIME | 归档时间 |
| `deleted_at` | DATETIME | 软删除时间 |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 更新时间（自动更新） |

**索引：** `(tenant_id, user_id, client_type, status)`, `(expires_at)`, `(archived_at)`, `(external_conversation_id)`

### 4.3 ai_message — 本地消息表

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT UNSIGNED PK | 消息 ID |
| `conversation_id` | BIGINT UNSIGNED | 所属会话 ID |
| `tenant_id` | BIGINT UNSIGNED | 租户 ID（冗余） |
| `user_id` | BIGINT UNSIGNED | 用户 ID（冗余） |
| `client_type` | VARCHAR(32) | 端类型 |
| `role` | VARCHAR(32) | USER / ASSISTANT / SYSTEM |
| `content` | MEDIUMTEXT | 消息正文 |
| `content_type` | VARCHAR(32) | TEXT / MARKDOWN / JSON |
| `contains_sensitive_data` | TINYINT | 是否含敏感数据 |
| `permission_snapshot` | VARCHAR(1024) | 写入时的权限快照 |
| `data_scope_snapshot` | VARCHAR(1024) | 写入时的数据范围快照 |
| `message_meta` | JSON | 扩展元数据（tokens、模型名等） |
| `external_message_id` | VARCHAR(128) | Dify 消息 ID，用于追溯 |
| `created_at` | DATETIME | 创建时间 |
| `deleted_at` | DATETIME | 软删除时间 |

**索引：** `(conversation_id, created_at)`, `(tenant_id, user_id)`, `(role)`

### 4.4 ai_audit_log — 审计日志表

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT UNSIGNED PK | 审计 ID |
| `tenant_id` | BIGINT UNSIGNED | 租户 ID |
| `operator_user_id` | BIGINT UNSIGNED | 操作人 ID |
| `operation_type` | VARCHAR(64) | SEND_MESSAGE / CONVERSATION_DELETE 等 |
| `target_conversation_id` | BIGINT UNSIGNED | 目标会话 ID |
| `target_message_id` | BIGINT UNSIGNED | 目标消息 ID |
| `client_type` | VARCHAR(32) | 触发端 |
| `operation_result` | VARCHAR(32) | SUCCESS / FAILED |
| `detail` | JSON | 操作详情 |
| `created_at` | DATETIME | 创建时间 |

**索引：** `(tenant_id, operation_type, created_at)`, `(target_conversation_id)`, `(operator_user_id, created_at)`

### 4.5 ai_external_conversation_ref — 外部会话映射表

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT UNSIGNED PK | 映射 ID |
| `tenant_id` | BIGINT UNSIGNED | 租户 ID |
| `conversation_id` | BIGINT UNSIGNED | 本地会话 ID |
| `external_provider` | VARCHAR(32) | DIFY / RAGFLOW |
| `external_conversation_id` | VARCHAR(128) | 外部平台会话 ID |
| `client_type` | VARCHAR(32) | 端类型 |
| `status` | VARCHAR(32) | ACTIVE / CLOSED / INVALID |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 更新时间 |

**唯一键：** `(conversation_id, external_provider)` — 每个本地会话在每个外部平台最多一条映射

### 4.6 ai_conversation_link — 跨端同步关系表

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT UNSIGNED PK | 关联 ID |
| `source_conversation_id` | BIGINT UNSIGNED | 源会话 ID |
| `target_conversation_id` | BIGINT UNSIGNED | 目标会话 ID |
| `link_type` | VARCHAR(32) | SYNC / MIGRATE |
| `source_client_type` | VARCHAR(32) | 源端类型 |
| `target_client_type` | VARCHAR(32) | 目标端类型 |
| `operator_user_id` | BIGINT UNSIGNED | 触发用户 ID |
| `sync_cursor_message_id` | BIGINT UNSIGNED | 同步游标 |
| `created_at` | DATETIME | 创建时间 |

---

## 五、保留期策略

### 5.1 保留天数

| 客户端 | 保留天数 | 说明 |
|--------|---------|------|
| MINI | 90 天 | 小程序端会话 90 天后自动归档 |
| PC | 365 天 | PC 端会话 365 天后自动归档 |
| FAVORITE | 永久 | 收藏会话不归档 |
| PINNED | 永久 | 置顶会话不归档 |

### 5.2 生命周期状态机

```
ACTIVE ──(到期)──▶ ARCHIVED ──(归档 30 天后)──▶ 消息软删除（会话保留）
  │                    │
  ├──(用户手动)────────┼──▶ DELETED（软删除）
  │
  └──(设为收藏/置顶)──▶ retention_level=FAVORITE/PINNED → 永不过期
```

### 5.3 定时任务

- **调度器：** APScheduler `BackgroundScheduler`
- **频率：** 每天凌晨 03:00（cron: `0 3 * * *`）
- **流程：**
  1. `archive_expired(now)` — 扫描 ACTIVE 会话，将到期者改为 ARCHIVED
  2. `delete_archived(now)` — 扫描 ARCHIVED 超过 30 天的会话，软删除其消息
- **禁用：** 设 `WMS_AI_DISABLE_SCHEDULER=true` 可关闭定时任务

---

## 六、接口文档

### 6.1 对话接口

#### 6.1.1 SSE 流式工作流对话（主接口）

```
POST /api/ai/chat/workflow/stream
```

**描述：** PC 端默认使用的对话接口，对接到 Dify 工作流应用。

**请求头：**
| 头 | 必填 | 说明 |
|----|------|------|
| `Authorization` | ✅ | `Bearer <JWT>` |
| `X-Client-Type` | 否 | `PC`（默认） |
| `Content-Type` | ✅ | `application/json` |

**请求体：**
```json
{
  "query": "帮我查一下库存",
  "conversation_id": null
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 用户输入内容 |
| `conversation_id` | string | 否 | 续传会话 ID；为 null 时新建会话 |
| `user_id` | string | 否 | 已废弃，由后端 AuthContext 覆盖 |

**响应：** `text/event-stream` (SSE)

SSE 事件类型：

| event | 说明 | 关键字段 |
|-------|------|---------|
| `workflow_started` | 工作流启动 | `data.id`, `data.inputs` |
| `node_started` | 节点开始执行 | `data.node_id`, `data.title`, `data.node_type` |
| `node_finished` | 节点执行完成 | `data.node_id`, `data.outputs`, `data.status` |
| `text_chunk` | 流式文本片段 | `data.text` |
| `workflow_finished` | 工作流完成 | `data.status`, `data.outputs`, `data.error` |
| `error` | 错误 | `message` |

示例流：
```
data: {"event":"workflow_started","data":{"id":"xxx","inputs":{"query":"帮我查库存"}}}
data: {"event":"node_started","data":{"node_id":"node1","title":"意图识别","node_type":"llm"}}
data: {"event":"node_finished","data":{"node_id":"node1","outputs":{"intent":"query_inventory"},"status":"succeeded"}}
data: {"event":"text_chunk","data":{"text":"好的，我来帮您查询库存情况。"}}
data: {"event":"text_chunk","data":{"text":"\n\n目前仓库A的库存如下：..."}}
data: {"event":"workflow_finished","data":{"status":"succeeded","outputs":{"answer":"..."}}}
```

#### 6.1.2 SSE 流式 Chat 对话

```
POST /api/ai/chat/stream
```

**描述：** 对接到 Dify Chat 类型应用（非工作流）。

**请求体：**
```json
{
  "query": "你好",
  "conversation_id": null,
  "dataset_ids": ["dataset-id-1"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 用户输入 |
| `conversation_id` | string | 否 | 会话 ID |
| `dataset_ids` | string[] | 否 | 知识库数据集 ID 列表 |

**SSE 事件：**

| event | 说明 |
|-------|------|
| `message` | 流式回答片段 |
| `message_end` | 回答结束，含 metadata |
| `agent_message` | Agent 模式回答 |
| `agent_thought` | Agent 思考过程 |
| `error` | 错误 |

#### 6.1.3 阻塞式对话

```
POST /api/ai/chat/send
```

**请求体：** 同 `/chat/stream`

**响应：**
```json
{
  "answer": "您好，有什么可以帮您？",
  "conversation_id": "abc123",
  "metadata": {
    "usage": {"total_tokens": 150}
  }
}
```

#### 6.1.4 会话列表

```
GET /api/ai/chat/conversations
```

**响应：**
```json
{
  "code": 200,
  "data": [
    {
      "id": "1",
      "title": "",
      "status": "ACTIVE",
      "client_type": "PC",
      "retention_level": "NORMAL",
      "created_at": "2026-07-29T10:00:00",
      "updated_at": "2026-07-29T10:30:00"
    }
  ],
  "source": "local"
}
```

`source` 字段：`"local"` = 从本地 MySQL 查询，`"dify"` = 回退到 Dify API。

#### 6.1.5 会话历史消息

```
GET /api/ai/chat/conversations/{conversation_id}/messages
```

**响应：**
```json
{
  "code": 200,
  "data": [
    {
      "id": "100",
      "conversation_id": "1",
      "role": "USER",
      "content": "帮我查一下库存",
      "created_at": "2026-07-29T10:00:00"
    },
    {
      "id": "101",
      "conversation_id": "1",
      "role": "ASSISTANT",
      "content": "好的，我来帮您查询库存情况...",
      "external_message_id": "dify-msg-xxx",
      "created_at": "2026-07-29T10:00:05"
    }
  ],
  "source": "local"
}
```

#### 6.1.6 删除会话

```
DELETE /api/ai/chat/conversations/{conversation_id}
```

**行为：** 本地软删除（status → DELETED）+ 调 Dify 删除接口 + 写审计日志。

---

### 6.2 知识库接口

所有接口前缀：`/api/ai/knowledge`

#### 6.2.1 数据集列表

```
GET /api/ai/knowledge/datasets
```

#### 6.2.2 创建数据集

```
POST /api/ai/knowledge/datasets
Content-Type: application/json

{"name": "产品手册", "description": "产品使用说明文档"}
```

#### 6.2.3 删除数据集

```
DELETE /api/ai/knowledge/datasets/{dataset_id}
```

#### 6.2.4 文档列表

```
GET /api/ai/knowledge/datasets/{dataset_id}/documents?page=1&page_size=50
```

#### 6.2.5 上传文档

```
POST /api/ai/knowledge/datasets/{dataset_id}/documents
Content-Type: multipart/form-data

file: <文件二进制>
```

#### 6.2.6 批量删除文档

```
DELETE /api/ai/knowledge/datasets/{dataset_id}/documents
Content-Type: application/json

{"ids": ["doc-id-1", "doc-id-2"]}
```

#### 6.2.7 文档解析状态

```
GET /api/ai/knowledge/datasets/{dataset_id}/documents/{doc_id}/status
```

#### 6.2.8 检索测试

```
POST /api/ai/knowledge/retrieval
Content-Type: application/json

{
  "question": "退货流程是什么",
  "dataset_ids": ["dataset-id-1"],
  "top_k": 5
}
```

---

### 6.3 配置管理接口

#### 6.3.1 全局配置（legacy，正在被 admin 配置取代）

```
GET /api/ai/config
```
返回脱敏后的全局配置（apiKey 显示为 `app-****Y3`）。

```
POST /api/ai/config
Content-Type: application/json

{"dify_api_key": "app-xxx", "dify_api_base_url": "http://docker-api-1:5001"}
```
部分更新，只允许白名单字段。

#### 6.3.2 多端配置（推荐）

```
GET /api/ai/admin/config?clientType=PC
```
返回 PC 端脱敏配置（apiKey 以 masked 形式展示）。

**响应示例：**
```json
{
  "code": 200,
  "message": "OK",
  "data": {
    "enabled": true,
    "provider": "DIFY",
    "baseUrl": "http://docker-api-1:5001",
    "apiKeyMasked": "app-****iY3",
    "appType": "WORKFLOW",
    "endpoint": "/workflows/run",
    "inputKey": "query",
    "outputKey": "answer",
    "timeoutMs": 120000,
    "userPrefix": "wms_"
  }
}
```

```
PUT /api/ai/admin/config?clientType=PC
Content-Type: application/json

{
  "enabled": true,
  "provider": "DIFY",
  "baseUrl": "http://docker-api-1:5001",
  "apiKey": "app-new-api-key",
  "appType": "WORKFLOW",
  "timeoutMs": 120000
}
```

**规则：**
- `apiKey` 为空时保留旧值
- `apiKey` 传入非空值时加密存储
- `baseUrl` 以 `/` 结尾时自动 `rstrip`
- 校验 provider = DIFY 时 appType 必须是 CHAT / AGENT_CHAT / WORKFLOW 之一

#### 6.3.3 连接测试

```
POST /api/ai/admin/config/test?clientType=PC
```

**响应：**
```json
{
  "code": 200,
  "data": {
    "success": true,
    "durationMs": 342,
    "message": "连接成功：WMS智能助手（WORKFLOW）"
  }
}
```

---

### 6.4 连接测试接口

```
POST /api/ai/test/dify
POST /api/ai/test/ragflow
```

**响应格式：**
```json
{"ok": true, "message": "应用名称（chat）"}
{"ok": false, "message": "API Key 无效（鉴权失败）"}
{"ok": false, "message": "无法连接 Dify：..."}
```

---

### 6.5 健康检查

```
GET /api/ai/health
```

**响应：**
```json
{
  "status": "ok",
  "dify_configured": true,
  "ragflow_configured": false
}
```

---

## 七、前端设计

### 7.1 组件树

```
App.vue
 └── MainLayout.vue
      ├── TaskDrivenSidebar.vue (侧边栏)
      │    └── SidebarMenuTree.vue → 包含"AI 助手"菜单项
      └── 主内容区
           └── AgentPlaceholder.vue (Agent 工作台面板)
                ├── 能力卡片 (数据分析 / 智能问答 / 文档检索 / 流程编排)
                └── 工具列表 (数据库查询 / API 调用 / 代码执行 / 文档解析)

AdminMainLayout.vue
 └── AdminAiConfigView.vue (AI 配置管理页)
      ├── 概览统计卡片
      ├── 配置表格 (PC/MINI 双端)
      ├── 新增/编辑弹窗 (Provider, BaseURL, API Key, AppType...)
      └── 测试连接按钮
```

### 7.2 核心 Composable

#### useSSEStream — SSE 流式消费

```javascript
const {
  content,          // Ref<string> — 累积的 AI 回复文本
  isStreaming,      // Ref<boolean> — 是否正在流式接收
  error,            // Ref<string|null> — 错误信息
  conversationId,   // Ref<string|null> — 当前会话 ID
  metadata,         // Ref<object> — token 用量等元数据
  thinkingSteps,    // Ref<array> — 工作流思考过程节点
  start,            // (fetchFn, callbacks?) => Promise — 开始流式
  stop,             // () => void — 中断流式
  reset,            // () => void — 重置状态
} = useSSEStream()
```

**`start(fetchFn, callbacks)` 工作流程：**

1. 调用 `fetchFn(signal)` → 获取 `Response`
2. `response.body.getReader()` → 逐块读取
3. 按 `\n` 分行 → 提取 `data:` 行 → `JSON.parse`
4. 按 `event` 类型分发：
   - `text_chunk` → `<think>` 标签过滤 → 追加到 `content`
   - `workflow_finished` → 暴露最终 outputs，触发 `onComplete`
   - `node_started` / `node_finished` → 记录思考步骤
   - `error` → 设置 error 状态
5. 网络错误时自动生成占位提示

**`<think>` 标签过滤：**
- 支持跨 chunk 的不完整标签（状态机实现）
- 标签外文本 → 正式回答（直接渲染）
- 标签内文本 → 存入 `thinkingSteps`（折叠显示）

#### useMarkdown — Markdown 渲染

```javascript
const html = useMarkdown(textRef)  // ComputedRef<string>
// 或直接调用
const html = renderMarkdown(text)  // string → string
```

支持语法：标题、粗体/斜体、代码块、行内代码、链接、图片、列表、表格、水平线、引用块。

### 7.3 API 封装

#### ai.js 核心方法

| 方法 | 说明 |
|------|------|
| `streamChat(query, conversationId, callbacks)` | SSE 流式工作流对话 |
| `sendMessage(query, conversationId)` | 阻塞式对话 |
| `getConversations()` | 获取会话列表 |
| `getMessages(conversationId)` | 获取会话历史 |
| `deleteConversation(id)` | 删除会话 |
| `testDifyConnection()` | 测试 Dify 连接 |
| `testRagFlowConnection()` | 测试 RAGFlow 连接 |
| `getConfig()` / `saveConfig(cfg)` | 读写全局配置 |

#### adminAiConfig.js

| 方法 | 说明 |
|------|------|
| `getAdminConfig(clientType)` | 获取指定端脱敏配置 |
| `saveAdminConfig(clientType, payload)` | 保存指定端配置 |
| `testAdminConfig(clientType)` | 测试指定端连接 |

---

## 八、部署架构

### 8.1 容器拓扑

```
                      ┌──────────────────┐
                      │   nginx :80      │
                      │   (frontend)     │
                      └──────┬───────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     /api/ai/*│     /api/*   │   /api/dify/*│  /api/ragflow/*
              ▼              ▼              ▼              ▼
    ┌─────────────┐  ┌─────────────┐  ┌──────────┐  ┌──────────────┐
    │ wms-backend │  │ wms-backend │  │docker-   │  │docker-ragflow│
    │ :8080       │  │ :8080       │  │api-1:5001│  │-cpu-1:9380   │
    │ (Java)      │  │ (业务API)   │  │ (Dify)   │  │ (RAGFlow)    │
    └──────┬──────┘  └─────────────┘  └──────────┘  └──────────────┘
           │
           │ trusted headers
           ▼
    ┌──────────────┐
    │wms-ai-backend│
    │ :8091        │
    │ (Python)     │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │  MySQL 8.0   │
    │  wms 库      │
    │  ai_* 表     │
    └──────────────┘
```

### 8.2 网络

| 容器 | 网络 |
|------|------|
| nginx | `project-10_wms-network` |
| wms-backend (Java) | `project-10_wms-network` |
| wms-ai-backend (Python) | `project-10_wms-network` + `docker_default`（双网卡访问 Dify） |
| docker-api-1 (Dify) | `docker_default` |
| docker-ragflow-cpu-1 | `docker_default` |
| mysql | `project-10_wms-network` |

### 8.3 环境变量（生产环境）

```bash
# ai-backend 容器
AI_CHAT_STORE_BACKEND=mysql           # 使用 MySQL 存储
WMS_AI_REQUIRE_TRUSTED_HEADERS=true   # 可信头鉴权模式
WMS_AI_REQUIRE_AUTH=true              # 备选 JWT 鉴权
WMS_JWT_SECRET=<与 Java 端一致>       # JWT HS256 密钥
DB_HOST=mysql
DB_PORT=3306
DB_USER=root
DB_PASSWORD=Zsds2604!
DB_NAME=wms
AI_CONFIG_SECRET=<Fernet 加密密钥>     # API Key 加密密钥
```

### 8.4 Docker 启动命令

```bash
docker run -d \
  --name wms-ai-backend \
  --network project-10_wms-network \
  --restart unless-stopped \
  -p 8091:8091 \
  -v /root/project-1.0/ai-backend/data:/app/data \
  -e AI_CHAT_STORE_BACKEND=mysql \
  -e WMS_AI_REQUIRE_TRUSTED_HEADERS=true \
  -e WMS_JWT_SECRET=<secret> \
  -e DB_HOST=mysql \
  -e DB_PORT=3306 \
  -e DB_USER=root \
  -e DB_PASSWORD=Zsds2604! \
  -e DB_NAME=wms \
  wms-ai-backend:latest \
  sh -c "pip install -r requirements.txt && cd /app && uvicorn main:app --host 0.0.0.0 --port 8091"

# 双网卡：连接 Dify
docker network connect docker_default wms-ai-backend
```

### 8.5 nginx 关键配置

```nginx
# AI 助手网关 → Java 鉴权 → ai-backend
location /api/ai/ {
    set $ai_upstream wms-backend:8080;
    proxy_pass http://$ai_upstream;
    proxy_read_timeout 300s;  # SSE 长连接
    proxy_buffering off;      # 流式透传
    proxy_http_version 1.1;
    chunked_transfer_encoding on;
}

# Dify 反代（浏览器直连）
location /api/dify/ {
    set $dify_upstream docker-api-1:5001;
    rewrite ^/api/dify/(.*)$ /$1 break;
    proxy_pass http://$dify_upstream;
    proxy_read_timeout 300s;
    proxy_buffering off;
}

# 静态资源永久缓存（Vite 内容哈希）
location /assets/ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

---

## 附录

### A. 项目文件索引

| 分层 | 关键文件 | 职责 |
|------|---------|------|
| Python 入口 | [ai-backend/main.py](../ai-backend/main.py) | FastAPI 启动、路由注册、定时任务 |
| 对话路由 | [ai-backend/routers/chat.py](../ai-backend/routers/chat.py) | SSE 流式对话、会话管理 |
| 知识库路由 | [ai-backend/routers/knowledge.py](../ai-backend/routers/knowledge.py) | RAGFlow 数据集/文档/检索 |
| 配置路由 | [ai-backend/routers/admin_ai_config.py](../ai-backend/routers/admin_ai_config.py) | 双端独立配置管理 |
| 鉴权服务 | [ai-backend/services/auth_context.py](../ai-backend/services/auth_context.py) | 三种鉴权模式、AuthContext |
| Dify 客户端 | [ai-backend/services/dify_service.py](../ai-backend/services/dify_service.py) | Dify API 封装 |
| RAGFlow 客户端 | [ai-backend/services/ragflow_service.py](../ai-backend/services/ragflow_service.py) | RAGFlow API 封装 |
| 存储协议 | [ai-backend/services/ai_chat_store.py](../ai-backend/services/ai_chat_store.py) | AiChatStore Protocol + 内存实现 |
| MySQL 存储 | [ai-backend/services/mysql_chat_store.py](../ai-backend/services/mysql_chat_store.py) | MySQL AiChatStore 实现 |
| ORM 模型 | [ai-backend/services/sql_models.py](../ai-backend/services/sql_models.py) | 5 张表的 SQLAlchemy 映射 |
| 保留期 | [ai-backend/services/retention_service.py](../ai-backend/services/retention_service.py) | 归档/清理定时任务 |
| 配置解析 | [ai-backend/services/chat_config_resolver.py](../ai-backend/services/chat_config_resolver.py) | X-Client-Type → 端配置 |
| Java 网关 | [src/.../controller/AiGatewayController.java](../src/main/java/com/wms/ai/controller/AiGatewayController.java) | /api/ai/** 通配入口 |
| Java 转发 | [src/.../service/AiGatewayService.java](../src/main/java/com/wms/ai/service/AiGatewayService.java) | 转发 + 可信头注入 |
| Java 鉴权 | [src/.../service/AiAssistantAccessService.java](../src/main/java/com/wms/ai/service/AiAssistantAccessService.java) | AI_CHAT 权限校验 |
| SQL 建表 | [sql/add_ai_chat_tables.sql](../sql/add_ai_chat_tables.sql) | 5 张表 DDL |
| 前端 SSE | [frontend/src/composables/useSSEStream.js](../frontend/src/composables/useSSEStream.js) | SSE 流式消费 |
| 前端渲染 | [frontend/src/composables/useMarkdown.js](../frontend/src/composables/useMarkdown.js) | Markdown → HTML |
| 前端面板 | [frontend/src/components/ai/AgentPlaceholder.vue](../frontend/src/components/ai/AgentPlaceholder.vue) | Agent 工作台 |
| 前端配置 | [frontend/src/views/AdminAiConfigView.vue](../frontend/src/views/AdminAiConfigView.vue) | AI 配置管理页 |
| nginx 配置 | [frontend/nginx.conf](../frontend/nginx.conf) | 路由规则、缓存策略 |

### B. 状态码约定

| HTTP 状态码 | 场景 |
|------------|------|
| 200 | 正常响应 |
| 400 | 请求参数错误 / 未配置 API Key |
| 401 | JWT 无效/过期/缺失 / 可信头缺失 / 无 AI_CHAT 权限 |
| 500 | 服务器内部错误 |

### C. 错误响应格式

```json
{
  "detail": "未提供有效Token或Token无效"
}
```

```json
{
  "detail": "缺少可信头 X-User-Id"
}
```

```json
{
  "detail": "缺少权限点 AI_CHAT"
}
```
