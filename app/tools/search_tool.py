"""Search Tool - 向量检索工具（Milvus）

职责：
- 文本向量化（调用远程 Embedding API）
- 向量相似度检索（Milvus）
- 关键词检索（Milvus scalar 字段匹配）
- 混合检索 + RRF 融合
- 知识库管理（增/查/建集合）
"""

import logging
from typing import Optional

from pymilvus import MilvusClient

from app.config import settings

logger = logging.getLogger(__name__)

# 集合字段名
FIELD_ID = "id"             # 主键，auto_id=True时自动生成 int64
FIELD_DOC_ID = "doc_id"     # 业务文档ID（如 doc-001）
FIELD_VECTOR = "vector"
FIELD_TITLE = "title"
FIELD_CONTENT = "content"
FIELD_CATEGORY = "category"


class SearchTool:
    """向量检索工具（Milvus 后端）"""

    def __init__(self):
        self.host = settings.milvus_host
        self.port = settings.milvus_port
        self.collection_name = settings.milvus_collection
        self.dim = settings.milvus_dim
        self._client: Optional[MilvusClient] = None

    def _get_client(self) -> MilvusClient:
        """获取 Milvus 客户端（惰性初始化）"""
        if self._client is None:
            uri = f"http://{self.host}:{self.port}"
            self._client = MilvusClient(uri=uri)
            logger.info(f"Milvus 客户端已连接: {uri}")
        return self._client

    # ─────────────────── 公共接口 ───────────────────

    async def execute(
        self,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None,
    ) -> dict:
        """混合检索（向量 + 关键词），RRF 融合"""
        try:
            await self.create_collection()

            query_vector = await self._get_embedding(query)
            vector_results = await self._search_vectors(query_vector, top_k * 2, category)
            keyword_results = await self._keyword_search(query, top_k * 2, category)
            merged = self._reciprocal_rank_fusion(vector_results, keyword_results, top_k)

            chunks = []
            for result in merged:
                chunks.append({
                    "id": result.get(FIELD_DOC_ID, result.get(FIELD_ID)),
                    "title": result.get(FIELD_TITLE, ""),
                    "content": result.get(FIELD_CONTENT, ""),
                    "category": result.get(FIELD_CATEGORY, ""),
                    "score": result.get("score", 0),
                })

            return {
                "status": "ok",
                "chunks": chunks,
                "query": query,
                "count": len(chunks),
            }

        except Exception as e:
            logger.error(f"混合检索失败: {e}", exc_info=True)
            return {
                "status": "error",
                "chunks": [],
                "query": query,
                "count": 0,
                "message": f"检索失败: {str(e)}",
            }

    async def add_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        category: str,
    ) -> bool:
        """添加文档到知识库"""
        try:
            vector = await self._get_embedding(content)
            client = self._get_client()

            data = [{
                FIELD_DOC_ID: doc_id,
                FIELD_VECTOR: vector,
                FIELD_TITLE: title,
                FIELD_CONTENT: content,
                FIELD_CATEGORY: category,
            }]

            result = client.insert(self.collection_name, data)
            logger.info(f"文档添加成功: {doc_id}，insert_count={result.get('insert_count', 0)}")
            return True

        except Exception as e:
            logger.error(f"文档添加失败: {e}", exc_info=True)
            return False

    async def create_collection(self) -> bool:
        """创建向量集合（幂等）"""
        try:
            client = self._get_client()

            if client.has_collection(self.collection_name):
                return True

            client.create_collection(
                collection_name=self.collection_name,
                dimension=self.dim,
                metric_type="COSINE",
                auto_id=True,  # Milvus 自动生成 int64 主键
                primary_field_name=FIELD_ID,
            )

            client.load_collection(self.collection_name)
            logger.info(f"集合创建成功: {self.collection_name}，维度={self.dim}")
            return True

        except Exception as e:
            logger.error(f"集合创建失败: {e}", exc_info=True)
            return False

    # ─────────────────── 内部方法 ───────────────────

    async def _get_embedding(self, text: str) -> list[float]:
        """调用 Embedding API 将文本转为向量"""
        api_url = settings.embedding_api_url
        api_key = settings.embedding_api_key
        model = settings.embedding_model

        if not api_url or not api_key:
            logger.warning("Embedding API 未配置，使用零向量占位")
            return [0.0] * self.dim

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    api_url,
                    json={"model": model, "input": text, "encoding_format": "float"},
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30,
                )
                if response.status_code == 200:
                    data = response.json()
                    embedding = data.get("data", [{}])[0].get("embedding", [])
                    if embedding:
                        return embedding

                logger.warning(f"Embedding API 返回异常: {response.status_code}")

        except Exception as e:
            logger.warning(f"Embedding API 调用失败: {e}")

        return [0.0] * self.dim

    async def _search_vectors(
        self,
        query_vector: list[float],
        top_k: int,
        category: Optional[str] = None,
    ) -> list[dict]:
        """Milvus 向量相似度检索"""
        try:
            client = self._get_client()

            filter_expr = None
            if category:
                filter_expr = f'{FIELD_CATEGORY} == "{category}"'

            results = client.search(
                collection_name=self.collection_name,
                data=[query_vector],
                limit=top_k,
                filter=filter_expr,
                output_fields=[FIELD_ID, FIELD_DOC_ID, FIELD_TITLE, FIELD_CONTENT, FIELD_CATEGORY],
            )

            hits = []
            for hit in results[0]:
                entity = hit.get("entity", hit)
                hits.append({
                    FIELD_ID: entity.get(FIELD_ID),
                    FIELD_DOC_ID: entity.get(FIELD_DOC_ID),
                    FIELD_TITLE: entity.get(FIELD_TITLE),
                    FIELD_CONTENT: entity.get(FIELD_CONTENT),
                    FIELD_CATEGORY: entity.get(FIELD_CATEGORY),
                    "score": float(hit.get("distance", 0)),
                })

            return hits

        except Exception as e:
            logger.error(f"向量检索失败: {e}", exc_info=True)
            return []

    async def _keyword_search(
        self,
        query: str,
        top_k: int,
        category: Optional[str] = None,
    ) -> list[dict]:
        """关键词检索：content LIKE 匹配"""
        try:
            client = self._get_client()

            keywords = [kw for kw in query.replace("，", ",").split(",")
                        if len(kw.strip()) >= 2]
            if not keywords:
                keywords = [query]

            all_hits: dict[str, dict] = {}

            for kw in keywords[:3]:
                expr = f'{FIELD_CONTENT} like "%{kw.strip()}%"'
                if category:
                    expr += f' and {FIELD_CATEGORY} == "{category}"'

                try:
                    results = client.query(
                        collection_name=self.collection_name,
                        filter=expr,
                        output_fields=[FIELD_ID, FIELD_DOC_ID, FIELD_TITLE, FIELD_CONTENT, FIELD_CATEGORY],
                        limit=top_k,
                    )

                    for row in results:
                        doc_id = row.get(FIELD_DOC_ID)
                        if doc_id and doc_id not in all_hits:
                            all_hits[doc_id] = {
                                FIELD_ID: row.get(FIELD_ID),
                                FIELD_DOC_ID: doc_id,
                                FIELD_TITLE: row.get(FIELD_TITLE, ""),
                                FIELD_CONTENT: row.get(FIELD_CONTENT, ""),
                                FIELD_CATEGORY: row.get(FIELD_CATEGORY, ""),
                                "score": 0.5,
                            }
                except Exception as e:
                    logger.debug(f"关键词检索跳过（{kw[:20]}）: {e}")

            return list(all_hits.values())

        except Exception as e:
            logger.warning(f"关键词检索失败: {e}")
            return []

    def _reciprocal_rank_fusion(
        self,
        vector_results: list[dict],
        keyword_results: list[dict],
        top_k: int,
    ) -> list[dict]:
        """RRF 融合算法"""
        scores: dict[str, dict] = {}

        for rank, result in enumerate(vector_results):
            doc_id = result.get(FIELD_DOC_ID) or str(result.get(FIELD_ID))
            if doc_id not in scores:
                scores[doc_id] = result
                scores[doc_id]["score"] = 0
            scores[doc_id]["score"] += 1.0 / (60 + rank)

        for rank, result in enumerate(keyword_results):
            doc_id = result.get(FIELD_DOC_ID) or str(result.get(FIELD_ID))
            if doc_id not in scores:
                scores[doc_id] = result
                scores[doc_id]["score"] = 0
            scores[doc_id]["score"] += 1.0 / (60 + rank)

        sorted_results = sorted(
            scores.values(), key=lambda x: x["score"], reverse=True
        )

        return sorted_results[:top_k]
