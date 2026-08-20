"""FAQ 热点缓存模块

基于 Redis 的知识库 FAQ 热点缓存：
- 热点 FAQ 缓存（带版本号与 TTL）
- 月度命中统计（ZSET）
- FAQ / 知识库缓存失效

设计约束：Redis 仅作为缓存层，绝不成为主链路强依赖。
所有 Redis 命令均在 try/except 中降级，Redis 不可用或超时时
返回安全默认值（None / 0 / {} / False），记录 warning 日志，绝不抛异常。
"""

import hashlib
import json
import logging
from datetime import datetime

from app.config import settings
from app.memory.session_memory import _get_redis

logger = logging.getLogger(__name__)

# 每秒天数换算常量
_SECONDS_PER_DAY = 24 * 3600


def question_hash(normalized_question: str) -> str:
    """基于归一化问题的 sha256 hex 哈希（稳定 key）"""
    return hashlib.sha256(normalized_question.encode("utf-8")).hexdigest()


def current_month() -> str:
    """返回当前月份字符串 yyyyMM"""
    return datetime.now().strftime("%Y%m")


def _hot_faq_key(tenant_id: int, kb_id: int, version: int, qhash: str) -> str:
    """构造热点 FAQ 缓存 key"""
    return f"faq:hot:{tenant_id}:{kb_id}:{version}:{qhash}"


def _faq_keys_key(tenant_id: int, kb_id: int, faq_id) -> str:
    """构造某 FAQ 的所有热点缓存 key 的 SET key"""
    return f"faq:keys:{tenant_id}:{kb_id}:{faq_id}"


def _hits_key(tenant_id: int, kb_id: int, month: str) -> str:
    """构造月度命中统计 ZSET key"""
    return f"faq:hits:{tenant_id}:{kb_id}:{month}"


def _retention_seconds() -> int:
    """命中统计保留时长（秒），约 retention 月数 * 31 天"""
    return settings.knowledge_faq_hit_retention_months * 31 * _SECONDS_PER_DAY


async def get_kb_version(tenant_id: int, kb_id: int) -> int:
    """读取知识库缓存版本号；Redis 不可用或未设置时返回 0"""
    try:
        r = _get_redis()
        raw = await r.get(f"kb:version:{tenant_id}:{kb_id}")
        if raw is None:
            return 0
        return int(raw)
    except Exception as e:
        logger.warning("读取知识库缓存版本号失败（tenant=%s kb=%s）: %s", tenant_id, kb_id, e)
        return 0


async def increment_kb_version(tenant_id: int, kb_id: int) -> int:
    """知识库缓存版本号 +1，返回新版本号；Redis 不可用返回 0"""
    try:
        r = _get_redis()
        new_version = await r.incr(f"kb:version:{tenant_id}:{kb_id}")
        return int(new_version)
    except Exception as e:
        logger.warning("递增知识库缓存版本号失败（tenant=%s kb=%s）: %s", tenant_id, kb_id, e)
        return 0


async def get_hot_faq(tenant_id: int, kb_id: int, version: int, qhash: str) -> dict | None:
    """读取热点 FAQ 缓存；未命中或 Redis 不可用返回 None。

    命中后不在此处计数（计数由调用方 record_hit 完成）。
    """
    if not settings.knowledge_faq_cache_enabled:
        return None
    try:
        r = _get_redis()
        raw = await r.get(_hot_faq_key(tenant_id, kb_id, version, qhash))
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning("读取热点 FAQ 缓存失败（tenant=%s kb=%s version=%s）: %s", tenant_id, kb_id, version, e)
        return None


async def set_hot_faq(tenant_id: int, kb_id: int, version: int, faq: dict, qhash: str) -> None:
    """写入热点 FAQ 缓存（带 TTL）。

    faq 需含 id/question/answer/category/updated_at；Value 序列化为 JSON 字符串，
    额外写入 kb_version 字段。同时把该缓存 key 加入 faq:keys SET，
    SET 自身也设 TTL（约 retention 天数）。
    """
    if not settings.knowledge_faq_cache_enabled:
        return
    try:
        r = _get_redis()
        faq_id = faq.get("id")
        payload = dict(faq)
        payload["kb_version"] = version
        value = json.dumps(payload, ensure_ascii=False)

        hot_key = _hot_faq_key(tenant_id, kb_id, version, qhash)
        ttl_seconds = settings.knowledge_faq_cache_ttl_days * _SECONDS_PER_DAY
        await r.setex(hot_key, ttl_seconds, value)

        keys_key = _faq_keys_key(tenant_id, kb_id, faq_id)
        await r.sadd(keys_key, hot_key)
        await r.expire(keys_key, _retention_seconds())
    except Exception as e:
        logger.warning("写入热点 FAQ 缓存失败（tenant=%s kb=%s version=%s）: %s", tenant_id, kb_id, version, e)


async def record_hit(tenant_id: int, kb_id: int, faq_id: int) -> None:
    """ZINCRBY 当月 faq:hits 计数 +1；ZSET 设 TTL。Redis 不可用静默忽略。"""
    if not settings.knowledge_faq_cache_enabled:
        return
    try:
        r = _get_redis()
        key = _hits_key(tenant_id, kb_id, current_month())
        await r.zincrby(key, 1, str(faq_id))
        await r.expire(key, _retention_seconds())
    except Exception as e:
        logger.warning("记录 FAQ 命中次数失败（tenant=%s kb=%s faq=%s）: %s", tenant_id, kb_id, faq_id, e)


async def get_monthly_hit(tenant_id: int, kb_id: int, faq_id: int, month: str | None = None) -> int:
    """读取某 FAQ 当月命中次数（ZSCORE）；未命中/Redis 不可用返回 0"""
    try:
        r = _get_redis()
        if month is None:
            month = current_month()
        score = await r.zscore(_hits_key(tenant_id, kb_id, month), str(faq_id))
        if score is None:
            return 0
        return int(float(score))
    except Exception as e:
        logger.warning("读取 FAQ 月度命中次数失败（tenant=%s kb=%s faq=%s）: %s", tenant_id, kb_id, faq_id, e)
        return 0


async def get_monthly_hits(tenant_id: int, kb_id: int, month: str | None = None) -> dict[int, int]:
    """读取当月全部命中统计 ZRANGE WITHSCORES，返回 {faq_id(int): count(int)}；Redis 不可用返回 {}"""
    try:
        r = _get_redis()
        if month is None:
            month = current_month()
        items = await r.zrange(_hits_key(tenant_id, kb_id, month), 0, -1, withscores=True)
        result: dict[int, int] = {}
        for member, score in items:
            result[int(member)] = int(float(score))
        return result
    except Exception as e:
        logger.warning("读取 FAQ 月度命中统计失败（tenant=%s kb=%s）: %s", tenant_id, kb_id, e)
        return {}


async def invalidate_faq(tenant_id: int, kb_id: int, faq_id: int) -> None:
    """使某 FAQ 的热点缓存失效：读 faq:keys SET 得到所有缓存 key，逐个 DEL，再 DEL 该 SET"""
    if not settings.knowledge_faq_cache_enabled:
        return
    try:
        r = _get_redis()
        keys_key = _faq_keys_key(tenant_id, kb_id, faq_id)
        keys = await r.smembers(keys_key)
        if keys:
            await r.delete(*keys)
        await r.delete(keys_key)
    except Exception as e:
        logger.warning("失效 FAQ 热点缓存失败（tenant=%s kb=%s faq=%s）: %s", tenant_id, kb_id, faq_id, e)


async def invalidate_kb(tenant_id: int, kb_id: int) -> None:
    """整库缓存失效：increment_kb_version（版本号 +1 使旧版本 key 逻辑失效）"""
    if not settings.knowledge_faq_cache_enabled:
        return
    await increment_kb_version(tenant_id, kb_id)
