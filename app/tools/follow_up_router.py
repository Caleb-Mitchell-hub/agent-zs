"""多轮追问一致性路由（确定性判断）

设计文档 §5.3 必须项：多轮追问时，"复用上次结果"还是"强制重新查询"，
必须由代码规则决定，不由 LLM 自行判断。

判断规则：
- 若追问信息已完整包含在上次工具调用的结构化结果里 → 直接基于结果组织回复，不重新查询
- 若追问涉及新的查询条件（换了地名/SKU/时间/单据类型等）→ 强制重新触发真实查询

判断依据是完全确定性的关键词/代词分析，零 LLM 调用。
"""

import re
import logging

logger = logging.getLogger(__name__)

# 触发"强制重新查询"的条件词：出现了这些词说明查询条件有变化
# 注意：这些词表示"新的维度/对象"，与上次查询不同
CHANGED_CONDITION_MARKERS = [
    "北京", "上海", "广州", "深圳", "杭州", "南京", "武汉", "成都",
    "天津", "重庆", "苏州", "西安", "长沙", "青岛", "大连", "宁波",
    "厦门", "福州", "合肥", "郑州", "济南", "沈阳", "长春", "哈尔滨",
    "其他", "别的", "另一个", "换个",
    "增加", "加上", "改为", "换成", "加", "减去",
    "这个月", "上月", "本月", "今年", "去年", "近7天", "近30天",
    "本季度", "上季度",
]

# 引用上次查询的省略/代词：这些词表示"沿用上次条件"，应复用结果
# 注意：不含"所有/全部/总共/一共"——它们常出现在全新查询里，不一定是引用上次
REFER_BACK_MARKERS = [
    "刚才", "上次", "刚才那", "之前那", "那个", "这些", "这条",
    "上面的", "如下",
]

# 纯查询修饰词（只看结果，不换条件）
LOOKUP_MODIFIERS = [
    "多少", "数量", "总共有", "总共", "一共", "还有",
    "分别是", "分别", "统计", "汇总", "合计", "看看",
]

# 全新查询指示词：出现这些词表示用户发起了一个新的查询请求，而非追问上次结果
# 注意：这些词与 REFER_BACK_MARKERS 互斥 —— 前者是"新的"，后者是"引用旧的"
NEW_QUERY_SIGNALS = [
    "查询", "查一下", "查查", "帮我查", "搜索",
    "所有", "全部", "列出", "显示", "看看",
    "有没有", "有哪些", "在哪", "什么时候",
]


def is_follow_up(user_input: str, context: dict) -> bool:
    """判断当前输入是否为追问（依赖上次查询结果）

    判定标准：
    - 会话 context 里有上次查询结果 last_result，且结果非空
    - 当前输入是短句、省略句或含代词

    Args:
        user_input: 当前用户输入
        context: 会话上下文

    Returns:
        bool: 是否为追问
    """
    last_result = context.get("last_result")
    if not last_result:
        return False

    # 上次查询结果为空 → 不存在可复用的数据，直接走重新查询
    if isinstance(last_result, dict):
        data = last_result.get("data")
        if not data or (isinstance(data, list) and len(data) == 0):
            return False

    # 明确创建/写操作信号 → 不是追问
    create_signals = ["新增", "创建", "新建", "下单", "开单", "建单"]
    if any(s in user_input for s in create_signals):
        return False

    # 全新查询指示词 → 用户发起了一个新查询，不是追问
    if any(signal in user_input for signal in NEW_QUERY_SIGNALS):
        return False

    # 追问通常是短句（≤12字），或含引用词
    # 阈值从 20 降到 12：太长大概率是新查询而非追问
    if len(user_input) <= 12:
        return True

    # 包含引用上次查询的词
    if any(marker in user_input for marker in REFER_BACK_MARKERS):
        return True

    return False


def should_reuse_result(user_input: str, context: dict) -> bool:
    """判断追问是否可以复用上次结果（确定性）

    返回 True 表示：上次查询结果已完整包含答案，直接基于 last_result 组织回复。
    返回 False 表示：涉及新查询条件，必须重新触发真实查询。

    Args:
        user_input: 当前用户输入
        context: 会话上下文

    Returns:
        bool: 是否复用上次结果
    """
    if not is_follow_up(user_input, context):
        return False

    # 出现新查询条件词 → 必须重新查询（如"北京呢"、"换成上海"、"上月呢"）
    if any(marker in user_input for marker in CHANGED_CONDITION_MARKERS):
        return False

    # 纯结果查看（"总共多少"、"有哪些"）且无新条件 → 可复用
    if any(marker in user_input for marker in LOOKUP_MODIFIERS) or any(
        marker in user_input for marker in REFER_BACK_MARKERS
    ):
        return True

    # 默认：只有明确引用上次且无新条件的短句才复用
    return len(user_input) <= 6


def compose_reuse_reply(user_input: str, context: dict) -> dict:
    """基于上次结构化结果组织回复（确定性模板）

    Args:
        user_input: 当前用户输入
        context: 会话上下文（含 last_result）

    Returns:
        dict: 回复结果
    """
    last_result = context.get("last_result", {})
    rows = last_result.get("data") or []
    last_query = context.get("last_query", "")

    # 防御：should_reuse_result 已保证数据非空，此处兜底
    if not rows:
        return {
            "status": "error",
            "message": "无法复用上次查询结果，请重新描述您的查询需求",
            "reused": False,
        }

    # 简单汇总：展示上次查询的全部结果
    row_count = len(rows)
    first_keys = list(rows[0].keys()) if rows else []
    fields = "、".join(first_keys[:5])

    return {
        "status": "ok",
        "data": rows,
        "sql": last_result.get("sql"),
        "message": f"这是上次查询（{last_query}）的结果，共 {row_count} 条，包含字段: {fields}",
        "reused": True,
    }
