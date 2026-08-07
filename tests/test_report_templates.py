"""报表模板优先测试

验证：高频报表命中预置模板，参数化生成 SQL，日期参数防注入。
"""

import pytest

from app.tools.report_templates import report_template_engine
from app.agents.report_agent import _parse_date_range


class TestTemplateMatch:
    def test_match_sales_summary(self):
        t = report_template_engine.match_template("生成销售汇总报表")
        assert t is not None
        assert t["name"] == "销售汇总报表"

    def test_match_inventory_status(self):
        t = report_template_engine.match_template("各仓库库存状态")
        assert t is not None
        assert t["name"] == "库存状态报表"

    def test_no_match_returns_none(self):
        assert report_template_engine.match_template("今天天气怎么样") is None


class TestGenerateSql:
    def test_generate_sql_with_valid_dates(self):
        t = report_template_engine.match_template("销售汇总")
        sql = report_template_engine.generate_sql(
            t, {"start_date": "2026-01-01", "end_date": "2026-02-01"}
        )
        assert "2026-01-01" in sql
        assert "2026-02-01" in sql
        assert sql.strip().upper().startswith("SELECT")

    def test_generate_sql_rejects_injection(self):
        t = report_template_engine.match_template("销售汇总")
        with pytest.raises(ValueError):
            report_template_engine.generate_sql(
                t, {"start_date": "2026-01-01' OR 1=1 --", "end_date": "2026-02-01"}
            )

    def test_generate_sql_rejects_bad_format(self):
        t = report_template_engine.match_template("销售汇总")
        with pytest.raises(ValueError):
            report_template_engine.generate_sql(t, {"start_date": "20260101"})


class TestParseDateRange:
    def test_near_days(self):
        start, end = _parse_date_range("近7天")
        assert start < end

    def test_current_month(self):
        start, end = _parse_date_range("本月")
        assert start.endswith("-01")

    def test_default_30_days(self):
        start, end = _parse_date_range("随便说说")
        assert start < end
