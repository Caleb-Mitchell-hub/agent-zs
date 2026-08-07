"""LLM 客户端封装

支持 DeepSeek（OpenAI 兼容接口）和 Anthropic Claude。
使用 httpx 直接调用，不依赖特定 SDK。

配置中心接线：refresh_from_config() 从 app_config 表热加载 LLM 连接，
覆盖优先级：显式实参 > 配置中心缓存 > settings 默认。
"""

import httpx
from app.config import settings


class LLMClient:
    """统一 LLM 客户端"""

    def __init__(self):
        self.provider = settings.llm_provider
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.base_url = settings.llm_base_url
        self.max_tokens = settings.llm_max_tokens
        self.temperature = settings.llm_temperature

    def _load_from_settings(self):
        """从 settings（env）加载默认连接参数"""
        self.provider = settings.llm_provider
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.base_url = settings.llm_base_url
        self.max_tokens = settings.llm_max_tokens
        self.temperature = settings.llm_temperature

    def refresh_from_config(self):
        """从配置中心热加载 LLM 连接（改 LLM 配置即生效，无需重启）"""
        try:
            from app.config_center.service import config_service
            import asyncio

            # 配置中心 get_llm_config 是 async，此处用事件循环同步取
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # 已有运行中的事件循环（FastAPI 内），用 create_task 异步刷新
                import threading
                import asyncio as _asyncio
                _asyncio.ensure_future(self._refresh_from_config_async())
            else:
                asyncio.run(self._refresh_from_config_async())
        except Exception as e:
            logger_warning(f"从配置中心刷新 LLM 配置失败，保持 settings 默认: {e}")

    async def _refresh_from_config_async(self):
        """异步从配置中心刷新 LLM 连接"""
        try:
            from app.config_center.service import config_service
            config = await config_service.get_llm_config()
            if config:
                if config.get("provider"):
                    self.provider = config["provider"]
                if config.get("api_key"):
                    self.api_key = config["api_key"]
                if config.get("model"):
                    self.model = config["model"]
                if config.get("base_url"):
                    self.base_url = config["base_url"]
                if config.get("max_tokens"):
                    self.max_tokens = int(config["max_tokens"])
                if config.get("temperature") is not None:
                    self.temperature = float(config["temperature"])
                logger_info(f"LLM 配置已从配置中心热加载: provider={self.provider}, model={self.model}")
        except Exception as e:
            logger_warning(f"从配置中心刷新 LLM 配置失败: {e}")

    async def chat(
        self,
        prompt: str,
        *,
        model: str = None,
        temperature: float = None,
        base_url: str = None,
        provider: str = None,
        api_key: str = None,
        max_tokens: int = None,
    ) -> str:
        """发送对话请求，返回 LLM 响应文本

        覆盖优先级：显式实参 > 配置中心缓存/实例属性 > settings 默认
        """
        use_provider = provider or self.provider
        use_model = model or self.model
        use_temperature = temperature if temperature is not None else self.temperature
        use_api_key = api_key or self.api_key
        use_base_url = base_url or self.base_url
        use_max_tokens = max_tokens or self.max_tokens

        if use_provider == "anthropic":
            return await self._call_anthropic(prompt, use_model, use_max_tokens, use_api_key)
        else:
            # DeepSeek / OpenAI 兼容接口
            return await self._call_openai_compatible(
                prompt, use_model, use_temperature, use_max_tokens, use_api_key, use_base_url
            )

    async def _call_openai_compatible(
        self, prompt: str, model: str, temperature: float,
        max_tokens: int, api_key: str, base_url: str,
    ) -> str:
        """调用 OpenAI 兼容接口（DeepSeek、OpenAI 等）"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{base_url}/v1/chat/completions",
                headers=headers,
                json=data,
            )

            if response.status_code != 200:
                raise Exception(f"LLM 调用失败: {response.status_code} - {response.text}")

            result = response.json()
            return result["choices"][0]["message"]["content"].strip()

    async def _call_anthropic(self, prompt: str, model: str, max_tokens: int, api_key: str) -> str:
        """调用 Anthropic Claude 接口"""
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        data = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=data,
            )

            if response.status_code != 200:
                raise Exception(f"LLM 调用失败: {response.status_code} - {response.text}")

            result = response.json()
            return result["content"][0]["text"].strip()


# 简易日志（避免依赖循环，用模块级函数包装）
import logging
_logger = logging.getLogger(__name__)
logger_warning = _logger.warning
logger_info = _logger.info


# 全局客户端实例
llm_client = LLMClient()
