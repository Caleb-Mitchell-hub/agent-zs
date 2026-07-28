"""单据创建工具

支持创建各类 ERP 单据：
- 采购订单 (purchase_order)
- 销售订单 (sales_order)
- 入库单 (stock_in_order)
- 出库单 (stock_out_order)

每个写操作都记录审计日志。
"""

import logging
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text
from app.db.session import get_session

logger = logging.getLogger(__name__)


class DocumentResult:
    """单据创建结果"""

    def __init__(self, doc_id: str, doc_type: str, status: str, message: str):
        self.doc_id = doc_id
        self.doc_type = doc_type
        self.status = status
        self.message = message

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "doc_type": self.doc_type,
            "status": self.status,
            "message": self.message,
        }


# 单据类型配置
DOCUMENT_TYPES = {
    "purchase_order": {
        "table": "purchase_order",
        "required_fields": ["supplier_id", "warehouse_id", "order_date"],
        "optional_fields": ["total_amount", "discount_amount", "pay_amount", "delivery_date", "remark"],
        "status_field": "status",
        "default_status": "DRAFT",
    },
    "sales_order": {
        "table": "sales_order",
        "required_fields": ["customer_id", "warehouse_id", "order_date"],
        "optional_fields": ["total_amount", "discount_amount", "pay_amount", "delivery_date", "remark"],
        "status_field": "status",
        "default_status": "DRAFT",
    },
    "stock_in_order": {
        "table": "stock_in_order",
        "required_fields": ["warehouse_id", "in_type"],
        "optional_fields": ["source_type", "source_no", "total_amount", "total_quantity", "remark"],
        "status_field": "status",
        "default_status": "DRAFT",
    },
    "stock_out_order": {
        "table": "stock_out_order",
        "required_fields": ["warehouse_id", "out_type"],
        "optional_fields": ["source_type", "source_no", "total_amount", "total_quantity", "remark"],
        "status_field": "status",
        "default_status": "DRAFT",
    },
}


async def create_document(
    doc_type: str,
    payload: dict,
    user_id: int,
    tenant_id: int,
    idempotency_key: str = None,
) -> DocumentResult:
    """创建单据

    Args:
        doc_type: 单据类型 (purchase_order, sales_order, stock_in_order, stock_out_order)
        payload: 单据数据
        user_id: 操作人 ID
        tenant_id: 租户 ID
        idempotency_key: 幂等键（防止重复创建）

    Returns:
        DocumentResult: 创建结果
    """
    # 验证单据类型
    if doc_type not in DOCUMENT_TYPES:
        return DocumentResult(
            doc_id="",
            doc_type=doc_type,
            status="error",
            message=f"不支持的单据类型: {doc_type}，支持: {', '.join(DOCUMENT_TYPES.keys())}",
        )

    config = DOCUMENT_TYPES[doc_type]

    # 验证必填字段
    missing_fields = []
    for field in config["required_fields"]:
        if field not in payload or payload[field] is None:
            missing_fields.append(field)

    if missing_fields:
        return DocumentResult(
            doc_id="",
            doc_type=doc_type,
            status="error",
            message=f"缺少必填字段: {', '.join(missing_fields)}",
        )

    # 生成单据 ID
    doc_id = f"{doc_type.upper()}-{uuid.uuid4().hex[:8].upper()}"

    try:
        async for session in get_session():
            # 检查幂等性
            if idempotency_key:
                existing = await session.execute(
                    text("SELECT doc_id FROM audit_log WHERE idempotency_key = :key"),
                    {"key": idempotency_key},
                )
                existing_row = existing.fetchone()
                if existing_row:
                    return DocumentResult(
                        doc_id=existing_row[0],
                        doc_type=doc_type,
                        status="ok",
                        message="单据已存在（幂等）",
                    )

            # 构建 INSERT 语句
            fields = ["id", "tenant_id", "created_by", "created_at"]
            values = [":id", ":tenant_id", ":created_by", ":created_at"]
            params = {
                "id": doc_id,
                "tenant_id": tenant_id,
                "created_by": user_id,
                "created_at": datetime.now(),
            }

            # 添加单据字段
            for field in config["required_fields"] + config["optional_fields"]:
                if field in payload and payload[field] is not None:
                    fields.append(field)
                    values.append(f":{field}")
                    params[field] = payload[field]

            # 添加状态字段
            if config["status_field"]:
                fields.append(config["status_field"])
                values.append(f":status")
                params["status"] = config["default_status"]

            # 执行插入
            sql = f"INSERT INTO {config['table']} ({', '.join(fields)}) VALUES ({', '.join(values)})"
            await session.execute(text(sql), params)

            # 记录审计日志
            await session.execute(
                text("""
                    INSERT INTO audit_log (doc_type, doc_id, action, user_id, tenant_id, payload, idempotency_key, created_at)
                    VALUES (:doc_type, :doc_id, :action, :user_id, :tenant_id, :payload, :idempotency_key, :created_at)
                """),
                {
                    "doc_type": doc_type,
                    "doc_id": doc_id,
                    "action": "CREATE",
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "payload": str(payload),
                    "idempotency_key": idempotency_key,
                    "created_at": datetime.now(),
                },
            )

            await session.commit()

            logger.info(f"单据创建成功: {doc_type} {doc_id}")

            return DocumentResult(
                doc_id=doc_id,
                doc_type=doc_type,
                status="ok",
                message=f"单据创建成功，状态: {config['default_status']}",
            )

    except Exception as e:
        logger.error(f"单据创建失败: {e}", exc_info=True)
        return DocumentResult(
            doc_id="",
            doc_type=doc_type,
            status="error",
            message=f"单据创建失败: {str(e)}",
        )


async def get_document(doc_type: str, doc_id: str) -> dict | None:
    """获取单据详情"""
    if doc_type not in DOCUMENT_TYPES:
        return None

    config = DOCUMENT_TYPES[doc_type]

    try:
        async for session in get_session():
            result = await session.execute(
                text(f"SELECT * FROM {config['table']} WHERE id = :id"),
                {"id": doc_id},
            )
            row = result.mappings().first()
            return dict(row) if row else None

    except Exception as e:
        logger.error(f"获取单据失败: {e}", exc_info=True)
        return None


async def update_document_status(
    doc_type: str,
    doc_id: str,
    new_status: str,
    user_id: int,
    remark: str = None,
) -> DocumentResult:
    """更新单据状态

    支持的状态流转：
    - DRAFT -> SUBMITTED -> APPROVED -> COMPLETED
    - DRAFT -> CANCELLED
    - SUBMITTED -> REJECTED -> DRAFT
    """
    if doc_type not in DOCUMENT_TYPES:
        return DocumentResult(
            doc_id=doc_id,
            doc_type=doc_type,
            status="error",
            message=f"不支持的单据类型: {doc_type}",
        )

    config = DOCUMENT_TYPES[doc_type]

    # 状态流转验证
    valid_transitions = {
        "DRAFT": ["SUBMITTED", "CANCELLED"],
        "SUBMITTED": ["APPROVED", "REJECTED"],
        "APPROVED": ["COMPLETED"],
        "REJECTED": ["DRAFT"],
    }

    try:
        async for session in get_session():
            # 获取当前状态
            result = await session.execute(
                text(f"SELECT {config['status_field']} FROM {config['table']} WHERE id = :id"),
                {"id": doc_id},
            )
            row = result.fetchone()
            if not row:
                return DocumentResult(
                    doc_id=doc_id,
                    doc_type=doc_type,
                    status="error",
                    message=f"单据不存在: {doc_id}",
                )

            current_status = row[0]

            # 验证状态流转
            if current_status not in valid_transitions:
                return DocumentResult(
                    doc_id=doc_id,
                    doc_type=doc_type,
                    status="error",
                    message=f"当前状态 {current_status} 不允许流转",
                )

            allowed_next = valid_transitions[current_status]
            if new_status not in allowed_next:
                return DocumentResult(
                    doc_id=doc_id,
                    doc_type=doc_type,
                    status="error",
                    message=f"不允许从 {current_status} 流转到 {new_status}，允许: {', '.join(allowed_next)}",
                )

            # 更新状态
            await session.execute(
                text(f"UPDATE {config['table']} SET {config['status_field']} = :status, updated_at = :updated_at WHERE id = :id"),
                {"status": new_status, "updated_at": datetime.now(), "id": doc_id},
            )

            # 记录审计日志
            await session.execute(
                text("""
                    INSERT INTO audit_log (doc_type, doc_id, action, user_id, payload, created_at)
                    VALUES (:doc_type, :doc_id, :action, :user_id, :payload, :created_at)
                """),
                {
                    "doc_type": doc_type,
                    "doc_id": doc_id,
                    "action": f"STATUS_CHANGE:{current_status}->{new_status}",
                    "user_id": user_id,
                    "payload": remark or "",
                    "created_at": datetime.now(),
                },
            )

            await session.commit()

            logger.info(f"单据状态更新: {doc_id} {current_status} -> {new_status}")

            return DocumentResult(
                doc_id=doc_id,
                doc_type=doc_type,
                status="ok",
                message=f"状态已更新: {current_status} -> {new_status}",
            )

    except Exception as e:
        logger.error(f"单据状态更新失败: {e}", exc_info=True)
        return DocumentResult(
            doc_id=doc_id,
            doc_type=doc_type,
            status="error",
            message=f"状态更新失败: {str(e)}",
        )
