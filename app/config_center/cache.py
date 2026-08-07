"""配置缓存

设计文档 §5.12 工程要点：配置读取走"缓存+失效"机制，
不能每次请求都查数据库；配置项变更后通过缓存失效让新配置立即生效，无需重启。

实现：
- 内存 namespace → {key: value} 缓存
- 写路径 invalidate(namespace) 立即清空该命名空间 → 下次读取重新载入（热生效）
- TTL 兜底（300s）：即使漏调 invalidate，缓存也会自动过期重新加载，防长期不一致
- 多实例扩展预留：invalidate 可改为 Redis Pub/Sub 广播（本期单容器不用）
"""

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ConfigCache:
    """配置缓存（内存 + TTL + 版本失效）"""

    TTL_SECONDS = 300  # 兜底过期时间，防止缓存与库长期不一致

    def __init__(self, ttl_seconds: int = TTL_SECONDS):
        self._data: dict[str, dict[str, Any]] = {}      # namespace -> {key: value}
        self._loaded_at: dict[str, float] = {}          # namespace -> 载入时间
        self.ttl_seconds = ttl_seconds

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        """读取单个配置值（未命中或缓存过期返回 default）"""
        if not self.is_fresh(namespace):
            return default
        return self._data.get(namespace, {}).get(key, default)

    def get_namespace(self, namespace: str) -> dict:
        """读取整个命名空间（工具策略/限流列表等行集合类）"""
        if not self.is_fresh(namespace):
            return {}
        return dict(self._data.get(namespace, {}))

    def set_namespace(self, namespace: str, data: dict):
        """写入整个命名空间缓存（由 loader 调用）"""
        self._data[namespace] = data
        self._loaded_at[namespace] = time.time()

    def invalidate(self, namespace: str):
        """使某命名空间缓存失效（配置变更后调用，立即热生效）"""
        if namespace in self._data:
            del self._data[namespace]
        self._loaded_at.pop(namespace, None)
        logger.info(f"配置缓存失效: {namespace}")

    def invalidate_all(self):
        """全部缓存失效"""
        self._data.clear()
        self._loaded_at.clear()

    def is_fresh(self, namespace: str) -> bool:
        """缓存是否有有效数据（存在且未到 TTL）"""
        loaded_at = self._loaded_at.get(namespace)
        if loaded_at is None:
            return False
        return (time.time() - loaded_at) < self.ttl_seconds

    def get_version(self, namespace: str) -> Optional[int]:
        """预留：返回命名空间版本号（多实例广播时用）"""
        if namespace in self._loaded_at:
            return int(self._loaded_at[namespace])
        return None


# 全局实例
config_cache = ConfigCache()
