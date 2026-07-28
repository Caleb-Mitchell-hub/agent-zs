-- 创建 Agent 相关表

-- 任务历史表
CREATE TABLE IF NOT EXISTS task_history (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    task_id VARCHAR(100) NOT NULL COMMENT '任务ID',
    session_id VARCHAR(100) NOT NULL COMMENT '会话ID',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
    tenant_id BIGINT UNSIGNED NOT NULL COMMENT '租户ID',
    task_type VARCHAR(50) NOT NULL COMMENT '任务类型',
    agent_name VARCHAR(50) NOT NULL COMMENT 'Agent名称',
    input_data TEXT COMMENT '输入数据',
    output_data TEXT COMMENT '输出数据',
    status VARCHAR(20) NOT NULL COMMENT '任务状态',
    error_message TEXT COMMENT '错误信息',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    INDEX idx_session_id (session_id),
    INDEX idx_user_id (user_id),
    INDEX idx_task_type (task_type),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='任务历史表';

-- 工具调用日志表
CREATE TABLE IF NOT EXISTS tool_call_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    task_id VARCHAR(100) NOT NULL COMMENT '任务ID',
    tool_name VARCHAR(50) NOT NULL COMMENT '工具名称',
    tool_input TEXT COMMENT '工具输入',
    tool_output TEXT COMMENT '工具输出',
    duration_ms INT COMMENT '执行时间（毫秒）',
    status VARCHAR(20) NOT NULL COMMENT '调用状态',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    INDEX idx_task_id (task_id),
    INDEX idx_tool_name (tool_name),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='工具调用日志表';

-- 用户偏好表
CREATE TABLE IF NOT EXISTS user_preferences (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
    preferences JSON COMMENT '偏好设置',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    updated_at DATETIME NOT NULL COMMENT '更新时间',
    UNIQUE INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户偏好表';
