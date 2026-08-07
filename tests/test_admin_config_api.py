"""配置中心 API 测试

通过 monkeypatch 隔离 DB 依赖，验证端点行为与二次确认流程。
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class FakeConfigService:
    """内存版配置服务（模拟 service 层，避免连 DB）"""

    def __init__(self):
        self.llm = {"provider": "deepseek", "base_url": "https://api.deepseek.com",
                    "api_key": "sk-abc", "model": "deepseek-chat",
                    "max_tokens": 4096, "temperature": 0.1}
        self.routes = {}
        self.tools = {}
        self.datasources = []
        self.rate_limits = []
        self.retention = {"task_days": 90, "session_days": 180, "memory_days": 365, "audit_days": 365}
        self.change_requests = []
        self._next_id = 1
        self.audit_calls = []

    async def get_llm_config_masked(self):
        c = dict(self.llm)
        if c.get("api_key"):
            c["api_key"] = "sk****bc"
        return c

    async def save_llm_config(self, data, updated_by="system_admin"):
        self.llm = data
        return {"status": "ok"}

    async def list_model_routes(self):
        return list(self.routes.values())

    async def save_model_route(self, task_type, data, updated_by="system_admin"):
        self.routes[task_type] = {"task_type": task_type, **data}
        return {"status": "ok"}

    async def delete_model_route(self, task_type):
        self.routes.pop(task_type, None)
        return {"status": "ok"}

    def known_task_types(self):
        return ["query", "report", "knowledge"]

    async def list_knowledge(self, keyword="", category=""):
        return []

    async def list_tool_policies(self):
        return {"tools": [{"name": "query_tool", "description": "查询", "permission_level": "medium",
                           "risk_level": "medium", "need_confirm": False, "timeout": 30,
                           "retry_count": 3, "enabled": True}]}

    async def save_tool_policy(self, tool_name, data, updated_by="system_admin"):
        if data.get("risk_level") == "low":
            return {"status": "waiting_confirm", "message": "需要确认", "change_request_id": 1}
        return {"status": "ok"}

    async def _get_tool_policy_rows(self):
        return {}

    async def list_datasources(self):
        return self.datasources

    async def save_datasource(self, data, updated_by="system_admin"):
        ds = {"id": self._next_id, "name": data["name"], "host": data["host"],
              "port": data["port"], "db_name": data.get("db_name", ""), "enabled": 0,
              "password_masked": "****"}
        self.datasources.append(ds)
        self._next_id += 1
        return {"status": "waiting_confirm", "change_request_id": self._next_id,
                "datasource_id": ds["id"]}

    async def list_change_requests(self, status="pending"):
        return self.change_requests

    async def confirm_change_request(self, request_id, confirmed_by="system_admin"):
        return {"status": "ok", "message": "已生效", "change_request_id": request_id}

    async def cancel_change_request(self, request_id):
        return {"status": "ok"}

    async def list_rate_limits(self):
        return self.rate_limits

    async def save_rate_limit(self, scope_type, scope_id, data, updated_by="system_admin"):
        self.rate_limits.append({"scope_type": scope_type, "scope_id": scope_id, **data})
        return {"status": "ok"}

    async def delete_rate_limit(self, scope_type, scope_id):
        return {"status": "ok"}

    async def get_retention(self):
        return self.retention

    async def save_retention(self, data, updated_by="system_admin"):
        self.retention = data
        return {"status": "ok"}

    async def retention_dry_run(self):
        return {"retention": self.retention, "tables": {"task_history": {"will_delete": 5}}}

    async def audit(self, action, ctx, before, after, risk_level="low", result=None):
        self.audit_calls.append(action)


@pytest.fixture(autouse=True)
def mock_service(monkeypatch):
    from app.routers import admin_config
    fake = FakeConfigService()
    monkeypatch.setattr(admin_config, "config_service", fake)
    return fake


def test_get_llm_config(client):
    """测试读取 LLM 配置（api_key 脱敏）"""
    resp = client.get("/api/v1/admin/config/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["data"]["api_key"] == "sk****bc"  # 脱敏


def test_save_llm_config(client):
    """测试保存 LLM 配置"""
    resp = client.put("/api/v1/admin/config/llm", json={
        "provider": "deepseek", "base_url": "https://api.deepseek.com",
        "api_key": "sk-new-key", "model": "deepseek-chat",
        "max_tokens": 2048, "temperature": 0.2,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_model_routes_crud(client):
    """测试模型路由 CRUD"""
    # 新增
    resp = client.put("/api/v1/admin/config/model-routes/sql_gen", json={
        "primary_model": "deepseek-coder", "fallback_models": [], "enabled": True, "priority": 10,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # 列表
    resp = client.get("/api/v1/admin/config/model-routes")
    assert resp.json()["status"] == "ok"

    # 删除
    resp = client.delete("/api/v1/admin/config/model-routes/sql_gen")
    assert resp.json()["status"] == "ok"


def test_tool_policy_downgrade_requires_confirm(client, mock_service):
    """测试工具风险降级走二次确认"""
    resp = client.put("/api/v1/admin/config/tools/query_tool", json={
        "enabled": True, "risk_level": "low", "need_confirm": False, "timeout": 30, "retry_count": 3,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "waiting_confirm"
    assert data["change_request_id"] is not None


def test_datasource_requires_confirm(client, mock_service):
    """测试新建数据源走二次确认"""
    resp = client.post("/api/v1/admin/config/datasources", json={
        "name": "erp-replica", "type": "mysql_replica", "host": "172.177.3.43",
        "port": 3306, "db_name": "wms", "username": "wms", "password": "secret", "connect_timeout": 10,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "waiting_confirm"
    assert data["change_request_id"] is not None


def test_change_request_confirm(client, mock_service):
    """测试二次确认生效"""
    resp = client.post("/api/v1/admin/config/change-requests/1/confirm", json={"change_request_id": 1})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_rate_limit_crud(client, mock_service):
    """测试限流配额 CRUD"""
    resp = client.put("/api/v1/admin/config/rate-limits/user/user_001", json={
        "qps": 20, "concurrency": 10, "token_quota_monthly": 500000, "enabled": True,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    resp = client.get("/api/v1/admin/config/rate-limits")
    assert resp.status_code == 200


def test_retention_read_write(client, mock_service):
    """测试保留期读写"""
    resp = client.get("/api/v1/admin/config/retention")
    assert resp.status_code == 200
    assert resp.json()["data"]["task_days"] == 90

    resp = client.put("/api/v1/admin/config/retention", json={
        "task_days": 30, "session_days": 60, "memory_days": 90, "audit_days": 365,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_retention_dry_run(client, mock_service):
    """测试清理预览"""
    resp = client.post("/api/v1/admin/config/retention/dry-run")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert "tables" in resp.json()["data"]


def test_audit_trails_recorded(client, mock_service):
    """测试写操作触发审计"""
    client.put("/api/v1/admin/config/retention", json={
        "task_days": 30, "session_days": 60, "memory_days": 90, "audit_days": 365,
    })
    assert any("config.retention.update" in a for a in mock_service.audit_calls)


def test_config_page_loads(client):
    """测试配置页面加载"""
    resp = client.get("/api/v1/admin/config")
    assert resp.status_code == 200
    assert "配置管理与后台运营中心" in resp.text
