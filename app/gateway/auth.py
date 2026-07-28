"""Gateway 认证模块

验证 ERP 签发的 JWT Token。
Gateway 不负责签发 token，只验证。
"""

import logging
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

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

    # TODO: 实际项目中应使用 JWT 解析和验证
    # 这里先做简单的 token 格式检查
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
    """解码 JWT Token

    实际项目中应使用 jwt 库验证签名和过期时间。
    这里先做简单实现。
    """
    # 简单实现：检查 token 格式
    if not token or len(token) < 10:
        raise ValueError("Token 格式无效")

    # TODO: 使用 jwt.decode() 验证
    # payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

    # 临时实现：返回模拟用户信息
    return {
        "user_id": 1,
        "tenant_id": 1,
        "roles": ["user"],
    }
