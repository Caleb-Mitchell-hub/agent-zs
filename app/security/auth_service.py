"""认证服务

负责：
- 用户登录验证（密码校验）
- 用户权限加载（仓库/区域/客户/商品范围）
- 用户角色查询
"""

import logging
from passlib.hash import bcrypt
from app.db.session import execute_query

logger = logging.getLogger(__name__)


class AuthService:
    """认证与权限服务"""

    async def authenticate(self, username: str, password: str) -> dict | None:
        """验证用户名/密码，返回用户基本信息。

        密码验证顺序：bcrypt → 明文（兼容未迁移的历史数据）

        Returns:
            dict | None: 用户信息（不含密码），验证失败返回 None
        """
        rows = await execute_query(
            "SELECT id, tenant_id, username, password, real_name, dept_id, is_super_admin, status "
            "FROM sys_user WHERE username = :username AND deleted = 0",
            {"username": username},
        )
        if not rows:
            logger.info(f"登录失败：用户不存在 — {username}")
            return None

        user = rows[0]
        stored_password = user["password"] or ""

        # bcrypt 验证（passlib 会自动识别 $2a$/$2b$/$2y$ 前缀）
        try:
            if bcrypt.verify(password, stored_password):
                return self._build_user_info(user)
        except ValueError:
            pass  # 不是有效的 bcrypt hash，尝试明文

        # 明文 fallback（兼容未迁移的数据）
        if password == stored_password:
            logger.warning(f"用户 {username} 使用明文密码登录，建议尽快迁移为 bcrypt")
            return self._build_user_info(user)

        logger.info(f"登录失败：密码错误 — {username}")
        return None

    def _build_user_info(self, user: dict) -> dict:
        """从 DB 行构建用户信息"""
        return {
            "user_id": user["id"],
            "tenant_id": user.get("tenant_id") or 1,
            "username": user["username"],
            "real_name": user.get("real_name") or user["username"],
            "dept_id": user.get("dept_id"),
            "is_super_admin": bool(user.get("is_super_admin", 0)),
            "status": user.get("status"),
        }

    async def get_user_permissions(self, user_id: int) -> dict:
        """加载用户数据权限范围（仓库/区域/客户/商品）

        查询四张 sys_user_* 关联表，返回该用户被授权访问的 ID 列表。
        super_admin 返回空字典表示无限制。
        """
        # 仓库权限
        wh_rows = await execute_query(
            "SELECT warehouse_id FROM sys_user_warehouse WHERE user_id = :uid AND deleted = 0",
            {"uid": user_id},
        )
        warehouse_ids = [r["warehouse_id"] for r in wh_rows]

        # 区域权限
        reg_rows = await execute_query(
            "SELECT region_id FROM sys_user_region WHERE user_id = :uid AND deleted = 0",
            {"uid": user_id},
        )
        region_ids = [r["region_id"] for r in reg_rows]

        # 客户权限
        cust_rows = await execute_query(
            "SELECT customer_id FROM sys_user_customer WHERE user_id = :uid AND deleted = 0",
            {"uid": user_id},
        )
        customer_ids = [r["customer_id"] for r in cust_rows]

        # 商品权限
        prod_rows = await execute_query(
            "SELECT product_id FROM sys_user_product WHERE user_id = :uid AND deleted = 0",
            {"uid": user_id},
        )
        product_ids = [r["product_id"] for r in prod_rows]

        return {
            "warehouse_ids": warehouse_ids,
            "region_ids": region_ids,
            "customer_ids": customer_ids,
            "product_ids": product_ids,
        }

    async def get_user_roles(self, user_id: int) -> list[str]:
        """获取用户的角色代码列表"""
        rows = await execute_query(
            "SELECT r.role_code FROM sys_user_role ur "
            "JOIN sys_role r ON ur.role_id = r.id "
            "WHERE ur.user_id = :uid",
            {"uid": user_id},
        )
        return [r["role_code"] for r in rows]


# 全局实例
auth_service = AuthService()
