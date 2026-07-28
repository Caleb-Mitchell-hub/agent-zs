"""Approval Tool - 审批流程工具

职责：
- 创建审批流程
- 审批/驳回单据
- 查询审批状态
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from app.db.session import get_session

logger = logging.getLogger(__name__)


class ApprovalTool:
    """审批流程工具"""

    async def create_approval(
        self,
        doc_type: str,
        doc_id: str,
        doc_no: str,
        applicant_id: int,
        tenant_id: int,
        amount: float = 0,
    ) -> dict:
        """创建审批流程

        Args:
            doc_type: 单据类型
            doc_id: 单据 ID
            doc_no: 单据编号
            applicant_id: 申请人 ID
            tenant_id: 租户 ID
            amount: 金额（用于判断审批级别）

        Returns:
            dict: 创建结果
        """
        try:
            # 获取审批配置
            approval_level = await self._get_approval_level(doc_type, amount, tenant_id)

            async for session in get_session():
                # 创建审批实例
                await session.execute(
                    text("""
                        INSERT INTO approval_instance (
                            doc_type, doc_id, doc_no,
                            applicant_id, tenant_id,
                            approval_level, current_level,
                            status, amount,
                            created_at, updated_at
                        ) VALUES (
                            :doc_type, :doc_id, :doc_no,
                            :applicant_id, :tenant_id,
                            :approval_level, 1,
                            'PENDING', :amount,
                            :created_at, :updated_at
                        )
                    """),
                    {
                        "doc_type": doc_type,
                        "doc_id": doc_id,
                        "doc_no": doc_no,
                        "applicant_id": applicant_id,
                        "tenant_id": tenant_id,
                        "approval_level": approval_level,
                        "amount": amount,
                        "created_at": datetime.now(),
                        "updated_at": datetime.now(),
                    },
                )

                # 记录审批日志
                await session.execute(
                    text("""
                        INSERT INTO approval_log (
                            doc_type, doc_id, doc_no,
                            action, operator_id,
                            tenant_id, created_at
                        ) VALUES (
                            :doc_type, :doc_id, :doc_no,
                            'SUBMIT', :operator_id,
                            :tenant_id, :created_at
                        )
                    """),
                    {
                        "doc_type": doc_type,
                        "doc_id": doc_id,
                        "doc_no": doc_no,
                        "operator_id": applicant_id,
                        "tenant_id": tenant_id,
                        "created_at": datetime.now(),
                    },
                )

                await session.commit()

                logger.info(f"审批流程创建成功: {doc_type} {doc_no}")

                return {
                    "status": "ok",
                    "message": f"审批流程已创建，审批级别: {approval_level}",
                    "approval_level": approval_level,
                }

        except Exception as e:
            logger.error(f"创建审批流程失败: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"创建审批流程失败: {str(e)}",
            }

    async def approve(
        self,
        doc_type: str,
        doc_id: str,
        operator_id: int,
        tenant_id: int,
        remark: str = "",
    ) -> dict:
        """审批通过

        Args:
            doc_type: 单据类型
            doc_id: 单据 ID
            operator_id: 操作人 ID
            tenant_id: 租户 ID
            remark: 备注

        Returns:
            dict: 审批结果
        """
        try:
            async for session in get_session():
                # 获取审批实例
                result = await session.execute(
                    text("""
                        SELECT id, current_level, approval_level, status
                        FROM approval_instance
                        WHERE doc_type = :doc_type AND doc_id = :doc_id AND tenant_id = :tenant_id
                    """),
                    {"doc_type": doc_type, "doc_id": doc_id, "tenant_id": tenant_id},
                )
                instance = result.fetchone()

                if not instance:
                    return {"status": "error", "message": "审批实例不存在"}

                instance_id, current_level, approval_level, status = instance

                if status != "PENDING":
                    return {"status": "error", "message": f"审批状态异常: {status}"}

                # 判断是否是最后一级
                if current_level >= approval_level:
                    # 最后一级，审批通过
                    new_status = "APPROVED"
                else:
                    # 不是最后一级，进入下一级
                    new_status = "PENDING"
                    current_level += 1

                # 更新审批实例
                await session.execute(
                    text("""
                        UPDATE approval_instance
                        SET status = :status, current_level = :current_level,
                            updated_at = :updated_at
                        WHERE id = :id
                    """),
                    {
                        "status": new_status,
                        "current_level": current_level,
                        "updated_at": datetime.now(),
                        "id": instance_id,
                    },
                )

                # 记录审批日志
                await session.execute(
                    text("""
                        INSERT INTO approval_log (
                            doc_type, doc_id, doc_no,
                            action, operator_id, remark,
                            tenant_id, created_at
                        ) VALUES (
                            :doc_type, :doc_id, :doc_no,
                            'APPROVE', :operator_id, :remark,
                            :tenant_id, :created_at
                        )
                    """),
                    {
                        "doc_type": doc_type,
                        "doc_id": doc_id,
                        "doc_no": doc_id,
                        "operator_id": operator_id,
                        "remark": remark,
                        "tenant_id": tenant_id,
                        "created_at": datetime.now(),
                    },
                )

                await session.commit()

                logger.info(f"审批通过: {doc_type} {doc_id}")

                return {
                    "status": "ok",
                    "message": "审批通过" if new_status == "APPROVED" else f"已审批，等待下一级",
                    "approval_status": new_status,
                }

        except Exception as e:
            logger.error(f"审批失败: {e}", exc_info=True)
            return {"status": "error", "message": f"审批失败: {str(e)}"}

    async def reject(
        self,
        doc_type: str,
        doc_id: str,
        operator_id: int,
        tenant_id: int,
        reason: str = "",
    ) -> dict:
        """驳回

        Args:
            doc_type: 单据类型
            doc_id: 单据 ID
            operator_id: 操作人 ID
            tenant_id: 租户 ID
            reason: 驳回原因

        Returns:
            dict: 驳回结果
        """
        try:
            async for session in get_session():
                # 更新审批实例
                await session.execute(
                    text("""
                        UPDATE approval_instance
                        SET status = 'REJECTED', reject_reason = :reason, updated_at = :updated_at
                        WHERE doc_type = :doc_type AND doc_id = :doc_id AND tenant_id = :tenant_id
                    """),
                    {
                        "reason": reason,
                        "updated_at": datetime.now(),
                        "doc_type": doc_type,
                        "doc_id": doc_id,
                        "tenant_id": tenant_id,
                    },
                )

                # 记录审批日志
                await session.execute(
                    text("""
                        INSERT INTO approval_log (
                            doc_type, doc_id, doc_no,
                            action, operator_id, remark,
                            tenant_id, created_at
                        ) VALUES (
                            :doc_type, :doc_id, :doc_no,
                            'REJECT', :operator_id, :remark,
                            :tenant_id, :created_at
                        )
                    """),
                    {
                        "doc_type": doc_type,
                        "doc_id": doc_id,
                        "doc_no": doc_id,
                        "operator_id": operator_id,
                        "remark": reason,
                        "tenant_id": tenant_id,
                        "created_at": datetime.now(),
                    },
                )

                await session.commit()

                logger.info(f"审批驳回: {doc_type} {doc_id}")

                return {
                    "status": "ok",
                    "message": "已驳回",
                    "approval_status": "REJECTED",
                }

        except Exception as e:
            logger.error(f"驳回失败: {e}", exc_info=True)
            return {"status": "error", "message": f"驳回失败: {str(e)}"}

    async def get_approval_status(
        self,
        doc_type: str,
        doc_id: str,
        tenant_id: int,
    ) -> dict:
        """获取审批状态

        Args:
            doc_type: 单据类型
            doc_id: 单据 ID
            tenant_id: 租户 ID

        Returns:
            dict: 审批状态
        """
        try:
            async for session in get_session():
                result = await session.execute(
                    text("""
                        SELECT id, approval_level, current_level, status, reject_reason, created_at
                        FROM approval_instance
                        WHERE doc_type = :doc_type AND doc_id = :doc_id AND tenant_id = :tenant_id
                    """),
                    {"doc_type": doc_type, "doc_id": doc_id, "tenant_id": tenant_id},
                )
                instance = result.fetchone()

                if not instance:
                    return {"status": "error", "message": "审批实例不存在"}

                instance_id, approval_level, current_level, status, reject_reason, created_at = instance

                return {
                    "status": "ok",
                    "approval_status": status,
                    "approval_level": approval_level,
                    "current_level": current_level,
                    "reject_reason": reject_reason,
                    "created_at": str(created_at),
                }

        except Exception as e:
            logger.error(f"获取审批状态失败: {e}", exc_info=True)
            return {"status": "error", "message": f"获取审批状态失败: {str(e)}"}

    async def _get_approval_level(self, doc_type: str, amount: float, tenant_id: int) -> int:
        """获取审批级别

        根据金额判断审批级别：
        - 金额 < 10000: 1级审批
        - 金额 10000-50000: 2级审批
        - 金额 > 50000: 3级审批
        """
        if amount < 10000:
            return 1
        elif amount < 50000:
            return 2
        else:
            return 3


# 全局实例
approval_tool = ApprovalTool()
