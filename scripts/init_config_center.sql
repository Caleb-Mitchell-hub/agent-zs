-- ============================================================
-- 配置管理与后台运营中心 数据层初始化脚本
-- 设计文档 §5.12
-- 全部幂等：IF NOT EXISTS / ALTER ... ADD COLUMN（重复执行安全）
-- ============================================================

-- (1) 通用 KV 配置表：承载单实体标量/JSON 配置（llm、retention、rate_limit.default）
CREATE TABLE IF NOT EXISTS app_config (
    config_key   VARCHAR(64) PRIMARY KEY COMMENT '配置键，如 llm / retention / rate_limit.default',
    config_value TEXT NOT NULL COMMENT 'JSON 序列化值；敏感字段存 Fernet 密文',
    value_type   VARCHAR(20) NOT NULL DEFAULT 'json' COMMENT 'string/number/bool/json',
    is_sensitive TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1=value 为密文，出参需脱敏',
    description  VARCHAR(255) COMMENT '配置说明',
    version      INT NOT NULL DEFAULT 1 COMMENT '乐观锁',
    updated_by   VARCHAR(36) COMMENT '最后修改人',
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='通用配置表';

-- (2) 工具策略表：每工具一行运营参数
CREATE TABLE IF NOT EXISTS tool_policy_config (
    tool_name    VARCHAR(50) PRIMARY KEY,
    enabled      TINYINT(1) NOT NULL DEFAULT 1 COMMENT '启停开关',
    risk_level   VARCHAR(10) NOT NULL DEFAULT 'medium' COMMENT 'low/medium/high',
    need_confirm TINYINT(1) NOT NULL DEFAULT 0,
    timeout      INT NOT NULL DEFAULT 30 COMMENT '秒',
    retry_count  INT NOT NULL DEFAULT 3,
    updated_by   VARCHAR(36),
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='工具策略配置表';

-- (3) 数据源连接表：每连接一行，密码 Fernet 加密，enabled=0 表示"已保存未确认生效"
CREATE TABLE IF NOT EXISTS datasource_config (
    id                BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name              VARCHAR(50) NOT NULL,
    type              VARCHAR(20) NOT NULL DEFAULT 'mysql_replica' COMMENT 'mysql_replica 只读副本',
    host              VARCHAR(255) NOT NULL,
    port              INT NOT NULL DEFAULT 3306,
    db_name           VARCHAR(64) NOT NULL,
    username          VARCHAR(64) NOT NULL,
    password_encrypted TEXT COMMENT 'Fernet 密文，明文不入库',
    connect_timeout   INT NOT NULL DEFAULT 10 COMMENT '秒',
    enabled           TINYINT(1) NOT NULL DEFAULT 0 COMMENT '0=待二次确认/未生效 1=生效',
    version           INT NOT NULL DEFAULT 1,
    updated_by        VARCHAR(36),
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据源连接配置表';

-- (4) 限流配额表：按 scope_type+scope_id 粒度
CREATE TABLE IF NOT EXISTS rate_limit_config (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    scope_type          VARCHAR(20) NOT NULL COMMENT 'user/department/tenant',
    scope_id            VARCHAR(64) NOT NULL,
    qps                 INT NOT NULL DEFAULT 10,
    concurrency         INT NOT NULL DEFAULT 5,
    token_quota_monthly BIGINT NOT NULL DEFAULT 0 COMMENT '0=不限制',
    enabled             TINYINT(1) NOT NULL DEFAULT 1,
    updated_by          VARCHAR(36),
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_scope (scope_type, scope_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='限流配额表';

-- (5) 二次确认待办表：数据源/工具风险降级的高风险变更走两段式
CREATE TABLE IF NOT EXISTS config_change_requests (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    namespace    VARCHAR(30) NOT NULL COMMENT 'datasource/tool_policy',
    target_key   VARCHAR(64) NOT NULL COMMENT '数据源 id 或工具名',
    operation    VARCHAR(20) NOT NULL COMMENT 'create/update/delete',
    old_value    JSON COMMENT '变更前（敏感字段已加密）',
    new_value    JSON COMMENT '变更后（敏感字段已加密）',
    status       VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/confirmed/cancelled/expired',
    requested_by VARCHAR(36),
    confirmed_by VARCHAR(36),
    expires_at   TIMESTAMP NULL COMMENT '默认 24h 过期自动判 expired',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMP NULL,
    INDEX idx_status (status),
    INDEX idx_namespace (namespace)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='配置二次确认待办表';

-- (6) 改造现有表（幂等 ALTER）
SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'model_routing_config' AND COLUMN_NAME = 'enabled');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE model_routing_config ADD COLUMN enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT ''路由是否启用'' AFTER sensitivity_level',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'model_routing_config' AND COLUMN_NAME = 'priority');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE model_routing_config ADD COLUMN priority INT NOT NULL DEFAULT 100 COMMENT ''路由优先级（小者优先）'' AFTER enabled',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'knowledge_base' AND COLUMN_NAME = 'permission_scope');
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE knowledge_base ADD COLUMN permission_scope VARCHAR(100) NOT NULL DEFAULT ''all'' COMMENT ''权限范围：all/角色/部门，逗号分隔'' AFTER category',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ============================================================
-- 种子数据（ON DUPLICATE KEY UPDATE 幂等）
-- ============================================================

-- 保留期默认配置
INSERT INTO app_config (config_key, config_value, value_type, is_sensitive, description, updated_by)
VALUES ('retention', '{"task_days":90,"session_days":180,"memory_days":365,"audit_days":365}',
        'json', 0, '保留期与生命周期配置（天）', 'system')
ON DUPLICATE KEY UPDATE description = VALUES(description);

-- 限流默认档
INSERT INTO app_config (config_key, config_value, value_type, is_sensitive, description, updated_by)
VALUES ('rate_limit.default', '{"max_requests":60,"window_seconds":60}',
        'json', 0, '默认限流档位', 'system')
ON DUPLICATE KEY UPDATE description = VALUES(description);

-- LLM 默认连接（api_key 需运行时用 Fernet 加密后写入，这里只留占位空值）
INSERT INTO app_config (config_key, config_value, value_type, is_sensitive, description, updated_by)
VALUES ('llm', '{"provider":"deepseek","base_url":"https://api.deepseek.com","model":"deepseek-chat","max_tokens":4096,"temperature":0.1,"api_key":""}',
        'json', 1, 'LLM 连接配置（api_key 加密存储）', 'system')
ON DUPLICATE KEY UPDATE description = VALUES(description);

-- 模型路由默认配置（8 个意图）
INSERT INTO model_routing_config (task_type, primary_model, fallback_models, sensitivity_level, enabled, priority)
VALUES
    ('query', 'deepseek-chat', JSON_ARRAY('deepseek-chat'), 'normal', 1, 100),
    ('report', 'deepseek-chat', JSON_ARRAY('deepseek-chat'), 'normal', 1, 100),
    ('knowledge', 'deepseek-chat', JSON_ARRAY('deepseek-chat'), 'normal', 1, 100),
    ('create', 'deepseek-chat', JSON_ARRAY('deepseek-chat'), 'normal', 1, 100),
    ('update', 'deepseek-chat', JSON_ARRAY('deepseek-chat'), 'normal', 1, 100),
    ('memory', 'deepseek-chat', JSON_ARRAY('deepseek-chat'), 'normal', 1, 100),
    ('chat', 'deepseek-chat', JSON_ARRAY('deepseek-chat'), 'normal', 1, 100),
    ('time', 'deepseek-chat', JSON_ARRAY('deepseek-chat'), 'normal', 1, 100)
ON DUPLICATE KEY UPDATE primary_model = VALUES(primary_model);
