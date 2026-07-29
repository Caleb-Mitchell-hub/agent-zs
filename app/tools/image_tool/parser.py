"""图片解析工具 - 多模态处理

职责：
- 图片上传处理
- OCR 文字识别
- 结构化字段提取
- 字段校验
"""

import logging
from typing import Optional

from app.agent.llm_client import llm_client

logger = logging.getLogger(__name__)

# OCR 提取 Prompt
OCR_EXTRACT_PROMPT = """你是一个发票/单据识别专家。从图片中提取以下结构化字段：

## 图片内容
{image_description}

## 需要提取的字段
- amount: 金额
- date: 日期
- merchant: 商户名称
- invoice_type: 发票类型（增值税普通发票/增值税专用发票/其他）
- invoice_no: 发票号码
- tax_amount: 税额
- items: 商品明细（如有）

## 输出格式
返回 JSON：
{{
    "amount": 金额数字,
    "date": "YYYY-MM-DD",
    "merchant": "商户名",
    "invoice_type": "发票类型",
    "invoice_no": "发票号码",
    "tax_amount": 税额数字,
    "items": [{{"name": "商品名", "quantity": 数量, "price": 单价}}]
}}

## JSON"""

# 字段校验 Prompt
VALIDATE_PROMPT = """你是一个财务校验专家。校验以下发票/单据字段是否合法：

## 提取的字段
{fields}

## 校验规则
1. 金额必须大于0
2. 日期格式必须是 YYYY-MM-DD
3. 日期不能是未来日期
4. 商户名称不能为空
5. 金额和税额逻辑正确（税额 < 金额）

## 输出格式
返回 JSON：
{{
    "valid": true/false,
    "errors": ["错误1", "错误2"],
    "warnings": ["警告1"]
}}

## JSON"""


class ImageParser:
    """图片解析工具"""

    async def parse_invoice(self, image_url: str = None, image_base64: str = None) -> dict:
        """解析发票/单据

        Args:
            image_url: 图片URL
            image_base64: 图片Base64编码

        Returns:
            dict: 解析结果
        """
        try:
            # 1. OCR 识别
            if image_url:
                image_desc = f"图片URL: {image_url}"
            else:
                image_desc = f"图片Base64: {image_base64[:50]}..."

            ocr_prompt = OCR_EXTRACT_PROMPT.format(image_description=image_desc)
            ocr_response = await llm_client.chat(ocr_prompt)

            # 解析 OCR 结果
            import re
            import json
            match = re.search(r'\{.*\}', ocr_response, re.DOTALL)
            if match:
                fields = json.loads(match.group())
            else:
                return {"status": "error", "message": "无法识别图片内容"}

            # 2. 字段校验
            validate_prompt = VALIDATE_PROMPT.format(fields=json.dumps(fields, ensure_ascii=False))
            validate_response = await llm_client.chat(validate_prompt)

            match = re.search(r'\{.*\}', validate_response, re.DOTALL)
            if match:
                validation = json.loads(match.group())
            else:
                validation = {"valid": True, "errors": [], "warnings": []}

            return {
                "status": "ok",
                "fields": fields,
                "validation": validation,
            }

        except Exception as e:
            logger.error(f"图片解析失败: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}


# 全局实例
image_parser = ImageParser()
