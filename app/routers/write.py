"""写操作端点 - 单据管理"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.gateway.auth import verify_token
from app.tools.erp_api_tool import DOCUMENT_TYPES

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/document/types")
async def get_document_types():
    """获取支持的单据类型"""
    return {
        "status": "ok",
        "types": list(DOCUMENT_TYPES.keys()),
    }


@router.get("/document/{doc_type}")
async def list_documents(
    doc_type: str,
    status: str = None,
    limit: int = 50,
    user_info: dict = Depends(verify_token),
):
    """查询单据列表

    Args:
        doc_type: 单据类型
        status: 状态过滤
        limit: 返回数量
    """
    if doc_type not in DOCUMENT_TYPES:
        return {"status": "error", "message": f"不支持的单据类型: {doc_type}"}

    from sqlalchemy import text
    from app.db.session import get_session

    try:
        async for session in get_session():
            table = DOCUMENT_TYPES[doc_type]["table"]
            no_field = DOCUMENT_TYPES[doc_type].get("no_field", "id")

            if status:
                result = await session.execute(
                    text(f"SELECT * FROM {table} WHERE status = :status AND (deleted = 0 OR deleted IS NULL) ORDER BY created_at DESC LIMIT :limit"),
                    {"status": status, "limit": limit},
                )
            else:
                result = await session.execute(
                    text(f"SELECT * FROM {table} WHERE (deleted = 0 OR deleted IS NULL) ORDER BY created_at DESC LIMIT :limit"),
                    {"limit": limit},
                )

            rows = result.mappings().all()

            # 转换为列表
            documents = []
            for row in rows:
                doc = dict(row)
                # 处理日期和 Decimal
                for k, v in doc.items():
                    from datetime import datetime, date
                    if isinstance(v, (datetime, date)):
                        doc[k] = str(v)
                    from decimal import Decimal
                    if isinstance(v, Decimal):
                        doc[k] = float(v)
                documents.append(doc)

            return {
                "status": "ok",
                "doc_type": doc_type,
                "count": len(documents),
                "documents": documents,
            }

    except Exception as e:
        logger.error(f"查询单据失败: {e}", exc_info=True)
        return {"status": "error", "message": f"查询失败: {str(e)}"}


@router.get("/document/{doc_type}/{doc_no}")
async def get_document(
    doc_type: str,
    doc_no: str,
    user_info: dict = Depends(verify_token),
):
    """查询单据详情"""
    if doc_type not in DOCUMENT_TYPES:
        return {"status": "error", "message": f"不支持的单据类型: {doc_type}"}

    from sqlalchemy import text
    from app.db.session import get_session

    try:
        async for session in get_session():
            table = DOCUMENT_TYPES[doc_type]["table"]
            no_field = DOCUMENT_TYPES[doc_type].get("no_field", "id")

            result = await session.execute(
                text(f"SELECT * FROM {table} WHERE `{no_field}` = :doc_no"),
                {"doc_no": doc_no},
            )
            row = result.mappings().first()

            if not row:
                return {"status": "error", "message": f"单据不存在: {doc_no}"}

            doc = dict(row)
            from datetime import datetime, date
            from decimal import Decimal
            for k, v in doc.items():
                if isinstance(v, (datetime, date)):
                    doc[k] = str(v)
                if isinstance(v, Decimal):
                    doc[k] = float(v)

            return {
                "status": "ok",
                "document": doc,
            }

    except Exception as e:
        logger.error(f"查询单据失败: {e}", exc_info=True)
        return {"status": "error", "message": f"查询失败: {str(e)}"}
