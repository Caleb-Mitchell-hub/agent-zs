"""配置加密工具

使用 Fernet 对称加密保护敏感配置字段（API Key、数据源密码等）。
密钥来源：settings.ai_config_secret（env AI_CONFIG_SECRET）。
若未配置密钥，生成后持久化到 Redis，保证重启一致。

设计文档 §5.12：敏感字段（apiKey、password 等）加密存储，日志/响应从不出现明文。
"""

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# 字段名含这些关键词即视为敏感
SENSITIVE_KEYWORDS = ("key", "token", "secret", "password", "pwd", "credential", "api_key", "apiKey")


class ConfigCrypto:
    """配置加解密工具"""

    def __init__(self, secret: Optional[str] = None):
        self._secret = secret
        self._fernet: Optional[Fernet] = None

    @property
    def secret(self) -> str:
        """获取加密密钥（未显式传入时取 settings）"""
        if self._secret:
            return self._secret
        try:
            from app.config import settings
            if settings.ai_config_secret:
                self._secret = settings.ai_config_secret
        except Exception as e:
            logger.warning(f"读取 AI_CONFIG_SECRET 失败: {e}")
        return self._secret or ""

    @property
    def fernet(self) -> Fernet:
        """惰性创建 Fernet 实例

        secret 为空时自动生成并持久化到 Redis，保证多实例/重启一致。
        """
        if self._fernet is not None:
            return self._fernet

        key = self.secret
        if not key:
            key = self._ensure_key()
            self._secret = key

        try:
            self._fernet = Fernet(self._normalize_key(key))
        except Exception as e:
            logger.error(f"AI_CONFIG_SECRET 无效，Fernet 初始化失败: {e}")
            raise ValueError(
                "AI_CONFIG_SECRET 无效：必须是 urlsafe-base64 编码的 32 字节密钥。"
                "可用 `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'` 生成。"
            ) from e

        return self._fernet

    def _normalize_key(self, key: str) -> bytes:
        """将密钥归一化为 Fernet 需要的 32 字节 urlsafe-base64

        兼容两种输入：
        1. 直接是 Fernet 生成的 urlsafe-base64（44字符）
        2. 任意字符串，自动派生（SHA-256 → urlsafe-base64）
        """
        key_bytes = key.encode("utf-8")
        # 已经是标准 Fernet key 格式则直接用
        try:
            decoded = base64.urlsafe_b64decode(key_bytes + b"=" * (-len(key_bytes) % 4))
            if len(decoded) == 32:
                return key_bytes if key_bytes.endswith(b"=") else key_bytes
        except Exception:
            pass
        # 派生：SHA-256 哈希后 urlsafe-base64
        digest = hashlib.sha256(key_bytes).digest()
        return base64.urlsafe_b64encode(digest)

    def _ensure_key(self) -> str:
        """生成并持久化密钥到 Redis（未配置 AI_CONFIG_SECRET 时的兜底）"""
        from cryptography.fernet import Fernet as _Fernet
        key = _Fernet.generate_key().decode()

        try:
            import redis as sync_redis
            from app.config import settings

            r = sync_redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password,
                decode_responses=True,
            )
            existing = r.get("agentzs:ai_config_secret")
            if existing:
                key = existing
            else:
                r.set("agentzs:ai_config_secret", key)
        except Exception as e:
            logger.warning(f"生成 AI_CONFIG_SECRET 并写入 Redis 失败（将使用内存临时密钥）: {e}")

        logger.warning("AI_CONFIG_SECRET 未配置，已自动生成。生产环境请在 .env 中显式配置。")
        return key

    def encrypt(self, plaintext: str) -> str:
        """加密明文，返回 str token"""
        if plaintext is None or plaintext == "":
            return ""
        return self.fernet.encrypt(plaintext.encode("utf-8")).decode()

    def decrypt(self, token: str) -> str:
        """解密密文，失败返回空串（容忍旧数据/格式错误，不抛异常）"""
        if not token:
            return ""
        try:
            return self.fernet.decrypt(token.encode("utf-8")).decode()
        except (InvalidToken, Exception) as e:
            logger.warning(f"解密失败（可能密钥变更或数据损坏）: {type(e).__name__}")
            return ""

    def mask(self, plaintext: str, keep_head: int = 2, keep_tail: int = 2) -> str:
        """脱敏：保留前 keep_head 后 keep_tail，中间 ****"""
        if not plaintext:
            return ""
        if len(plaintext) <= keep_head + keep_tail:
            return "*" * len(plaintext)
        return plaintext[:keep_head] + "****" + plaintext[-keep_tail:]


def is_sensitive_field(field_name: str) -> bool:
    """判断字段名是否敏感（含 key/token/secret/password 等关键词）"""
    field_lower = field_name.lower()
    return any(kw in field_lower for kw in SENSITIVE_KEYWORDS)


# 全局实例
config_crypto = ConfigCrypto()
