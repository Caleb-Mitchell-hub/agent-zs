#!/usr/bin/env python3
"""初始化知识库

添加示例知识到 Milvus 向量数据库
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pymilvus import MilvusClient
from app.config import settings

MILVUS_HOST = settings.milvus_host
MILVUS_PORT = settings.milvus_port
MILVUS_URI = f"http://{MILVUS_HOST}:{MILVUS_PORT}"
COLLECTION_NAME = settings.milvus_collection
VECTOR_DIM = settings.milvus_dim

FIELD_ID = "id"
FIELD_DOC_ID = "doc_id"
FIELD_VECTOR = "vector"
FIELD_TITLE = "title"
FIELD_CONTENT = "content"
FIELD_CATEGORY = "category"

KNOWLEDGE_DATA = [
    {
        "doc_id": "doc-001",
        "title": "采购订单创建流程",
        "content": """采购订单创建流程：

1. 进入采购管理模块
2. 点击"新建采购订单"
3. 选择供应商（必填）
4. 选择仓库（必填）
5. 选择订单日期（必填）
6. 添加采购商品和数量
7. 填写备注信息（可选）
8. 点击"保存"按钮

注意事项：
- 供应商必须是已审核状态
- 仓库必须是启用状态
- 采购数量不能为0
- 保存后可以提交审批""",
        "category": "manual",
    },
    {
        "doc_id": "doc-002",
        "title": "销售订单审批规则",
        "content": """销售订单审批规则：

1. 金额小于10000元：自动审批
2. 金额10000-50000元：部门经理审批
3. 金额大于50000元：总经理审批

审批流程：
1. 销售人员创建订单
2. 提交审批
3. 审批人审核
4. 审批通过/驳回

特殊规则：
- 新客户首单必须人工审批
- 超信用额度订单必须人工审批
- 特殊商品需要专项审批""",
        "category": "rule",
    },
    {
        "doc_id": "doc-003",
        "title": "库存查询方法",
        "content": """库存查询方法：

1. 进入库存管理模块
2. 选择查询方式：
   - 按商品名称查询
   - 按SKU编码查询
   - 按仓库查询
   - 按商品分类查询

3. 设置查询条件：
   - 库存状态（正常/预警/缺货）
   - 库存数量范围
   - 最后入库时间

4. 点击"查询"按钮

5. 导出结果：
   - 支持导出Excel
   - 支持导出PDF""",
        "category": "faq",
    },
    {
        "doc_id": "doc-004",
        "title": "入库操作规范",
        "content": """入库操作规范：

1. 核对采购订单
   - 检查订单号是否正确
   - 确认供应商信息

2. 检验商品质量
   - 检查商品外观
   - 核对商品数量
   - 检查商品质量

3. 录入入库信息
   - 选择入库仓库
   - 录入实际入库数量
   - 填写质检结果

4. 确认入库
   - 确认信息无误
   - 点击"确认入库"

5. 打印入库单
   - 打印入库单据
   - 存档备查""",
        "category": "manual",
    },
    {
        "doc_id": "doc-005",
        "title": "出库操作规范",
        "content": """出库操作规范：

1. 核对销售订单
   - 检查订单号是否正确
   - 确认客户信息

2. 拣货
   - 根据订单拣货
   - 核对商品和数量

3. 复核
   - 复核商品信息
   - 确认数量正确

4. 录入出库信息
   - 选择出库仓库
   - 录入实际出库数量
   - 填写物流信息

5. 确认出库
   - 确认信息无误
   - 点击"确认出库"

6. 打印出库单
   - 打印出库单据
   - 存档备查""",
        "category": "manual",
    },
]


async def main():
    """主函数"""
    print(f"初始化知识库（Milvus {MILVUS_URI}）...")

    client = MilvusClient(uri=MILVUS_URI)

    # 删除旧集合（如有 schema 冲突）
    if client.has_collection(COLLECTION_NAME):
        stats = client.get_collection_stats(COLLECTION_NAME)
        row_count = stats.get("row_count", 0)
        if row_count > 0:
            print(f"集合中已有 {row_count} 条数据，跳过初始化")
            return
        # 空集合，删除后重建
        client.drop_collection(COLLECTION_NAME)
        print("已删除空集合，准备重建")

    # 创建集合（auto_id=True，Milvus 自动生成 int64 主键）
    client.create_collection(
        collection_name=COLLECTION_NAME,
        dimension=VECTOR_DIM,
        metric_type="COSINE",
        auto_id=True,
        primary_field_name=FIELD_ID,
    )
    client.load_collection(COLLECTION_NAME)
    print(f"集合创建成功: {COLLECTION_NAME}，维度={VECTOR_DIM}")

    # 添加文档（零向量占位）
    data = []
    for doc in KNOWLEDGE_DATA:
        data.append({
            FIELD_DOC_ID: doc["doc_id"],
            FIELD_VECTOR: [0.0] * VECTOR_DIM,
            FIELD_TITLE: doc["title"],
            FIELD_CONTENT: doc["content"],
            FIELD_CATEGORY: doc["category"],
        })

    result = client.insert(COLLECTION_NAME, data)
    count = result.get("insert_count", 0)
    print(f"文档添加成功: {count} 条（零向量占位，配置 Embedding API 后需重新向量化）")
    print("知识库初始化完成!")


if __name__ == "__main__":
    asyncio.run(main())
