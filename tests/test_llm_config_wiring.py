"""LLM 客户端配置接线测试"""

import pytest

from app.agent.llm_client import LLMClient


class FakeConfigService:
    """模拟配置中心 service"""

    def __init__(self, config):
        self._config = config

    async def get_llm_config(self):
        return self._config


@pytest.fixture
def llm_client():
    c = LLMClient()
    # 用默认 settings
    c._load_from_settings()
    return c


class TestRefreshFromConfig:
    @pytest.mark.asyncio
    async def test_refresh_from_config_async(self, llm_client, monkeypatch):
        """测试从配置中心刷新 LLM 连接"""
        fake = FakeConfigService({
            "provider": "deepseek",
            "base_url": "https://custom.deepseek.com",
            "model": "deepseek-custom",
            "api_key": "sk-custom-key",
            "max_tokens": 8192,
            "temperature": 0.5,
        })
        import app.config_center.service as svc
        monkeypatch.setattr(svc, "config_service", fake)
        await llm_client._refresh_from_config_async()
        assert llm_client.model == "deepseek-custom"
        assert llm_client.api_key == "sk-custom-key"
        assert llm_client.base_url == "https://custom.deepseek.com"
        assert llm_client.max_tokens == 8192
        assert llm_client.temperature == 0.5


class TestChatOverride:
    @pytest.mark.asyncio
    async def test_chat_with_override_uses_explicit_params(self, llm_client, monkeypatch):
        """测试显式实参覆盖默认配置"""
        called_with = {}

        async def fake_call(prompt, model, temperature, max_tokens, api_key, base_url):
            called_with.update(prompt=prompt, model=model, temperature=temperature,
                               max_tokens=max_tokens, api_key=api_key, base_url=base_url)
            return "ok"

        monkeypatch.setattr(llm_client, "_call_openai_compatible", fake_call)
        await llm_client.chat("hello", model="override-model", temperature=0.9,
                              base_url="https://override.com", api_key="override-key")
        assert called_with["model"] == "override-model"
        assert called_with["temperature"] == 0.9
        assert called_with["base_url"] == "https://override.com"
        assert called_with["api_key"] == "override-key"

    @pytest.mark.asyncio
    async def test_chat_without_override_uses_instance_defaults(self, llm_client, monkeypatch):
        """测试无显式实参时用实例属性"""
        called_with = {}

        async def fake_call(prompt, model, temperature, max_tokens, api_key, base_url):
            called_with.update(model=model, temperature=temperature)
            return "ok"

        monkeypatch.setattr(llm_client, "_call_openai_compatible", fake_call)
        await llm_client.chat("hello")
        assert called_with["model"] == llm_client.model
        assert called_with["temperature"] == llm_client.temperature
