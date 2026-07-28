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


@router.get("/admin")
async def admin_index():
    """管理页面首页"""
    return {
        "status": "ok",
        "endpoints": {
            "agents": "/api/v1/admin/agents",
            "prompts": "/api/v1/admin/prompts",
            "monitor": "/api/v1/admin/monitor",
        },
    }


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
