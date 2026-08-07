"""管理端点 - Agent 管理中心

职责：
- Agent 配置管理
- Agent 监控
- Prompt 模板管理
"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


from fastapi.responses import HTMLResponse


@router.get("/admin", response_class=HTMLResponse)
async def admin_index():
    """管理页面首页"""
    return """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Agent-Zs 管理中心</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f0f2f5; color: #333; }
            .header { background: #1890ff; color: white; padding: 16px 24px; font-size: 20px; }
            .container { max-width: 1200px; margin: 20px auto; padding: 0 20px; }
            .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; }
            .card { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
            .card h3 { color: #1890ff; margin-bottom: 12px; font-size: 16px; }
            .card p { color: #666; font-size: 14px; margin-bottom: 8px; }
            .stat { display: inline-block; margin-right: 20px; }
            .stat .num { font-size: 24px; font-weight: bold; color: #1890ff; }
            .stat .label { font-size: 12px; color: #999; }
            .btn { background: #1890ff; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-right: 8px; }
            .btn:hover { background: #40a9ff; }
            .btn-danger { background: #ff4d4f; }
            .btn-danger:hover { background: #ff7875; }
            .list { margin-top: 12px; }
            .list-item { padding: 10px; border-bottom: 1px solid #f0f0f0; display: flex; justify-content: space-between; align-items: center; }
            .list-item:last-child { border-bottom: none; }
            .tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
            .tag-success { background: #f6ffed; color: #52c41a; border: 1px solid #b7eb8f; }
            .tag-info { background: #e6f7ff; color: #1890ff; border: 1px solid #91d5ff; }
            .workflow-list { margin-top: 12px; }
            .workflow-item { padding: 12px; border: 1px solid #f0f0f0; border-radius: 6px; margin-bottom: 8px; cursor: pointer; }
            .workflow-item:hover { border-color: #1890ff; background: #f0f5ff; }
            .workflow-item h4 { margin-bottom: 4px; }
            .workflow-item p { color: #666; font-size: 13px; }
        </style>
    </head>
    <body>
        <div class="header">Agent-Zs 管理中心</div>
        <div class="container">
            <div class="cards">
                <!-- Agent 管理 -->
                <div class="card">
                    <h3>Agent 管理</h3>
                    <p>配置和监控 Agent</p>
                    <div id="agents-stats"></div>
                    <div class="list" id="agents-list"></div>
                    <button class="btn" onclick="loadAgents()">刷新</button>
                </div>

                <!-- 工作流管理 -->
                <div class="card">
                    <h3>工作流</h3>
                    <p>管理工作流定义</p>
                    <div class="workflow-list" id="workflow-list"></div>
                    <button class="btn" onclick="loadWorkflows()">刷新</button>
                </div>

                <!-- 监控 -->
                <div class="card" style="grid-column: 1 / -1;">
                    <h3>监控数据</h3>
                    <p>最近 24 小时任务统计</p>
                    <div id="monitor-stats"></div>
                    <button class="btn" onclick="loadMonitor()">刷新</button>
                </div>
            </div>
        </div>

        <script>
            const BASE = '/api/v1';

            async function loadAgents() {
                try {
                    const res = await fetch(`${BASE}/admin/agents`);
                    const data = await res.json();
                    const list = document.getElementById('agents-list');
                    const stats = document.getElementById('agents-stats');

                    if (data.agents) {
                        stats.innerHTML = `<span class="stat"><span class="num">${data.agents.length}</span><span class="label">个 Agent</span></span>`;
                        list.innerHTML = data.agents.map(a => `
                            <div class="list-item">
                                <span><strong>${a.name}</strong></span>
                                <span>
                                    <span class="tag ${a.enabled ? 'tag-success' : 'tag-info'}">${a.enabled ? '已启用' : '已禁用'}</span>
                                    <span class="tag tag-info">${a.model}</span>
                                </span>
                            </div>
                        `).join('');
                    }
                } catch(e) {
                    console.error('加载 Agent 失败:', e);
                }
            }

            async function loadWorkflows() {
                try {
                    const res = await fetch(`${BASE}/workflow/list`);
                    const data = await res.json();
                    const list = document.getElementById('workflow-list');

                    if (data.workflows) {
                        list.innerHTML = data.workflows.map(w => `
                            <div class="workflow-item" onclick="runWorkflow('${w.workflow_id}')">
                                <h4>${w.name}</h4>
                                <p>${w.description}</p>
                                <p style="color:#999;font-size:12px">${w.steps} 个步骤</p>
                            </div>
                        `).join('');
                    }
                } catch(e) {
                    console.error('加载工作流失败:', e);
                }
            }

            async function loadMonitor() {
                try {
                    const res = await fetch(`${BASE}/admin/monitor`);
                    const data = await res.json();
                    const stats = document.getElementById('monitor-stats');

                    if (data.monitor && data.monitor.stats) {
                        const total = data.monitor.stats.reduce((sum, s) => sum + s.count, 0);
                        stats.innerHTML = `
                            <span class="stat"><span class="num">${total}</span><span class="label">总任务数</span></span>
                        `;

                        if (data.monitor.stats.length === 0) {
                            stats.innerHTML += '<p style="color:#999;margin-top:12px">暂无数据</p>';
                        }
                    } else {
                        stats.innerHTML = '<p style="color:#999">暂无监控数据</p>';
                    }
                } catch(e) {
                    console.error('加载监控失败:', e);
                }
            }

            async function runWorkflow(id) {
                if (!confirm(`确认执行工作流: ${id}?`)) return;

                try {
                    const res = await fetch(`${BASE}/workflow/execute`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + (localStorage.getItem('token') || '')
                        },
                        body: JSON.stringify({ workflow_id: id })
                    });
                    const data = await res.json();
                    alert(data.message || '执行完成');
                } catch(e) {
                    alert('执行失败: ' + e.message);
                }
            }

            // 页面加载时初始化
            loadAgents();
            loadWorkflows();
            loadMonitor();
        </script>
    </body>
    </html>
    """


class AgentConfig(BaseModel):
    """Agent 配置"""
    name: str
    enabled: bool = True
    model: str = "deepseek-chat"
    temperature: float = 0.1
    max_tokens: int = 4096


class PromptTemplate(BaseModel):
    """Prompt 模板"""
    name: str
    template: str
    description: str = ""


# Agent 配置存储
_agent_configs = {
    "data_agent": {
        "name": "data_agent",
        "enabled": True,
        "model": "deepseek-chat",
        "temperature": 0.1,
        "max_tokens": 4096,
    },
    "write_agent": {
        "name": "write_agent",
        "enabled": True,
        "model": "deepseek-chat",
        "temperature": 0.1,
        "max_tokens": 4096,
    },
    "knowledge_agent": {
        "name": "knowledge_agent",
        "enabled": True,
        "model": "deepseek-chat",
        "temperature": 0.1,
        "max_tokens": 4096,
    },
}

# Prompt 模板存储
_prompt_templates = {
    "nl_to_sql": {
        "name": "nl_to_sql",
        "template": "你是一个 SQL 专家。根据用户的自然语言问题，结合数据库 schema，生成正确的 MySQL SQL 语句。",
        "description": "NL-to-SQL 转换模板",
    },
    "intent识别": {
        "name": "intent识别",
        "template": "你是一个意图识别专家。根据用户的输入，判断用户想要做什么。",
        "description": "意图识别模板",
    },
    "参数提取": {
        "name": "参数提取",
        "template": "你是一个 ERP 系统参数提取专家。根据用户的自然语言输入，提取创建单据所需的参数。",
        "description": "参数提取模板",
    },
}


@router.get("/admin/agents")
async def list_agents():
    """获取所有 Agent 列表"""
    return {
        "status": "ok",
        "agents": list(_agent_configs.values()),
    }


@router.get("/admin/agents/{agent_name}")
async def get_agent(agent_name: str):
    """获取 Agent 配置"""
    if agent_name not in _agent_configs:
        return {"status": "error", "message": f"Agent 不存在: {agent_name}"}

    return {
        "status": "ok",
        "agent": _agent_configs[agent_name],
    }


@router.put("/admin/agents/{agent_name}")
async def update_agent(agent_name: str, config: AgentConfig):
    """更新 Agent 配置"""
    _agent_configs[agent_name] = config.model_dump()

    logger.info(f"Agent 配置更新: {agent_name}")

    return {
        "status": "ok",
        "message": f"Agent 配置已更新: {agent_name}",
    }


@router.get("/admin/prompts")
async def list_prompts():
    """获取所有 Prompt 模板"""
    return {
        "status": "ok",
        "prompts": list(_prompt_templates.values()),
    }


@router.get("/admin/prompts/{prompt_name}")
async def get_prompt(prompt_name: str):
    """获取 Prompt 模板"""
    if prompt_name not in _prompt_templates:
        return {"status": "error", "message": f"Prompt 模板不存在: {prompt_name}"}

    return {
        "status": "ok",
        "prompt": _prompt_templates[prompt_name],
    }


@router.put("/admin/prompts/{prompt_name}")
async def update_prompt(prompt_name: str, template: PromptTemplate):
    """更新 Prompt 模板"""
    _prompt_templates[prompt_name] = template.model_dump()

    logger.info(f"Prompt 模板更新: {prompt_name}")

    return {
        "status": "ok",
        "message": f"Prompt 模板已更新: {prompt_name}",
    }


@router.get("/admin/monitor")
async def get_monitor():
    """获取 Agent 监控数据"""
    # 从数据库获取最近的统计数据
    from sqlalchemy import text
    from app.db.session import get_session

    try:
        async for session in get_session():
            # 获取最近 24 小时的任务统计
            result = await session.execute(
                text("""
                    SELECT
                        task_type,
                        agent_name,
                        status,
                        COUNT(*) as count
                    FROM task_history
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                    GROUP BY task_type, agent_name, status
                """)
            )
            rows = result.fetchall()

            stats = []
            for row in rows:
                stats.append({
                    "task_type": row[0],
                    "agent_name": row[1],
                    "status": row[2],
                    "count": row[3],
                })

            return {
                "status": "ok",
                "monitor": {
                    "period": "24h",
                    "stats": stats,
                },
            }

    except Exception as e:
        logger.error(f"获取监控数据失败: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"获取监控数据失败: {str(e)}",
        }
