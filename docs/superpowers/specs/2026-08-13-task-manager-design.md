# 任务管理器 设计文档

- 日期：2026-08-13
- 分支：feature/task-manager
- 状态：待审阅

## 1. 背景与目标

Agent-Zs 现有聊天界面只支持「会话」维度，缺少一个面向用户的**任务管理**入口。用户需要在日常工作中创建、跟踪、规划任务，并能回看自己的工作记录。

本设计在**最小侵入**前提下（复用现有 SSE + LangGraph + 单文件前端），为 Agent-Zs 增加任务管理器能力，让用户在同一界面内完成「会话」与「任务」两类工作。

## 2. 范围

### 2.1 功能需求（5 项）

| # | 需求 | 说明 |
|---|------|------|
| F1 | 左侧面板增加任务管理器 | 左侧面板变为上下包含结构：会话列表 + 任务列表 |
| F2 | 任务列表 4 个过滤 | 全部 / 已完成 / 待办 / 处理中 |
| F3 | 定时任务 | 针对**待办**和**处理中**任务支持创建定时任务 |
| F4 | 大任务自动切分 | 用户输入「今日任务 / 本月任务 / 本年任务」时，根据任务规划细节，大任务进一步切分（1 天任务自动规划到下班，本月任务根据工作日/节假日/请假调整） |
| F5 | 工作记录展示 | 展示某年 / 月 / 周 / 日的工作记录（日历视图） |

### 2.2 不做什么

- 不做多租户协作 / 团队共享任务（本期限单人视角，行级 `user_id` 隔离）
- 不做任务审批流（复用现有审批机制，不在本范围内）
- 不做移动端 / 小程序端任务管理
- 不做跨系统的外部任务同步（飞书 / 企业微信等，后续再说）

## 3. UI 设计（已定稿）

设计稿：[task-manager-mockup.html](../../ui-mockup/task-manager-mockup.html)（浏览器打开预览）。

### 3.1 左侧面板（上下包含结构）

```
┌─────────────────────┐
│ 会话区（可折叠）       │  ← 按时间分组（今天 / 昨天 / 更早）
│   搜索框             │
│   会话列表            │
├─────────────────────┤
│ 任务区（可折叠）       │  ← 4 个 tab + 按截止时间分组
│   [全部][已完成][待办][处理中] │
│   搜索框             │
│   任务列表            │
└─────────────────────┘
```

三层折叠结构应对「数量多」的归类管理：
1. **区块级折叠**：会话区 / 任务区各自可整体折叠
2. **分组级折叠**：会话按时间分组、任务按截止时间分组，分组可折叠
3. **搜索过滤**：两区各有一个搜索框，输入即过滤

### 3.2 状态色语义

| 状态 | 颜色 | 变量 |
|------|------|------|
| 待办 | 蓝 | `--primary: #1890ff` |
| 处理中 | 橙 | `--warning: #fa8c16` |
| 已完成 | 绿 | `--success: #52c41a` |
| 逾期 | 红 | `--danger: #ff4d4f` |

> 「逾期」不是独立状态，而是派生标记：`deadline < now 且 status != done` 时，视觉上用红色高亮（不落库为独立枚举值）。

### 3.3 工作记录：日历视图（F5）

- **月视图（默认）**：标准月历，每天一格；格内左上角日期号（今天蓝底圆标），下方 `✓完成数`（绿）+ `+创建数`（蓝）；格子背景绿色深浅 = 当天完成数（活跃度 5 级色阶）。
- **顶部导航**：`‹ 2026年8月 ›` 月份翻页 + 「月视图 / 年视图」切换。
- **年视图**：12 个月迷你月历缩略图，全年活跃度总览，悬浮看具体数字。
- **点击某天** → 下方「当日明细」面板列出该天的完成 / 创建记录。
- **顶部 4 张数字卡片**：本月完成 / 本月创建 / 活跃天数 / 完成率，随翻页联动重算。

> 日历视图本身承载「年/月/周/日」时间粒度：月视图看单月、翻页看不同月、年视图看全年、点某天看当日明细。「某周」暂并入月视图（日历里的一行），不单独做周视图标签页。

## 4. 数据模型（4 张新表）

> 现有 `tasks` / `task_steps` 是「Agent 执行任务」的 DAG 快照表，与「用户任务管理器」语义不同，故新建独立表，行级 `user_id` 隔离。

### 4.1 `user_tasks` — 用户任务主表

| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | BIGINT UNSIGNED PK AUTO | 任务 ID |
| user_id | BIGINT UNSIGNED | 用户 ID（隔离） |
| title | VARCHAR(200) | 任务标题 |
| status | VARCHAR(20) | `pending`(待办) / `doing`(处理中) / `done`(已完成) |
| priority | TINYINT | 优先级（默认 0） |
| deadline | DATETIME NULL | 截止时间 |
| parent_id | BIGINT NULL | 父任务 ID（大任务切分后的子任务指向父） |
| plan_detail | JSON NULL | 规划细节（切分结果 / 时间安排） |
| created_at | DATETIME | 创建时间 |
| completed_at | DATETIME NULL | 完成时间 |

索引：`idx_user (user_id)`、`idx_status (status)`、`idx_deadline (deadline)`、`idx_parent (parent_id)`。

> 日历视图的「创建数」由 `created_at` 聚合、「完成数」由 `completed_at` 聚合，无需额外日志表。

### 4.2 `task_schedules` — 定时任务表

| 字段 | 类型 | 说明 |
|------|------|------|
| schedule_id | BIGINT UNSIGNED PK AUTO | 定时任务 ID |
| task_id | BIGINT UNSIGNED | 关联任务 |
| user_id | BIGINT UNSIGNED | 用户 ID |
| trigger_time | DATETIME | 触发时间 |
| action | VARCHAR(20) | `remind`(仅提醒) / `remind_advance`(提醒+自动推进) |
| advance_to | VARCHAR(20) NULL | 自动推进到 `doing` / `done`（仅 remind_advance 时） |
| fired | TINYINT | 是否已触发 |
| created_at | DATETIME | 创建时间 |

索引：`idx_task (task_id)`、`idx_user (user_id)`、`idx_trigger (trigger_time)`。

### 4.3 `holidays` — 公共节假日表（内置只读预置）

| 字段 | 类型 | 说明 |
|------|------|------|
| holiday_id | BIGINT UNSIGNED PK AUTO | ID |
| day | DATE | 日期 |
| type | VARCHAR(20) | `holiday`(法定节假日) / `workday`(调休上班日) |
| note | VARCHAR(100) NULL | 备注 |

索引：`idx_day (day)`。

> 内置中国大陆法定节假日 + 调休上班日，系统预置，用户不可增删改。

### 4.4 `leaves` — 个人请假表（用户级，可增删改）

| 字段 | 类型 | 说明 |
|------|------|------|
| leave_id | BIGINT UNSIGNED PK AUTO | ID |
| user_id | BIGINT UNSIGNED | 用户 ID |
| day | DATE | 请假日期 |
| note | VARCHAR(100) NULL | 备注 |
| created_at | DATETIME | 创建时间 |

索引：`idx_user_day (user_id, day)`。

## 5. API 设计

统一前缀 `/api/v1/tasks`，Bearer JWT 认证，`user_id` 从 token 提取（行级隔离）。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/tasks` | GET | 任务列表（`?filter=all/done/pending/doing&q=关键词`） |
| `/api/v1/tasks` | POST | 创建任务 |
| `/api/v1/tasks/{id}` | PATCH | 更新任务（标题/状态/截止/优先级） |
| `/api/v1/tasks/{id}` | DELETE | 删除任务 |
| `/api/v1/tasks/{id}/schedule` | POST | 创建定时任务（trigger_time + action） |
| `/api/v1/tasks/{id}/schedule` | DELETE | 取消定时任务 |
| `/api/v1/tasks/worklog` | GET | 工作记录（`?year=&month=`，从 user_tasks 聚合，供日历视图） |
| `/api/v1/tasks/plan` | POST | 触发大任务切分（复用 query 流程，走 LangGraph） |

> 定时任务的「提醒 + 自动推进」由 APScheduler 触发后，直接更新 `user_tasks`（含 `completed_at`），并通过 SSE 向在线前端推送提示（角标 + 聊天区提示）。

## 6. 定时任务（APScheduler）

- 依赖新增 `APScheduler`（AsyncIOScheduler），随 FastAPI 应用启动/关闭。
- 定时任务在应用启动时从 `task_schedules` 加载未触发的记录注册到 scheduler；新创建/取消时实时增删 job。
- 触发动作：`remind` 仅推送提醒；`remind_advance` 推送提醒 + 将任务状态推进到 `advance_to`（推进到 `done` 时写 `completed_at`）。
- 推送通道：复用现有 SSE，`/api/v1/tasks/events` 流，前端监听后更新角标 + 聊天区提示。

## 7. 大任务切分（F4）

触发词：用户输入「今日任务 / 本月任务 / 本年任务」时，路由到 LangGraph 新增的 `task_plan` 节点。

> 意图区分：「今日任务 / 本月任务 / 本年任务」作为**规划指令**触发切分；若用户只想**查看**某天/月/年的已有任务，走任务列表过滤（F2）或日历视图（F5），不触发切分。

确定性优先原则（LLM 只做意图判定，切分逻辑用代码）：

1. **意图判定**（LLM）：识别「今日 / 本月 / 本年」粒度。
2. **切分逻辑**（代码，确定性）：
   - **今日任务**：把大任务切到当天，1 天任务自动规划到**下班时间**（默认 18:00，可配置）。
   - **本月任务**：按**工作日**切分到天，跳过节假日，遇「请假」跳过并顺延。
   - **本年任务**：先切到月（里程碑），每月再按工作日展开到天。
3. **预览确认**：切分结果以「预览」形式返回（不落库），用户确认后才写入 `user_tasks`（子任务挂 `parent_id`）与 `plan_detail`。

## 8. 时间数据源（节假日 + 请假）

- **内置节假日表**：`holidays` 表预置中国大陆法定节假日 + 调休上班日（`type=holiday/workday`，全局只读）。
- **手动请假**：用户通过任务区入口添加请假记录（`leaves` 表，user_id 级）。
- 切分算法在计算「工作日」时同时排除公共节假日、调休、个人请假。

## 9. 实现顺序

| 步骤 | 内容 | 验证 |
|------|------|------|
| 1 | 4 张表建表 SQL | 建表成功 |
| 2 | 任务 CRUD REST API | curl 增删改查 |
| 3 | APScheduler 定时任务 + SSE 推送 | 定时触发提醒 |
| 4 | LangGraph `task_plan` 节点（切分） | 「今日/本月/本年任务」返回预览 |
| 5 | 前端左侧面板 + 任务列表 + 日历视图 | 浏览器全流程 |

## 10. 关键决策记录

| 决策点 | 结论 |
|--------|------|
| 集成方案 | 方案 A：最小侵入，复用 SSE + LangGraph + 单文件前端 |
| 定时任务形态 | 提醒 + 可选自动推进 |
| 时间数据源 | 内置节假日表（holidays）+ 个人请假表（leaves） |
| 工作记录图示 | 日历视图（月视图 + 年视图，点某天看明细） |
| 规划落库 | 预览确认后落库 |
| 提醒形式 | 角标 + 聊天区提示 |
| 状态色 | 待办蓝 / 处理中橙 / 已完成绿 / 逾期红（派生态） |
