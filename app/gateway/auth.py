"""Gateway 认证模块

JWT Token 签发与验证。
"""

import secrets
import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

# JWT 密钥模块级缓存，避免每次请求都查 Redis
_jwt_secret_cache: str | None = None


def _get_jwt_secret() -> str:
    """获取 JWT 签名密钥

    优先级：settings.jwt_secret_key → Redis 持久化密钥 → 自动生成
    """
    global _jwt_secret_cache
    if _jwt_secret_cache is not None:
        return _jwt_secret_cache

    if settings.jwt_secret_key:
        _jwt_secret_cache = settings.jwt_secret_key
        return _jwt_secret_cache

    # 尝试从 Redis 读取持久化密钥
    try:
        import redis as sync_redis
        r = sync_redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            decode_responses=True,
        )
        existing = r.get("agentzs:jwt_secret_key")
        if existing:
            _jwt_secret_cache = existing
            return _jwt_secret_cache
    except Exception as e:
        logger.warning(f"Redis 不可用，无法读取持久化 JWT 密钥: {e}")

    # 生成随机 64 字符密钥并持久化到 Redis
    new_key = secrets.token_hex(32)  # 64 hex characters
    try:
        import redis as sync_redis
        r = sync_redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            decode_responses=True,
        )
        r.set("agentzs:jwt_secret_key", new_key)
    except Exception as e:
        logger.warning(f"Redis 不可用，JWT 密钥未持久化（重启后失效）: {e}")

    logger.warning(
        "JWT_SECRET_KEY 未配置，已自动生成随机密钥。"
        "生产环境请在 .env 中显式配置 JWT_SECRET_KEY。"
    )
    _jwt_secret_cache = new_key
    return new_key


def create_access_token(user_info: dict) -> str:
    """签发 HMAC-SHA256 JWT Token

    Args:
        user_info: 用户信息 dict，包含 user_id/tenant_id/username/real_name/
                   is_super_admin/roles/warehouse_ids/region_ids/customer_ids/product_ids

    Returns:
        JWT token string
    """
    secret = _get_jwt_secret()
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)

    payload = {
        "user_id": user_info.get("user_id"),
        "tenant_id": user_info.get("tenant_id"),
        "username": user_info.get("username"),
        "real_name": user_info.get("real_name"),
        "is_super_admin": user_info.get("is_super_admin", False),
        "roles": user_info.get("roles", []),
        "permissions": user_info.get("permissions", []),
        "warehouse_ids": user_info.get("warehouse_ids", []),
        "region_ids": user_info.get("region_ids", []),
        "customer_ids": user_info.get("customer_ids", []),
        "product_ids": user_info.get("product_ids", []),
        "exp": expire,
    }

    return jwt.encode(payload, secret, algorithm="HS256")


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict:
    """验证 JWT Token（FastAPI 依赖）

    验证签名（必须），检查 exp 过期。非 JWT 格式直接 401。

    Returns:
        user_info dict，包含 user_id/tenant_id/username/real_name/
        is_super_admin/roles/warehouse_ids/region_ids/customer_ids/product_ids
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "缺少认证 token", "error_code": "UNAUTHORIZED"},
        )

    token = credentials.credentials

    try:
        secret = _get_jwt_secret()
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return dict(payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "Token 已过期", "error_code": "UNAUTHORIZED"},
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token 验证失败: {e}")
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "Token 无效", "error_code": "UNAUTHORIZED"},
        )


async def require_admin(
    user_info: dict = Depends(verify_token),
) -> dict:
    """管理员权限依赖（FastAPI 依赖）

    先调用 verify_token 验证 JWT，再检查 is_super_admin。
    非管理员返回 403。
    """
    if not user_info.get("is_super_admin"):
        raise HTTPException(
            status_code=403,
            detail={"status": "error", "message": "需要管理员权限", "error_code": "FORBIDDEN"},
        )
    return user_info


async def require_knowledge_admin(
    user_info: dict = Depends(verify_token),
) -> dict:
    """知识库管理权限依赖（FastAPI 依赖）

    先调用 verify_token 验证 JWT，再判断是否拥有知识库管理权限：
    - 超级管理员（is_super_admin）恒放行
    - 或 permissions 中包含 ERP 侧分配的 AI_KB（知识库管理）权限码
      （系统管理员 ROLE_ADMIN 已在 ERP 侧持有该权限码，自动放行）
    非上述两者返回 403。

    数据边界由 service 层按 user_info["tenant_id"] 强制过滤，
    此处只做「能否管理知识库」的权限码判定。
    """
    if user_info.get("is_super_admin"):
        return user_info

    permissions = user_info.get("permissions") or []
    if "AI_KB" in permissions:
        return user_info

    raise HTTPException(
        status_code=403,
        detail={"status": "error", "message": "需要知识库管理权限", "error_code": "FORBIDDEN"},
    )
