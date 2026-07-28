# 企业级 Agent 落地设计方案

## 1. 项目定位

本项目不是简单的 LLM 查询机器人，而是面向 ERP
企业系统的自然语言智能操作层。

目标：

-   使用自然语言替代复杂 ERP 操作流程
-   实现数据查询、分析、报表生成、业务操作、知识检索
-   建立安全、可审计、可扩展的企业级 Agent 平台

------------------------------------------------------------------------

# 2. 企业级 Agent 总体架构

    用户层
     PC端 / 微信小程序 / Web

            |
            v

    API Gateway

            |
            v

    Agent Orchestrator

            |
            v

    Agent Runtime

    ---------------------------------

    Data Agent
    Write Agent
    Knowledge Agent
    Report Agent

    ---------------------------------

    Tools Layer

    Database Tool
    ERP API Tool
    Search Tool
    File Tool
    Approval Tool

    ---------------------------------

    Enterprise Data Layer

    数据库
    业务系统
    知识库
    文档系统


    ---------------------------------

    基础设施

    Memory
    Task State
    Audit
    Evaluation
    Vector Database

------------------------------------------------------------------------

# 3. 核心设计原则

## 3.1 Agent不是工具集合

工具负责执行：

-   查询数据库
-   创建单据
-   检索知识
-   生成文件

Agent负责：

-   理解目标
-   制定计划
-   调度工具
-   验证结果

------------------------------------------------------------------------

# 4. 核心组件设计

## 4.1 API Gateway

职责：

-   用户认证
-   权限校验
-   请求路由
-   限流
-   Token管理
-   用户上下文注入

输入：

用户请求

输出：

带权限上下文的 Agent 请求

------------------------------------------------------------------------

## 4.2 Agent Orchestrator

系统大脑。

职责：

-   判断任务类型
-   选择 Agent
-   创建任务
-   管理执行流程

示例：

用户：

查询销售趋势

流程：

Orchestrator

↓

Data Agent

用户：

创建采购订单

流程：

Orchestrator

↓

Write Agent

------------------------------------------------------------------------

# 5. Agent Runtime设计

Runtime负责Agent生命周期。

包含：

## Task管理

任务状态：

    CREATED

    PLANNING

    EXECUTING

    VERIFYING

    COMPLETED

    FAILED

## Tool执行管理

记录：

-   工具名称
-   参数
-   返回结果
-   执行时间

## 错误恢复

支持：

-   重试
-   回滚
-   人工介入

------------------------------------------------------------------------

# 6. Memory设计

企业Agent需要三层记忆。

## 6.1 Session Memory

短期上下文。

存储：

-   当前聊天
-   当前任务

技术：

Redis

------------------------------------------------------------------------

## 6.2 Task Memory

任务执行历史。

保存：

-   SQL
-   Tool调用
-   中间结果
-   错误信息

------------------------------------------------------------------------

## 6.3 User Memory

长期用户习惯。

例如：

销售经理：

默认查看：

-   本季度
-   华东区域
-   销售排行

------------------------------------------------------------------------

# 7. Agent设计

## 7.1 Data Agent

职责：

企业数据分析。

工具：

-   Database Tool
-   SQL Tool
-   Chart Tool

能力：

自然语言查询数据库。

------------------------------------------------------------------------

## 7.2 Write Agent

负责业务写操作。

工具：

-   ERP API Tool
-   Approval Tool
-   Audit Tool

特点：

必须：

-   独立权限
-   独立数据库账号
-   完整审计

------------------------------------------------------------------------

## 7.3 Knowledge Agent

负责企业知识。

内容：

-   ERP操作手册
-   制度文件
-   产品资料
-   业务规则

架构：

    Query

    ↓

    Embedding

    ↓

    Vector DB

    ↓

    Reranker

    ↓

    LLM

------------------------------------------------------------------------

# 8. Tool层设计

工具不属于Agent。

统一Tool Runtime。

基础工具：

## Database Tool

查询业务数据。

## ERP API Tool

调用ERP业务接口。

## Search Tool

企业搜索。

## File Tool

生成文件。

## Approval Tool

人工审批。

------------------------------------------------------------------------

# 9. 数据架构

Agent数据库：

    agent_db

    ├── task

    ├── conversation

    ├── memory

    ├── tool_call_log

    ├── audit

    ├── evaluation

    └── permission

------------------------------------------------------------------------

# 10. 审计体系

所有Agent行为必须记录。

记录：

-   用户
-   时间
-   Agent
-   Tool
-   参数
-   返回结果
-   最终状态

满足企业合规要求。

------------------------------------------------------------------------

# 11. 企业部署架构

Docker Compose:

    gateway

    agent-runtime

    orchestrator

    data-agent

    write-agent

    knowledge-agent

    postgres

    redis

    vector-db

部署：

Linux服务器

------------------------------------------------------------------------

# 12. 推荐技术栈

## 后端

Python

FastAPI

Pydantic

SQLAlchemy

## Agent

OpenAI Agents SDK

Anthropic Tool Use

或者自研Runtime

## 数据

PostgreSQL

Redis

Milvus/Qdrant

## 部署

Docker

Docker Compose

------------------------------------------------------------------------

# 13. 实施路线

## Phase 1

目标：

自然语言查询。

实现：

-   Gateway
-   Runtime
-   Data Agent
-   Memory
-   Audit

------------------------------------------------------------------------

## Phase 2

目标：

业务操作。

增加：

-   Write Agent
-   ERP API
-   审批流程

------------------------------------------------------------------------

## Phase 3

目标：

企业知识智能化。

增加：

-   Knowledge Agent
-   RAG
-   企业知识库

------------------------------------------------------------------------

## Phase 4

目标：

Agent平台化。

增加：

-   Agent管理中心
-   Agent评估系统
-   Prompt优化
-   Workflow编排

------------------------------------------------------------------------

# 14. 最终目标

形成：

企业级 Agent Operating System

核心能力：

-   智能规划
-   工具调用
-   任务执行
-   长短期记忆
-   权限控制
-   审计追踪
-   企业数据连接

从：

LLM + Tool

升级为：

Agent Runtime + Orchestrator + Memory + Enterprise Tools
