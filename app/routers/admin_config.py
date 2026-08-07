"""配置管理与后台运营中心（设计文档 §5.12）

端点前缀：/api/v1/admin/config
6 个 Tab：模型与路由 / 知识库 / 工具与风险 / 数据源 / 限流与配额 / 保留期
+ 审计日志查看

统一机制：
- get_admin_context：解析 Authorization，返回操作人上下文（写审计）
- 统一响应包装 {status, data} / {status, message, error_code}
- 写操作：审计 → 缓存失效
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.config_center.service import config_service
from app.gateway.auth import require_admin
from app.security.data_masking import data_masking
from app.security.crypto import config_crypto

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────── 请求模型 ───────────────────────────

class LLMConfigBody(BaseModel):
    provider: str = "deepseek"
    base_url: str = ""
    api_key: str = ""
    model: str = "deepseek-chat"
    max_tokens: int = 4096
    temperature: float = 0.1


class ModelRouteBody(BaseModel):
    primary_model: str = "deepseek-chat"
    fallback_models: list[str] = []
    sensitivity_level: str = "normal"
    enabled: bool = True
    priority: int = 100


class ToolPolicyBody(BaseModel):
    enabled: bool = True
    risk_level: str = "medium"
    need_confirm: bool = False
    timeout: int = 30
    retry_count: int = 3


class DatasourceBody(BaseModel):
    name: str
    type: str = "mysql_replica"
    host: str
    port: int = 3306
    db_name: str = ""
    username: str = ""
    password: str = ""
    connect_timeout: int = 10


class RateLimitBody(BaseModel):
    qps: int = 10
    concurrency: int = 5
    token_quota_monthly: int = 0
    enabled: bool = True


class RetentionBody(BaseModel):
    task_days: int = 90
    session_days: int = 180
    memory_days: int = 365
    audit_days: int = 365


class ConfirmBody(BaseModel):
    change_request_id: int


# ─────────────────────────── 依赖 ───────────────────────────

async def get_admin_context(user_info: dict = Depends(require_admin)) -> dict:
    """解析操作人上下文（写审计用，要求管理员权限）"""
    return {
        "user_id": user_info.get("user_id"),
        "tenant_id": user_info.get("tenant_id", 1),
        "roles": user_info.get("roles", []),
    }


# ─────────────────────────── 页面 ───────────────────────────

@router.get("/admin/config", response_class=HTMLResponse)
async def config_page():
    """配置中心页面（内嵌 HTML 单页）"""
    return _render_config_page()


# ─────────────────────────── 审计日志 ───────────────────────────

@router.get("/admin/config/audit-logs")
async def get_audit_logs_endpoint(action: str = "", limit: int = 100, user_info: dict = Depends(require_admin)):
    """查看审计日志"""
    from app.security.audit import audit_logger
    logs = await audit_logger.get_audit_logs(action=action or None, limit=limit)
    return {"status": "ok", "data": logs}


# ─────────────────────────── Tab1 模型与路由 ───────────────────────────

@router.post("/admin/config/llm/test")
async def test_llm_connection(body: LLMConfigBody, ctx: dict = Depends(get_admin_context)):
    """测试 LLM 连通性（不落库）"""
    try:
        import httpx
        headers = {"Authorization": f"Bearer {body.api_key}", "Content-Type": "application/json"}
        data = {
            "model": body.model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{body.base_url}/v1/chat/completions", headers=headers, json=data)
            if resp.status_code == 200:
                return {"status": "ok", "message": "LLM 连接成功"}
            return {"status": "error", "message": f"LLM 连接失败: HTTP {resp.status_code} - {resp.text[:200]}"}
    except Exception as e:
        return {"status": "error", "message": f"LLM 连接失败: {str(e)}"}


@router.get("/admin/config/llm")
async def get_llm_config(user_info: dict = Depends(require_admin)):
    """读取 LLM 连接配置（api_key 脱敏）"""
    config = await config_service.get_llm_config_masked()
    return {"status": "ok", "data": config}


@router.put("/admin/config/llm")
async def save_llm_config(body: LLMConfigBody, ctx: dict = Depends(get_admin_context)):
    """保存 LLM 连接（api_key 加密）"""
    before = await config_service.get_llm_config_masked()
    await config_service.save_llm_config(body.model_dump(), updated_by=str(ctx.get("user_id", "system_admin")))
    after = await config_service.get_llm_config_masked()
    await config_service.audit("config.llm.update", ctx, before, after, risk_level="medium")
    return {"status": "ok", "message": "LLM 配置已保存"}


@router.get("/admin/config/model-routes")
async def list_model_routes(user_info: dict = Depends(require_admin)):
    """列出模型路由"""
    routes = await config_service.list_model_routes()
    return {"status": "ok", "data": routes}


@router.get("/admin/config/model-routes/task-types")
async def get_task_types(user_info: dict = Depends(require_admin)):
    """已知任务类型（下拉源）"""
    return {"status": "ok", "data": config_service.known_task_types()}


@router.put("/admin/config/model-routes/{task_type}")
async def save_model_route(task_type: str, body: ModelRouteBody, ctx: dict = Depends(get_admin_context)):
    """upsert 模型路由"""
    before = await config_service.list_model_routes()
    await config_service.save_model_route(task_type, body.model_dump(), updated_by=str(ctx.get("user_id", "system_admin")))
    after = await config_service.list_model_routes()
    await config_service.audit("config.model_route.update", ctx,
                               {"before": before}, {"after": after}, risk_level="medium")
    return {"status": "ok", "message": f"路由 {task_type} 已保存"}


@router.delete("/admin/config/model-routes/{task_type}")
async def delete_model_route(task_type: str, ctx: dict = Depends(get_admin_context)):
    """删除模型路由"""
    before = await config_service.list_model_routes()
    await config_service.delete_model_route(task_type)
    after = await config_service.list_model_routes()
    await config_service.audit("config.model_route.delete", ctx,
                               {"before": before}, {"after": after}, risk_level="medium")
    return {"status": "ok", "message": f"路由 {task_type} 已删除"}


# ─────────────────────────── Tab2 知识库管理 ───────────────────────────

class KnowledgeBody(BaseModel):
    title: str
    content: str = ""
    category: str = "manual"
    tags: str = ""
    permission_scope: str = "all"


@router.get("/admin/config/knowledge")
async def list_knowledge(keyword: str = "", category: str = "", user_info: dict = Depends(require_admin)):
    """列出知识库"""
    items = await config_service.list_knowledge(keyword=keyword, category=category)
    return {"status": "ok", "data": items}


@router.post("/admin/config/knowledge")
async def add_knowledge(body: KnowledgeBody, ctx: dict = Depends(get_admin_context)):
    """新增知识条目"""
    from app.tools.rag_tool import add_knowledge
    result = await add_knowledge(title=body.title, content=body.content, category=body.category, tags=body.tags)
    await config_service.audit("config.knowledge.create", ctx, {}, body.model_dump(), risk_level="low")
    return result


@router.delete("/admin/config/knowledge/{knowledge_id}")
async def delete_knowledge(knowledge_id: int, ctx: dict = Depends(get_admin_context)):
    """删除知识条目"""
    from sqlalchemy import text
    from app.db.session import get_session
    async for session in get_session():
        await session.execute(
            text("DELETE FROM knowledge_base WHERE id = :id"), {"id": knowledge_id}
        )
        await session.commit()
    await config_service.audit("config.knowledge.delete", ctx, {"id": knowledge_id}, {}, risk_level="low")
    return {"status": "ok", "message": f"知识条目 #{knowledge_id} 已删除"}


# ─────────────────────────── Tab3 工具与风险策略 ───────────────────────────

@router.get("/admin/config/tools")
async def list_tools(user_info: dict = Depends(require_admin)):
    """列出工具完整策略"""
    result = await config_service.list_tool_policies()
    return {"status": "ok", "data": result.get("tools", [])}


@router.put("/admin/config/tools/{tool_name}")
async def update_tool_policy(tool_name: str, body: ToolPolicyBody, ctx: dict = Depends(get_admin_context)):
    """更新工具策略（降级走二次确认）"""
    before = await config_service._get_tool_policy_rows()
    old = before.get(tool_name, {})
    result = await config_service.save_tool_policy(tool_name, body.model_dump(), updated_by=str(ctx.get("user_id", "system_admin")))
    if result.get("status") == "ok":
        await config_service.audit("config.tool_policy.update", ctx,
                                   {"before": old}, {"after": body.model_dump()}, risk_level="high")
    return result


@router.post("/admin/config/tools/{tool_name}/reset")
async def reset_tool_policy(tool_name: str, ctx: dict = Depends(get_admin_context)):
    """恢复工具策略默认值"""
    before = await config_service._get_tool_policy_rows()
    await config_service.reset_tool_policy(tool_name)
    await config_service.audit("config.tool_policy.reset", ctx,
                               {"before": before.get(tool_name, {})}, {}, risk_level="medium")
    return {"status": "ok", "message": f"工具 {tool_name} 策略已重置"}


# ─────────────────────────── Tab4 数据源连接 ───────────────────────────

@router.get("/admin/config/datasources")
async def list_datasources(user_info: dict = Depends(require_admin)):
    """列出数据源"""
    items = await config_service.list_datasources()
    return {"status": "ok", "data": items}


@router.post("/admin/config/datasources/test")
async def test_datasource(body: DatasourceBody):
    """测试数据源连接（不落库）"""
    try:
        import pymysql
        conn = pymysql.connect(
            host=body.host, port=body.port, user=body.username,
            password=body.password, database=body.db_name or None,
            connect_timeout=body.connect_timeout,
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        conn.close()
        return {"status": "ok", "message": "数据源连接成功"}
    except Exception as e:
        return {"status": "error", "message": f"数据源连接失败: {str(e)}"}


@router.post("/admin/config/datasources")
async def create_datasource(body: DatasourceBody, ctx: dict = Depends(get_admin_context)):
    """新建数据源（待二次确认）"""
    # 审计快照中密码必须脱敏，不得出现明文（设计文档 §5.12）
    audit_snapshot = body.model_dump()
    if audit_snapshot.get("password"):
        audit_snapshot["password"] = config_crypto.mask(audit_snapshot["password"])
    result = await config_service.save_datasource(body.model_dump(), updated_by=str(ctx.get("user_id", "system_admin")))
    if result.get("status") == "waiting_confirm":
        await config_service.audit("config.datasource.create", ctx,
                                   {}, audit_snapshot, risk_level="high")
    return result


@router.delete("/admin/config/datasources/{datasource_id}")
async def delete_datasource(datasource_id: int, ctx: dict = Depends(get_admin_context)):
    """删除数据源"""
    from sqlalchemy import text
    from app.db.session import get_session
    async for session in get_session():
        await session.execute(
            text("DELETE FROM datasource_config WHERE id = :id"), {"id": datasource_id}
        )
        await session.commit()
    await config_service.audit("config.datasource.delete", ctx,
                               {"id": datasource_id}, {}, risk_level="high")
    return {"status": "ok", "message": f"数据源 #{datasource_id} 已删除"}


@router.get("/admin/config/change-requests")
async def list_change_requests(status: str = "pending", user_info: dict = Depends(require_admin)):
    """列出待确认队列"""
    items = await config_service.list_change_requests(status=status)
    return {"status": "ok", "data": items}


@router.post("/admin/config/change-requests/{request_id}/confirm")
async def confirm_change_request(request_id: int, body: ConfirmBody, ctx: dict = Depends(get_admin_context)):
    """二次确认生效"""
    result = await config_service.confirm_change_request(request_id, confirmed_by=str(ctx.get("user_id", "system_admin")))
    if result.get("status") == "ok":
        await config_service.audit("config.change_request.confirm", ctx,
                                   {"request_id": request_id}, {"status": "confirmed"}, risk_level="high")
    return result


@router.post("/admin/config/change-requests/{request_id}/cancel")
async def cancel_change_request(request_id: int, body: ConfirmBody, ctx: dict = Depends(get_admin_context)):
    """取消待确认"""
    result = await config_service.cancel_change_request(request_id)
    await config_service.audit("config.change_request.cancel", ctx,
                               {"request_id": request_id}, {"status": "cancelled"}, risk_level="medium")
    return result


# ─────────────────────────── Tab5 限流与配额 ───────────────────────────

@router.get("/admin/config/rate-limits")
async def list_rate_limits(user_info: dict = Depends(require_admin)):
    """列出限流配额"""
    items = await config_service.list_rate_limits()
    return {"status": "ok", "data": items}


@router.put("/admin/config/rate-limits/{scope_type}/{scope_id}")
async def save_rate_limit(scope_type: str, scope_id: str, body: RateLimitBody, ctx: dict = Depends(get_admin_context)):
    """upsert 限流配额"""
    before = await config_service.list_rate_limits()
    result = await config_service.save_rate_limit(scope_type, scope_id, body.model_dump(),
                                                  updated_by=str(ctx.get("user_id", "system_admin")))
    after = await config_service.list_rate_limits()
    await config_service.audit("config.rate_limit.update", ctx,
                               {"before": before}, {"after": after}, risk_level="low")
    return result


@router.delete("/admin/config/rate-limits/{scope_type}/{scope_id}")
async def delete_rate_limit(scope_type: str, scope_id: str, ctx: dict = Depends(get_admin_context)):
    """删除限流配额（回退默认）"""
    before = await config_service.list_rate_limits()
    result = await config_service.delete_rate_limit(scope_type, scope_id)
    after = await config_service.list_rate_limits()
    await config_service.audit("config.rate_limit.delete", ctx,
                               {"before": before}, {"after": after}, risk_level="low")
    return result


# ─────────────────────────── Tab6 保留期 ───────────────────────────

@router.get("/admin/config/retention")
async def get_retention(user_info: dict = Depends(require_admin)):
    """读取保留期配置"""
    retention = await config_service.get_retention()
    return {"status": "ok", "data": retention}


@router.put("/admin/config/retention")
async def save_retention(body: RetentionBody, ctx: dict = Depends(get_admin_context)):
    """保存保留期配置"""
    before = await config_service.get_retention()
    await config_service.save_retention(body.model_dump(), updated_by=str(ctx.get("user_id", "system_admin")))
    after = await config_service.get_retention()
    await config_service.audit("config.retention.update", ctx,
                               {"before": before}, {"after": after}, risk_level="low")
    return {"status": "ok", "message": "保留期配置已保存"}


@router.post("/admin/config/retention/dry-run")
async def retention_dry_run():
    """预览将被清理的数据（不真正删除）"""
    preview = await config_service.retention_dry_run()
    return {"status": "ok", "data": preview}


def _render_config_page() -> str:
    """渲染配置中心单页（Phase3 完善，先返回骨架）"""
    return """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>配置管理与后台运营中心</title>
        <style>
            :root {
                --brand: #1677ff;
                --brand-dark: #0958d9;
                --brand-light: #e6f4ff;
                --bg: #f5f6f8;
                --surface: #ffffff;
                --border: #e5e8ec;
                --text: #1f2329;
                --text-secondary: #61666d;
                --text-muted: #8f959e;
                --success: #00b42a;
                --danger: #f53f3f;
                --warning: #ff7d00;
                --radius: 10px;
                --shadow: 0 1px 2px rgba(0,0,0,0.03), 0 4px 16px rgba(0,0,0,0.06);
                --mono: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
            }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
                background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.6;
            }
            .header {
                background: linear-gradient(135deg, #0b1e3d 0%, #12315e 55%, #1677ff 140%);
                color: #fff; padding: 18px 28px; display: flex; align-items: center; justify-content: space-between;
                box-shadow: 0 2px 12px rgba(9,30,66,0.18); position: sticky; top: 0; z-index: 100;
            }
            .header h1 { font-size: 17px; font-weight: 600; letter-spacing: 0.5px; display: flex; align-items: center; gap: 10px; }
            .header h1::before {
                content: ''; width: 8px; height: 24px; border-radius: 4px;
                background: linear-gradient(180deg, #69b1ff, #1677ff); display: inline-block;
            }
            #pending-badge {
                font-size: 13px; opacity: 0.95; background: rgba(255,255,255,0.12);
                padding: 5px 14px; border-radius: 20px; backdrop-filter: blur(4px);
            }
            #pending-count { color: #ffd666; font-weight: 700; }
            .tabs {
                display: flex; background: var(--surface); border-bottom: 1px solid var(--border);
                padding: 0 28px; position: sticky; top: 60px; z-index: 99; box-shadow: 0 1px 4px rgba(0,0,0,0.04);
            }
            .tab {
                padding: 14px 18px; cursor: pointer; font-size: 14px; color: var(--text-secondary);
                border-bottom: 2px solid transparent; transition: color 0.2s, border-color 0.2s; position: relative;
            }
            .tab:hover { color: var(--brand); }
            .tab.active { color: var(--brand); border-bottom-color: var(--brand); font-weight: 600; }
            .container { max-width: 1280px; margin: 22px auto; padding: 0 28px; }
            .panel { display: none; }
            .panel.active { display: block; animation: fadeIn 0.25s ease; }
            @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
            .card {
                background: var(--surface); border-radius: var(--radius); padding: 22px 24px; margin-bottom: 18px;
                box-shadow: var(--shadow); border: 1px solid var(--border);
                transition: box-shadow 0.2s, transform 0.2s;
            }
            .card:hover { box-shadow: 0 2px 4px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.08); }
            .card h3 {
                color: var(--text); font-size: 15px; font-weight: 600; margin-bottom: 16px;
                padding-bottom: 10px; border-bottom: 1px solid var(--border);
                display: flex; align-items: center; gap: 8px;
            }
            .card h3::before { content: ''; width: 4px; height: 16px; border-radius: 2px; background: var(--brand); }
            .btn {
                background: var(--brand); color: #fff; border: none; padding: 7px 16px; border-radius: 6px;
                cursor: pointer; font-size: 13px; font-weight: 500; transition: background 0.2s, transform 0.1s;
                display: inline-flex; align-items: center; gap: 6px;
            }
            .btn:hover { background: var(--brand-dark); }
            .btn:active { transform: scale(0.97); }
            .btn-default { background: #fff; color: var(--text); border: 1px solid var(--border); }
            .btn-default:hover { border-color: var(--brand); color: var(--brand); background: var(--brand-light); }
            .btn-danger { background: var(--danger); }
            .btn-danger:hover { background: #d03030; }
            .btn-success { background: var(--success); }
            .btn-success:hover { background: #00911f; }
            input, select, textarea {
                padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px;
                margin: 4px 0; width: 100%; background: #fff; color: var(--text);
                transition: border-color 0.2s, box-shadow 0.2s; outline: none;
            }
            input:focus, select:focus, textarea:focus { border-color: var(--brand); box-shadow: 0 0 0 3px rgba(22,119,255,0.12); }
            .form-row { display: flex; gap: 14px; flex-wrap: wrap; }
            .form-row .field { flex: 1; min-width: 180px; }
            .form-row label { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 3px; font-weight: 500; }
            table { width: 100%; border-collapse: collapse; margin-top: 12px; }
            th, td { border-bottom: 1px solid var(--border); padding: 10px 12px; text-align: left; font-size: 13px; }
            th { background: #fafbfc; color: var(--text-secondary); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.3px; }
            tbody tr { transition: background 0.15s; }
            tbody tr:hover { background: #f7f9fc; }
            td code, .mono { font-family: var(--mono); font-size: 12px; color: #0b5bcc; background: #f0f5ff; padding: 1px 6px; border-radius: 4px; }
            .tag { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 500; }
            .tag-green { background: #e8ffea; color: #00a01a; border: 1px solid #9be2a6; }
            .tag-red { background: #ffece8; color: #d92d20; border: 1px solid #ffb8ad; }
            .tag-blue { background: #e8f3ff; color: #1677ff; border: 1px solid #a3ccff; }
            .tag-orange { background: #fff3e8; color: #e8590c; border: 1px solid #ffc28a; }
            .status-text { font-size: 13px; margin-top: 8px; margin-left: 8px; }
            .status-text.ok { color: var(--success); }
            .status-text.err { color: var(--danger); }
            .switch { position: relative; width: 42px; height: 22px; background: #d0d5dd; border-radius: 11px; cursor: pointer; display: inline-block; transition: background 0.2s; }
            .switch.on { background: var(--brand); }
            .switch::after {
                content: ''; position: absolute; top: 2px; left: 2px; width: 18px; height: 18px;
                background: #fff; border-radius: 50%; transition: left 0.2s; box-shadow: 0 1px 3px rgba(0,0,0,0.2);
            }
            .switch.on::after { left: 22px; }
            .modal-mask { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(9,30,66,0.5); z-index: 1000; backdrop-filter: blur(2px); }
            .modal {
                display: none; position: fixed; top: 50%; left: 50%; transform: translate(-50%,-50%);
                background: #fff; border-radius: 12px; padding: 26px; width: 520px; z-index: 1001;
                box-shadow: 0 12px 48px rgba(9,30,66,0.25); animation: fadeIn 0.2s ease;
            }
            .modal h3 { margin-bottom: 16px; font-size: 16px; display: flex; align-items: center; gap: 8px; }
            .modal h3::before { content: ''; width: 4px; height: 18px; border-radius: 2px; background: var(--warning); }
            .modal .diff { background: #fafbfc; border: 1px solid var(--border); padding: 14px; border-radius: 8px; font-size: 12px; margin-bottom: 14px; }
            .modal .diff pre { white-space: pre-wrap; word-break: break-all; font-family: var(--mono); line-height: 1.7; }
            details { font-size: 13px; }
            details summary { cursor: pointer; color: var(--brand); }
            details pre { background: #f6f8fb; border-radius: 6px; padding: 10px; font-size: 12px; max-height: 200px; overflow: auto; font-family: var(--mono); margin-top: 6px; }
            .change-item {
                display: flex; justify-content: space-between; align-items: center; padding: 10px 14px;
                border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; transition: background 0.15s;
            }
            .change-item:hover { background: #f7f9fc; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>配置管理与后台运营中心</h1>
            <span id="pending-badge" style="font-size:13px;opacity:0.9">待确认: <b id="pending-count">0</b></span>
        </div>
        <div class="tabs" id="tabs">
            <div class="tab active" data-tab="model">模型与路由</div>
            <div class="tab" data-tab="knowledge">知识库</div>
            <div class="tab" data-tab="tools">工具与风险</div>
            <div class="tab" data-tab="datasource">数据源</div>
            <div class="tab" data-tab="ratelimit">限流与配额</div>
            <div class="tab" data-tab="retention">保留期</div>
            <div class="tab" data-tab="audit">审计日志</div>
        </div>
        <div class="container">
            <div class="panel active" id="panel-model">
                <div class="card">
                    <h3>LLM 连接</h3>
                    <div class="form-row">
                        <div class="field"><label>Provider</label><select id="llm-provider"><option>deepseek</option><option>anthropic</option><option>openai</option></select></div>
                        <div class="field"><label>Base URL</label><input id="llm-base-url" placeholder="https://api.deepseek.com"></div>
                        <div class="field"><label>API Key</label><input id="llm-api-key" type="password" placeholder="****"></div>
                        <div class="field"><label>Model</label><input id="llm-model" placeholder="deepseek-chat"></div>
                        <div class="field"><label>Max Tokens</label><input id="llm-max-tokens" type="number" value="4096"></div>
                        <div class="field"><label>Temperature</label><input id="llm-temperature" type="number" step="0.1" value="0.1"></div>
                    </div>
                    <div style="margin-top:12px">
                        <button class="btn" onclick="testLLM()">测试连接</button>
                        <button class="btn btn-success" onclick="saveLLM()">保存</button>
                        <span id="llm-status" class="status-text"></span>
                    </div>
                </div>
                <div class="card">
                    <h3>模型路由</h3>
                    <button class="btn btn-default" onclick="openRouteModal()">+ 新增路由</button>
                    <table id="routes-table"><thead><tr><th>任务类型</th><th>主模型</th><th>备用模型</th><th>敏感级别</th><th>优先级</th><th>启用</th><th>操作</th></tr></thead><tbody></tbody></table>
                </div>
            </div>
            <div class="panel" id="panel-knowledge">
                <div class="card">
                    <h3>知识库管理</h3>
                    <div class="form-row">
                        <div class="field"><label>搜索</label><input id="kw-search" placeholder="标题/内容/标签"></div>
                        <div class="field"><label>分类</label><select id="kw-category"><option value="">全部</option><option value="manual">手册</option><option value="rule">规则</option><option value="faq">FAQ</option></select></div>
                        <div style="align-self:flex-end"><button class="btn" onclick="searchKnowledge()">搜索</button><button class="btn btn-success" onclick="openKnowledgeModal()">+ 新增</button></div>
                    </div>
                    <table id="knowledge-table"><thead><tr><th>ID</th><th>标题</th><th>分类</th><th>标签</th><th>权限范围</th><th>操作</th></tr></thead><tbody></tbody></table>
                </div>
            </div>
            <div class="panel" id="panel-tools">
                <div class="card">
                    <h3>工具与风险策略</h3>
                    <table id="tools-table"><thead><tr><th>工具</th><th>描述</th><th>权限等级</th><th>风险等级</th><th>需确认</th><th>超时(秒)</th><th>重试</th><th>启用</th><th>操作</th></tr></thead><tbody></tbody></table>
                </div>
            </div>
            <div class="panel" id="panel-datasource">
                <div class="card">
                    <h3>数据源连接</h3>
                    <div class="form-row">
                        <div class="field"><label>名称</label><input id="ds-name" placeholder="erp-read-replica"></div>
                        <div class="field"><label>类型</label><select id="ds-type"><option value="mysql_replica">MySQL 只读副本</option></select></div>
                        <div class="field"><label>Host</label><input id="ds-host"></div>
                        <div class="field"><label>Port</label><input id="ds-port" type="number" value="3306"></div>
                        <div class="field"><label>数据库</label><input id="ds-db"></div>
                        <div class="field"><label>用户名</label><input id="ds-user"></div>
                        <div class="field"><label>密码</label><input id="ds-password" type="password"></div>
                        <div class="field"><label>超时(秒)</label><input id="ds-timeout" type="number" value="10"></div>
                    </div>
                    <div style="margin-top:12px">
                        <button class="btn" onclick="testDatasource()">测试连接</button>
                        <button class="btn btn-success" onclick="saveDatasource()">保存</button>
                        <span id="ds-status" class="status-text"></span>
                    </div>
                </div>
                <div class="card">
                    <h3>待确认队列</h3>
                    <div id="change-requests"></div>
                </div>
                <div class="card">
                    <h3>数据源列表</h3>
                    <table id="datasource-table"><thead><tr><th>ID</th><th>名称</th><th>Host</th><th>数据库</th><th>密码</th><th>状态</th><th>操作</th></tr></thead><tbody></tbody></table>
                </div>
            </div>
            <div class="panel" id="panel-ratelimit">
                <div class="card">
                    <h3>限流与配额</h3>
                    <div class="form-row">
                        <div class="field"><label>范围类型</label><select id="rl-type"><option value="user">用户</option><option value="department">部门</option><option value="tenant">租户</option></select></div>
                        <div class="field"><label>范围 ID</label><input id="rl-id" placeholder="如 user_001 / dept_001 / 1"></div>
                        <div class="field"><label>QPS</label><input id="rl-qps" type="number" value="10"></div>
                        <div class="field"><label>并发</label><input id="rl-concurrency" type="number" value="5"></div>
                        <div class="field"><label>Token月配额</label><input id="rl-quota" type="number" value="0"></div>
                        <div style="align-self:flex-end"><button class="btn btn-success" onclick="saveRateLimit()">添加/更新</button></div>
                    </div>
                    <table id="ratelimit-table"><thead><tr><th>范围</th><th>范围ID</th><th>QPS</th><th>并发</th><th>Token月配额</th><th>启用</th><th>操作</th></tr></thead><tbody></tbody></table>
                </div>
            </div>
            <div class="panel" id="panel-retention">
                <div class="card">
                    <h3>保留期与生命周期</h3>
                    <div class="form-row">
                        <div class="field"><label>任务保留(天)</label><input id="rt-task" type="number" value="90"></div>
                        <div class="field"><label>会话保留(天)</label><input id="rt-session" type="number" value="180"></div>
                        <div class="field"><label>记忆保留(天)</label><input id="rt-memory" type="number" value="365"></div>
                        <div class="field"><label>审计保留(天)</label><input id="rt-audit" type="number" value="365"></div>
                    </div>
                    <div style="margin-top:12px">
                        <button class="btn btn-success" onclick="saveRetention()">保存</button>
                        <button class="btn" onclick="retentionDryRun()">预览清理</button>
                        <span id="rt-status" class="status-text"></span>
                    </div>
                    <div id="rt-preview"></div>
                </div>
            </div>
            <div class="panel" id="panel-audit">
                <div class="card">
                    <h3>审计日志</h3>
                    <div class="form-row">
                        <div class="field"><label>Action 过滤</label><input id="audit-action" placeholder="如 config.llm.update"></div>
                        <div style="align-self:flex-end"><button class="btn" onclick="loadAuditLogs()">查询</button></div>
                    </div>
                    <table id="audit-table"><thead><tr><th>时间</th><th>Action</th><th>风险</th><th>用户</th><th>快照</th></tr></thead><tbody></tbody></table>
                </div>
            </div>
        </div>

        <!-- 二次确认 Modal -->
        <div class="modal-mask" id="confirm-mask"></div>
        <div class="modal" id="confirm-modal">
            <h3 id="confirm-title">二次确认</h3>
            <div class="diff"><pre id="confirm-detail"></pre></div>
            <div style="text-align:right">
                <button class="btn btn-default" onclick="closeConfirm()">取消</button>
                <button class="btn btn-success" onclick="doConfirm()">确认生效</button>
            </div>
        </div>

        <script>
            const BASE = '/api/v1/admin/config';
            const TOKEN = 'Bearer ' + (localStorage.getItem('token') || '');
            // 未登录则跳转
            if (!localStorage.getItem('token')) { window.location.href = '/login'; }
            const $ = id => document.getElementById(id);
            let pendingRequestId = null;
            let pendingConfirmData = null;

            async function api(path, method='GET', body=null) {
                const opts = { method, headers: { 'Authorization': TOKEN, 'Content-Type': 'application/json' } };
                if (body) opts.body = JSON.stringify(body);
                const res = await fetch(BASE + path, opts);
                return await res.json();
            }

            // Tab 切换
            document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
                document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
                document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
                t.classList.add('active');
                $('panel-' + t.dataset.tab).classList.add('active');
                loaders[t.dataset.tab]();
            });
            const loaders = {
                model: () => { loadLLM(); loadRoutes(); },
                knowledge: searchKnowledge,
                tools: loadTools,
                datasource: () => { loadDatasources(); loadChangeRequests(); },
                ratelimit: loadRateLimits,
                retention: loadRetention,
                audit: loadAuditLogs,
            };

            // ---- 模型与路由 ----
            async function loadLLM() {
                const d = await api('/llm');
                if (d.status === 'ok') {
                    $('llm-provider').value = d.data.provider || 'deepseek';
                    $('llm-base-url').value = d.data.base_url || '';
                    $('llm-api-key').value = d.data.api_key || '';
                    $('llm-model').value = d.data.model || '';
                    $('llm-max-tokens').value = d.data.max_tokens || 4096;
                    $('llm-temperature').value = d.data.temperature || 0.1;
                }
            }
            async function testLLM() {
                $('llm-status').textContent = '测试中...';
                const body = { provider: $('llm-provider').value, base_url: $('llm-base-url').value, api_key: $('llm-api-key').value, model: $('llm-model').value };
                const d = await api('/llm/test', 'POST', body);
                $('llm-status').className = 'status-text ' + (d.status === 'ok' ? 'ok' : 'err');
                $('llm-status').textContent = d.message || (d.status === 'ok' ? '连接成功' : '连接失败');
            }
            async function saveLLM() {
                const body = {
                    provider: $('llm-provider').value, base_url: $('llm-base-url').value,
                    api_key: $('llm-api-key').value, model: $('llm-model').value,
                    max_tokens: parseInt($('llm-max-tokens').value) || 4096,
                    temperature: parseFloat($('llm-temperature').value) || 0.1,
                };
                const d = await api('/llm', 'PUT', body);
                $('llm-status').className = 'status-text ' + (d.status === 'ok' ? 'ok' : 'err');
                $('llm-status').textContent = d.message || '保存完成';
            }
            async function loadRoutes() {
                const d = await api('/model-routes');
                const tb = $('routes-table').querySelector('tbody');
                tb.innerHTML = (d.data || []).map(r => `
                    <tr>
                        <td>${r.task_type}</td>
                        <td>${r.primary_model}</td>
                        <td>${Array.isArray(r.fallback_models) ? r.fallback_models.join(', ') : ''}</td>
                        <td>${r.sensitivity_level || 'normal'}</td>
                        <td>${r.priority || 100}</td>
                        <td>${r.enabled ? '<span class="tag tag-green">启用</span>' : '<span class="tag tag-red">停用</span>'}</td>
                        <td><button class="btn btn-default" onclick="deleteRoute('${r.task_type}')">删除</button></td>
                    </tr>`).join('');
            }
            async function deleteRoute(taskType) {
                if (!confirm('确认删除路由: ' + taskType + '?')) return;
                await api('/model-routes/' + taskType, 'DELETE');
                loadRoutes();
            }
            async function openRouteModal() {
                const tt = prompt('任务类型 (如 query / report / sql_gen):');
                if (!tt) return;
                const pm = prompt('主模型 (默认 deepseek-chat):') || 'deepseek-chat';
                await api('/model-routes/' + tt, 'PUT', { primary_model: pm, fallback_models: [], sensitivity_level: 'normal', enabled: true, priority: 100 });
                loadRoutes();
            }

            // ---- 知识库 ----
            async function searchKnowledge() {
                const kw = $('kw-search').value;
                const cat = $('kw-category').value;
                const d = await api('/knowledge?keyword=' + encodeURIComponent(kw) + '&category=' + encodeURIComponent(cat));
                const tb = $('knowledge-table').querySelector('tbody');
                tb.innerHTML = (d.data || []).map(k => `
                    <tr>
                        <td>${k.id}</td>
                        <td>${k.title || ''}</td>
                        <td>${k.category || ''}</td>
                        <td>${k.tags || ''}</td>
                        <td>${k.permission_scope || 'all'}</td>
                        <td><button class="btn btn-default" onclick="deleteKnowledge(${k.id})">删除</button></td>
                    </tr>`).join('');
            }
            async function openKnowledgeModal() {
                const title = prompt('标题:');
                if (!title) return;
                const content = prompt('内容:');
                const category = prompt('分类 (manual/rule/faq):') || 'manual';
                await api('/knowledge', 'POST', { title, content, category, tags: '', permission_scope: 'all' });
                searchKnowledge();
            }
            async function deleteKnowledge(id) {
                if (!confirm('确认删除知识条目 #' + id + '?')) return;
                await api('/knowledge/' + id, 'DELETE');
                searchKnowledge();
            }

            // ---- 工具与风险 ----
            async function loadTools() {
                const d = await api('/tools');
                const tb = $('tools-table').querySelector('tbody');
                tb.innerHTML = (d.data || []).map(t => `
                    <tr>
                        <td>${t.name}</td>
                        <td>${t.description || ''}</td>
                        <td><span class="tag tag-blue">${t.permission_level}</span></td>
                        <td>
                            <select data-tool="${t.name}" data-field="risk_level">
                                ${['low','medium','high'].map(l => `<option value="${l}" ${t.risk_level === l ? 'selected' : ''}>${l}</option>`).join('')}
                            </select>
                        </td>
                        <td><span class="switch ${t.need_confirm ? 'on' : ''}" data-tool="${t.name}" data-field="need_confirm"></span></td>
                        <td><input data-tool="${t.name}" data-field="timeout" type="number" value="${t.timeout}" style="width:70px"></td>
                        <td><input data-tool="${t.name}" data-field="retry_count" type="number" value="${t.retry_count}" style="width:70px"></td>
                        <td><span class="switch ${t.enabled ? 'on' : ''}" data-tool="${t.name}" data-field="enabled"></span></td>
                        <td><button class="btn btn-success" onclick="saveTool('${t.name}', '${t.risk_level}', ${t.need_confirm})">保存</button></td>
                    </tr>`).join('');
                document.querySelectorAll('.switch').forEach(s => s.onclick = () => {
                    s.classList.toggle('on');
                    const isOn = s.classList.contains('on');
                    const field = s.dataset.field;
                    if (field === 'enabled') s.classList.toggle('on', isOn);
                });
            }
            async function saveTool(name, oldRisk, oldConfirm) {
                const row = [...document.querySelectorAll(`[data-tool="${name}"]`)];
                const data = {};
                row.forEach(el => data[el.dataset.field] = el.dataset.field === 'need_confirm' || el.dataset.field === 'enabled'
                    ? el.classList.contains('on') : (el.dataset.field === 'timeout' || el.dataset.field === 'retry_count' ? parseInt(el.value) : el.value));
                // 判断是否降级
                const isDowngrade = (oldRisk === 'high' && ['medium','low'].includes(data.risk_level)) || (oldConfirm && !data.need_confirm);
                const d = await api('/tools/' + name, 'PUT', data);
                if (d.status === 'waiting_confirm') {
                    pendingRequestId = d.change_request_id;
                    pendingConfirmData = { namespace: 'tool_policy', target: name, new_value: data };
                    $('confirm-title').textContent = '工具风险降级确认';
                    $('confirm-detail').textContent = '工具: ' + name + '\\n变更前: risk=' + oldRisk + ', need_confirm=' + oldConfirm + '\\n变更后: ' + JSON.stringify(data, null, 2);
                    $('confirm-modal').style.display = 'block';
                    $('confirm-mask').style.display = 'block';
                } else {
                    alert(d.message || '已保存');
                    loadTools();
                }
            }

            // ---- 数据源 ----
            async function testDatasource() {
                $('ds-status').textContent = '测试中...';
                const body = {
                    name: $('ds-name').value, type: $('ds-type').value, host: $('ds-host').value,
                    port: parseInt($('ds-port').value) || 3306, db_name: $('ds-db').value,
                    username: $('ds-user').value, password: $('ds-password').value,
                    connect_timeout: parseInt($('ds-timeout').value) || 10,
                };
                const d = await api('/datasources/test', 'POST', body);
                $('ds-status').className = 'status-text ' + (d.status === 'ok' ? 'ok' : 'err');
                $('ds-status').textContent = d.message || '测试完成';
            }
            async function saveDatasource() {
                const body = {
                    name: $('ds-name').value, type: $('ds-type').value, host: $('ds-host').value,
                    port: parseInt($('ds-port').value) || 3306, db_name: $('ds-db').value,
                    username: $('ds-user').value, password: $('ds-password').value,
                    connect_timeout: parseInt($('ds-timeout').value) || 10,
                };
                const d = await api('/datasources', 'POST', body);
                if (d.status === 'waiting_confirm') {
                    pendingRequestId = d.change_request_id;
                    pendingConfirmData = { namespace: 'datasource', target: d.datasource_id, new_value: body };
                    $('confirm-title').textContent = '数据源连接确认';
                    $('confirm-detail').textContent = '数据源: ' + body.name + '\\nHost: ' + body.host + ':' + body.port + '\\n数据库: ' + body.db_name;
                    $('confirm-modal').style.display = 'block';
                    $('confirm-mask').style.display = 'block';
                } else {
                    alert(d.message || '已保存');
                    loadDatasources();
                }
            }
            async function loadDatasources() {
                const d = await api('/datasources');
                const tb = $('datasource-table').querySelector('tbody');
                tb.innerHTML = (d.data || []).map(ds => `
                    <tr>
                        <td>${ds.id}</td>
                        <td>${ds.name}</td>
                        <td>${ds.host}:${ds.port}</td>
                        <td>${ds.db_name}</td>
                        <td>${ds.password_masked || ''}</td>
                        <td>${ds.enabled ? '<span class="tag tag-green">生效</span>' : '<span class="tag tag-orange">待确认</span>'}</td>
                        <td><button class="btn btn-default" onclick="deleteDatasource(${ds.id})">删除</button></td>
                    </tr>`).join('');
            }
            async function deleteDatasource(id) {
                if (!confirm('确认删除数据源 #' + id + '?')) return;
                await api('/datasources/' + id, 'DELETE');
                loadDatasources();
            }
            async function loadChangeRequests() {
                const d = await api('/change-requests?status=pending');
                const list = d.data || [];
                $('pending-count').textContent = list.length;
                $('change-requests').innerHTML = list.length === 0 ? '<p style="color:#999">无待确认项</p>' : list.map(cr => `
                    <div style="padding:10px;border:1px solid #eee;border-radius:6px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center">
                        <span>${cr.namespace} · ${cr.target_key} · ${cr.operation} · 请求人:${cr.requested_by}</span>
                        <span>
                            <button class="btn btn-success" onclick="confirmChange(${cr.id})">确认</button>
                            <button class="btn btn-default" onclick="cancelChange(${cr.id})">取消</button>
                        </span>
                    </div>`).join('');
            }
            async function confirmChange(id) {
                await api('/change-requests/' + id + '/confirm', 'POST', { change_request_id: id });
                loadChangeRequests();
                loadDatasources();
            }
            async function cancelChange(id) {
                await api('/change-requests/' + id + '/cancel', 'POST', { change_request_id: id });
                loadChangeRequests();
            }

            // ---- 限流 ----
            async function loadRateLimits() {
                const d = await api('/rate-limits');
                const tb = $('ratelimit-table').querySelector('tbody');
                tb.innerHTML = (d.data || []).map(r => `
                    <tr>
                        <td>${r.scope_type}</td>
                        <td>${r.scope_id}</td>
                        <td>${r.qps}</td>
                        <td>${r.concurrency}</td>
                        <td>${r.token_quota_monthly}</td>
                        <td>${r.enabled ? '<span class="tag tag-green">启用</span>' : '<span class="tag tag-red">停用</span>'}</td>
                        <td><button class="btn btn-default" onclick="deleteRateLimit('${r.scope_type}','${r.scope_id}')">删除</button></td>
                    </tr>`).join('');
            }
            async function saveRateLimit() {
                const body = {
                    qps: parseInt($('rl-qps').value) || 10, concurrency: parseInt($('rl-concurrency').value) || 5,
                    token_quota_monthly: parseInt($('rl-quota').value) || 0, enabled: true,
                };
                await api('/rate-limits/' + $('rl-type').value + '/' + encodeURIComponent($('rl-id').value), 'PUT', body);
                loadRateLimits();
            }
            async function deleteRateLimit(type, id) {
                if (!confirm('确认删除限流配额: ' + type + '/' + id + '?')) return;
                await api('/rate-limits/' + type + '/' + encodeURIComponent(id), 'DELETE');
                loadRateLimits();
            }

            // ---- 保留期 ----
            async function loadRetention() {
                const d = await api('/retention');
                if (d.status === 'ok') {
                    $('rt-task').value = d.data.task_days || 90;
                    $('rt-session').value = d.data.session_days || 180;
                    $('rt-memory').value = d.data.memory_days || 365;
                    $('rt-audit').value = d.data.audit_days || 365;
                }
            }
            async function saveRetention() {
                const body = {
                    task_days: parseInt($('rt-task').value) || 90, session_days: parseInt($('rt-session').value) || 180,
                    memory_days: parseInt($('rt-memory').value) || 365, audit_days: parseInt($('rt-audit').value) || 365,
                };
                const d = await api('/retention', 'PUT', body);
                $('rt-status').textContent = d.message || '已保存';
                $('rt-status').className = 'status-text ' + (d.status === 'ok' ? 'ok' : 'err');
            }
            async function retentionDryRun() {
                const d = await api('/retention/dry-run', 'POST');
                const pv = d.data || {};
                $('rt-preview').innerHTML = '<h4 style="margin-top:12px">清理预览</h4><table><tr><th>表</th><th>保留天数</th><th>将被清理</th></tr>' +
                    Object.entries(pv.tables || {}).map(([t, v]) => `<tr><td>${t}</td><td>${v.days}</td><td>${v.will_delete}</td></tr>`).join('') + '</table>';
            }

            // ---- 审计 ----
            async function loadAuditLogs() {
                const action = $('audit-action').value;
                const d = await api('/audit-logs?limit=100&action=' + encodeURIComponent(action));
                const tb = $('audit-table').querySelector('tbody');
                tb.innerHTML = (d.data || []).map(a => `
                    <tr>
                        <td>${a.created_at}</td>
                        <td>${a.action}</td>
                        <td><span class="tag ${a.risk_level === 'high' ? 'tag-red' : a.risk_level === 'medium' ? 'tag-orange' : 'tag-green'}">${a.risk_level}</span></td>
                        <td>${a.user_id}</td>
                        <td><details><summary>查看</summary><pre>${JSON.stringify(a.request_snapshot || {}, null, 2)}</pre></details></td>
                    </tr>`).join('');
            }

            // ---- 二次确认 ----
            function closeConfirm() {
                $('confirm-modal').style.display = 'none';
                $('confirm-mask').style.display = 'none';
                pendingRequestId = null;
            }
            async function doConfirm() {
                if (pendingRequestId) {
                    await api('/change-requests/' + pendingRequestId + '/confirm', 'POST', { change_request_id: pendingRequestId });
                }
                closeConfirm();
                loadChangeRequests();
                loadDatasources();
                loadTools();
            }
            $('confirm-mask').onclick = closeConfirm;

            // 初始化
            loaders.model();
            loadChangeRequests();
        </script>
    </body>
    </html>
    """
