-- 创建知识库表
CREATE TABLE IF NOT EXISTS knowledge_base (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    title VARCHAR(200) NOT NULL COMMENT '标题',
    content TEXT NOT NULL COMMENT '内容',
    category VARCHAR(50) NOT NULL COMMENT '类别 (manual, rule, faq)',
    tags VARCHAR(500) COMMENT '标签（逗号分隔）',
    relevance_score DECIMAL(5,2) DEFAULT 1.0 COMMENT '相关性分数',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    updated_at DATETIME COMMENT '更新时间',
    INDEX idx_category (category),
    FULLTEXT idx_title_content (title, content)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库表';

-- 插入示例数据
INSERT INTO knowledge_base (title, content, category, tags, relevance_score, created_at) VALUES
('采购订单创建流程', '1. 进入采购管理模块\n2. 点击"新建采购订单"\n3. 选择供应商和仓库\n4. 添加采购商品和数量\n5. 提交审批', 'manual', '采购,订单,创建', 1.0, NOW()),
('销售订单审批规则', '销售订单金额超过10000元需要部门经理审批，超过50000元需要总经理审批。', 'rule', '销售,订单,审批', 1.0, NOW()),
('如何查询库存', '在库存管理模块中，可以通过商品名称、SKU编码或仓库名称进行查询。支持导出Excel报表。', 'faq', '库存,查询', 1.0, NOW()),
('入库操作规范', '1. 核对采购订单\n2. 检验商品质量\n3. 录入实际入库数量\n4. 确认入库', 'manual', '入库,操作', 1.0, NOW()),
('出库操作规范', '1. 核对销售订单\n2. 拣货并复核\n3. 录入实际出库数量\n4. 确认出库', 'manual', '出库,操作', 1.0, NOW());
