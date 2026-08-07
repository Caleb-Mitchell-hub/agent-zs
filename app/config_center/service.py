"""配置服务

职责（设计文档 §5.12）：
- 各命名空间配置的读写（app_config KV 表 + 各专用表）
- 配置缓存读路径（miss 时载入）+ 写路径失效
- 统一审计接线（config.<namespace>.<op>，Before/After 双快照）
- 二次确认流程（数据源/工具风险降级）
- 运行时接线（LLM 连接热生效、工具策略、限流档位）

命名空间：
- llm / retention / rate_limit.default  → app_config 表（单实体标量/JSON）
- model_route   → model_routing_config 表（多行集合）
- tool_policy   → tool_policy_config 表
- datasource    → datasource_config 表
- rate_limit    → rate_limit_config 表
- change_request → config_change_requests 表
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import text

from app.db.session import get_session
from app.config_center.cache import config_cache
from app.security.crypto import config_crypto, is_sensitive_field
from app.security.data_masking import data_masking
from app.security.audit import audit_logger
from app.security.tracing import get_trace_id

logger = logging.getLogger(__name__)


class ConfigService:
    """配置中心服务"""

    # ---------- 通用 KV 配置（app_config 表） ----------

    async def _load_app_config(self) -> dict:
        """载入 app_config 全量到缓存（解密敏感字段）"""
        data = {}
        async for session in get_session():
            result = await session.execute(
                text("SELECT config_key, config_value, is_sensitive FROM app_config")
            )
            for row in result.fetchall():
                key, value, is_sensitive = row[0], row[1], row[2]
                if is_sensitive and value:
                    # 敏感字段：先尝试解密（Fernet 密文），失败则视为明文 JSON（兼容种子数据）
                    decrypted = None
                    if value.startswith("gAAAAA"):  # Fernet token 前缀
                        decrypted = config_crypto.decrypt(value)
                    if decrypted is not None and decrypted != "":
                        value = decrypted
                try:
                    data[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    data[key] = value
        config_cache.set_namespace("app_config", data)
        return data

    async def get_app_config(self) -> dict:
        """读 app_config（走缓存）"""
        data = config_cache.get_namespace("app_config")
        if data:
            return data
        return await self._load_app_config()

    async def get_config(self, key: str, default: Any = None) -> Any:
        """读单个配置值（走缓存）"""
        data = await self.get_app_config()
        return data.get(key, default)

    async def _save_app_config(
        self,
        key: str,
        value: Any,
        *,
        is_sensitive: bool = False,
        description: str = "",
        updated_by: str = "system_admin",
        value_type: str = "json",
    ) -> dict:
        """写单个配置值（敏感字段加密）"""
        raw = value
        if is_sensitive and isinstance(raw, dict):
            # 对 dict 中的敏感字段逐个加密
            encrypted = {}
            for k, v in raw.items():
                if is_sensitive_field(k) and isinstance(v, str) and v:
                    encrypted[k] = config_crypto.encrypt(v)
                else:
                    encrypted[k] = v
            raw = json.dumps(encrypted, ensure_ascii=False)
        elif is_sensitive and isinstance(raw, str):
            raw = config_crypto.encrypt(raw)
        else:
            raw = json.dumps(raw, ensure_ascii=False) if not isinstance(raw, str) else raw

        async for session in get_session():
            result = await session.execute(
                text("""
                    INSERT INTO app_config (config_key, config_value, value_type, is_sensitive, description, updated_by)
                    VALUES (:key, :value, :value_type, :is_sensitive, :description, :updated_by)
                    ON DUPLICATE KEY UPDATE
                        config_value = VALUES(config_value),
                        value_type = VALUES(value_type),
                        is_sensitive = VALUES(is_sensitive),
                        description = VALUES(description),
                        updated_by = VALUES(updated_by),
                        version = version + 1
                """),
                {
                    "key": key,
                    "value": raw,
                    "value_type": value_type,
                    "is_sensitive": 1 if is_sensitive else 0,
                    "description": description,
                    "updated_by": updated_by,
                },
            )
            await session.commit()
        config_cache.invalidate("app_config")
        return {"status": "ok", "key": key}

    # ---------- LLM 配置 ----------

    async def get_llm_config(self) -> dict:
        """读 LLM 连接配置（api_key 解密返回）"""
        config = await self.get_config("llm", {}) or {}
        # api_key 若仍是 Fernet 密文则解密（_load_app_config 已处理，这里兜底）
        api_key = config.get("api_key", "")
        if api_key and api_key.startswith("gAAAAA"):
            config["api_key"] = config_crypto.decrypt(api_key)
        return config

    async def get_llm_config_masked(self) -> dict:
        """读 LLM 配置，api_key 只返回脱敏值（供前端展示）"""
        config = await self.get_llm_config()
        api_key = config.get("api_key", "")
        if api_key:
            config["api_key"] = config_crypto.mask(api_key)
        return config

    async def save_llm_config(self, data: dict, updated_by: str = "system_admin") -> dict:
        """保存 LLM 连接配置（api_key 加密入库，热生效）"""
        await self._save_app_config(
            "llm", data, is_sensitive=True,
            description="LLM 连接配置", updated_by=updated_by,
        )
        # LLM 连接热生效
        try:
            from app.agent.llm_client import llm_client
            llm_client.refresh_from_config()
        except Exception as e:
            logger.warning(f"LLM 配置热生效失败: {e}")
        return {"status": "ok", "message": "LLM 配置已保存"}

    # ---------- 保留期配置 ----------

    async def get_retention(self) -> dict:
        """读保留期配置"""
        return await self.get_config("retention", {
            "task_days": 90, "session_days": 180, "memory_days": 365, "audit_days": 365,
        })

    async def save_retention(self, data: dict, updated_by: str = "system_admin") -> dict:
        """保存保留期配置"""
        await self._save_app_config(
            "retention", data, is_sensitive=False,
            description="保留期与生命周期配置", updated_by=updated_by,
        )
        return {"status": "ok", "message": "保留期配置已保存"}

    async def retention_dry_run(self) -> dict:
        """生成保留期清理预览（各表将被清理的数量，不真正删除）"""
        retention = await self.get_retention()
        preview = {"retention": retention, "tables": {}}

        # 各表按保留期统计旧数据量
        checks = [
            ("task_history", "task_days", "created_at"),
            ("tasks", "task_days", "created_at"),
            ("audit_logs", "audit_days", "created_at"),
        ]
        async for session in get_session():
            for table, config_key, ts_col in checks:
                days = retention.get(config_key, 90)
                try:
                    result = await session.execute(
                        text(f"SELECT COUNT(*) FROM {table} WHERE {ts_col} < DATE_SUB(NOW(), INTERVAL :days DAY)"),
                        {"days": days},
                    )
                    row = result.fetchone()
                    preview["tables"][table] = {"config_key": config_key, "days": days, "will_delete": row[0] if row else 0}
                except Exception as e:
                    logger.warning(f"预览清理 {table} 失败: {e}")
                    preview["tables"][table] = {"config_key": config_key, "days": days, "will_delete": -1}
        return preview

    # ---------- 模型路由 ----------

    async def list_model_routes(self) -> list[dict]:
        """列出模型路由配置"""
        async for session in get_session():
            result = await session.execute(
                text("SELECT * FROM model_routing_config ORDER BY priority ASC")
            )
            rows = result.mappings().all()
            return [dict(row) for row in rows]
        return []

    async def save_model_route(self, task_type: str, data: dict, updated_by: str = "system_admin") -> dict:
        """upsert 模型路由"""
        async for session in get_session():
            await session.execute(
                text("""
                    INSERT INTO model_routing_config (task_type, primary_model, fallback_models, sensitivity_level, enabled, priority)
                    VALUES (:task_type, :primary_model, :fallback, :sensitivity, :enabled, :priority)
                    ON DUPLICATE KEY UPDATE
                        primary_model = VALUES(primary_model),
                        fallback_models = VALUES(fallback_models),
                        sensitivity_level = VALUES(sensitivity_level),
                        enabled = VALUES(enabled),
                        priority = VALUES(priority)
                """),
                {
                    "task_type": task_type,
                    "primary_model": data.get("primary_model", "deepseek-chat"),
                    "fallback": json.dumps(data.get("fallback_models", []), ensure_ascii=False),
                    "sensitivity": data.get("sensitivity_level", "normal"),
                    "enabled": 1 if data.get("enabled", True) else 0,
                    "priority": int(data.get("priority", 100)),
                },
            )
            await session.commit()
        return {"status": "ok", "message": f"路由 {task_type} 已保存"}

    async def delete_model_route(self, task_type: str) -> dict:
        """删除模型路由"""
        async for session in get_session():
            await session.execute(
                text("DELETE FROM model_routing_config WHERE task_type = :task_type"),
                {"task_type": task_type},
            )
            await session.commit()
        return {"status": "ok", "message": f"路由 {task_type} 已删除"}

    async def resolve_model(self, task_type: str) -> str:
        """按任务类型解析主模型（无配置回退 settings 默认）

        本期只铺钩子，不做 LLM 调用点接线（见计划 A7）。
        """
        routes = await self.list_model_routes()
        for r in routes:
            if r.get("task_type") == task_type and r.get("enabled", 1):
                return r.get("primary_model", "deepseek-chat")
        try:
            from app.config import settings
            return settings.llm_model
        except Exception:
            return "deepseek-chat"

    @staticmethod
    def known_task_types() -> list[str]:
        """已知任务类型（前端下拉源）"""
        return ["query", "report", "knowledge", "create", "update", "memory", "chat", "time", "sql_gen", "planning", "vision"]

    # ---------- 工具策略 ----------

    async def list_tool_policies(self) -> dict:
        """列出工具策略（registry 元数据 + DB 策略叠加）"""
        from app.tools.registry import tool_registry

        db_policies = await self._get_tool_policy_rows()
        tools = tool_registry.list_tools_full()
        result = []
        for tool in tools:
            name = tool["name"]
            policy = db_policies.get(name, {})
            merged = {
                **tool,
                "enabled": policy.get("enabled", True),
                "risk_level": policy.get("risk_level", tool.get("risk_level", "medium")),
                "need_confirm": policy.get("need_confirm", tool.get("need_confirm", False)),
                "timeout": policy.get("timeout", tool.get("timeout", 30)),
                "retry_count": policy.get("retry_count", tool.get("retry_count", 3)),
            }
            result.append(merged)
        return {"tools": result}

    async def _get_tool_policy_rows(self) -> dict:
        """读工具策略表全量（走缓存）"""
        cached = config_cache.get_namespace("tool_policy")
        if cached:
            return cached
        rows = {}
        async for session in get_session():
            result = await session.execute(text("SELECT * FROM tool_policy_config"))
            for row in result.mappings().all():
                rows[row["tool_name"]] = dict(row)
        config_cache.set_namespace("tool_policy", rows)
        return rows

    async def save_tool_policy(self, tool_name: str, data: dict, updated_by: str = "system_admin") -> dict:
        """保存工具策略（risk_level 降级或 need_confirm 关闭 → 走二次确认）

        返回 status: ok（直接生效）或 waiting_confirm（需二次确认）
        """
        current = await self._get_tool_policy_rows()
        old = current.get(tool_name, {})

        # 判断是否降级（高风险变更需二次确认）
        new_risk = data.get("risk_level", old.get("risk_level", "medium"))
        old_risk = old.get("risk_level", "medium")
        new_confirm = data.get("need_confirm", old.get("need_confirm", False))
        old_confirm = old.get("need_confirm", False)
        is_downgrade = (old_risk == "high" and new_risk in ("medium", "low")) or \
                       (old_confirm is True and new_confirm is False)

        if is_downgrade:
            # 走二次确认
            request_id = await self._create_change_request(
                namespace="tool_policy",
                target_key=tool_name,
                operation="update",
                old_value=old,
                new_value=data,
                requested_by=updated_by,
            )
            return {
                "status": "waiting_confirm",
                "message": f"工具 {tool_name} 风险降级操作需要二次确认",
                "change_request_id": request_id,
            }

        # 直接生效
        await self._upsert_tool_policy(tool_name, data, updated_by)
        config_cache.invalidate("tool_policy")
        return {"status": "ok", "message": f"工具 {tool_name} 策略已保存"}

    async def _upsert_tool_policy(self, tool_name: str, data: dict, updated_by: str):
        async for session in get_session():
            await session.execute(
                text("""
                    INSERT INTO tool_policy_config (tool_name, enabled, risk_level, need_confirm, timeout, retry_count, updated_by)
                    VALUES (:name, :enabled, :risk, :confirm, :timeout, :retry, :by)
                    ON DUPLICATE KEY UPDATE
                        enabled = VALUES(enabled), risk_level = VALUES(risk_level),
                        need_confirm = VALUES(need_confirm), timeout = VALUES(timeout),
                        retry_count = VALUES(retry_count), updated_by = VALUES(updated_by)
                """),
                {
                    "name": tool_name,
                    "enabled": 1 if data.get("enabled", True) else 0,
                    "risk": data.get("risk_level", "medium"),
                    "confirm": 1 if data.get("need_confirm", False) else 0,
                    "timeout": int(data.get("timeout", 30)),
                    "retry": int(data.get("retry_count", 3)),
                    "by": updated_by,
                },
            )
            await session.commit()

    async def reset_tool_policy(self, tool_name: str) -> dict:
        """恢复工具策略到注册表默认值（删除 DB 行）"""
        async for session in get_session():
            await session.execute(
                text("DELETE FROM tool_policy_config WHERE tool_name = :tool_name"),
                {"tool_name": tool_name},
            )
            await session.commit()
        config_cache.invalidate("tool_policy")
        return {"status": "ok", "message": f"工具 {tool_name} 策略已重置为默认"}

    async def apply_tool_policies(self, tool_registry) -> None:
        """启动时将 DB 工具策略应用到注册表"""
        try:
            rows = await self._get_tool_policy_rows()
            for name, policy in rows.items():
                tool_registry.apply_policy(
                    tool_name=name,
                    enabled=bool(policy.get("enabled", True)),
                    risk_level=policy.get("risk_level"),
                    need_confirm=bool(policy.get("need_confirm", False)),
                    timeout=policy.get("timeout"),
                    retry_count=policy.get("retry_count"),
                )
            logger.info(f"工具策略已应用: {len(rows)} 个工具")
        except Exception as e:
            logger.warning(f"应用工具策略失败（可能表未初始化）: {e}")

    # ---------- 二次确认 ----------

    async def _create_change_request(
        self, namespace: str, target_key: str, operation: str,
        old_value: dict, new_value: dict, requested_by: str,
    ) -> int:
        """创建二次确认待办"""
        async for session in get_session():
            result = await session.execute(
                text("""
                    INSERT INTO config_change_requests
                        (namespace, target_key, operation, old_value, new_value, status, requested_by, expires_at)
                    VALUES (:ns, :key, :op, :old, :new, 'pending', :by, DATE_ADD(NOW(), INTERVAL 24 HOUR))
                """),
                {
                    "ns": namespace,
                    "key": target_key,
                    "op": operation,
                    "old": json.dumps(old_value, ensure_ascii=False),
                    "new": json.dumps(new_value, ensure_ascii=False),
                    "by": requested_by,
                },
            )
            await session.commit()
            return result.lastrowid

    async def list_change_requests(self, status: str = "pending") -> list[dict]:
        """列出现待确认队列（超时自动置 expired）"""
        async for session in get_session():
            if status == "pending":
                # 先批量过期
                await session.execute(
                    text("""
                        UPDATE config_change_requests
                        SET status = 'expired'
                        WHERE status = 'pending' AND expires_at < NOW()
                    """)
                )
                await session.commit()
            result = await session.execute(
                text("""
                    SELECT * FROM config_change_requests
                    WHERE (:status IS NULL OR status = :status)
                    ORDER BY created_at DESC
                """),
                {"status": status},
            )
            return [dict(row) for row in result.mappings().all()]
        return []

    async def confirm_change_request(self, request_id: int, confirmed_by: str) -> dict:
        """二次确认生效（幂等：重复确认直接返回已生效）"""
        async for session in get_session():
            result = await session.execute(
                text("SELECT * FROM config_change_requests WHERE id = :id"),
                {"id": request_id},
            )
            row = result.mappings().first()
            if not row:
                return {"status": "error", "message": f"待确认记录不存在: {request_id}"}

            if row["status"] == "confirmed":
                return {"status": "ok", "message": "该变更已生效", "change_request_id": request_id}
            if row["status"] in ("cancelled", "expired"):
                return {"status": "error", "message": f"待确认记录状态为 {row['status']}，无法确认"}

            namespace = row["namespace"]
            target_key = row["target_key"]
            operation = row["operation"]
            new_value = json.loads(row["new_value"]) if row["new_value"] else {}

            # 根据命名空间执行目标写入
            if namespace == "datasource":
                await self._apply_datasource_change(target_key, operation, new_value, confirmed_by)
            elif namespace == "tool_policy":
                await self._upsert_tool_policy(target_key, new_value, confirmed_by)
                config_cache.invalidate("tool_policy")
            else:
                return {"status": "error", "message": f"未知命名空间: {namespace}"}

            # 标记已确认
            await session.execute(
                text("""
                    UPDATE config_change_requests
                    SET status = 'confirmed', confirmed_by = :by, confirmed_at = NOW()
                    WHERE id = :id
                """),
                {"by": confirmed_by, "id": request_id},
            )
            await session.commit()

        return {"status": "ok", "message": "变更已确认生效", "change_request_id": request_id}

    async def cancel_change_request(self, request_id: int, cancelled_by: str = "") -> dict:
        """取消待确认"""
        async for session in get_session():
            result = await session.execute(
                text("""
                    UPDATE config_change_requests
                    SET status = 'cancelled', confirmed_by = :by, confirmed_at = NOW()
                    WHERE id = :id AND status = 'pending'
                """),
                {"by": cancelled_by or "system_admin", "id": request_id},
            )
            await session.commit()
        return {"status": "ok", "message": "变更已取消"}

    # ---------- 数据源 ----------

    async def list_datasources(self) -> list[dict]:
        """列出数据源（密码只返回脱敏值）"""
        async for session in get_session():
            result = await session.execute(text("SELECT * FROM datasource_config ORDER BY id DESC"))
            rows = []
            for row in result.mappings().all():
                item = dict(row)
                encrypted = item.get("password_encrypted") or ""
                item["password_masked"] = config_crypto.mask(config_crypto.decrypt(encrypted))
                item.pop("password_encrypted", None)
                rows.append(item)
            return rows
        return []

    async def save_datasource(self, data: dict, updated_by: str = "system_admin") -> dict:
        """新建数据源（写入 pending 待确认）"""
        encrypted_password = config_crypto.encrypt(data.get("password", ""))
        # 先以 enabled=0 暂存，确认后置 1
        async for session in get_session():
            result = await session.execute(
                text("""
                    INSERT INTO datasource_config
                        (name, type, host, port, db_name, username, password_encrypted, connect_timeout, enabled, updated_by)
                    VALUES (:name, :type, :host, :port, :db, :username, :pwd, :timeout, 0, :by)
                """),
                {
                    "name": data["name"],
                    "type": data.get("type", "mysql_replica"),
                    "host": data["host"],
                    "port": int(data.get("port", 3306)),
                    "db": data.get("db_name", ""),
                    "username": data.get("username", ""),
                    "pwd": encrypted_password,
                    "timeout": int(data.get("connect_timeout", 10)),
                    "by": updated_by,
                },
            )
            await session.commit()
            datasource_id = result.lastrowid

        # 创建待确认
        request_id = await self._create_change_request(
            namespace="datasource",
            target_key=str(datasource_id),
            operation="create",
            old_value={},
            new_value={"name": data["name"], "host": data["host"], "db_name": data.get("db_name", "")},
            requested_by=updated_by,
        )
        return {
            "status": "waiting_confirm",
            "message": "数据源已保存，待二次确认后生效",
            "change_request_id": request_id,
            "datasource_id": datasource_id,
        }

    async def _apply_datasource_change(self, datasource_id: str, operation: str, new_value: dict, confirmed_by: str):
        """确认时应用数据源变更"""
        if operation == "delete":
            async for session in get_session():
                await session.execute(
                    text("DELETE FROM datasource_config WHERE id = :id"),
                    {"id": int(datasource_id)},
                )
                await session.commit()
        else:
            async for session in get_session():
                await session.execute(
                    text("""
                        UPDATE datasource_config
                        SET enabled = 1, updated_by = :by, version = version + 1
                        WHERE id = :id
                    """),
                    {"by": confirmed_by, "id": int(datasource_id)},
                )
                await session.commit()

    # ---------- 限流配额 ----------

    async def list_rate_limits(self) -> list[dict]:
        """列出限流配额"""
        async for session in get_session():
            result = await session.execute(text("SELECT * FROM rate_limit_config ORDER BY scope_type, scope_id"))
            return [dict(row) for row in result.mappings().all()]
        return []

    async def save_rate_limit(self, scope_type: str, scope_id: str, data: dict, updated_by: str = "system_admin") -> dict:
        """upsert 限流配额"""
        async for session in get_session():
            await session.execute(
                text("""
                    INSERT INTO rate_limit_config (scope_type, scope_id, qps, concurrency, token_quota_monthly, enabled, updated_by)
                    VALUES (:scope_type, :scope_id, :qps, :concurrency, :quota, :enabled, :by)
                    ON DUPLICATE KEY UPDATE
                        qps = VALUES(qps), concurrency = VALUES(concurrency),
                        token_quota_monthly = VALUES(token_quota_monthly),
                        enabled = VALUES(enabled), updated_by = VALUES(updated_by)
                """),
                {
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "qps": int(data.get("qps", 10)),
                    "concurrency": int(data.get("concurrency", 5)),
                    "quota": int(data.get("token_quota_monthly", 0)),
                    "enabled": 1 if data.get("enabled", True) else 0,
                    "by": updated_by,
                },
            )
            await session.commit()
        config_cache.invalidate("rate_limit")
        return {"status": "ok", "message": f"限流配额 {scope_type}:{scope_id} 已保存"}

    async def delete_rate_limit(self, scope_type: str, scope_id: str) -> dict:
        """删除限流配额（回退默认）"""
        async for session in get_session():
            await session.execute(
                text("DELETE FROM rate_limit_config WHERE scope_type = :scope_type AND scope_id = :scope_id"),
                {"scope_type": scope_type, "scope_id": scope_id},
            )
            await session.commit()
        config_cache.invalidate("rate_limit")
        return {"status": "ok", "message": f"限流配额 {scope_type}:{scope_id} 已删除"}

    # ---------- 审计 ----------

    async def audit(self, action: str, ctx: dict, before: dict, after: dict, risk_level: str = "low", result: dict = None):
        """统一审计：Before/After 双快照 + 敏感字段脱敏"""
        masked_before = data_masking.mask_for_log(before or {})
        masked_after = data_masking.mask_for_log(after or {})
        await audit_logger.log(
            action=action,
            user_id=str(ctx.get("user_id", "system_admin")),
            tenant_id=str(ctx.get("tenant_id", 1)),
            request_snapshot={"before": masked_before, "after": masked_after},
            result_snapshot=result or {"status": "ok"},
            risk_level=risk_level,
            trace_id=get_trace_id(),
        )

    # ---------- 知识库（复用 rag_tool 逻辑） ----------

    async def list_knowledge(self, keyword: str = "", category: str = "") -> list[dict]:
        """列出知识库条目"""
        async for session in get_session():
            conditions = []
            params = {}
            if keyword:
                conditions.append("(title LIKE :kw OR content LIKE :kw OR tags LIKE :kw)")
                params["kw"] = f"%{keyword}%"
            if category:
                conditions.append("category = :category")
                params["category"] = category
            where = " AND ".join(conditions) if conditions else "1=1"
            result = await session.execute(
                text(f"SELECT * FROM knowledge_base WHERE {where} ORDER BY id DESC LIMIT 200"),
                params,
            )
            return [dict(row) for row in result.mappings().all()]
        return []


# 全局实例
config_service = ConfigService()
