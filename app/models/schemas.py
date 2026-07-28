"""Pydantic 数据模型

定义 API 请求/响应的数据结构。
"""

from pydantic import BaseModel


# 查询相关
class QueryRequest(BaseModel):
    question: str
    user_id: int | None = None
    tenant_id: int | None = None


class QueryResponse(BaseModel):
    status: str  # ok / clarify / error
    data: list[dict] | None = None
    sql: str | None = None
    message: str | None = None
    error_code: str | None = None


# 报表相关
class ReportRequest(BaseModel):
    question: str
    format: str = "table"  # table / chart / excel
    user_id: int | None = None
    tenant_id: int | None = None


class ReportResponse(BaseModel):
    status: str
    data: list[dict] | None = None
    title: str | None = None
    columns: list[dict] | None = None
    message: str | None = None
    error_code: str | None = None


# 健康检查
class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
