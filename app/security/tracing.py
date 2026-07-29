"""分布式追踪

职责：
- 生成 trace_id
- 贯穿全链路
- 记录每个步骤的调用信息
"""

import uuid
import logging
import time
from contextvars import ContextVar
from typing import Optional

logger = logging.getLogger(__name__)

# 上下文变量，存储当前 trace_id
trace_id_var: ContextVar[str] = ContextVar('trace_id', default='')


def generate_trace_id() -> str:
    """生成 trace_id"""
    return f"trace-{uuid.uuid4().hex[:16]}"


def get_trace_id() -> str:
    """获取当前 trace_id"""
    return trace_id_var.get()


def set_trace_id(trace_id: str):
    """设置 trace_id"""
    trace_id_var.set(trace_id)


class TraceSpan:
    """追踪跨度"""

    def __init__(self, name: str, parent_id: str = None):
        self.name = name
        self.span_id = f"span-{uuid.uuid4().hex[:8]}"
        self.parent_id = parent_id or get_trace_id()
        self.start_time = time.time()
        self.end_time = None
        self.attributes = {}

    def set_attribute(self, key: str, value):
        """设置属性"""
        self.attributes[key] = value

    def finish(self):
        """结束跨度"""
        self.end_time = time.time()

    def to_dict(self) -> dict:
        """转为字典"""
        return {
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "start_time": self.start_time,
            "duration_ms": int((self.end_time - self.start_time) * 1000) if self.end_time else None,
            "attributes": self.attributes,
        }


class Tracer:
    """追踪器"""

    def __init__(self):
        self._spans: dict[str, list[TraceSpan]] = {}

    def start_span(self, name: str, trace_id: str = None) -> TraceSpan:
        """开始一个跨度"""
        if trace_id:
            set_trace_id(trace_id)

        span = TraceSpan(name)
        current_trace_id = get_trace_id()

        if current_trace_id not in self._spans:
            self._spans[current_trace_id] = []
        self._spans[current_trace_id].append(span)

        return span

    def get_trace(self, trace_id: str) -> list[dict]:
        """获取追踪信息"""
        spans = self._spans.get(trace_id, [])
        return [span.to_dict() for span in spans]


# 全局实例
tracer = Tracer()
