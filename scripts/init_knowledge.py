#!/usr/bin/env python3
"""初始化知识库

添加示例知识到 Qdrant 向量数据库
"""

import asyncio
import httpx
import random

# Qdrant 配置
QDRANT_URL = "http://172.177.3.43:6333"
COLLECTION_NAME = "knowledge_base"

# 示例知识
KNOWLEDGE_DATA = [
    {
        "id": "doc-001",
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
        "id": "doc-002",
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
        "id": "doc-003",
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
        "id": "doc-004",
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
        "id": "doc-005",
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


def get_embedding(text: str) -> list[float]:
    """生成文本向量（简单实现）"""
    # 实际项目中应该使用 sentence-transformers
    # 这里使用简单的哈希方法生成伪向量
    import hashlib
    hash_obj = hashlib.md5(text.encode())
    hash_hex = hash_obj.hexdigest()

    # 将哈希转换为向量
    vector = []
    for i in range(0, len(hash_hex), 2):
        val = int(hash_hex[i:i+2], 16) / 255.0
        vector.append(val)

    # 扩展到 384 维
    while len(vector) < 384:
        vector.extend(vector[:384-len(vector)])

    return vector[:384]


async def create_collection():
    """创建向量集合"""
    async with httpx.AsyncClient() as client:
        # 检查集合是否存在
        response = await client.get(f"{QDRANT_URL}/collections/{COLLECTION_NAME}")

        if response.status_code == 200:
            print(f"集合已存在: {COLLECTION_NAME}")
            return True

        # 创建集合
        response = await client.put(
            f"{QDRANT_URL}/collections/{COLLECTION_NAME}",
            json={
                "vectors": {
                    "size": 384,
                    "distance": "Cosine",
                },
            },
        )

        if response.status_code == 200:
            print(f"集合创建成功: {COLLECTION_NAME}")
            return True
        else:
            print(f"集合创建失败: {response.status_code}")
            return False


async def add_documents():
    """添加文档到知识库"""
    async with httpx.AsyncClient() as client:
        points = []
        for doc in KNOWLEDGE_DATA:
            vector = get_embedding(doc["content"])
            points.append({
                "id": doc["id"],
                "vector": vector,
                "payload": {
                    "title": doc["title"],
                    "content": doc["content"],
                    "category": doc["category"],
                },
            })

        response = await client.put(
            f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points",
            json={"points": points},
        )

        if response.status_code == 200:
            print(f"文档添加成功: {len(points)} 条")
            return True
        else:
            print(f"文档添加失败: {response.status_code}")
            return False


async def main():
    """主函数"""
    print("初始化知识库...")

    # 创建集合
    if not await create_collection():
        return

    # 添加文档
    if not await add_documents():
        return

    print("知识库初始化完成!")


if __name__ == "__main__":
    asyncio.run(main())
