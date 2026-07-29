# 小程序 AI 模块 — 代码设计方案与接口文档

## 一、架构总览

```
微信小程序
  │
  ├─ src/config/ai.ts              ← 配置层（API 路径、超时、存储键）
  ├─ src/config/env.ts             ← 配置层（后端 Base URL）
  │
  ├─ src/utils/sse.ts              ← 基础设施层（SSE 流解析器）
  │
  ├─ src/services/ai.ts            ← 服务层（流式 / 非流式 AI 调用）
  ├─ src/services/api.ts           ← 服务层（文件上传）
  │
  └─ src/components/ai-assistant/  ← UI 层（悬浮机器人 + 对话面板）
       ├─ ai-assistant.js          组件逻辑（1011行）
       ├─ ai-assistant.wxml        模板（155行）
       ├─ ai-assistant.wxss        样式（1214行）
       ├─ ai-assistant.json        组件声明
       ├─ markdown.js              Markdown → HTML（193行）
       └─ robot-icon.png           机器人图标
```

**调用链**：

```
微信小程序 ─→ 业务后端 /api/ai/chat/workflow/stream ─→ Dify /v1/workflows/run
```

**核心安全约束**：小程序端绝不持有 Dify API Key 和 Dify 地址，敏感配置仅由后端保管。

**使用页面**：首页（`src/pages/index`）、业务中心（`src/pages/business`），通过 `<ai-assistant />` 标签引入。

---

## 二、配置层

### ai.ts — 客户端配置

| 配置项 | 值 | 说明 |
|---|---|---|
| `API_PATH` | `/api/ai/chat/workflow/stream` | 业务后端 AI 代理端点 |
| `CLIENT_TYPE` | `MINI` | 客户端类型标识 |
| `TIMEOUT` | `120000`（2分钟） | 请求超时，AI 响应较慢 |
| `STORAGE_KEY_MESSAGES` | `ai_assistant_messages` | 消息本地存储键 |
| `STORAGE_KEY_SESSIONS` | `ai_assistant_sessions` | 会话列表存储键 |
| `STORAGE_KEY_CURRENT_SESSION` | `ai_assistant_current_session_id` | 当前会话 ID 存储键 |
| `MAX_HISTORY_MESSAGES` | `50` | 单会话最大历史消息数 |

### env.ts — 环境配置

提供 `BASE_URL`，AI 服务通过 `BASE_URL + API_PATH` 拼装完整请求地址，支持内网/外网切换。

---

## 三、基础设施层 — SSE 流解析器

**文件**：[src/utils/sse.ts](src/utils/sse.ts)

### SseEvent 接口

```typescript
interface SseEvent {
  event: string;   // 事件类型，默认 "message"
  data: unknown;   // 解析后的数据（JSON 或字符串）
  raw: string;     // 原始 data 文本
}
```

### SseParser 类

| 方法 | 说明 |
|---|---|
| `push(chunk: string): SseEvent[]` | 喂入原始分片，返回本次解析出的完整事件数组 |

内部逻辑：

1. 换行符统一为 `\n`
2. 缓冲区拼接，按 `\n\n` 切分事件记录
3. 逐记录解析 `event:` / `data:` 字段
4. `data` 行尝试 JSON.parse，多行合并为数组
5. `[DONE]` 标记保留原始字符串
6. 未消费数据留在缓冲区等待下一分片

---

## 四、服务层

**文件**：[src/services/ai.ts](src/services/ai.ts)

### 4.1 核心函数：streamMessage

```typescript
function streamMessage(
  query: string,
  options: StreamMessageOptions
): WechatMiniprogram.RequestTask
```

**请求参数**：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `query` | string | 是 | 用户问题（1-500字符） |
| `options.userId` | string | 否 | 用户标识 |
| `options.conversationId` | string | 否 | 会话标识 |
| `options.onDelta` | function | 否 | 增量文本回调 |
| `options.onEvent` | function | 否 | 原始 SSE 事件回调 |
| `options.onComplete` | function | 否 | 完成回调 |
| `options.onError` | function | 否 | 错误回调 |

**HTTP 请求**：

```http
POST {baseUrl}/api/ai/chat/workflow/stream
Authorization: Bearer {token}
Content-Type: application/json
Accept: text/event-stream
X-Client-Type: MINI
```

```json
{
  "query": "用户问题",
  "user_id": "xxx",
  "conversation_id": "xxx"
}
```

**流式处理流程**：

```
wx.request (enableChunked: true)
  │
  ├─ task.onChunkReceived ─→ SseParser.push() ─→ events[]
  │                              │
  │                              ├─ text_chunk       → extractText → onDelta
  │                              ├─ node_finished     → extractText → onDelta
  │                              ├─ workflow_finished → mergeExtractedText（去重）→ onDelta
  │                              └─ 其他事件          → onEvent
  │
  ├─ success (2xx)  → onComplete({ answer })
  └─ fail / !2xx    → onError
```

**Dify 输出适配 — 文本提取优先级**：

```
data.answer
  → data.text
  → data.delta
  → data.data.answer
  → data.data.text
  → data.data.outputs.answer
  → data.outputs.answer
```

**workflow_finished 去重逻辑**：

- 若最终文本以已累积文本开头 → 用最终文本替换，delta 置空
- 若已累积文本以最终文本开头 → 保留累积文本，delta 置空
- 防止同一内容重复追加

### 4.2 封装函数：sendMessageStream

```typescript
function sendMessageStream(
  query: string,
  handlers: SendMessageStreamHandlers
): WechatMiniprogram.RequestTask
```

对 `streamMessage` 的语义化封装，回调名更友好：

| handlers 字段 | streamMessage 对应 | 说明 |
|---|---|---|
| `onChunk` | `onDelta` | 增量文本 |
| `onEvent` | `onEvent` | 原始 SSE 事件 |
| `onComplete(answer, result, response)` | `onComplete` | 完成（直接给 answer 字符串） |
| `onError` | `onError` | 错误 |

### 4.3 封装函数：sendMessage（非流式）

```typescript
function sendMessage(
  query: string,
  options?: { userId?: string; conversationId?: string }
): Promise<AiChatResponse>

interface AiChatResponse {
  answer: string;
}
```

内部调用 `sendMessageStream`，将流式结果聚合成 Promise，适用于不需要实时展示的场景。

### 4.4 调试日志

所有关键节点输出结构化日志（`[AI assistant][stream]` 前缀），包含：

- `requestId` — 唯一请求标识（`ai-{timestamp}-{random}`）
- `chunkCount` / `eventCount` — 分片/事件计数
- `difyEvent` / `workflowStatus` / `workflowError` — Dify 状态追踪
- `triedPaths` / `matchedPath` — 文本提取路径诊断
- `elapsed` — 请求耗时

### 4.5 文件上传（api.ts）

```typescript
function uploadAiAssistantFile(
  filePath: string,
  fileName: string
): Promise<{
  id: string;
  fileName: string;
  fileUrl: string;
  fileSize: number;
  fileType: string;
  mimeType: string;
}>
```

使用 `AI_ASSISTANT` 业务类型上传，返回值包含文件 ID、URL、大小、MIME 等。

---

## 五、UI 层 — ai-assistant 组件

**路径**：`src/components/ai-assistant/`

### 5.1 组件数据模型

```javascript
data: {
  messages: [],            // 消息列表 [{id, role, content, html, reasoning, ...}]
  sessions: [],            // 会话列表 [{id, title, updatedAt, messageCount, messages}]
  currentSessionId: '',    // 当前会话 ID
  sessionPanelVisible: false, // 会话面板显隐
  inputValue: '',          // 输入框内容
  loading: false,          // 等待 AI 回复
  hasStreamingContent: false, // 是否有流式内容
  uploadedFile: null,      // 已上传文件信息
  uploadingFile: false,    // 上传中
  dialogVisible: false,    // 对话框显隐
  posX: 0, posY: 300,      // 机器人按钮坐标(px)
  side: 'right',           // 贴边侧 left/right
  collapsed: true,         // 是否折叠（露出 1/4）
  btnDragging: false,      // 拖拽中
  scrollToId: '',          // 滚动目标消息 ID
  _msgId: 0,               // 消息 ID 计数器
}
```

### 5.2 消息数据结构

```typescript
interface Message {
  id: number;                    // 自增 ID
  role: 'user' | 'ai';          // 角色
  content: string;              // 原始文本（AI 消息为提取 `</think>` 后的纯答案）
  html?: string;                // Markdown → HTML（供 rich-text 渲染）
  time: string;                 // HH:mm 格式
  reasoning?: string;           // <think> 标签内推理过程原文
  reasoningHtml?: string;       // 推理过程 Markdown → HTML
  reasoningExpanded?: boolean;   // 推理面板是否展开
  _streaming?: boolean;         // 流式传输中标记
}
```

### 5.3 交互行为

| 交互 | 行为 |
|---|---|
| 点击悬浮按钮 | 展开→弹出对话框（无拖拽时触发） |
| 拖拽悬浮按钮 | 跟随手指，松手吸附最近边缘并折叠 |
| 发送消息 | 调 `sendMessageStream`，占位消息实时更新 |
| 切换会话 | 保存当前会话，加载目标会话历史 |
| 新建会话 | 上限 20 条，超出裁剪最旧 |
| 复制 AI 回复 | `wx.setClipboardData` 复制原始 Markdown |
| 展开推理 | 解析 `<think>...</think>` 在可折叠面板中展示 |
| 文件上传 | `wx.chooseMessageFile` + `uploadAiAssistantFile` |
| 清空历史 | 清除 Storage 并重建空会话 |

### 5.4 悬浮按钮拖拽算法

```
onTouchStart: 记录起始坐标，标记 hasMoved=false
onTouchMove:
  ├─ 位移 >5px → 标记拖拽，折叠态先展开到可见位置
  └─ 跟随手指，边界限制（至少 20rpx 在屏幕内）
onTouchEnd:
  ├─ hasMoved=true  → 判断中心点在哪半边，吸附折叠
  └─ hasMoved=false → 展开按钮 + 打开对话框（350ms 延迟）
```

折叠态：左侧 `-(btnSize - 22rpx)`，右侧 `screenWidth - 22rpx`，仅露出 22rpx（约 1/4）。

### 5.5 Markdown 渲染器（markdown.js）

自研轻量解析器，支持语法：

| 语法 | 输出标签 | CSS class |
|---|---|---|
| `# / ## / ###` | `<h1>` ~ `<h3>` | `ai-md-h1` ~ `ai-md-h3` |
| `**粗体**` `__粗体__` | `<strong>` | — |
| `*斜体*` `_斜体_` | `<em>` | — |
| `~~删除线~~` | `<del>` | — |
| `` `代码` `` | `<code>` | `ai-md-code` |
| ` ```代码块``` ` | `<pre><code>` | `ai-md-pre` / `ai-md-codeblock` |
| `[文字](url)` | `<a>` | `ai-md-link` |
| `- / * 列表` | `<ul><li>` | `ai-md-ul` |
| `1. 列表` | `<ol><li>` | `ai-md-ol` |
| `> 引用` | `<blockquote>` | `ai-md-quote` |
| `---` | `<hr>` | `ai-md-hr` |

安全措施：所有文本先 `escapeHtml`（转义 `& < > "`），链接仅允许 `http/https` / 相对路径。

### 5.6 思考过程提取

```javascript
function parseAssistantContent(content) → { answer, reasoning }
```

- 正则匹配 `<think>...</think>` 标签
- reasoning 存入可折叠面板，默认折叠
- answer 为去掉标签后的纯响应文本
- 支持不完整的 `<think>`（无闭合标签时截断到末尾）

### 5.7 本地存储

```javascript
// 三层存储结构
wx.setStorageSync('ai_assistant_sessions', sessions)          // 会话列表
wx.setStorageSync('ai_assistant_current_session_id', id)      // 当前会话
wx.setStorageSync('ai_assistant_messages', messages)          // 当前消息（兼容旧版）
```

会话上限 20 条，单会话消息上限 50 条。`loadHistory()` 加载时自动迁移旧版格式。

---

## 六、业务后端接口规范

### 6.1 AI 对话接口

```http
POST /api/ai/chat/workflow/stream
Authorization: Bearer <登录Token>
Content-Type: application/json
Accept: text/event-stream
X-Client-Type: MINI
```

**请求体**：

```json
{
  "query": "如何创建销售订单？",
  "user_id": "xxx",
  "conversation_id": "xxx"
}
```

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `query` | string | 是 | 1-500 字符 | 用户问题 |
| `user_id` | string | 否 | — | 用户标识（后端可选使用） |
| `conversation_id` | string | 否 | — | 会话标识（后端可选使用） |

**SSE 事件类型**：

| 事件 | 说明 | data 包含 |
|---|---|---|
| `text_chunk` | Dify 文本增量 | `{ data: { text: "..." } }` |
| `node_finished` | 工作流节点完成 | `{ data: { node_id, node_type, title, outputs } }` |
| `workflow_finished` | 工作流结束 | `{ data: { status, outputs: { answer: "..." } } }` |
| `error` | 工作流异常 | `{ data: { status: "failed", error: "..." } }` |

**响应完成**：HTTP 200 + 最后一条 `workflow_finished` 事件。

**错误响应**：

| HTTP 状态 | code | message | 场景 |
|---|---|---|---|
| 400 | 400 | 问题内容不能为空 | query 缺失或格式错误 |
| 401 | 401 | 登录已过期 | Token 无效 |
| 403 | 403 | 当前用户无权使用 AI 助手 | 权限不足 |
| 503 | 503 | AI 服务未启用 | 租户未配置或已停用 |
| 503 | 503 | AI 服务配置错误 | 地址、密钥或输出字段错误 |
| 504 | 504 | AI 响应超时 | Dify 调用超时（120s） |
| 500 | 500 | AI 服务处理失败 | 未分类异常 |

### 6.2 文件上传接口

```http
POST /api/file/upload
Content-Type: multipart/form-data
```

| 参数 | 说明 |
|---|---|
| `file` | 文件 |
| `bizType` | `AI_ASSISTANT` |

返回：`{ id, fileName, fileUrl, fileSize, fileType, mimeType }`

### 6.3 后端 Dify 调用方式

```http
POST {difyBaseUrl}/workflows/run
Authorization: Bearer {difyApiKey}
Content-Type: application/json
```

```json
{
  "inputs": { "query": "用户问题" },
  "response_mode": "blocking",
  "user": "wms_tenant_{tenantId}_user_{userId}"
}
```

后端从登录 Token 读取 `tenantId` / `userId`，生成稳定 Dify user 标识。小程序端不传入也不感知这些字段。

### 6.4 后端 AI 配置项

| 字段 | 示例 | 说明 |
|---|---|---|
| `enabled` | true | 是否启用 |
| `provider` | DIFY | AI 服务提供方 |
| `baseUrl` | http://127.0.0.1:8089/v1 | Dify API 基础地址 |
| `apiKey` | app-*** | Dify API Key（加密存储） |
| `appType` | WORKFLOW | 应用类型 |
| `endpoint` | /workflows/run | Dify 调用路径 |
| `inputKey` | query | 工作流输入变量名 |
| `outputKey` | answer | 工作流输出字段名 |
| `timeoutMs` | 120000 | 请求超时 10s-180s |
| `userPrefix` | wms_ | Dify user 前缀 |

---

## 七、安全设计

| 规则 | 说明 |
|---|---|
| 前端不持有 API Key | Dify 密钥仅后端保存，环境变量或密文存储 |
| 前端不持有 Dify URL | 小程序只调业务后端 |
| 身份由后端判定 | 从 JWT 读取 tenantId/userId，不接受客户端传入 |
| 日志脱敏 | 不记录完整 API Key、用户问题全文 |
| 登录校验 | AI 接口强制要求 Authorization 头 |
| 输入校验 | 后端校验 query 长度 1-500 |
| 租户隔离 | 不同租户独立配置、独立 Dify user |
| 链接过滤 | markdown.js 仅允许 http/https 协议链接 |

---

## 八、文件清单

| 文件 | 行数 | 职责 |
|---|---|---|
| `src/config/ai.ts` | 23 | 客户端配置常量 |
| `src/config/env.ts` | 33 | 环境 URL 配置 |
| `src/utils/sse.ts` | 61 | SSE 流增量解析器 |
| `src/utils/sse.test.js` | 75 | SSE 解析器单元测试 |
| `src/services/ai.ts` | 353 | 核心 AI 服务（流式/非流式） |
| `src/services/ai.test.js` | 199 | AI 服务单元测试 |
| `src/services/api.ts` | — | 文件上传（AI_ASSISTANT 业务类型） |
| `src/components/ai-assistant/ai-assistant.js` | 1011 | 组件主逻辑 |
| `src/components/ai-assistant/ai-assistant.wxml` | 155 | 组件模板 |
| `src/components/ai-assistant/ai-assistant.wxss` | 1214 | 组件样式 |
| `src/components/ai-assistant/ai-assistant.json` | 4 | 组件声明 |
| `src/components/ai-assistant/markdown.js` | 193 | Markdown → HTML 解析器 |
| `src/components/ai-assistant/ai-assistant.test.js` | 238 | 组件单元测试 |
| `src/components/ai-assistant/robot-icon.png` | — | 机器人图标 |
| `docs/AI后端接口对接文档.md` | 284 | 后端对接规范 |

---

## 九、测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `sse.test.js` | SSE 分片解析、多行 data、跨 chunk 拼接 |
| `ai.test.js` | `sendMessageStream` 增量回调、`sendMessage` Promise、`workflow_finished` 去重、事件诊断日志 |
| `ai-assistant.test.js` | 流式消息更新、`<think>` 提取、旧版历史迁移、会话创建/切换、文件上传状态 |
