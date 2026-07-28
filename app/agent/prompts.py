"""Prompt 模板

管理所有 LLM 提示词模板。
"""

# NL-to-SQL 转换 prompt
NL_TO_SQL_PROMPT = """你是一个 SQL 专家。根据用户的自然语言问题，结合数据库 schema，生成正确的 MySQL SQL 语句。

## 数据库 Schema

{schema}

## 用户问题

{question}

## 要求

1. 只返回 SQL 语句，不要解释
2. 使用 MySQL 语法
3. 确保 SQL 语句可以直接执行
4. 如果需要多表关联，使用正确的 JOIN 条件
5. 如果涉及日期计算，使用 MySQL 的日期函数
6. 如果问题不明确，返回: CLARIFY: <需要澄清的问题>

## SQL"""

# 报表生成 prompt
REPORT_PROMPT = """你是一个报表专家。根据用户的自然语言描述，生成结构化报表。

## 数据库 Schema

{schema}

## 用户描述

{question}

## 要求

1. 返回 JSON 格式：{{"title": "...", "sql": "...", "columns": [...]}}
2. title: 报表标题
3. sql: 查询 SQL
4. columns: 列定义数组，每个元素包含 "name"、"label"、"type"
5. 使用 MySQL 语法

## JSON"""

# SQL 验证 prompt
SQL_VALIDATE_PROMPT = """检查以下 SQL 语句是否安全且正确。

## SQL

{sql}

## 要求

1. 检查是否只包含 SELECT 语句
2. 检查是否有 SQL 注入风险
3. 检查语法是否正确

返回 JSON: {{"safe": true/false, "reason": "..."}}"""

# 结果解释 prompt
EXPLAIN_PROMPT = """用简洁的中文解释以下查询结果。

## 用户问题

{question}

## 查询结果

{result}

## 要求

用 1-2 句话总结查询结果，让用户快速理解。"""
