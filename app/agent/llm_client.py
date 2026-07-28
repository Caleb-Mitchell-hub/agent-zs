"""LLM 客户端封装

支持 DeepSeek（OpenAI 兼容接口）和 Anthropic Claude。
使用 httpx 直接调用，不依赖特定 SDK。
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

    async def chat(self, prompt: str) -> str:
        """发送对话请求，返回 LLM 响应文本"""
        if self.provider == "anthropic":
            return await self._call_anthropic(prompt)
        else:
            # DeepSeek / OpenAI 兼容接口
            return await self._call_openai_compatible(prompt)

    async def _call_openai_compatible(self, prompt: str) -> str:
        """调用 OpenAI 兼容接口（DeepSeek、OpenAI 等）"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=data,
            )

            if response.status_code != 200:
                raise Exception(f"LLM 调用失败: {response.status_code} - {response.text}")

            result = response.json()
            return result["choices"][0]["message"]["content"].strip()

    async def _call_anthropic(self, prompt: str) -> str:
        """调用 Anthropic Claude 接口"""
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        data = {
            "model": self.model,
            "max_tokens": self.max_tokens,
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


# 全局客户端实例
llm_client = LLMClient()
