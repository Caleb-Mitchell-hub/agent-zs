-- ============================================================
-- 任务管理器 4 张表
-- ============================================================

-- 1. 用户任务主表
CREATE TABLE IF NOT EXISTS user_tasks (
    task_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '任务ID',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
    title VARCHAR(200) NOT NULL COMMENT '任务标题',
    status VARCHAR(20) DEFAULT 'pending' COMMENT 'pending/doing/done',
    priority TINYINT DEFAULT 0 COMMENT '优先级',
    deadline DATETIME NULL COMMENT '截止时间',
    parent_id BIGINT UNSIGNED NULL COMMENT '父任务ID',
    plan_detail JSON NULL COMMENT '规划细节',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    completed_at DATETIME NULL COMMENT '完成时间',
    INDEX idx_user (user_id),
    INDEX idx_status (status),
    INDEX idx_deadline (deadline),
    INDEX idx_parent (parent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户任务表';

-- 2. 定时任务表
CREATE TABLE IF NOT EXISTS task_schedules (
    schedule_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '定时任务ID',
    task_id BIGINT UNSIGNED NOT NULL COMMENT '关联任务',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
    trigger_time DATETIME NOT NULL COMMENT '触发时间',
    action VARCHAR(20) NOT NULL COMMENT 'remind/remind_advance',
    advance_to VARCHAR(20) NULL COMMENT 'doing/done',
    fired TINYINT DEFAULT 0 COMMENT '是否已触发',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_task (task_id),
    INDEX idx_user (user_id),
    INDEX idx_trigger (trigger_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='定时任务表';

-- 3. 公共节假日表（内置只读）
CREATE TABLE IF NOT EXISTS holidays (
    holiday_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
    day DATE NOT NULL COMMENT '日期',
    type VARCHAR(20) NOT NULL COMMENT 'holiday/workday',
    note VARCHAR(100) NULL COMMENT '备注',
    INDEX idx_day (day)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='公共节假日表';

-- 4. 个人请假表
CREATE TABLE IF NOT EXISTS leaves (
    leave_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
    day DATE NOT NULL COMMENT '请假日期',
    note VARCHAR(100) NULL COMMENT '备注',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_user_day (user_id, day)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='个人请假表';

-- 预置 2026 年国庆/中秋调休示例（holiday=放假，workday=调休上班）
INSERT INTO holidays (day, type, note) VALUES
    ('2026-10-01', 'holiday', '国庆节'),
    ('2026-10-02', 'holiday', '国庆节'),
    ('2026-10-06', 'holiday', '中秋节')
ON DUPLICATE KEY UPDATE note = VALUES(note);
