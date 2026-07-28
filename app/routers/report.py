"""报表端点 - 自然语言生成报表"""

import logging

from fastapi import APIRouter, Depends, Request

from app.models.schemas import ReportRequest, ReportResponse
from app.agent.orchestrator import ReportOrchestrator
from app.gateway.auth import verify_token
from app.gateway.rate_limit import check_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter()

# 编排器实例
report_orchestrator = ReportOrchestrator()


@router.post("/report", response_model=ReportResponse)
async def generate_report(
    req: ReportRequest,
    request: Request,
    user_info: dict = Depends(verify_token),
    _: None = Depends(check_rate_limit),
):
    """自然语言报表生成入口

    接收用户自然语言描述，生成结构化报表。
    需要认证 token。
    """
    logger.info(f"用户 {user_info['user_id']} 生成报表: {req.question}")

    result = await report_orchestrator.process_report(
        question=req.question,
        format=req.format,
    )
    return ReportResponse(**result)
