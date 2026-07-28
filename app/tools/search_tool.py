"""Search Tool - 向量检索工具

职责：
- 文本向量化
- 向量相似度检索
- 知识库管理
"""

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Qdrant 配置
QDRANT_URL = "http://172.177.3.43:6333"
COLLECTION_NAME = "knowledge_base"


class SearchTool:
    """向量检索工具"""

    def __init__(self):
        self.qdrant_url = QDRANT_URL
        self.collection_name = COLLECTION_NAME

    async def execute(
        self,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None,
    ) -> dict:
        """执行向量检索

        Args:
            query: 查询文本
            top_k: 返回结果数量
            category: 知识类别过滤

        Returns:
            dict: 检索结果
        """
        try:
            # 1. 将查询文本转换为向量
            query_vector = await self._get_embedding(query)

            # 2. 在 Qdrant 中检索相似向量
            results = await self._search_vectors(query_vector, top_k, category)

            # 3. 格式化结果
            chunks = []
            for result in results:
                chunks.append({
                    "id": result.get("id"),
                    "title": result.get("payload", {}).get("title", ""),
                    "content": result.get("payload", {}).get("content", ""),
                    "category": result.get("payload", {}).get("category", ""),
                    "score": result.get("score", 0),
                })

            return {
                "status": "ok",
                "chunks": chunks,
                "query": query,
                "count": len(chunks),
            }

        except Exception as e:
            logger.error(f"向量检索失败: {e}", exc_info=True)
            return {
                "status": "error",
                "chunks": [],
                "query": query,
                "count": 0,
                "message": f"检索失败: {str(e)}",
            }

    async def _get_embedding(self, text: str) -> list[float]:
        """将文本转换为向量

        使用本地 Embedding 模型或远程 API
        """
        # 这里使用一个简单的实现
        # 实际项目中应该使用 sentence-transformers 或其他 Embedding 模型
        # 例如: text2vec-base-chinese

        # 简单实现：使用随机向量（仅用于测试）
        # 实际项目中应该替换为真正的 Embedding 模型
        import random
        return [random.random() for _ in range(384)]  # 384 维向量

    async def _search_vectors(
        self,
        query_vector: list[float],
        top_k: int,
        category: Optional[str] = None,
    ) -> list[dict]:
        """在 Qdrant 中检索相似向量

        Args:
            query_vector: 查询向量
            top_k: 返回数量
            category: 类别过滤

        Returns:
            list[dict]: 检索结果
        """
        try:
            # 构建检索请求
            search_request = {
                "vector": query_vector,
                "limit": top_k,
                "with_payload": True,
            }

            # 添加过滤条件
            if category:
                search_request["filter"] = {
                    "must": [
                        {
                            "key": "category",
                            "match": {"value": category},
                        }
                    ]
                }

            # 调用 Qdrant API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.qdrant_url}/collections/{self.collection_name}/points/search",
                    json=search_request,
                    timeout=10,
                )

                if response.status_code == 200:
                    result = response.json()
                    return result.get("result", [])
                else:
                    logger.error(f"Qdrant 检索失败: {response.status_code}")
                    return []

        except Exception as e:
            logger.error(f"Qdrant 检索异常: {e}", exc_info=True)
            return []

    async def add_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        category: str,
    ) -> bool:
        """添加文档到知识库

        Args:
            doc_id: 文档 ID
            title: 标题
            content: 内容
            category: 类别

        Returns:
            bool: 是否添加成功
        """
        try:
            # 1. 将文档内容转换为向量
            vector = await self._get_embedding(content)

            # 2. 存储到 Qdrant
            point = {
                "id": doc_id,
                "vector": vector,
                "payload": {
                    "title": title,
                    "content": content,
                    "category": category,
                },
            }

            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.qdrant_url}/collections/{self.collection_name}/points",
                    json={"points": [point]},
                    timeout=10,
                )

                if response.status_code == 200:
                    logger.info(f"文档添加成功: {doc_id}")
                    return True
                else:
                    logger.error(f"文档添加失败: {response.status_code}")
                    return False

        except Exception as e:
            logger.error(f"文档添加异常: {e}", exc_info=True)
            return False

    async def create_collection(self) -> bool:
        """创建向量集合

        Returns:
            bool: 是否创建成功
        """
        try:
            async with httpx.AsyncClient() as client:
                # 检查集合是否存在
                response = await client.get(
                    f"{self.qdrant_url}/collections/{self.collection_name}",
                    timeout=10,
                )

                if response.status_code == 200:
                    logger.info(f"集合已存在: {self.collection_name}")
                    return True

                # 创建集合
                response = await client.put(
                    f"{self.qdrant_url}/collections/{self.collection_name}",
                    json={
                        "vectors": {
                            "size": 384,
                            "distance": "Cosine",
                        },
                    },
                    timeout=10,
                )

                if response.status_code == 200:
                    logger.info(f"集合创建成功: {self.collection_name}")
                    return True
                else:
                    logger.error(f"集合创建失败: {response.status_code}")
                    return False

        except Exception as e:
            logger.error(f"集合创建异常: {e}", exc_info=True)
            return False
