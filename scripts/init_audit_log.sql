-- 创建审计日志表
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    doc_type VARCHAR(50) NOT NULL COMMENT '单据类型',
    doc_id VARCHAR(50) NOT NULL COMMENT '单据ID',
    action VARCHAR(100) NOT NULL COMMENT '操作类型',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '操作人ID',
    tenant_id BIGINT UNSIGNED COMMENT '租户ID',
    payload TEXT COMMENT '操作数据',
    idempotency_key VARCHAR(100) COMMENT '幂等键',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    INDEX idx_doc_type_doc_id (doc_type, doc_id),
    INDEX idx_user_id (user_id),
    INDEX idx_idempotency_key (idempotency_key),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='审计日志表';
