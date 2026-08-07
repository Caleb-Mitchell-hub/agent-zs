"""RAG 确定性排序测试

验证：知识检索结果用分数排序而非 LLM 重排序。
"""

import pytest

from app.tools.rag_tool import _split_keywords, _score_chunk


class TestSplitKeywords:
    def test_splits_by_space_and_comma(self):
        assert set(_split_keywords("报销 流程,说明")) == {"报销", "流程", "说明", "报销 流程,说明"}

    def test_whole_query_included(self):
        kws = _split_keywords("采购审批流程")
        assert "采购审批流程" in kws


class TestScoreChunk:
    def test_score_combines_relevance_and_overlap(self):
        chunk = {
            "title": "采购审批流程",
            "content": "采购审批需要提交申请",
            "score": 0.8,
        }
        score = _score_chunk("采购 审批", chunk)
        # relevance_score*0.5 + 重合度
        assert score >= 0.4 + 1

    def test_no_overlap_gets_base_score(self):
        chunk = {"title": "无关内容", "content": "完全不相关", "score": 0.5}
        score = _score_chunk("报销流程", chunk)
        assert score == 0.25  # 0.5 * 0.5

    def test_higher_relevance_with_overlap_outranks(self):
        """验证：关键词重合可以提升排序"""
        a = {"title": "采购流程说明", "content": "采购", "score": 0.5}
        b = {"title": "报销流程说明", "content": "报销", "score": 0.9}
        # 查询"采购"时，a 有重合应排前面
        assert _score_chunk("采购", a) > _score_chunk("采购", b)
