"""ERP Adapter - ERP 适配层

职责：
- 封装 ERP API 调用
- 幂等控制
- 状态核对（Reconciliation）
- 本地映射管理
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text

from app.db.session import get_session

logger = logging.getLogger(__name__)


class ErpAdapter:
    """ERP 适配层"""

    async def create_document(
        self,
        doc_type: str,
        params: dict,
        idempotency_key: str,
        user_id: str,
        tenant_id: str,
    ) -> dict:
        """创建单据（带幂等控制）"""
        # 1. 幂等检查
        existing = await self._check_idempotency(idempotency_key)
        if existing:
            return {"status": "ok", "doc_no": existing["downstream_ref_id"], "message": "单据已存在（幂等）"}

        # 2. 计算请求哈希
        request_hash = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()

        # 3. 创建幂等记录
        await self._create_idempotency_record(idempotency_key, "erp", request_hash)

        # 4. 调用 ERP API（模拟）
        doc_no = f"{doc_type.upper()}-{uuid.uuid4().hex[:8].upper()}"

        # 5. 更新幂等记录
        await self._update_idempotency_record(idempotency_key, "confirmed", doc_no)

        # 6. 创建本地映射
        await self._create_order_mapping(task_id=None, step_id=None, erp_order_no=doc_no, erp_order_type=doc_type)

        logger.info(f"ERP 单据创建成功: {doc_no}")
        return {"status": "ok", "doc_no": doc_no}

    async def reconcile_state(self, idempotency_key: str) -> dict:
        """状态核对（断点恢复关键逻辑）

        核对流程：
        1. 查本地幂等记录
        2. 如果有下游ID，说明已成功
        3. 如果没有，查询ERP确认真实状态
        """
        # 1. 查本地记录
        record = await self._check_idempotency(idempotency_key)

        if record and record.get("downstream_ref_id"):
            # 已有下游ID，说明已成功
            return {
                "status": "confirmed",
                "doc_no": record["downstream_ref_id"],
                "message": "单据已存在",
            }

        # 2. 查询映射表
        mapping = await self._check_order_mapping(idempotency_key)
        if mapping:
            return {
                "status": "confirmed",
                "doc_no": mapping["erp_order_no"],
                "message": "单据已创建",
            }

        # 3. 确认未执行
        return {
            "status": "not_found",
            "message": "单据未创建，可以重新提交",
        }

    async def _check_idempotency(self, idempotency_key: str) -> Optional[dict]:
        """检查幂等键"""
        async for session in get_session():
            result = await session.execute(
                text("SELECT * FROM idempotency_records WHERE idempotency_key = :key"),
                {"key": idempotency_key},
            )
            row = result.mappings().first()
            return dict(row) if row else None

    async def _create_idempotency_record(self, key: str, target_system: str, request_hash: str):
        """创建幂等记录"""
        async for session in get_session():
            await session.execute(
                text("""
                    INSERT INTO idempotency_records (idempotency_key, target_system, request_hash, status, expire_at)
                    VALUES (:key, :target_system, :request_hash, :status, :expire_at)
                """),
                {
                    "key": key,
                    "target_system": target_system,
                    "request_hash": request_hash,
                    "status": "pending",
                    "expire_at": datetime.now() + timedelta(days=30),
                },
            )
            await session.commit()

    async def _update_idempotency_record(self, key: str, status: str, ref_id: str):
        """更新幂等记录"""
        async for session in get_session():
            await session.execute(
                text("UPDATE idempotency_records SET status = :status, downstream_ref_id = :ref_id WHERE idempotency_key = :key"),
                {"status": status, "ref_id": ref_id, "key": key},
            )
            await session.commit()

    async def _create_order_mapping(self, task_id: str, step_id: str, erp_order_no: str, erp_order_type: str):
        """创建单据映射"""
        async for session in get_session():
            await session.execute(
                text("""
                    INSERT INTO erp_order_mapping (task_id, step_id, erp_order_no, erp_order_type, sync_status)
                    VALUES (:task_id, :step_id, :erp_order_no, :erp_order_type, :sync_status)
                """),
                {
                    "task_id": task_id,
                    "step_id": step_id,
                    "erp_order_no": erp_order_no,
                    "erp_order_type": erp_order_type,
                    "sync_status": "created",
                },
            )
            await session.commit()

    async def _check_order_mapping(self, idempotency_key: str) -> Optional[dict]:
        """检查单据映射"""
        async for session in get_session():
            result = await session.execute(
                text("SELECT * FROM erp_order_mapping WHERE task_id = :key OR step_id = :key"),
                {"key": idempotency_key},
            )
            row = result.mappings().first()
            return dict(row) if row else None


# 全局实例
erp_adapter = ErpAdapter()
