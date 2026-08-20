"""多租户知识库管理服务

数据分层（MySQL 为事实源，Milvus/Redis 为可重建索引）：
- MySQL：knowledge_bases / knowledge_documents / knowledge_chunks / faq_pairs / faq_aliases
- Milvus（集合 knowledge_base_v2）：文档切片 + FAQ 向量，带 tenant_id/kb_id/is_active 做租户与状态过滤
- Redis：热点 FAQ 缓存 + 月度命中统计（见 faq_cache.py）

铁律：所有 CRUD 的 SQL WHERE 必须同时携带 tenant_id（租户隔离），
绝不允许只按主键 id 操作。Milvus/Redis 均 try/except 降级，绝不抛异常中断主链路。
"""

import hashlib
import logging
import re
import unicodedata

from sqlalchemy import text

from app.config import settings
from app.tools.search_tool import get_embedding

logger = logging.getLogger(__name__)

# ─────────────────────── 数据库辅助 ───────────────────────


def _get_factory():
    from app.db.session import async_session_factory
    if async_session_factory is None:
        raise RuntimeError("数据库未初始化")
    return async_session_factory


async def _execute_read(sql: str, params: dict = None) -> list[dict]:
    factory = _get_factory()
    async with factory() as session:
        result = await session.execute(text(sql), params or {})
        rows = result.mappings().all()
        return [dict(row) for row in rows]


async def _execute_write(sql: str, params: dict = None) -> int:
    factory = _get_factory()
    async with factory() as session:
        result = await session.execute(text(sql), params or {})
        await session.commit()
        return result.rowcount


async def _insert_get_id(sql: str, params: dict) -> int:
    """执行 INSERT 并返回自增主键。"""
    factory = _get_factory()
    async with factory() as session:
        await session.execute(text(sql), params)
        row = (await session.execute(text("SELECT LAST_INSERT_ID() AS id"))).mappings().one()
        await session.commit()
        return int(row["id"])


# ─────────────────────── Milvus 辅助 ───────────────────────

_milvus_client = None
_milvus_ready = False


def _get_milvus():
    """惰性获取 MilvusClient（同步客户端，参考 search_tool.py 用法）"""
    global _milvus_client
    if _milvus_client is None:
        from pymilvus import MilvusClient
        uri = f"http://{settings.milvus_host}:{settings.milvus_port}"
        _milvus_client = MilvusClient(uri=uri)
        logger.info(f"知识库 Milvus 客户端已连接: {uri}")
    return _milvus_client


def _ensure_collection() -> bool:
    """幂等创建知识库向量集合（带 tenant_id/kb_id/is_active），并确保索引与加载。

    Milvus 集合在 query/search 前必须先 create_index 再 load_collection；
    缺任一步都会报「index not found / collection not loaded」。
    失败返回 False（由调用方降级）。
    """
    global _milvus_ready
    if _milvus_ready:
        return True
    try:
        from pymilvus import DataType
        client = _get_milvus()
        name = settings.knowledge_milvus_collection

        # 1. 集合不存在则创建（仅建 schema，索引与加载单独处理）
        if not client.has_collection(name):
            schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field(field_name="pk", datatype=DataType.VARCHAR, is_primary=True, max_length=128)
            schema.add_field(field_name="tenant_id", datatype=DataType.INT64)
            schema.add_field(field_name="kb_id", datatype=DataType.INT64)
            schema.add_field(field_name="source_type", datatype=DataType.VARCHAR, max_length=16)
            schema.add_field(field_name="source_id", datatype=DataType.INT64)
            schema.add_field(field_name="chunk_index", datatype=DataType.INT64)
            schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=settings.milvus_dim)
            schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=512)
            schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=8192)
            schema.add_field(field_name="answer", datatype=DataType.VARCHAR, max_length=8192)
            schema.add_field(field_name="category", datatype=DataType.VARCHAR, max_length=64)
            schema.add_field(field_name="is_active", datatype=DataType.BOOL)
            client.create_collection(collection_name=name, schema=schema)
            logger.info(f"知识库向量集合创建成功: {name}")

        # 2. 无索引则显式建 HNSW 索引（已存在集合也可能缺索引，需补齐）
        if not client.list_indexes(name):
            index_params = client.prepare_index_params()
            index_params.add_index(
                field_name="vector", index_type="HNSW", metric_type="COSINE",
                params={"M": 16, "efConstruction": 200},
            )
            client.create_index(collection_name=name, index_params=index_params)
            logger.info(f"知识库向量集合索引创建成功: {name}")

        # 3. 加载集合到内存（query/search 前必需）
        client.load_collection(name)
        logger.info(f"知识库向量集合已加载: {name}")

        _milvus_ready = True
        return True
    except Exception as e:
        logger.warning(f"知识库向量集合初始化失败: {e}")
        return False


def _safe(text_val, max_len: int) -> str:
    """截断字符串到 Milvus VARCHAR 安全长度。"""
    if not text_val:
        return ""
    return text_val[:max_len]


async def _delete_milvus_by_filter(filter_expr: str) -> None:
    """按 filter 删除 Milvus 向量（先 query 拿 pk，再按主键 delete）。失败静默降级。"""
    try:
        if not _ensure_collection():
            return
        client = _get_milvus()
        name = settings.knowledge_milvus_collection
        rows = client.query(collection_name=name, filter=filter_expr, output_fields=["pk"])
        pks = [r["pk"] for r in rows]
        if pks:
            client.delete(collection_name=name, ids=pks)
    except Exception as e:
        logger.warning(f"删除 Milvus 向量失败（filter={filter_expr}）: {e}")


# ─────────────────────── 纯函数（可单测） ───────────────────────

_SENTENCE_BOUNDARY = "。！？!?；;"


def normalize_question(text: str) -> str:
    """问题归一化：NFKC 规范化 + 首尾去空白 + 连续空白合并为单个空格 + 英文小写 + 去句末标点。"""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    normalized = normalized.rstrip("。！？!?；;，,. ")
    return normalized


def _split_long_chunk(text: str, chunk_size: int) -> list[str]:
    """超长文本按句子边界切分，仍超长则硬截断。"""
    parts = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            pos = end
            while pos > start and text[pos - 1] not in _SENTENCE_BOUNDARY and text[pos - 1] != "\n":
                pos -= 1
            if pos > start:
                end = pos
        parts.append(text[start:end].strip())
        start = end
    return [p for p in parts if p]


def chunk_text(content: str, chunk_size: int = 500) -> list[str]:
    """轻量切块：统一换行 → 按空行分段 → 短段聚合 → 超长段按句子边界切分。"""
    if not content:
        return []
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]

    merged = []
    buf = ""
    for p in paragraphs:
        if not buf:
            buf = p
        elif len(buf) + len(p) + 1 <= chunk_size:
            buf = f"{buf}\n{p}"
        else:
            merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)

    result = []
    for c in merged:
        if len(c) <= chunk_size:
            result.append(c)
        else:
            result.extend(_split_long_chunk(c, chunk_size))
    return [c for c in result if c.strip()]


# ─────────────────────── 知识库 ───────────────────────


async def list_bases(tenant_id: int) -> list[dict]:
    rows = await _execute_read(
        """
        SELECT b.id, b.name, b.description, b.status, b.embedding_model, b.created_at, b.updated_at,
               (SELECT COUNT(*) FROM knowledge_documents d WHERE d.kb_id = b.id AND d.tenant_id = b.tenant_id) AS doc_count,
               (SELECT COUNT(*) FROM faq_pairs f WHERE f.kb_id = b.id AND f.tenant_id = b.tenant_id) AS faq_count
        FROM knowledge_bases b
        WHERE b.tenant_id = :tid
        ORDER BY b.created_at DESC, b.id DESC
        """,
        {"tid": tenant_id},
    )
    for r in rows:
        r["doc_count"] = int(r.get("doc_count") or 0)
        r["faq_count"] = int(r.get("faq_count") or 0)
    return rows


async def create_base(tenant_id: int, name: str, description: str = "", created_by=None) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("知识库名称不能为空")
    exists = await _execute_read(
        "SELECT id FROM knowledge_bases WHERE tenant_id = :tid AND name = :name LIMIT 1",
        {"tid": tenant_id, "name": name},
    )
    if exists:
        raise ValueError("同名知识库已存在")
    kb_id = await _insert_get_id(
        """
        INSERT INTO knowledge_bases (tenant_id, name, description, status, embedding_model, created_by)
        VALUES (:tid, :name, :desc, 'active', :model, :created_by)
        """,
        {"tid": tenant_id, "name": name, "desc": description or "",
         "model": settings.embedding_model, "created_by": created_by},
    )
    return {"kb_id": kb_id}


async def get_base(tenant_id: int, kb_id: int) -> dict | None:
    rows = await _execute_read(
        "SELECT * FROM knowledge_bases WHERE tenant_id = :tid AND id = :kid",
        {"tid": tenant_id, "kid": kb_id},
    )
    return rows[0] if rows else None


async def update_base(tenant_id: int, kb_id: int, name=None, description=None) -> dict | None:
    base = await get_base(tenant_id, kb_id)
    if base is None:
        return None
    sets, params = [], {"tid": tenant_id, "kid": kb_id}
    if name is not None and name.strip():
        sets.append("name = :name")
        params["name"] = name.strip()
    if description is not None:
        sets.append("description = :desc")
        params["desc"] = description
    if sets:
        await _execute_write(
            f"UPDATE knowledge_bases SET {', '.join(sets)} WHERE tenant_id = :tid AND id = :kid",
            params,
        )
    return await get_base(tenant_id, kb_id)


async def set_base_status(tenant_id: int, kb_id: int, status: str) -> bool:
    if status not in ("active", "disabled"):
        raise ValueError("非法状态")
    affected = await _execute_write(
        "UPDATE knowledge_bases SET status = :status WHERE tenant_id = :tid AND id = :kid",
        {"status": status, "tid": tenant_id, "kid": kb_id},
    )
    if affected > 0:
        from app.services import faq_cache
        await faq_cache.invalidate_kb(tenant_id, kb_id)
    return affected > 0


async def delete_base(tenant_id: int, kb_id: int) -> bool:
    from app.services import faq_cache
    # 删 Milvus 该知识库全部向量
    await _delete_milvus_by_filter(f"tenant_id == {tenant_id} and kb_id == {kb_id}")
    # 级联删 MySQL 各子表
    await _execute_write("DELETE FROM faq_aliases WHERE tenant_id = :tid AND kb_id = :kid", {"tid": tenant_id, "kid": kb_id})
    await _execute_write("DELETE FROM faq_pairs WHERE tenant_id = :tid AND kb_id = :kid", {"tid": tenant_id, "kid": kb_id})
    await _execute_write("DELETE FROM knowledge_chunks WHERE tenant_id = :tid AND kb_id = :kid", {"tid": tenant_id, "kid": kb_id})
    await _execute_write("DELETE FROM knowledge_documents WHERE tenant_id = :tid AND kb_id = :kid", {"tid": tenant_id, "kid": kb_id})
    affected = await _execute_write("DELETE FROM knowledge_bases WHERE tenant_id = :tid AND id = :kid", {"tid": tenant_id, "kid": kb_id})
    if affected > 0:
        await faq_cache.invalidate_kb(tenant_id, kb_id)
    return affected > 0


# ─────────────────────── 文档 ───────────────────────


async def _index_doc_chunks(tenant_id: int, kb_id: int, doc_id: int, title: str, category: str, chunks: list[str]) -> None:
    """逐块向量化 + upsert Milvus，成功标记 indexed，失败标记 failed 并记 index_error。"""
    failed = 0
    for i, chunk in enumerate(chunks):
        vector_id = f"doc:{tenant_id}:{doc_id}:{i}"
        try:
            vector = await get_embedding(chunk, settings.milvus_dim)
            if not _ensure_collection():
                raise RuntimeError("Milvus 集合不可用")
            client = _get_milvus()
            client.upsert(
                collection_name=settings.knowledge_milvus_collection,
                data=[{
                    "pk": vector_id,
                    "tenant_id": tenant_id,
                    "kb_id": kb_id,
                    "source_type": "doc",
                    "source_id": doc_id,
                    "chunk_index": i,
                    "vector": vector,
                    "title": _safe(title, 512),
                    "content": _safe(chunk, 8192),
                    "answer": "",
                    "category": _safe(category, 64),
                    "is_active": True,
                }],
            )
            await _execute_write(
                "UPDATE knowledge_chunks SET index_status = 'indexed', index_error = '', vector_id = :vid WHERE doc_id = :doc_id AND chunk_index = :ci",
                {"vid": vector_id, "doc_id": doc_id, "ci": i},
            )
        except Exception as e:
            failed += 1
            logger.warning(f"文档切片向量化失败（doc={doc_id} chunk={i}）: {e}")
            await _execute_write(
                "UPDATE knowledge_chunks SET index_status = 'failed', index_error = :err WHERE doc_id = :doc_id AND chunk_index = :ci",
                {"err": str(e)[:500], "doc_id": doc_id, "ci": i},
            )

    if failed == 0:
        await _execute_write(
            "UPDATE knowledge_documents SET index_status = 'indexed', index_error = '' WHERE id = :doc_id AND tenant_id = :tid",
            {"doc_id": doc_id, "tid": tenant_id},
        )
    else:
        await _execute_write(
            "UPDATE knowledge_documents SET index_status = 'failed', index_error = :err WHERE id = :doc_id AND tenant_id = :tid",
            {"err": f"{failed} 个切片向量化失败", "doc_id": doc_id, "tid": tenant_id},
        )


async def list_documents(tenant_id: int, kb_id: int, page: int = 1, page_size: int = 20,
                         status: str | None = None, category: str | None = None, keyword: str | None = None) -> dict:
    cond = "tenant_id = :tid AND kb_id = :kid"
    params = {"tid": tenant_id, "kid": kb_id}
    if status:
        cond += " AND status = :status"
        params["status"] = status
    if category:
        cond += " AND category = :category"
        params["category"] = category
    if keyword:
        cond += " AND title LIKE :kw"
        params["kw"] = f"%{keyword}%"

    total = int((await _execute_read(f"SELECT COUNT(*) AS c FROM knowledge_documents WHERE {cond}", params))[0]["c"])
    offset = (page - 1) * page_size
    items = await _execute_read(
        f"""
        SELECT id, kb_id, title, source_type, file_name, category, tags, status, index_status, created_at, updated_at
        FROM knowledge_documents WHERE {cond}
        ORDER BY id DESC LIMIT :limit OFFSET :offset
        """,
        {**params, "limit": page_size, "offset": offset},
    )
    return {"total": total, "items": items}


async def create_document(tenant_id: int, kb_id: int, title: str, content: str, category: str = "",
                          tags: str = "", source_type: str = "text", file_name: str = "", created_by=None) -> dict:
    title = (title or "").strip()
    if not title or not content:
        raise ValueError("文档标题与正文不能为空")
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    doc_id = await _insert_get_id(
        """
        INSERT INTO knowledge_documents (tenant_id, kb_id, title, source_type, file_name, content, content_hash, category, tags, status, index_status, created_by)
        VALUES (:tid, :kid, :title, :st, :fn, :content, :chash, :category, :tags, 'active', 'pending', :created_by)
        """,
        {"tid": tenant_id, "kid": kb_id, "title": title, "st": source_type, "fn": file_name,
         "content": content, "chash": content_hash, "category": category or "", "tags": tags or "",
         "created_by": created_by},
    )

    chunks = chunk_text(content, settings.knowledge_chunk_size)
    for i, chunk in enumerate(chunks):
        await _insert_get_id(
            """
            INSERT INTO knowledge_chunks (tenant_id, kb_id, doc_id, chunk_index, content, content_hash, index_status)
            VALUES (:tid, :kid, :doc_id, :ci, :content, :chash, 'pending')
            """,
            {"tid": tenant_id, "kid": kb_id, "doc_id": doc_id, "ci": i,
             "content": chunk, "chash": hashlib.sha256(chunk.encode("utf-8")).hexdigest()},
        )

    await _execute_write(
        "UPDATE knowledge_documents SET index_status = 'indexing' WHERE id = :doc_id AND tenant_id = :tid",
        {"doc_id": doc_id, "tid": tenant_id},
    )
    await _index_doc_chunks(tenant_id, kb_id, doc_id, title, category, chunks)
    return {"doc_id": doc_id}


async def get_document(tenant_id: int, kb_id: int, doc_id: int) -> dict | None:
    rows = await _execute_read(
        "SELECT * FROM knowledge_documents WHERE tenant_id = :tid AND kb_id = :kid AND id = :doc_id",
        {"tid": tenant_id, "kid": kb_id, "doc_id": doc_id},
    )
    return rows[0] if rows else None


async def update_document(tenant_id: int, kb_id: int, doc_id: int, title=None, content=None, category=None, tags=None) -> dict | None:
    doc = await get_document(tenant_id, kb_id, doc_id)
    if doc is None:
        return None
    sets, params = [], {"tid": tenant_id, "kid": kb_id, "doc_id": doc_id}
    if title is not None and title.strip():
        sets.append("title = :title")
        params["title"] = title.strip()
    if category is not None:
        sets.append("category = :category")
        params["category"] = category
    if tags is not None:
        sets.append("tags = :tags")
        params["tags"] = tags
    if content is not None:
        sets.append("content = :content")
        params["content"] = content
        sets.append("content_hash = :chash")
        params["chash"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        sets.append("index_status = 'pending'")
    if sets:
        await _execute_write(
            f"UPDATE knowledge_documents SET {', '.join(sets)} WHERE tenant_id = :tid AND kb_id = :kid AND id = :doc_id",
            params,
        )

    if content is not None:
        # 原文变更 → 删旧切片 + 向量，重切块重索引
        await _delete_milvus_by_filter(f"tenant_id == {tenant_id} and kb_id == {kb_id} and source_type == 'doc' and source_id == {doc_id}")
        await _execute_write("DELETE FROM knowledge_chunks WHERE tenant_id = :tid AND kb_id = :kid AND doc_id = :doc_id", params)
        chunks = chunk_text(content, settings.knowledge_chunk_size)
        for i, chunk in enumerate(chunks):
            await _insert_get_id(
                """
                INSERT INTO knowledge_chunks (tenant_id, kb_id, doc_id, chunk_index, content, content_hash, index_status)
                VALUES (:tid, :kid, :doc_id, :ci, :content, :chash, 'pending')
                """,
                {"tid": tenant_id, "kid": kb_id, "doc_id": doc_id, "ci": i,
                 "content": chunk, "chash": hashlib.sha256(chunk.encode("utf-8")).hexdigest()},
            )
        await _execute_write(
            "UPDATE knowledge_documents SET index_status = 'indexing' WHERE id = :doc_id AND tenant_id = :tid",
            {"doc_id": doc_id, "tid": tenant_id},
        )
        await _index_doc_chunks(tenant_id, kb_id, doc_id, doc.get("title", ""), doc.get("category", ""), chunks)

    return await get_document(tenant_id, kb_id, doc_id)


async def set_document_status(tenant_id: int, kb_id: int, doc_id: int, status: str) -> bool:
    if status not in ("active", "disabled"):
        raise ValueError("非法状态")
    affected = await _execute_write(
        "UPDATE knowledge_documents SET status = :status WHERE tenant_id = :tid AND kb_id = :kid AND id = :doc_id",
        {"status": status, "tid": tenant_id, "kid": kb_id, "doc_id": doc_id},
    )
    if affected > 0:
        if status == "disabled":
            # 停用：删除该文档全部向量，检索不再命中
            await _delete_milvus_by_filter(
                f"tenant_id == {tenant_id} and kb_id == {kb_id} and source_type == 'doc' and source_id == {doc_id}"
            )
        else:
            # 启用：重新向量化（内容未变，重新入库恢复可检索）
            await reindex_document(tenant_id, kb_id, doc_id)
    return affected > 0


async def reindex_document(tenant_id: int, kb_id: int, doc_id: int) -> bool:
    doc = await get_document(tenant_id, kb_id, doc_id)
    if doc is None:
        return False
    chunks = chunk_text(doc.get("content") or "", settings.knowledge_chunk_size)
    if not chunks:
        await _execute_write(
            "UPDATE knowledge_documents SET index_status = 'failed', index_error = '正文为空' WHERE id = :doc_id AND tenant_id = :tid",
            {"doc_id": doc_id, "tid": tenant_id},
        )
        return True
    await _delete_milvus_by_filter(f"tenant_id == {tenant_id} and kb_id == {kb_id} and source_type == 'doc' and source_id == {doc_id}")
    await _execute_write("DELETE FROM knowledge_chunks WHERE tenant_id = :tid AND kb_id = :kid AND doc_id = :doc_id", {"tid": tenant_id, "kid": kb_id, "doc_id": doc_id})
    for i, chunk in enumerate(chunks):
        await _insert_get_id(
            """
            INSERT INTO knowledge_chunks (tenant_id, kb_id, doc_id, chunk_index, content, content_hash, index_status)
            VALUES (:tid, :kid, :doc_id, :ci, :content, :chash, 'pending')
            """,
            {"tid": tenant_id, "kid": kb_id, "doc_id": doc_id, "ci": i,
             "content": chunk, "chash": hashlib.sha256(chunk.encode("utf-8")).hexdigest()},
        )
    await _execute_write("UPDATE knowledge_documents SET index_status = 'indexing' WHERE id = :doc_id AND tenant_id = :tid", {"doc_id": doc_id, "tid": tenant_id})
    await _index_doc_chunks(tenant_id, kb_id, doc_id, doc.get("title", ""), doc.get("category", ""), chunks)
    return True


async def delete_document(tenant_id: int, kb_id: int, doc_id: int) -> bool:
    await _delete_milvus_by_filter(f"tenant_id == {tenant_id} and kb_id == {kb_id} and source_type == 'doc' and source_id == {doc_id}")
    await _execute_write("DELETE FROM knowledge_chunks WHERE tenant_id = :tid AND kb_id = :kid AND doc_id = :doc_id", {"tid": tenant_id, "kid": kb_id, "doc_id": doc_id})
    affected = await _execute_write(
        "DELETE FROM knowledge_documents WHERE tenant_id = :tid AND kb_id = :kid AND id = :doc_id",
        {"tid": tenant_id, "kid": kb_id, "doc_id": doc_id},
    )
    return affected > 0


# ─────────────────────── FAQ ───────────────────────


async def _index_faq(tenant_id: int, kb_id: int, faq_id: int, question: str, answer: str, category: str) -> None:
    """FAQ 向量化 + upsert Milvus。"""
    vector_id = f"faq:{tenant_id}:{faq_id}"
    try:
        vector = await get_embedding(question, settings.milvus_dim)
        if not _ensure_collection():
            raise RuntimeError("Milvus 集合不可用")
        client = _get_milvus()
        client.upsert(
            collection_name=settings.knowledge_milvus_collection,
            data=[{
                "pk": vector_id,
                "tenant_id": tenant_id,
                "kb_id": kb_id,
                "source_type": "faq",
                "source_id": faq_id,
                "chunk_index": 0,
                "vector": vector,
                "title": _safe(question, 512),
                "content": _safe(question, 8192),
                "answer": _safe(answer, 8192),
                "category": _safe(category, 64),
                "is_active": True,
            }],
        )
        await _execute_write(
            "UPDATE faq_pairs SET index_status = 'indexed', index_error = '', vector_id = :vid WHERE id = :faq_id AND tenant_id = :tid",
            {"vid": vector_id, "faq_id": faq_id, "tid": tenant_id},
        )
    except Exception as e:
        logger.warning(f"FAQ 向量化失败（faq={faq_id}）: {e}")
        await _execute_write(
            "UPDATE faq_pairs SET index_status = 'failed', index_error = :err WHERE id = :faq_id AND tenant_id = :tid",
            {"err": str(e)[:500], "faq_id": faq_id, "tid": tenant_id},
        )


async def list_faqs(tenant_id: int, kb_id: int, page: int = 1, page_size: int = 20,
                    status: str | None = None, keyword: str | None = None) -> dict:
    cond = "tenant_id = :tid AND kb_id = :kid"
    params = {"tid": tenant_id, "kid": kb_id}
    if status:
        cond += " AND status = :status"
        params["status"] = status
    if keyword:
        cond += " AND question LIKE :kw"
        params["kw"] = f"%{keyword}%"
    total = int((await _execute_read(f"SELECT COUNT(*) AS c FROM faq_pairs WHERE {cond}", params))[0]["c"])
    offset = (page - 1) * page_size
    items = await _execute_read(
        f"""
        SELECT f.id, f.kb_id, f.question, f.answer, f.category, f.hit_count, f.status, f.index_status, f.updated_at,
               (SELECT COUNT(*) FROM faq_aliases a WHERE a.faq_id = f.id) AS alias_count
        FROM faq_pairs f WHERE {cond}
        ORDER BY f.id DESC LIMIT :limit OFFSET :offset
        """,
        {**params, "limit": page_size, "offset": offset},
    )
    for r in items:
        r["alias_count"] = int(r.get("alias_count") or 0)
    return {"total": total, "items": items}


async def _replace_aliases(tenant_id: int, kb_id: int, faq_id: int, aliases: list[str]) -> None:
    await _execute_write(
        "DELETE FROM faq_aliases WHERE tenant_id = :tid AND kb_id = :kid AND faq_id = :faq_id",
        {"tid": tenant_id, "kid": kb_id, "faq_id": faq_id},
    )
    for alias in aliases:
        alias = (alias or "").strip()
        if not alias:
            continue
        await _execute_write(
            """
            INSERT INTO faq_aliases (tenant_id, kb_id, faq_id, alias, normalized_alias)
            VALUES (:tid, :kid, :faq_id, :alias, :nalias)
            """,
            {"tid": tenant_id, "kid": kb_id, "faq_id": faq_id, "alias": alias,
             "nalias": normalize_question(alias)},
        )


async def create_faq(tenant_id: int, kb_id: int, question: str, answer: str, category: str = "",
                     aliases: list[str] | None = None, created_by=None) -> dict:
    question = (question or "").strip()
    answer = (answer or "").strip()
    if not question or not answer:
        raise ValueError("标准问与答案不能为空")
    norm = normalize_question(question)
    faq_id = await _insert_get_id(
        """
        INSERT INTO faq_pairs (tenant_id, kb_id, question, normalized_question, answer, category, hit_count, status, index_status, created_by)
        VALUES (:tid, :kid, :question, :norm, :answer, :category, 0, 'active', 'pending', :created_by)
        """,
        {"tid": tenant_id, "kid": kb_id, "question": question, "norm": norm, "answer": answer,
         "category": category or "", "created_by": created_by},
    )
    if aliases:
        await _replace_aliases(tenant_id, kb_id, faq_id, aliases)
    await _index_faq(tenant_id, kb_id, faq_id, question, answer, category)
    return {"faq_id": faq_id}


async def get_faq(tenant_id: int, kb_id: int, faq_id: int) -> dict | None:
    rows = await _execute_read(
        "SELECT * FROM faq_pairs WHERE tenant_id = :tid AND kb_id = :kid AND id = :faq_id",
        {"tid": tenant_id, "kid": kb_id, "faq_id": faq_id},
    )
    if not rows:
        return None
    faq = rows[0]
    alias_rows = await _execute_read(
        "SELECT alias FROM faq_aliases WHERE tenant_id = :tid AND kb_id = :kid AND faq_id = :faq_id ORDER BY id",
        {"tid": tenant_id, "kid": kb_id, "faq_id": faq_id},
    )
    faq["aliases"] = [r["alias"] for r in alias_rows]
    return faq


async def update_faq(tenant_id: int, kb_id: int, faq_id: int, question=None, answer=None, category=None, aliases=None) -> dict | None:
    faq = await get_faq(tenant_id, kb_id, faq_id)
    if faq is None:
        return None
    from app.services import faq_cache
    sets, params = [], {"tid": tenant_id, "kid": kb_id, "faq_id": faq_id}
    if question is not None and question.strip():
        sets.append("question = :question")
        params["question"] = question.strip()
        sets.append("normalized_question = :norm")
        params["norm"] = normalize_question(question)
        sets.append("index_status = 'pending'")
    if answer is not None:
        sets.append("answer = :answer")
        params["answer"] = answer
    if category is not None:
        sets.append("category = :category")
        params["category"] = category
    if sets:
        await _execute_write(
            f"UPDATE faq_pairs SET {', '.join(sets)} WHERE tenant_id = :tid AND kb_id = :kid AND id = :faq_id",
            params,
        )
    if aliases is not None:
        await _replace_aliases(tenant_id, kb_id, faq_id, aliases)

    await faq_cache.invalidate_faq(tenant_id, kb_id, faq_id)
    # 内容变更需重向量化（用最新 question/answer）
    updated = await get_faq(tenant_id, kb_id, faq_id)
    if updated is None:
        return None
    await _index_faq(tenant_id, kb_id, faq_id, updated["question"], updated["answer"], updated.get("category", ""))
    return await get_faq(tenant_id, kb_id, faq_id)


async def set_faq_status(tenant_id: int, kb_id: int, faq_id: int, status: str) -> bool:
    if status not in ("active", "disabled"):
        raise ValueError("非法状态")
    affected = await _execute_write(
        "UPDATE faq_pairs SET status = :status WHERE tenant_id = :tid AND kb_id = :kid AND id = :faq_id",
        {"status": status, "tid": tenant_id, "kid": kb_id, "faq_id": faq_id},
    )
    if affected > 0:
        from app.services import faq_cache
        await faq_cache.invalidate_faq(tenant_id, kb_id, faq_id)
        # 停用：删向量；启用：重新向量化
        if status == "disabled":
            await _delete_milvus_by_filter(f"tenant_id == {tenant_id} and kb_id == {kb_id} and source_type == 'faq' and source_id == {faq_id}")
        else:
            faq = await get_faq(tenant_id, kb_id, faq_id)
            if faq:
                await _index_faq(tenant_id, kb_id, faq_id, faq["question"], faq["answer"], faq.get("category", ""))
    return affected > 0


async def reindex_faq(tenant_id: int, kb_id: int, faq_id: int) -> bool:
    faq = await get_faq(tenant_id, kb_id, faq_id)
    if faq is None:
        return False
    await _index_faq(tenant_id, kb_id, faq_id, faq["question"], faq["answer"], faq.get("category", ""))
    return True


async def delete_faq(tenant_id: int, kb_id: int, faq_id: int) -> bool:
    from app.services import faq_cache
    await _delete_milvus_by_filter(f"tenant_id == {tenant_id} and kb_id == {kb_id} and source_type == 'faq' and source_id == {faq_id}")
    await _execute_write("DELETE FROM faq_aliases WHERE tenant_id = :tid AND kb_id = :kid AND faq_id = :faq_id", {"tid": tenant_id, "kid": kb_id, "faq_id": faq_id})
    affected = await _execute_write(
        "DELETE FROM faq_pairs WHERE tenant_id = :tid AND kb_id = :kid AND id = :faq_id",
        {"tid": tenant_id, "kid": kb_id, "faq_id": faq_id},
    )
    if affected > 0:
        await faq_cache.invalidate_faq(tenant_id, kb_id, faq_id)
    return affected > 0


# ─────────────────────── 分类 ───────────────────────


async def list_categories(tenant_id: int, kb_id: int) -> list[str]:
    doc_rows = await _execute_read(
        "SELECT DISTINCT category FROM knowledge_documents WHERE tenant_id = :tid AND kb_id = :kid AND category != ''",
        {"tid": tenant_id, "kid": kb_id},
    )
    faq_rows = await _execute_read(
        "SELECT DISTINCT category FROM faq_pairs WHERE tenant_id = :tid AND kb_id = :kid AND category != ''",
        {"tid": tenant_id, "kid": kb_id},
    )
    cats = sorted({r["category"] for r in doc_rows + faq_rows})
    return cats


# ─────────────────────── 检索（统一入口） ───────────────────────


def _build_filter(tenant_id: int, kb_ids: list[int] | None, source_type: str | None = None) -> str:
    """构造 Milvus filter 表达式（仅内部调用，绝不让调用方传原始 filter）。"""
    parts = [f"tenant_id == {tenant_id}", "is_active == true"]
    if kb_ids:
        ids_str = ", ".join(str(k) for k in kb_ids)
        parts.append(f"kb_id in [{ids_str}]")
    if source_type:
        parts.append(f'source_type == "{source_type}"')
    return " and ".join(parts)


async def _resolve_kb_ids(tenant_id: int, kb_ids: list[int] | None) -> list[int]:
    if kb_ids:
        return [k for k in kb_ids if k]
    rows = await _execute_read(
        "SELECT id FROM knowledge_bases WHERE tenant_id = :tid AND status = 'active'",
        {"tid": tenant_id},
    )
    return [int(r["id"]) for r in rows]


async def _faq_exact_recall(tenant_id: int, kb_id: int, norm: str) -> dict | None:
    """FAQ 三级精确召回（Redis 热点 → 标准问 → 别名）。命中返回 exact dict，否则 None。"""
    from app.services import faq_cache

    version = await faq_cache.get_kb_version(tenant_id, kb_id)
    hot = await faq_cache.get_hot_faq(tenant_id, kb_id, version, faq_cache.question_hash(norm))
    if hot:
        await faq_cache.record_hit(tenant_id, kb_id, hot.get("id"))
        return {"match_type": "faq_exact", "faq_id": hot.get("id"), "question": hot.get("question", ""),
                "answer": hot.get("answer", ""), "category": hot.get("category", ""), "kb_id": kb_id}

    # 标准问精确匹配
    rows = await _execute_read(
        "SELECT id, question, answer, category FROM faq_pairs WHERE tenant_id = :tid AND kb_id = :kid AND status = 'active' AND normalized_question = :norm LIMIT 1",
        {"tid": tenant_id, "kid": kb_id, "norm": norm},
    )
    if rows:
        faq = rows[0]
        await faq_cache.record_hit(tenant_id, kb_id, faq["id"])
        await _execute_write("UPDATE faq_pairs SET hit_count = hit_count + 1 WHERE id = :fid", {"fid": faq["id"]})
        if await faq_cache.get_monthly_hit(tenant_id, kb_id, faq["id"]) >= settings.knowledge_faq_hot_threshold:
            await faq_cache.set_hot_faq(tenant_id, kb_id, version, faq, faq_cache.question_hash(norm))
        return {"match_type": "faq_exact", "faq_id": faq["id"], "question": faq["question"],
                "answer": faq["answer"], "category": faq.get("category", ""), "kb_id": kb_id}

    # 别名精确匹配
    alias_rows = await _execute_read(
        """
        SELECT f.id, f.question, f.answer, f.category
        FROM faq_aliases a JOIN faq_pairs f ON f.id = a.faq_id AND f.kb_id = a.kb_id AND f.tenant_id = a.tenant_id
        WHERE a.tenant_id = :tid AND a.kb_id = :kid AND a.normalized_alias = :norm AND f.status = 'active'
        LIMIT 1
        """,
        {"tid": tenant_id, "kid": kb_id, "norm": norm},
    )
    if alias_rows:
        faq = alias_rows[0]
        await faq_cache.record_hit(tenant_id, kb_id, faq["id"])
        await _execute_write("UPDATE faq_pairs SET hit_count = hit_count + 1 WHERE id = :fid", {"fid": faq["id"]})
        return {"match_type": "faq_alias", "faq_id": faq["id"], "question": faq["question"],
                "answer": faq["answer"], "category": faq.get("category", ""), "kb_id": kb_id}

    return None


async def search(query: str, tenant_id: int, kb_ids: list[int] | None = None,
                 source_type: str | None = None, top_k: int = 5) -> dict:
    """统一检索：FAQ 三级精确召回 → Milvus 向量召回。全程异常兜底。"""
    if not tenant_id:
        return {"status": "error", "exact": None, "chunks": [], "message": "缺少租户上下文"}
    if not query or not query.strip():
        return {"status": "ok", "exact": None, "chunks": []}

    kb_ids = await _resolve_kb_ids(tenant_id, kb_ids)
    if not kb_ids:
        return {"status": "ok", "exact": None, "chunks": []}

    norm = normalize_question(query)

    # 1. FAQ 精确召回（仅当未限定 doc 类型时）
    if source_type in (None, "faq"):
        for kb_id in kb_ids:
            exact = await _faq_exact_recall(tenant_id, kb_id, norm)
            if exact:
                return {"status": "ok", "exact": exact, "chunks": []}

    # 2. Milvus 向量召回
    chunks = []
    try:
        vector = await get_embedding(query, settings.milvus_dim)
        if not _ensure_collection():
            raise RuntimeError("Milvus 集合不可用")
        client = _get_milvus()
        filter_expr = _build_filter(tenant_id, kb_ids, source_type)
        results = client.search(
            collection_name=settings.knowledge_milvus_collection,
            data=[vector],
            limit=top_k,
            filter=filter_expr,
            output_fields=["source_type", "source_id", "kb_id", "title", "content", "answer", "category"],
        )
        for hit in results[0]:
            entity = hit.get("entity", {})
            chunks.append({
                "source_type": entity.get("source_type"),
                "source_id": entity.get("source_id"),
                "kb_id": entity.get("kb_id"),
                "title": entity.get("title", ""),
                "content": entity.get("content", ""),
                "answer": entity.get("answer", ""),
                "category": entity.get("category", ""),
                "score": float(hit.get("distance", 0)),
            })
    except Exception as e:
        logger.warning(f"向量检索失败: {e}")
        chunks = []

    return {"status": "ok", "exact": None, "chunks": chunks}
