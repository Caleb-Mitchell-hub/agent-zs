"""认证端点 - 登录 / 当前用户 / 登出"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.gateway.auth import verify_token, create_access_token
from app.security.auth_service import auth_service

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(body: LoginRequest):
    """用户登录

    body: {username, password}
    成功返回 JWT token + 用户信息，失败返回 401。
    """
    try:
        user = await auth_service.authenticate(body.username, body.password)
    except Exception as e:
        logger.error(f"登录异常 — username={body.username}, error={e}", exc_info=True)
        return _401(f"认证服务异常: {e}")
    if not user:
        return _401("用户名或密码错误")

    # 加载权限和角色
    user_id = user["user_id"]
    permissions = await auth_service.get_user_permissions(user_id)
    roles = await auth_service.get_user_roles(user_id)
    perm_codes = await auth_service.get_user_permission_codes(user_id)

    # 组装完整用户信息（perm_codes 为 None 表示 super_admin 无限制）
    user_info = {
        **user,
        "roles": roles,
        "permissions": perm_codes,
        "warehouse_ids": permissions.get("warehouse_ids", []),
        "region_ids": permissions.get("region_ids", []),
        "customer_ids": permissions.get("customer_ids", []),
        "product_ids": permissions.get("product_ids", []),
    }

    # 签发 JWT
    token = create_access_token(user_info)

    return {
        "status": "ok",
        "token": token,
        "user": {
            "user_id": user_info["user_id"],
            "tenant_id": user_info["tenant_id"],
            "username": user_info["username"],
            "real_name": user_info["real_name"],
            "is_super_admin": user_info["is_super_admin"],
            "roles": user_info["roles"],
            "perm_codes": user_info["permissions"],
            "permissions": {
                "warehouse_ids": user_info["warehouse_ids"],
                "region_ids": user_info["region_ids"],
                "customer_ids": user_info["customer_ids"],
                "product_ids": user_info["product_ids"],
            },
        },
    }


@router.get("/auth/me")
async def me(user_info: dict = Depends(verify_token)):
    """获取当前用户信息（从 JWT 解析）"""
    return {
        "status": "ok",
        "user": {
            "user_id": user_info.get("user_id"),
            "tenant_id": user_info.get("tenant_id"),
            "username": user_info.get("username"),
            "real_name": user_info.get("real_name"),
            "is_super_admin": user_info.get("is_super_admin", False),
            "roles": user_info.get("roles", []),
            "perm_codes": user_info.get("permissions", []),
            "permissions": {
                "warehouse_ids": user_info.get("warehouse_ids", []),
                "region_ids": user_info.get("region_ids", []),
                "customer_ids": user_info.get("customer_ids", []),
                "product_ids": user_info.get("product_ids", []),
            },
        },
    }


@router.post("/auth/logout")
async def logout(user_info: dict = Depends(verify_token)):
    """登出（无状态 JWT，仅前端清除 token）"""
    return {"status": "ok", "message": "已退出"}


def _401(message: str):
    """返回 401 响应的辅助函数"""
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=401,
        content={"status": "error", "message": message, "error_code": "UNAUTHORIZED"},
    )
