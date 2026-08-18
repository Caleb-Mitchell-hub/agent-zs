# ERP AI 助手对接文档

## 1. 背景

现有 ERP 系统已经有一个 AI 助手路由。Agent-Zs 已提供可用的 AI 对话页面和接口服务，当前服务地址为：

- 页面入口：`http://172.177.3.43:8001/`
- 健康检查：`http://172.177.3.43:8001/health`
- 登录接口：`POST /api/v1/auth/login`
- 流式对话接口：`GET /api/v1/query/stream`
- 会话列表接口：`GET /api/v1/sessions`
- 会话消息接口：`GET /api/v1/sessions/{session_id}/messages`

ERP 端的目标是：复用现有 ERP 的 AI 助手路由和导航入口，让用户在 ERP 内使用 Agent-Zs 的对话 UI，并复用 ERP 当前登录用户身份、租户和数据权限。

## 2. 推荐架构

推荐采用“ERP 前端路由 + ERP 网关反向代理 + Agent-Zs 服务”的方式接入。

```text
ERP 用户
  -> ERP AI 助手路由
  -> ERP 前端加载 Agent-Zs 对话页面
  -> ERP 网关代理 /agent-ai 和 /agent-ai-api
  -> Agent-Zs
  -> ERP/WMS 数据库
```

这样做的好处：

- 用户仍然从 ERP 原有 AI 助手入口进入。
- 避免浏览器跨域、Cookie、Authorization 头不一致的问题。
- ERP 可以统一控制登录态、菜单权限、租户权限和审计。
- Agent-Zs 可以继续独立部署和迭代。

## 3. ERP 端需要做什么

### 3.1 保留现有 AI 助手路由

ERP 端已有 AI 助手路由，例如：

```text
/ai-assistant
```

或实际项目中的已有路径：

```text
<ERP_AI_ASSISTANT_ROUTE>
```

该路由不需要重做聊天 UI，建议改为承载 Agent-Zs 页面。

前端可以选择以下两种方式之一。

方式 A：iframe 嵌入，最快落地。

```html
<iframe
  src="/agent-ai/"
  style="width: 100%; height: 100%; border: 0;"
></iframe>
```

方式 B：新窗口或内嵌 WebView 打开。

```ts
window.open('/agent-ai/', '_blank')
```

如果 ERP 是后台管理系统，推荐方式 A，用户体验最接近“ERP 内置 AI 助手”。

### 3.2 增加反向代理

ERP 部署层需要把 Agent-Zs 页面和 API 代理到同域路径。

示例 Nginx 配置：

```nginx
location /agent-ai/ {
    proxy_pass http://172.177.3.43:8001/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /agent-ai-api/ {
    proxy_pass http://172.177.3.43:8001/api/v1/;
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Authorization $http_authorization;
}
```

注意：`/api/v1/query/stream` 是 SSE 流式接口，必须关闭代理缓冲：

```nginx
proxy_buffering off;
proxy_cache off;
```

否则前端可能长时间看不到 AI 输出，或者连接中途断开。

### 3.3 登录态对接

Agent-Zs 当前使用 JWT 鉴权，前端请求接口时会携带：

```http
Authorization: Bearer <agent_zs_token>
```

ERP 端需要在用户进入 AI 助手页面前，为当前 ERP 用户换取 Agent-Zs token。

推荐 ERP 后端新增接口：

```http
GET /api/ai/sso-token
```

返回：

```json
{
  "status": "ok",
  "token": "<agent_zs_jwt>",
  "expires_in": 86400
}
```

Agent-Zs token 中应包含以下用户信息：

```json
{
  "user_id": 1,
  "tenant_id": 1,
  "username": "zhangsan",
  "real_name": "张三",
  "is_super_admin": false,
  "roles": ["sales"],
  "warehouse_ids": [1, 2],
  "region_ids": [10],
  "customer_ids": [1001, 1002],
  "product_ids": []
}
```

字段说明：

| 字段 | 来源 | 用途 |
| --- | --- | --- |
| `user_id` | ERP 当前用户 ID | 会话归属、任务归属、审计 |
| `tenant_id` | ERP 当前租户 ID | 多租户隔离 |
| `username` | ERP 用户名 | 展示和审计 |
| `real_name` | ERP 用户姓名 | 页面展示 |
| `is_super_admin` | ERP 超管标识 | 是否拥有全量数据权限 |
| `roles` | ERP 角色编码 | 后续扩展权限控制 |
| `warehouse_ids` | 用户可访问仓库 | 库存、订单、出入库过滤 |
| `region_ids` | 用户可访问区域 | 区域维度过滤 |
| `customer_ids` | 用户可访问客户 | 销售订单、客户数据过滤 |
| `product_ids` | 用户可访问商品 | 商品、库存维度过滤 |

### 3.4 前端 token 注入

ERP AI 助手路由加载 Agent-Zs 页面前，需要把 token 传给 Agent-Zs。

推荐方式：ERP 页面先调用 `/api/ai/sso-token`，再通过 URL 参数传给 Agent-Zs 页面。

```ts
const res = await fetch('/api/ai/sso-token')
const data = await res.json()
const url = `/agent-ai/?token=${encodeURIComponent(data.token)}`
```

iframe 示例：

```html
<iframe id="agentAiFrame" style="width:100%;height:100%;border:0;"></iframe>
```

```ts
async function loadAgentAi() {
  const res = await fetch('/api/ai/sso-token')
  const data = await res.json()
  document.getElementById('agentAiFrame').src =
    `/agent-ai/?token=${encodeURIComponent(data.token)}`
}
```

Agent-Zs 前端需要支持读取 URL 中的 `token` 并写入 `localStorage`：

```js
const urlToken = new URLSearchParams(window.location.search).get('token');
if (urlToken) {
  localStorage.setItem('token', urlToken);
  window.history.replaceState({}, document.title, window.location.pathname);
}
```

如果不希望 token 出现在 URL，也可以使用 `postMessage`：

```ts
iframe.contentWindow.postMessage(
  { type: 'AGENT_ZS_TOKEN', token: data.token },
  window.location.origin
)
```

对应 Agent-Zs 页面监听：

```js
window.addEventListener('message', event => {
  if (event.origin !== window.location.origin) return;
  if (event.data?.type === 'AGENT_ZS_TOKEN' && event.data.token) {
    localStorage.setItem('token', event.data.token);
  }
});
```

生产环境推荐 `postMessage` 或同域 Cookie，URL 参数方案适合先快速联调。

### 3.5 菜单权限

ERP 端需要控制哪些用户能看到 AI 助手菜单。

建议新增或复用权限码：

```text
AI_CHAT
```

菜单显示逻辑：

```text
用户拥有 AI_CHAT 权限 -> 显示 AI 助手入口
用户没有 AI_CHAT 权限 -> 不显示入口或提示无权限
```

Agent-Zs 后端仍会根据 JWT 校验接口权限和数据权限，ERP 菜单权限只负责入口控制。

### 3.6 会话和刷新

Agent-Zs 当前会把对话消息落库到自己的 `sessions` 和 `messages` 表。

ERP 端不需要自己保存 AI 对话记录，只需要保证：

- iframe 页面不被频繁销毁。
- 用户切换 ERP 页面后，再回到 AI 路由时可以继续使用同一个 Agent-Zs 页面。
- 如果 ERP 刷新页面，需要重新注入 token。

### 3.7 数据权限

ERP 端最重要的是把当前用户的数据范围传给 Agent-Zs。

如果用户是超管：

```json
{
  "is_super_admin": true,
  "warehouse_ids": [],
  "region_ids": [],
  "customer_ids": [],
  "product_ids": []
}
```

如果用户不是超管：

```json
{
  "is_super_admin": false,
  "warehouse_ids": [1, 2],
  "region_ids": [10],
  "customer_ids": [1001, 1002],
  "product_ids": [2001, 2002]
}
```

Agent-Zs 查询工具会根据这些字段限制 SQL 查询范围。

## 4. Agent-Zs 端需要配合什么

ERP 端接入时，Agent-Zs 建议补充以下能力：

1. 支持 URL token 或 `postMessage` token 注入。
2. 支持被 iframe 嵌入，必要时调整 `X-Frame-Options` 或 CSP。
3. 支持代理前缀，例如页面在 `/agent-ai/` 下运行时，API 仍能正确请求。
4. 提供 ERP SSO token 签发接口，或暴露内部签发工具给 ERP 后端调用。
5. 保证 `/api/v1/query/stream` 经过代理时能正常 SSE 输出。

## 5. 接口清单

### 5.1 ERP 新增接口

```http
GET /api/ai/sso-token
```

用途：当前 ERP 登录用户换取 Agent-Zs JWT。

响应：

```json
{
  "status": "ok",
  "token": "<agent_zs_jwt>",
  "expires_in": 86400
}
```

### 5.2 ERP 代理接口

```http
GET /agent-ai/
```

用途：访问 Agent-Zs 对话页面。

```http
GET /agent-ai-api/query/stream
```

用途：代理 Agent-Zs 流式对话。

```http
GET /agent-ai-api/sessions
```

用途：代理 Agent-Zs 会话列表。

```http
GET /agent-ai-api/sessions/{session_id}/messages
```

用途：代理 Agent-Zs 历史消息。

## 6. 联调步骤

1. ERP 部署层增加 `/agent-ai/` 和 `/agent-ai-api/` 反向代理。
2. ERP 后端新增 `/api/ai/sso-token`。
3. ERP AI 助手路由加载 Agent-Zs 页面。
4. ERP 前端把当前用户 token 注入 Agent-Zs。
5. 登录 ERP 后打开 AI 助手菜单。
6. 输入“查询销售订单”。
7. 验证页面能展示 AI 回复和表格数据。
8. 刷新 ERP 页面后再次进入 AI 助手，验证会话历史正常。
9. 使用普通用户验证只能查询授权范围内的数据。
10. 使用无 `AI_CHAT` 权限用户验证看不到入口或无法访问。

## 7. 验收标准

功能验收：

- ERP 菜单能打开 AI 助手页面。
- 无需用户在 Agent-Zs 再登录一次。
- 输入问题后能看到 AI 回复。
- 查询销售订单、库存、本月销售等常用问题能返回数据。
- 刷新后历史消息仍正常显示。
- SSE 流式接口不会出现 `network error`。

权限验收：

- 普通用户只能查询自己有权限的数据。
- 超管可以查询全量数据。
- 无 AI 权限用户不能进入 AI 助手。

运维验收：

- `/health` 返回正常。
- Agent-Zs 容器日志没有 `Exception in ASGI application`。
- Nginx 日志没有大量 499、502、504。
- `/api/v1/query/stream` 在代理下不会被缓冲。

## 8. 风险和注意事项

- 不建议让 ERP 前端直接访问 `http://172.177.3.43:8001`，容易遇到跨域和 token 管理问题。
- 不建议把 ERP 数据库主账号给 AI 服务使用，生产环境应使用只读账号。
- 如果 iframe 内页面无法显示，需要检查 ERP 响应头是否禁止 iframe。
- 如果对话请求一直转圈，需要检查 Nginx 是否关闭 `proxy_buffering`。
- 如果 AI 返回的数据越权，需要优先检查 Agent-Zs JWT 中的数据权限字段。
- 如果刷新后显示正常但实时显示异常，需要检查 `/api/v1/query/stream` 和会话落库是否一致。

## 9. 建议实施顺序

第一阶段：快速接入。

- ERP AI 路由 iframe 加载 `/agent-ai/`。
- ERP 网关配置 `/agent-ai/` 代理。
- 使用 Agent-Zs 当前登录机制或临时 token 完成验证。

第二阶段：登录打通。

- ERP 新增 `/api/ai/sso-token`。
- Agent-Zs 支持 token 注入。
- 用户进入 AI 助手不再二次登录。

第三阶段：权限闭环。

- ERP 把仓库、区域、客户、商品权限写入 Agent-Zs JWT。
- 使用普通用户和超管分别验证查询范围。

第四阶段：生产加固。

- 使用只读数据库账号。
- 增加审计日志。
- 增加接口限流。
- 增加异常监控和日志告警。

