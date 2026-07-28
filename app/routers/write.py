"""写操作端点 - 单据创建"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.gateway.auth import verify_token
from app.gateway.rate_limit import check_rate_limit
from app.tools.create_document_tool import (
    create_document,
    get_document,
    update_document_status,
    DOCUMENT_TYPES,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateDocumentRequest(BaseModel):
    """创建单据请求"""
    doc_type: str  # purchase_order, sales_order, stock_in_order, stock_out_order
    payload: dict
    idempotency_key: str | None = None


class UpdateStatusRequest(BaseModel):
    """更新状态请求"""
    new_status: str
    remark: str | None = None


class DocumentResponse(BaseModel):
    """单据响应"""
    status: str
    doc_id: str | None = None
    doc_type: str | None = None
    message: str | None = None
    data: dict | None = None


@router.post("/create", response_model=DocumentResponse)
async def create_doc(
    req: CreateDocumentRequest,
    user_info: dict = Depends(verify_token),
    _: None = Depends(check_rate_limit),
):
    """创建单据

    支持的单据类型：
    - purchase_order: 采购订单
    - sales_order: 销售订单
    - stock_in_order: 入库单
    - stock_out_order: 出库单
    """
    logger.info(f"用户 {user_info['user_id']} 创建 {req.doc_type}")

    result = await create_document(
        doc_type=req.doc_type,
        payload=req.payload,
        user_id=user_info["user_id"],
        tenant_id=user_info.get("tenant_id", 1),
        idempotency_key=req.idempotency_key,
    )

    return DocumentResponse(**result.to_dict())


@router.get("/document/{doc_type}/{doc_id}", response_model=DocumentResponse)
async def get_doc(
    doc_type: str,
    doc_id: str,
    user_info: dict = Depends(verify_token),
):
    """获取单据详情"""
    logger.info(f"用户 {user_info['user_id']} 查询 {doc_type} {doc_id}")

    doc = await get_document(doc_type, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "message": f"单据不存在: {doc_id}",
            "error_code": "NOT_FOUND",
        })

    return DocumentResponse(
        status="ok",
        doc_id=doc_id,
        doc_type=doc_type,
        data=doc,
    )


@router.put("/document/{doc_type}/{doc_id}/status", response_model=DocumentResponse)
async def update_status(
    doc_type: str,
    doc_id: str,
    req: UpdateStatusRequest,
    user_info: dict = Depends(verify_token),
    _: None = Depends(check_rate_limit),
):
    """更新单据状态

    状态流转：
    - DRAFT -> SUBMITTED -> APPROVED -> COMPLETED
    - DRAFT -> CANCELLED
    - SUBMITTED -> REJECTED -> DRAFT
    """
    logger.info(f"用户 {user_info['user_id']} 更新 {doc_type} {doc_id} 状态为 {req.new_status}")

    result = await update_document_status(
        doc_type=doc_type,
        doc_id=doc_id,
        new_status=req.new_status,
        user_id=user_info["user_id"],
        remark=req.remark,
    )

    return DocumentResponse(**result.to_dict())


@router.get("/document/types")
async def get_document_types():
    """获取支持的单据类型"""
    return {
        "status": "ok",
        "types": list(DOCUMENT_TYPES.keys()),
    }
