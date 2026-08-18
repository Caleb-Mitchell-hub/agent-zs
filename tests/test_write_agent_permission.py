"""Write Agent 权限码校验测试（doc_type → ADD 权限码）

验证创建单据的权限由后端 ERP 返回的权限码驱动：拥有对应 _ADD 权限码才能创建，
超级管理员恒放行。不连数据库，mock LLM 与 ERP Adapter。
"""

import pytest
from unittest.mock import AsyncMock

from app.agents import write_agent as write_agent_mod


SALES_ORDER_DOC = (
    '{"doc_type": "sales_order", "params": {'
    '"customer_name": "张三", "warehouse_name": "北京仓", "order_date": "2026-08-18"}}'
)

PURCHASE_ORDER_DOC = (
    '{"doc_type": "purchase_order", "params": {'
    '"supplier_name": "供应商A", "warehouse_name": "北京仓", "order_date": "2026-08-18"}}'
)


@pytest.mark.asyncio
async def test_create_denied_without_add_permission(monkeypatch):
    """用户缺少 SALES_ORDER_ADD 权限码 → 创建销售订单被拒绝（不调 ERP）"""
    monkeypatch.setattr(write_agent_mod.llm_client, "chat", AsyncMock(return_value=SALES_ORDER_DOC))

    erp_called = []
    async def fake_create_document(**kwargs):
        erp_called.append(True)
        return {"status": "ok", "doc_no": "SO001"}
    monkeypatch.setattr(write_agent_mod.erp_adapter, "create_document", AsyncMock(side_effect=fake_create_document))

    agent = write_agent_mod.WriteAgent()
    result = await agent.execute(
        "创建销售订单", [], {}, "sess", 1, 1,
        {"is_super_admin": False, "perm_codes": ["INVENTORY_VIEW"]},
    )

    assert result["status"] == "denied"
    assert result["error_code"] == "PERMISSION_DENIED"
    assert "SALES_ORDER_ADD" in result["message"]
    assert erp_called == []


@pytest.mark.asyncio
async def test_create_allowed_with_add_permission(monkeypatch):
    """用户拥有 SALES_ORDER_ADD 权限码 → 进入 ERP 创建流程"""
    monkeypatch.setattr(write_agent_mod.llm_client, "chat", AsyncMock(return_value=SALES_ORDER_DOC))

    async def fake_create_document(**kwargs):
        return {"status": "ok", "doc_no": "SO001"}
    monkeypatch.setattr(write_agent_mod.erp_adapter, "create_document", AsyncMock(side_effect=fake_create_document))

    agent = write_agent_mod.WriteAgent()
    result = await agent.execute(
        "创建销售订单", [], {}, "sess", 1, 1,
        {"is_super_admin": False, "perm_codes": ["SALES_ORDER_ADD"]},
    )

    assert result["status"] == "ok"
    assert result["doc_no"] == "SO001"


@pytest.mark.asyncio
async def test_create_super_admin_allowed(monkeypatch):
    """超级管理员无需权限码即可创建（perm_codes 为 None）"""
    monkeypatch.setattr(write_agent_mod.llm_client, "chat", AsyncMock(return_value=PURCHASE_ORDER_DOC))

    async def fake_create_document(**kwargs):
        return {"status": "ok", "doc_no": "PO001"}
    monkeypatch.setattr(write_agent_mod.erp_adapter, "create_document", AsyncMock(side_effect=fake_create_document))

    agent = write_agent_mod.WriteAgent()
    result = await agent.execute(
        "创建采购订单", [], {}, "sess", 1, 1,
        {"is_super_admin": True, "perm_codes": None},
    )

    assert result["status"] == "ok"
    assert result["doc_no"] == "PO001"
