"""ERP API Tool - 业务操作工具

职责：
- 创建单据
- 更新单据状态
- 调用 ERP 业务接口
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy import text

from app.db.session import get_session

logger = logging.getLogger(__name__)


# 单据类型配置
DOCUMENT_TYPES = {
    "purchase_order": {
        "table": "purchase_order",
        "no_field": "order_no",
        "required_fields": ["supplier_id", "warehouse_id", "order_date"],
    },
    "sales_order": {
        "table": "sales_order",
        "no_field": "order_no",
        "required_fields": ["customer_id", "warehouse_id", "order_date"],
    },
    "stock_in_order": {
        "table": "stock_in_order",
        "no_field": "in_no",
        "required_fields": ["warehouse_id", "in_type"],
    },
    "stock_out_order": {
        "table": "stock_out_order",
        "no_field": "out_no",
        "required_fields": ["warehouse_id", "out_type"],
    },
}


class ErpApiTool:
    """ERP API 工具"""

    async def execute(
        self,
        action: str,
        doc_type: str,
        params: dict,
        user_id: int,
        tenant_id: int,
    ) -> dict:
        """执行 ERP 操作

        Args:
            action: 操作类型 (create/update)
            doc_type: 单据类型
            params: 操作参数
            user_id: 用户 ID
            tenant_id: 租户 ID

        Returns:
            dict: 操作结果
        """
        if action == "create":
            return await self._create_document(doc_type, params, user_id, tenant_id)
        elif action == "update":
            return await self._update_document(doc_type, params, user_id, tenant_id)
        else:
            return {
                "status": "error",
                "message": f"不支持的操作: {action}",
                "error_code": "UNSUPPORTED_ACTION",
            }

    async def _create_document(
        self,
        doc_type: str,
        params: dict,
        user_id: int,
        tenant_id: int,
    ) -> dict:
        """创建单据"""
        if doc_type not in DOCUMENT_TYPES:
            return {
                "status": "error",
                "message": f"不支持的单据类型: {doc_type}",
                "error_code": "INVALID_DOC_TYPE",
            }

        config = DOCUMENT_TYPES[doc_type]
        doc_no = f"{doc_type.upper()}-{uuid.uuid4().hex[:8].upper()}"

        try:
            async for session in get_session():
                # 构建 INSERT 语句
                fields = ["tenant_id", "created_by", "created_at"]
                values = [":tenant_id", ":created_by", ":created_at"]
                query_params = {
                    "tenant_id": tenant_id,
                    "created_by": user_id,
                    "created_at": datetime.now(),
                }

                # 添加单据编号
                if config["no_field"]:
                    fields.append(config["no_field"])
                    values.append(f":no_field")
                    query_params["no_field"] = doc_no

                # 添加状态
                fields.append("status")
                values.append(":status")
                query_params["status"] = "DRAFT"

                # 执行插入
                sql = f"INSERT INTO {config['table']} ({', '.join(fields)}) VALUES ({', '.join(values)})"
                await session.execute(text(sql), query_params)

                # 记录审计日志
                await session.execute(
                    text("""
                        INSERT INTO audit_log (tenant_id, user_id, module, operation, entity_type, entity_no, content, status, created_at)
                        VALUES (:tenant_id, :user_id, :module, :operation, :entity_type, :entity_no, :content, :status, :created_at)
                    """),
                    {
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "module": doc_type,
                        "operation": "CREATE",
                        "entity_type": doc_type,
                        "entity_no": doc_no,
                        "content": str(params),
                        "status": "SUCCESS",
                        "created_at": datetime.now(),
                    },
                )

                await session.commit()

                logger.info(f"单据创建成功: {doc_type} {doc_no}")

                return {
                    "status": "ok",
                    "doc_id": doc_no,
                    "doc_type": doc_type,
                    "message": f"单据创建成功: {doc_no}",
                }

        except Exception as e:
            logger.error(f"单据创建失败: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"单据创建失败: {str(e)}",
                "error_code": "CREATE_ERROR",
            }

    async def _update_document(
        self,
        doc_type: str,
        params: dict,
        user_id: int,
        tenant_id: int,
    ) -> dict:
        """更新单据状态"""
        if doc_type not in DOCUMENT_TYPES:
            return {
                "status": "error",
                "message": f"不支持的单据类型: {doc_type}",
                "error_code": "INVALID_DOC_TYPE",
            }

        config = DOCUMENT_TYPES[doc_type]
        doc_id = params.get("doc_id")
        new_status = params.get("status")

        if not doc_id or not new_status:
            return {
                "status": "error",
                "message": "缺少 doc_id 或 status 参数",
                "error_code": "MISSING_PARAMS",
            }

        try:
            async for session in get_session():
                # 更新状态
                await session.execute(
                    text(f"UPDATE {config['table']} SET status = :status, updated_at = :updated_at WHERE id = :id"),
                    {"status": new_status, "updated_at": datetime.now(), "id": doc_id},
                )

                # 记录审计日志
                await session.execute(
                    text("""
                        INSERT INTO audit_log (tenant_id, user_id, module, operation, entity_type, entity_no, content, status, created_at)
                        VALUES (:tenant_id, :user_id, :module, :operation, :entity_type, :entity_no, :content, :status, :created_at)
                    """),
                    {
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "module": doc_type,
                        "operation": "UPDATE_STATUS",
                        "entity_type": doc_type,
                        "entity_no": str(doc_id),
                        "content": json.dumps({"new_status": new_status}),
                        "status": "SUCCESS",
                        "created_at": datetime.now(),
                    },
                )

                await session.commit()

                logger.info(f"单据状态更新: {doc_type} {doc_id} -> {new_status}")

                return {
                    "status": "ok",
                    "message": f"状态已更新: {new_status}",
                }

        except Exception as e:
            logger.error(f"单据状态更新失败: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"状态更新失败: {str(e)}",
                "error_code": "UPDATE_ERROR",
            }
