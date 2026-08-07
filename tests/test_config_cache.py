"""配置缓存测试"""

import time

from app.config_center.cache import ConfigCache


class TestConfigCache:
    def test_miss_returns_default(self):
        cache = ConfigCache()
        assert cache.get("llm", "api_key", "default") == "default"

    def test_set_and_get_namespace(self):
        cache = ConfigCache()
        cache.set_namespace("llm", {"model": "deepseek-chat"})
        assert cache.get("llm", "model") == "deepseek-chat"

    def test_invalidate_clears(self):
        cache = ConfigCache()
        cache.set_namespace("llm", {"model": "a"})
        assert cache.is_fresh("llm")
        cache.invalidate("llm")
        assert not cache.is_fresh("llm")
        assert cache.get("llm", "model") is None

    def test_invalidate_all(self):
        cache = ConfigCache()
        cache.set_namespace("a", {"x": 1})
        cache.set_namespace("b", {"y": 2})
        cache.invalidate_all()
        assert not cache.is_fresh("a")
        assert not cache.is_fresh("b")

    def test_ttl_expiry(self):
        cache = ConfigCache(ttl_seconds=1)
        cache.set_namespace("llm", {"model": "a"})
        assert cache.is_fresh("llm")
        time.sleep(1.1)
        assert not cache.is_fresh("llm")

    def test_get_namespace_returns_copy(self):
        cache = ConfigCache()
        cache.set_namespace("a", {"x": 1})
        ns = cache.get_namespace("a")
        ns["x"] = 99  # 修改副本不影响缓存
        assert cache.get("a", "x") == 1
