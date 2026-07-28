"""中间件

- 请求日志记录
- 全局异常处理
"""

import time
import logging
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件

    记录每个请求的方法、路径、状态码、耗时。
    """

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # 记录请求开始
        logger.info(f"请求开始: {request.method} {request.url.path}")

        # 处理请求
        try:
            response = await call_next(request)
        except Exception as e:
            # 记录异常
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"请求异常: {request.method} {request.url.path} "
                f"耗时={duration_ms:.1f}ms 错误={str(e)}"
            )
            raise

        # 记录请求完成
        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            f"请求完成: {request.method} {request.url.path} "
            f"状态={response.status_code} 耗时={duration_ms:.1f}ms"
        )

        # 添加响应头
        response.headers["X-Request-Duration-Ms"] = f"{duration_ms:.1f}"

        return response


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """全局异常处理中间件

    捕获未处理的异常，返回统一的错误响应。
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            # 记录异常详情
            logger.error(
                f"未处理异常: {request.method} {request.url.path}\n"
                f"{traceback.format_exc()}"
            )

            # 返回统一错误响应
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": "服务器内部错误，请稍后重试",
                    "error_code": "INTERNAL_ERROR",
                },
            )
