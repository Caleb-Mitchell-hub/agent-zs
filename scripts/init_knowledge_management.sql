-- ============================================================
-- 多租户知识库管理建表脚本
--
-- 用途：为「多租户知识库管理」功能创建 MySQL 表结构，
--       覆盖知识库、文档、切片、FAQ 问答对、FAQ 别名五类实体。
--
-- 约定：
--   - 全部使用 CREATE TABLE IF NOT EXISTS，脚本可重复执行。
--   - tenant_id 采用 BIGINT UNSIGNED，与 JWT 中的 int 型租户 ID 一致，
--     所有表均包含 tenant_id 用于租户隔离。
--   - 切片与 FAQ 的向量检索走 Milvus，vector_id 记录 Milvus 主键。
-- ============================================================

-- 1. 知识库表
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    tenant_id BIGINT UNSIGNED NOT NULL COMMENT '租户ID',
    name VARCHAR(100) NOT NULL COMMENT '知识库名称',
    description VARCHAR(500) DEFAULT '' COMMENT '描述',
    status VARCHAR(20) DEFAULT 'active' COMMENT '状态：active/disabled',
    embedding_model VARCHAR(100) DEFAULT 'BAAI/bge-large-zh-v1.5' COMMENT '向量化模型',
    created_by BIGINT UNSIGNED NULL COMMENT '创建人ID',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uq_tenant_name (tenant_id, name),
    INDEX idx_tenant_status (tenant_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库表';

-- 2. 知识库文档表
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    tenant_id BIGINT UNSIGNED NOT NULL COMMENT '租户ID',
    kb_id BIGINT UNSIGNED NOT NULL COMMENT '知识库ID',
    title VARCHAR(200) NOT NULL COMMENT '文档标题',
    source_type VARCHAR(20) DEFAULT 'text' COMMENT '来源类型：text/upload',
    file_name VARCHAR(255) DEFAULT '' COMMENT '文件名',
    mime_type VARCHAR(100) DEFAULT '' COMMENT 'MIME类型',
    content LONGTEXT NOT NULL COMMENT '文档正文',
    content_hash CHAR(64) DEFAULT '' COMMENT '正文哈希',
    category VARCHAR(50) DEFAULT '' COMMENT '分类',
    tags VARCHAR(500) DEFAULT '' COMMENT '标签',
    status VARCHAR(20) DEFAULT 'active' COMMENT '状态：active/disabled',
    index_status VARCHAR(20) DEFAULT 'pending' COMMENT '索引状态：pending/indexing/indexed/failed/stale',
    index_error VARCHAR(500) DEFAULT '' COMMENT '索引错误信息',
    created_by BIGINT UNSIGNED NULL COMMENT '创建人ID',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_tenant_kb_status (tenant_id, kb_id, status),
    INDEX idx_tenant_kb_index (tenant_id, kb_id, index_status),
    INDEX idx_content_hash (content_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库文档表';

-- 3. 知识库切片表
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    tenant_id BIGINT UNSIGNED NOT NULL COMMENT '租户ID',
    kb_id BIGINT UNSIGNED NOT NULL COMMENT '知识库ID',
    doc_id BIGINT UNSIGNED NOT NULL COMMENT '文档ID',
    chunk_index INT NOT NULL COMMENT '切片序号',
    content TEXT NOT NULL COMMENT '切片内容',
    content_hash CHAR(64) DEFAULT '' COMMENT '切片内容哈希',
    vector_id VARCHAR(128) DEFAULT '' COMMENT 'Milvus主键：doc:{tenant_id}:{doc_id}:{chunk_index}',
    index_status VARCHAR(20) DEFAULT 'pending' COMMENT '索引状态',
    index_error VARCHAR(500) DEFAULT '' COMMENT '索引错误信息',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uq_doc_chunk (doc_id, chunk_index),
    INDEX idx_tenant_kb_doc (tenant_id, kb_id, doc_id),
    INDEX idx_vector_id (vector_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库切片表';

-- 4. FAQ 问答对表
CREATE TABLE IF NOT EXISTS faq_pairs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    tenant_id BIGINT UNSIGNED NOT NULL COMMENT '租户ID',
    kb_id BIGINT UNSIGNED NOT NULL COMMENT '知识库ID',
    question VARCHAR(500) NOT NULL COMMENT '标准问题',
    normalized_question VARCHAR(500) NOT NULL COMMENT '归一化后的标准问',
    answer TEXT NOT NULL COMMENT '答案',
    category VARCHAR(50) DEFAULT '' COMMENT '分类',
    hit_count INT UNSIGNED DEFAULT 0 COMMENT '命中次数',
    status VARCHAR(20) DEFAULT 'active' COMMENT '状态：active/disabled',
    index_status VARCHAR(20) DEFAULT 'pending' COMMENT '索引状态',
    index_error VARCHAR(500) DEFAULT '' COMMENT '索引错误信息',
    vector_id VARCHAR(128) DEFAULT '' COMMENT 'Milvus主键：faq:{tenant_id}:{faq_id}',
    created_by BIGINT UNSIGNED NULL COMMENT '创建人ID',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uq_tenant_kb_nq (tenant_id, kb_id, normalized_question),
    INDEX idx_tenant_kb_status (tenant_id, kb_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='FAQ问答对表';

-- 5. FAQ 别名表
CREATE TABLE IF NOT EXISTS faq_aliases (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    tenant_id BIGINT UNSIGNED NOT NULL COMMENT '租户ID',
    kb_id BIGINT UNSIGNED NOT NULL COMMENT '知识库ID',
    faq_id BIGINT UNSIGNED NOT NULL COMMENT 'FAQ问答对ID',
    alias VARCHAR(500) NOT NULL COMMENT '别名',
    normalized_alias VARCHAR(500) NOT NULL COMMENT '归一化后的别名',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY uq_tenant_kb_na (tenant_id, kb_id, normalized_alias),
    INDEX idx_faq (faq_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='FAQ别名表';
