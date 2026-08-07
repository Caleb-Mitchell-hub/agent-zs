"""正则记忆抽取测试

验证：记忆抽取使用正则规则而非 LLM，确定性抽取偏好/事实/习惯。
"""

import pytest

from app.memory.extractor import EXTRACT_PATTERNS


class TestExtractPatterns:
    """测试正则模式能匹配对应记忆类型"""

    def test_preference_pattern(self):
        """每个偏好模式都应能匹配对应的表达"""
        import re
        samples = {
            "我喜欢用表格展示数据": EXTRACT_PATTERNS["preference"][0],
            "我习惯用表格展示": EXTRACT_PATTERNS["preference"][1],
            "请按老规矩报销": EXTRACT_PATTERNS["preference"][2],
            "按老规矩报销": EXTRACT_PATTERNS["preference"][3],
        }
        for text, pattern in samples.items():
            assert re.search(pattern, text), f"模式 {pattern} 未匹配: {text}"

    def test_fact_pattern(self):
        import re
        assert re.search(EXTRACT_PATTERNS["fact"][0], "我的部门是财务部")

    def test_habit_pattern(self):
        import re
        assert re.search(EXTRACT_PATTERNS["habit"][0], "每月月初出报表")

    def test_no_false_positive_irrelevant_text(self):
        """测试无关文本不匹配任何模式"""
        import re
        text = "请帮我查询一下仓库的库存情况"
        for patterns in EXTRACT_PATTERNS.values():
            for pattern in patterns:
                assert not re.search(pattern, text), f"误匹配: {pattern}"

    def test_patterns_cover_all_types(self):
        assert set(EXTRACT_PATTERNS.keys()) == {"preference", "fact", "habit"}


@pytest.mark.asyncio
async def test_extract_and_save_writes_preferences(monkeypatch):
    """测试 extract_and_save 调用 user_memory 保存匹配到的记忆"""
    from app.memory import extractor

    saved = []

    class FakeUserMemory:
        async def update_user_preferences(self, user_id, preferences):
            saved.append((user_id, preferences))

    monkeypatch.setattr(extractor.user_memory, "update_user_preferences", FakeUserMemory().update_user_preferences)

    conversation = "用户: 我喜欢用表格展示数据\nAI: 好的"
    await extractor.memory_extractor.extract_and_save(conversation, "1", "1", "sess-1")

    assert len(saved) == 1
    user_id, prefs = saved[0]
    assert user_id == "1"
    assert prefs["memory_type"] == "preference"
    assert "表格" in prefs["content"]
    assert prefs["source_session"] == "sess-1"


@pytest.mark.asyncio
async def test_extract_and_save_no_match_does_nothing(monkeypatch):
    """测试无匹配内容时不写入任何记忆"""
    from app.memory import extractor

    saved = []

    class FakeUserMemory:
        async def update_user_preferences(self, user_id, preferences):
            saved.append(preferences)

    monkeypatch.setattr(extractor.user_memory, "update_user_preferences", FakeUserMemory().update_user_preferences)

    conversation = "用户: 帮我查询一下库存\nAI: 查询到 5 条记录"
    await extractor.memory_extractor.extract_and_save(conversation, "1", "1", "sess-1")

    assert len(saved) == 0
