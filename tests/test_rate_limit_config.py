"""限流配置接线测试"""

import pytest

from app.gateway.rate_limit import RateLimiter


class FakeConfigService:
    """模拟配置中心 service"""

    def __init__(self, default_cfg=None, limits=None):
        self._default = default_cfg
        self._limits = limits or []

    async def get_config(self, key, default=None):
        return self._default if self._default is not None else default

    async def list_rate_limits(self):
        return self._limits


class TestRateLimitConfig:
    @pytest.mark.asyncio
    async def test_load_from_config_updates_default(self, monkeypatch):
        """测试 default 档位从配置中心加载"""
        fake = FakeConfigService(default_cfg={"max_requests": 200, "window_seconds": 30})
        import app.config_center.service as svc
        monkeypatch.setattr(svc, "config_service", fake)

        limiter = RateLimiter()
        await limiter.load_from_config()
        assert limiter.configs["default"]["max_requests"] == 200
        assert limiter.configs["default"]["window_seconds"] == 30

    @pytest.mark.asyncio
    async def test_load_from_config_applies_scope_overrides(self, monkeypatch):
        """测试 user/tenant 档位被 rate_limit_config 覆盖"""
        fake = FakeConfigService(default_cfg=None, limits=[
            {"scope_type": "user", "scope_id": "u1", "qps": 50, "enabled": True},
            {"scope_type": "tenant", "scope_id": "t1", "qps": 500, "enabled": True},
            {"scope_type": "user", "scope_id": "u2", "qps": 999, "enabled": False},  # 禁用不生效
        ])
        import app.config_center.service as svc
        monkeypatch.setattr(svc, "config_service", fake)

        limiter = RateLimiter()
        await limiter.load_from_config()
        assert limiter.configs["user"]["max_requests"] == 50
        assert limiter.configs["tenant"]["max_requests"] == 500
        assert limiter.configs["default"]["max_requests"] == 60  # 无 default 配置保持默认

    @pytest.mark.asyncio
    async def test_load_from_config_failure_keeps_defaults(self, monkeypatch):
        """测试加载失败保持默认档位"""
        class BrokenService:
            async def get_config(self, key, default=None):
                raise Exception("db down")

            async def list_rate_limits(self):
                raise Exception("db down")

        import app.config_center.service as svc
        monkeypatch.setattr(svc, "config_service", BrokenService())

        limiter = RateLimiter()
        await limiter.load_from_config()
        assert limiter.configs["default"]["max_requests"] == 60
        assert limiter.configs["user"]["max_requests"] == 120

    def test_is_allowed_normal(self):
        """测试限流基本功能"""
        limiter = RateLimiter()
        allowed, remaining = limiter.is_allowed("test-key", "default")
        assert allowed is True
        assert remaining >= 0
