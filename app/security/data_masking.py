"""数据脱敏

职责：
- 敏感字段识别
- 数据脱敏处理
- 日志脱敏
"""

import re
import logging

logger = logging.getLogger(__name__)


class DataMasking:
    """数据脱敏工具"""

    # 敏感字段模式
    SENSITIVE_PATTERNS = {
        "phone": (r'1[3-9]\d{9}', lambda m: m.group()[:3] + "****" + m.group()[-4:]),
        "id_card": (r'\d{17}[\dXx]', lambda m: m.group()[:6] + "********" + m.group()[-4:]),
        "bank_card": (r'\d{16,19}', lambda m: m.group()[:4] + " **** **** " + m.group()[-4:]),
        "email": (r'[\w.]+@[\w.]+\.\w+', lambda m: m.group()[:2] + "***@" + m.group().split("@")[1]),
    }

    def mask_sensitive_data(self, data: dict) -> dict:
        """脱敏敏感数据

        Args:
            data: 原始数据

        Returns:
            dict: 脱敏后的数据
        """
        masked_data = {}

        for key, value in data.items():
            if isinstance(value, str):
                masked_data[key] = self._mask_string(value)
            elif isinstance(value, dict):
                masked_data[key] = self.mask_sensitive_data(value)
            elif isinstance(value, list):
                masked_data[key] = [
                    self.mask_sensitive_data(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                masked_data[key] = value

        return masked_data

    def _mask_string(self, text: str) -> str:
        """脱敏字符串"""
        masked = text

        for pattern_name, (pattern, mask_fn) in self.SENSITIVE_PATTERNS.items():
            regex = re.compile(pattern)
            masked = regex.sub(mask_fn, masked)

        return masked

    def mask_for_log(self, data: dict) -> dict:
        """为日志脱敏

        Args:
            data: 原始数据

        Returns:
            dict: 脱敏后的数据
        """
        return self.mask_sensitive_data(data)

    def is_sensitive_field(self, field_name: str) -> bool:
        """判断是否为敏感字段

        Args:
            field_name: 字段名

        Returns:
            bool: 是否敏感
        """
        sensitive_keywords = [
            "password", "pwd", "secret", "token", "key",
            "phone", "mobile", "id_card", "bank_card", "email",
        ]

        field_lower = field_name.lower()
        return any(keyword in field_lower for keyword in sensitive_keywords)


# 全局实例
data_masking = DataMasking()
