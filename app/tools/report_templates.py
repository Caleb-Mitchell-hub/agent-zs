"""报表模板库

职责：
- 预置常用报表模板
- 自然语言匹配模板
- 参数化生成
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# 报表模板
REPORT_TEMPLATES = {
    "sales_summary": {
        "name": "销售汇总报表",
        "description": "按时间维度汇总销售数据",
        "keywords": ["销售", "汇总", "总额"],
        "sql_template": """
            SELECT
                DATE_FORMAT(order_date, '%Y-%m') AS month,
                COUNT(*) AS order_count,
                SUM(total_amount) AS total_amount
            FROM sales_order
            WHERE order_date >= '{start_date}'
              AND order_date < '{end_date}'
              AND (deleted = 0 OR deleted IS NULL)
            GROUP BY DATE_FORMAT(order_date, '%Y-%m')
            ORDER BY month DESC
        """,
        "columns": [
            {"name": "month", "label": "月份", "type": "date"},
            {"name": "order_count", "label": "订单数", "type": "number"},
            {"name": "total_amount", "label": "销售总额", "type": "number"},
        ],
        "chart_type": "bar",
    },
    "inventory_status": {
        "name": "库存状态报表",
        "description": "各仓库库存状态统计",
        "keywords": ["库存", "仓库", "状态"],
        "sql_template": """
            SELECT
                w.warehouse_name,
                COUNT(DISTINCT i.sku_id) AS sku_count,
                SUM(i.quantity) AS total_quantity,
                SUM(i.locked_quantity) AS locked_quantity,
                SUM(i.available_quantity) AS available_quantity
            FROM inventory i
            JOIN warehouse w ON i.warehouse_id = w.id
            GROUP BY w.id, w.warehouse_name
            ORDER BY total_quantity DESC
        """,
        "columns": [
            {"name": "warehouse_name", "label": "仓库", "type": "string"},
            {"name": "sku_count", "label": "SKU数", "type": "number"},
            {"name": "total_quantity", "label": "总库存", "type": "number"},
            {"name": "locked_quantity", "label": "锁定库存", "type": "number"},
            {"name": "available_quantity", "label": "可用库存", "type": "number"},
        ],
        "chart_type": "table",
    },
    "purchase_summary": {
        "name": "采购汇总报表",
        "description": "按供应商汇总采购数据",
        "keywords": ["采购", "供应商", "汇总"],
        "sql_template": """
            SELECT
                supplier_name,
                COUNT(*) AS order_count,
                SUM(total_amount) AS total_amount
            FROM purchase_order
            WHERE order_date >= '{start_date}'
              AND order_date < '{end_date}'
              AND (deleted = 0 OR deleted IS NULL)
            GROUP BY supplier_name
            ORDER BY total_amount DESC
        """,
        "columns": [
            {"name": "supplier_name", "label": "供应商", "type": "string"},
            {"name": "order_count", "label": "订单数", "type": "number"},
            {"name": "total_amount", "label": "采购总额", "type": "number"},
        ],
        "chart_type": "pie",
    },
}


class ReportTemplateEngine:
    """报表模板引擎"""

    def match_template(self, query: str) -> Optional[dict]:
        """根据自然语言匹配报表模板

        Args:
            query: 用户查询

        Returns:
            Optional[dict]: 匹配的模板
        """
        query_lower = query.lower()

        best_match = None
        best_score = 0

        for template_id, template in REPORT_TEMPLATES.items():
            score = 0
            for keyword in template["keywords"]:
                if keyword in query_lower:
                    score += 1

            if score > best_score:
                best_score = score
                best_match = template

        if best_score > 0:
            return best_match
        return None

    def generate_sql(self, template: dict, params: dict) -> str:
        """根据模板生成 SQL

        Args:
            template: 报表模板
            params: 参数

        Returns:
            str: 生成的 SQL
        """
        sql = template["sql_template"]

        # 替换参数
        for key, value in params.items():
            sql = sql.replace(f"{{{key}}}", str(value))

        return sql


# 全局实例
report_template_engine = ReportTemplateEngine()
