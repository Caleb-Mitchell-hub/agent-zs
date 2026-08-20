"""知识库服务纯函数单元测试（不连数据库 / Milvus / Redis）

覆盖 normalize_question 与 chunk_text 两个可独立验证的纯函数。
"""

from app.services.knowledge_service import normalize_question, chunk_text


# ============================================================
# normalize_question：问题归一化
# ============================================================

def test_normalize_strips_whitespace_and_punctuation():
    """去首尾空白 + 去句末标点"""
    assert normalize_question("  如何退货？  ") == "如何退货"
    assert normalize_question("退款流程。") == "退款流程"


def test_normalize_collapses_inner_whitespace():
    """连续空白合并为单个空格"""
    assert normalize_question("如何\t\t退货\n流程") == "如何 退货 流程"


def test_normalize_lowercases_english():
    """英文转小写"""
    assert normalize_question("How To REFUND?") == "how to refund"


def test_normalize_empty_input():
    """空输入 / 纯空白返回空串"""
    assert normalize_question("") == ""
    assert normalize_question("   ") == ""


def test_normalize_keeps_chinese_content():
    """中文内容不被破坏"""
    assert normalize_question("采购订单怎么审批") == "采购订单怎么审批"


# ============================================================
# chunk_text：文档切块
# ============================================================

def test_chunk_empty_or_whitespace():
    """空内容返回空列表"""
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_short_text_single_chunk():
    """短文本切为单个片段"""
    result = chunk_text("这是很短的一段文本")
    assert len(result) == 1
    assert result[0] == "这是很短的一段文本"


def test_chunk_merges_short_paragraphs():
    """多个短段落聚合到一个片段"""
    result = chunk_text("第一段。\n\n第二段。\n\n第三段。", chunk_size=500)
    assert len(result) == 1
    assert "第一段" in result[0] and "第三段" in result[0]


def test_chunk_long_text_split_within_limit():
    """超长文本切分后每段不超过 chunk_size"""
    # 构造一段超过 chunk_size 的文本（含句号边界）
    sentence = "这是用于测试知识库切块逻辑的一个标准句子。"
    content = sentence * 40  # 明显超过 chunk_size=100
    result = chunk_text(content, chunk_size=100)
    assert result
    for c in result:
        assert len(c) <= 100
    # 内容不丢失（拼接后包含全部句号句）
    assert "".join(result).count("标准句子") == 40


def test_chunk_normalizes_crlf():
    """统一换行符（\r\n 视为换行）"""
    result = chunk_text("第一段\r\n\r\n第二段")
    assert len(result) >= 1
    assert "第一段" in result[0]
