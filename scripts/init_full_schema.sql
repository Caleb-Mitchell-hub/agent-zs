-- ============================================================
-- 按设计方案创建完整的数据库表结构
-- ============================================================

-- 1. 会话表
CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(36) PRIMARY KEY COMMENT 'UUID',
    tenant_id VARCHAR(36) NOT NULL COMMENT '租户ID',
    user_id VARCHAR(36) NOT NULL COMMENT '用户ID',
    channel VARCHAR(20) DEFAULT 'web' COMMENT 'web/feishu/wecom/mobile',
    status VARCHAR(20) DEFAULT 'active' COMMENT 'active/archived',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '最后活跃时间',
    INDEX idx_user (user_id),
    INDEX idx_tenant (tenant_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会话表';

-- 2. 消息表
CREATE TABLE IF NOT EXISTS messages (
    message_id VARCHAR(36) PRIMARY KEY COMMENT '消息ID',
    session_id VARCHAR(36) NOT NULL COMMENT '会话ID',
    role VARCHAR(10) NOT NULL COMMENT 'user/assistant/tool',
    content TEXT COMMENT '文本内容',
    tool_call_ref VARCHAR(36) COMMENT '关联工具调用ID',
    trace_id VARCHAR(36) COMMENT '全链路追踪ID',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_session (session_id),
    INDEX idx_trace (trace_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='消息表';

-- 3. 任务表
CREATE TABLE IF NOT EXISTS tasks (
    task_id VARCHAR(36) PRIMARY KEY COMMENT '任务ID',
    session_id VARCHAR(36) NOT NULL COMMENT '会话ID',
    user_id VARCHAR(36) NOT NULL COMMENT '用户ID',
    tenant_id VARCHAR(36) NOT NULL COMMENT '租户ID',
    goal TEXT COMMENT '任务目标描述',
    status VARCHAR(20) DEFAULT 'pending' COMMENT 'pending/planning/running/waiting_confirm/succeeded/failed/cancelled',
    current_step_id VARCHAR(36) COMMENT '当前步骤ID',
    plan_snapshot JSON COMMENT '任务DAG快照',
    version INT DEFAULT 1 COMMENT '乐观锁版本',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_session (session_id),
    INDEX idx_user (user_id),
    INDEX idx_status (status),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='任务表';

-- 4. 任务步骤表
CREATE TABLE IF NOT EXISTS task_steps (
    step_id VARCHAR(36) PRIMARY KEY COMMENT '步骤ID',
    task_id VARCHAR(36) NOT NULL COMMENT '任务ID',
    step_index INT NOT NULL COMMENT '步骤序号',
    depends_on JSON COMMENT '依赖的step_id数组',
    tool_name VARCHAR(50) COMMENT '工具名称',
    input_params JSON COMMENT '入参快照',
    output_result JSON COMMENT '执行结果',
    status VARCHAR(20) DEFAULT 'pending' COMMENT 'pending/running/succeeded/failed/waiting_confirm/skipped',
    idempotency_key VARCHAR(64) UNIQUE COMMENT '幂等键',
    need_confirm BOOLEAN DEFAULT FALSE COMMENT '是否需要人工确认',
    confirmed_by VARCHAR(36) COMMENT '确认人ID',
    confirmed_at TIMESTAMP NULL COMMENT '确认时间',
    retry_count INT DEFAULT 0 COMMENT '已重试次数',
    last_error TEXT COMMENT '最近错误信息',
    heartbeat_at TIMESTAMP NULL COMMENT 'Worker心跳时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_task (task_id),
    INDEX idx_status (status),
    INDEX idx_idempotency (idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='任务步骤表';

-- 5. 幂等记录表
CREATE TABLE IF NOT EXISTS idempotency_records (
    idempotency_key VARCHAR(64) PRIMARY KEY COMMENT '幂等键',
    target_system VARCHAR(30) NOT NULL COMMENT '目标系统',
    request_hash VARCHAR(64) COMMENT '请求参数哈希',
    downstream_ref_id VARCHAR(64) COMMENT '下游系统返回的业务ID',
    status VARCHAR(20) DEFAULT 'pending' COMMENT 'pending/confirmed/expired',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    expire_at TIMESTAMP NOT NULL COMMENT '过期时间',
    INDEX idx_target (target_system),
    INDEX idx_status (status),
    INDEX idx_expire (expire_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='幂等记录表';

-- 6. ERP单据映射表
CREATE TABLE IF NOT EXISTS erp_order_mapping (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    task_id VARCHAR(36) COMMENT '任务ID',
    step_id VARCHAR(36) COMMENT '步骤ID',
    erp_order_no VARCHAR(50) NOT NULL COMMENT 'ERP单据号',
    erp_order_type VARCHAR(30) NOT NULL COMMENT '单据类型',
    sync_status VARCHAR(20) DEFAULT 'created' COMMENT 'created/approved/rejected/unknown',
    last_synced_at TIMESTAMP NULL COMMENT '最近同步时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_task (task_id),
    INDEX idx_erp_no (erp_order_no),
    INDEX idx_sync (sync_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='ERP单据映射表';

-- 7. 长期记忆表
CREATE TABLE IF NOT EXISTS memory_long_term (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    user_id VARCHAR(36) NOT NULL COMMENT '用户ID',
    tenant_id VARCHAR(36) NOT NULL COMMENT '租户ID',
    memory_type VARCHAR(20) NOT NULL COMMENT 'preference/fact/habit',
    content TEXT NOT NULL COMMENT '记忆内容',
    source_session_id VARCHAR(36) COMMENT '来源会话ID',
    confidence FLOAT DEFAULT 1.0 COMMENT '置信度',
    last_confirmed_at TIMESTAMP NULL COMMENT '最近确认时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_user (user_id),
    INDEX idx_type (memory_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='长期记忆表';

-- 8. 情景记忆表
CREATE TABLE IF NOT EXISTS memory_episodic (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    task_id VARCHAR(36) NOT NULL COMMENT '任务ID',
    summary TEXT COMMENT '任务摘要',
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '归档时间',
    INDEX idx_task (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='情景记忆表';

-- 9. RAG文档元数据表
CREATE TABLE IF NOT EXISTS rag_documents (
    doc_id VARCHAR(36) PRIMARY KEY COMMENT '文档ID',
    title VARCHAR(200) NOT NULL COMMENT '标题',
    source_url VARCHAR(500) COMMENT '来源URL',
    permission_scope VARCHAR(50) COMMENT '权限分区',
    version INT DEFAULT 1 COMMENT '版本号',
    status VARCHAR(20) DEFAULT 'active' COMMENT 'active/deprecated',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_status (status),
    INDEX idx_permission (permission_scope)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG文档元数据表';

-- 10. RAG切片表
CREATE TABLE IF NOT EXISTS rag_chunks (
    chunk_id VARCHAR(36) PRIMARY KEY COMMENT '切片ID',
    doc_id VARCHAR(36) NOT NULL COMMENT '文档ID',
    doc_version INT NOT NULL COMMENT '文档版本',
    content TEXT NOT NULL COMMENT '内容',
    vector_id VARCHAR(64) COMMENT '向量数据库ID',
    index_status VARCHAR(20) DEFAULT 'pending' COMMENT 'pending/indexed/stale/deleted',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_doc (doc_id),
    INDEX idx_status (index_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG切片表';

-- 11. 模型路由配置表
CREATE TABLE IF NOT EXISTS model_routing_config (
    task_type VARCHAR(30) PRIMARY KEY COMMENT '任务类型',
    primary_model VARCHAR(50) NOT NULL COMMENT '主模型',
    fallback_models JSON COMMENT '备用模型列表',
    sensitivity_level VARCHAR(20) COMMENT '敏感级别',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模型路由配置表';

-- 12. 模型调用日志表
CREATE TABLE IF NOT EXISTS model_call_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    trace_id VARCHAR(36) COMMENT '追踪ID',
    model_used VARCHAR(50) NOT NULL COMMENT '使用的模型',
    is_fallback BOOLEAN DEFAULT FALSE COMMENT '是否备用模型',
    latency_ms INT COMMENT '延迟毫秒',
    token_in INT COMMENT '输入token数',
    token_out INT COMMENT '输出token数',
    success BOOLEAN DEFAULT TRUE COMMENT '是否成功',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_trace (trace_id),
    INDEX idx_model (model_used),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模型调用日志表';

-- 13. 审计日志表（扩展）
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    trace_id VARCHAR(36) COMMENT '追踪ID',
    user_id VARCHAR(36) NOT NULL COMMENT '用户ID',
    tenant_id VARCHAR(36) NOT NULL COMMENT '租户ID',
    action VARCHAR(50) NOT NULL COMMENT '操作类型',
    request_snapshot JSON COMMENT '请求快照',
    result_snapshot JSON COMMENT '结果快照',
    risk_level VARCHAR(10) DEFAULT 'low' COMMENT '风险级别',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_trace (trace_id),
    INDEX idx_user (user_id),
    INDEX idx_action (action),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='审计日志表';

-- 14. 审批实例表（已存在，确认结构）
-- CREATE TABLE IF NOT EXISTS approval_instance ...

-- 15. 审批日志表（已存在，确认结构）
-- CREATE TABLE IF NOT EXISTS approval_log ...

-- 16. 用户偏好表（已存在，确认结构）
-- CREATE TABLE IF NOT EXISTS user_preferences ...

-- 17. Agent评估表（已存在，确认结构）
-- CREATE TABLE IF NOT EXISTS agent_evaluation ...
