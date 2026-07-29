"""Model Gateway - 模型网关

职责：
- 多模型路由
- 限流降级
- 调用日志
"""

import logging
import time
from typing import Optional

from sqlalchemy import text

from app.db.session import get_session
from app.agent.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ModelGateway:
    """模型网关"""

    def __init__(self):
        self.llm_client = LLMClient()
        self._rate_limiter = {}  # 简单的内存限流

    async def route_and_call(
        self,
        task_type: str,
        prompt: str,
        user_id: str = None,
        tenant_id: str = None,
    ) -> dict:
        """路由并调用模型

        Args:
            task_type: 任务类型（intent_classify/sql_gen等）
            prompt: 提示词
            user_id: 用户ID
            tenant_id: 租户ID

        Returns:
            dict: 调用结果
        """
        # 1. 获取路由配置
        config = await self._get_routing_config(task_type)

        # 2. 选择模型
        model = config.get("primary_model", "deepseek-chat")

        # 3. 调用模型
        start_time = time.time()
        try:
            response = await self.llm_client.chat(prompt)
            latency_ms = int((time.time() - start_time) * 1000)

            # 4. 记录调用日志
            await self._log_model_call(
                model_used=model,
                latency_ms=latency_ms,
                token_in=len(prompt),
                token_out=len(response),
                success=True,
            )

            return {"status": "ok", "response": response, "model": model}

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)

            # 记录失败日志
            await self._log_model_call(
                model_used=model,
                latency_ms=latency_ms,
                token_in=len(prompt),
                token_out=0,
                success=False,
            )

            # 尝试备用模型
            fallback_models = config.get("fallback_models", [])
            for fallback in fallback_models:
                try:
                    response = await self.llm_client.chat(prompt)
                    return {"status": "ok", "response": response, "model": fallback}
                except:
                    continue

            return {"status": "error", "message": str(e)}

    async def _get_routing_config(self, task_type: str) -> dict:
        """获取路由配置"""
        try:
            async for session in get_session():
                result = await session.execute(
                    text("SELECT * FROM model_routing_config WHERE task_type = :task_type"),
                    {"task_type": task_type},
                )
                row = result.mappings().first()
                if row:
                    return dict(row)
        except:
            pass

        # 默认配置
        return {
            "primary_model": "deepseek-chat",
            "fallback_models": [],
        }

    async def _log_model_call(
        self,
        model_used: str,
        latency_ms: int,
        token_in: int,
        token_out: int,
        success: bool,
    ):
        """记录模型调用日志"""
        try:
            async for session in get_session():
                await session.execute(
                    text("""
                        INSERT INTO model_call_logs (model_used, latency_ms, token_in, token_out, success)
                        VALUES (:model_used, :latency_ms, :token_in, :token_out, :success)
                    """),
                    {
                        "model_used": model_used,
                        "latency_ms": latency_ms,
                        "token_in": token_in,
                        "token_out": token_out,
                        "success": success,
                    },
                )
                await session.commit()
        except Exception as e:
            logger.warning(f"记录模型调用日志失败: {e}")


# 全局实例
model_gateway = ModelGateway()
