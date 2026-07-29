"""Gateway 认证模块

验证 ERP 签发的 JWT Token。
Gateway 不负责签发 token，只验证。
"""

import json
import hmac
import hashlib
import base64
import logging
from datetime import datetime
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict:
    """验证 JWT Token

    返回 token 中的用户信息：
    {
        "user_id": 123,
        "tenant_id": 1,
        "roles": ["admin"]
    }
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "缺少认证 token", "error_code": "UNAUTHORIZED"},
        )

    token = credentials.credentials

    try:
        user_info = _decode_token(token)
        return user_info
    except Exception as e:
        logger.warning(f"Token 验证失败: {e}")
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "Token 无效或已过期", "error_code": "UNAUTHORIZED"},
        )


def _decode_token(token: str) -> dict:
    """解码 JWT Token（HS256）"""
    if not token or len(token) < 10:
        raise ValueError("Token 格式无效")

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Token 格式无效")

    try:
        # 解码 payload
        payload_b64 = parts[1]
        # 补齐 padding
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes)

        # 检查过期时间
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp) < datetime.now():
            raise ValueError("Token 已过期")

        # 验证签名
        secret = settings.jwt_secret_key or settings.llm_api_key
        if secret:
            signing_input = f"{parts[0]}.{parts[1]}"
            expected_sig = hmac.new(
                secret.encode(),
                signing_input.encode(),
                hashlib.sha256
            ).digest()
            expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode()

            if parts[2] != expected_sig_b64:
                raise ValueError("签名验证失败")

        return {
            "user_id": payload.get("user_id", 1),
            "tenant_id": payload.get("tenant_id", 1),
            "roles": payload.get("roles", ["user"]),
        }

    except json.JSONDecodeError:
        raise ValueError("Token 格式无效")
    except Exception as e:
        if "已过期" in str(e) or "签名" in str(e):
            raise
        raise ValueError("Token 解析失败")
