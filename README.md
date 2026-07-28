# Agent-Zs — ERP 自然语言操作层

让业务人员用自然语言查询 ERP 数据、生成报表。

## 快速开始

### 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 创建 .env 文件
cp .env.example .env
# 编辑 .env 填入 LLM API Key

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker 部署

```bash
# 创建 .env 文件
cp .env.example .env
# 编辑 .env 填入配置

# 启动服务
docker compose up -d
```

## API 端点

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/health` | GET | 健康检查 | 否 |
| `/api/v1/query` | POST | 自然语言查询 | Bearer Token |
| `/api/v1/query/stream` | GET | SSE 流式查询 | Bearer Token |
| `/api/v1/report` | POST | 报表生成 | Bearer Token |
| `/api/v1/admin` | GET | 管理页面 | 否 |
| `/api/v1/admin/config` | GET/POST | 配置读写 | 否 |

### 查询示例

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{"question": "统计每个仓库的库存总数量"}'
```

## 测试

```bash
pytest tests/ -v
```

## 项目结构

```
app/
├── main.py           # FastAPI 入口
├── config.py         # 配置管理
├── routers/          # API 端点
│   ├── health.py     # 健康检查
│   ├── query.py      # 查询端点
│   ├── report.py     # 报表端点
│   └── admin.py      # 管理页面
├── tools/            # 工具层
│   ├── query_tool.py    # SQL 沙箱
│   ├── report_tool.py   # 报表生成
│   └── schema_tool.py   # Schema 获取
├── agent/            # 编排层
│   ├── orchestrator.py  # 查询/报表编排
│   ├── llm_client.py    # LLM 客户端
│   └── prompts.py       # Prompt 模板
├── db/               # 数据库层
│   ├── session.py       # 连接池管理
│   └── schema.py        # Schema 导出
├── gateway/          # 网关层
│   ├── auth.py          # Token 认证
│   └── rate_limit.py    # 速率限制
└── models/           # 数据模型
    └── schemas.py       # Pydantic 模型
```

## 文档

- [设计文档](docs/design.md)
- [环境配置](ENVIRONMENT.md)
