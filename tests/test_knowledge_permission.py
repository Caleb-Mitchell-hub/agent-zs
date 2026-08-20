"""知识库管理权限测试

验证 require_knowledge_admin 的权限码判定：非超管且无 AI_KB（知识库管理）权限码 → 403。
仅测试依赖层拒绝路径，不触达 service / 数据库。
"""

from app.gateway.auth import create_access_token


def _headers(**overrides):
    payload = {
        "user_id": 2, "tenant_id": 2, "username": "normal_user",
        "real_name": "普通用户", "is_super_admin": False,
        "roles": ["member"], "permissions": [], "warehouse_ids": [],
        "region_ids": [], "customer_ids": [], "product_ids": [],
    }
    payload.update(overrides)
    return {"Authorization": f"Bearer {create_access_token(payload)}"}


def test_no_permission_forbidden(client):
    """非超管 + 无 AI_KB 权限 → 403"""
    res = client.get("/api/v1/knowledge/bases", headers=_headers())
    assert res.status_code == 403
