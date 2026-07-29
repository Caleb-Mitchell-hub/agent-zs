# Agent-Zs — 企业级 ERP 自然语言智能操作层

## 项目简介

让业务人员用自然语言替代复杂 ERP 操作。支持查询数据、创建单据、知识检索、报表生成。

## 功能列表

| 功能 | 说明 | 示例 |
|------|------|------|
| 自然语言查询 | NL→SQL，查询业务数据 | "查询所有仓库的库存" |
| 创建单据 | 支持采购订单、销售订单、报销单等 | "创建采购订单，供应商华为，仓库北京中心仓" |
| 知识检索 | 从企业知识库语义搜索 | "采购订单审批流程是什么" |
| 报表生成 | 数据可视化 | "统计本月销售额" |

## 支持的单据类型

| 单据 | 必填字段 |
|------|----------|
| 采购订单 | 供应商名称、仓库名称、订单日期 |
| 销售订单 | 客户名称、仓库名称、订单日期 |
| 报销单 | 报销类型、金额、费用日期 |
| 入库单 | 仓库名称、入库类型 |
| 出库单 | 仓库名称、出库类型 |

## 快速开始

### 1. 访问前端页面

```
http://172.177.3.43:8001/
```

直接在对话框输入问题即可使用。

### 2. API 调用

```bash
# 查询
curl -X POST http://172.177.3.43:8001/api/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer any-token" \
  -d '{"question": "查询所有仓库的库存"}'

# 创建单据
curl -X POST http://172.177.3.43:8001/api/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer any-token" \
  -d '{"question": "创建采购订单，供应商华为，仓库北京中心仓，金额50000"}'

# 知识检索
curl -X POST http://172.177.3.43:8001/api/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer any-token" \
  -d '{"question": "采购订单审批流程是什么"}'
```

### 3. 前端接入

在你的 ERP 前端代码中添加：

```javascript
async function askAgent(question) {
  const response = await fetch('http://172.177.3.43:8001/api/v1/query', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + erpToken  // ERP 的 token
    },
    body: JSON.stringify({ question: question })
  });
  return await response.json();
}

// 使用
const result = await askAgent('查询库存');
console.log(result.data);
```

## API 端点

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/` | GET | 前端对话页面 | 否 |
| `/health` | GET | 健康检查 | 否 |
| `/api/v1/query` | POST | 自然语言查询/创建单据 | Bearer Token |
| `/api/v1/admin` | GET | 管理页面 | 否 |
| `/api/v1/admin/agents` | GET | Agent 列表 | 否 |
| `/api/v1/workflow/list` | GET | 工作流列表 | 否 |

## 项目结构

```
app/
├── main.py              # 入口
├── config.py            # 配置
├── adapter/             # ERP 适配层
├── agents/              # Agent 层
│   ├── data_agent.py    # 数据查询
│   ├── write_agent.py   # 单据创建
│   ├── knowledge_agent.py # 知识检索
│   └── report_agent.py  # 报表生成
├── gateway/             # 网关层
├── memory/              # 记忆层
├── orchestrator/        # 编排器
├── runtime/             # 运行时
├── security/            # 安全模块
├── tools/               # 工具层
└── routers/             # 路由层
```

## 部署信息

| 服务 | 地址 |
|------|------|
| Agent-Zs | http://172.177.3.43:8001 |
| Redis | 172.177.3.43:6381 |
| Qdrant | 172.177.3.43:6333 |
| MySQL | 172.177.3.43:3309 |

## 技术栈

- 后端：Python FastAPI
- 数据库：MySQL 8.0
- 缓存：Redis 7
- 向量数据库：Qdrant
- LLM：DeepSeek

## 相关文档

- [设计方案](docs/企业级Agent系统设计方案from claude code.md)
- [环境配置](ENVIRONMENT.md)
