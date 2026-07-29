"""ERP Adapter - ERP 适配层

职责：
- 封装 ERP API 调用
- 幂等控制
- 状态核对
- 本地映射管理
"""

import hashlib
import logging
from datetime import datetime
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
        """创建单据

        Args:
            doc_type: 单据类型
            params: 参数
            idempotency_key: 幂等键
            user_id: 用户ID
            tenant_id: 租户ID

        Returns:
            dict: 创建结果
        """
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
                    "expire_at": datetime.now().replace(day=datetime.now().day + 30),
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


import json
import uuid

# 全局实例
erp_adapter = ErpAdapter()
