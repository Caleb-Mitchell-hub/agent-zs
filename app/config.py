"""应用配置模块

所有配置从环境变量读取，不硬编码敏感信息。
API Key 通过管理页面配置（Phase 2 实现），此处只定义默认值。
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""

    # 应用基本配置
    app_name: str = "Agent-Zs"
    app_version: str = "0.1.0"
    debug: bool = False

    # LLM 配置（从环境变量读取，不硬编码）
    llm_provider: str = "deepseek"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_base_url: str = "https://api.deepseek.com"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.1
    llm_timeout: int = 120  # LLM API 调用超时（秒）

    # 配置中心敏感字段加密密钥（Fernet，urlsafe-base64 32字节）
    # 来源：env AI_CONFIG_SECRET；未配置时启动自动生成并持久化到 Redis
    ai_config_secret: str = ""

    # JWT 认证密钥（HMAC-SHA256）
    # 来源：env JWT_SECRET_KEY；未配置时启动自动生成（仅开发环境）
    jwt_secret_key: str = ""
    jwt_expire_hours: int = 24

    # 数据库配置（从环境变量读取，不硬编码）
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = ""
    db_password: str = ""
    db_name: str = "wms"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 3600

    # Redis 配置
    redis_host: str = "172.177.3.43"
    redis_port: int = 6381
    redis_db: int = 0
    redis_password: str = ""

    # 会话配置
    session_ttl: int = 86400        # 会话过期时间（秒），默认 24 小时
    session_max_messages: int = 50  # 会话消息保留上限

    # Milvus 向量数据库配置
    milvus_host: str = "172.177.3.43"
    milvus_port: int = 19530
    milvus_collection: str = "knowledge_base"
    milvus_dim: int = 1024  # 向量维度（BAAI/bge-large-zh-v1.5 = 1024）

    # Embedding 配置（从环境变量读取，不硬编码敏感信息）
    embedding_api_url: str = ""  # 嵌入 API 地址，来源：env EMBEDDING_API_URL
    embedding_api_key: str = ""  # 嵌入 API 密钥，来源：env EMBEDDING_API_KEY
    embedding_model: str = "BAAI/bge-m3"  # 嵌入模型名称（非敏感，默认 bge-m3）

    # 知识库管理配置（多租户知识库：MySQL 事实源 + Milvus 向量 + Redis 热点 FAQ）
    knowledge_milvus_collection: str = "knowledge_base_v2"  # 新向量集合（带 tenant_id/kb_id/is_active）
    knowledge_chunk_size: int = 500  # 文档切块目标长度（字）
    knowledge_search_top_k: int = 5  # 向量检索默认返回数量
    knowledge_max_upload_mb: int = 5  # 上传文件大小上限（MB）

    # FAQ 热点缓存配置
    knowledge_faq_cache_enabled: bool = True  # 是否启用 Redis 热点 FAQ 缓存
    knowledge_faq_hot_threshold: int = 10  # 同一自然月命中该次数后晋升热点缓存
    knowledge_faq_cache_ttl_days: int = 35  # 热点缓存 TTL（天）
    knowledge_faq_hit_retention_months: int = 6  # 月度命中 ZSET 保留月数

    # 天气查询配置（和风天气 QWeather）
    # 2025-04 起推行独立 API Host，公共域名已逐步停用，须配置控制台分配的独立 Host
    qweather_api_key: str = ""  # 和风天气 API Key，来源：env QWEATHER_API_KEY
    qweather_api_host: str = ""  # 独立 API Host，来源：env QWEATHER_API_HOST（控制台设置页获取，如 xxx.re.qweatherapi.com）

    # 查询沙箱配置
    sql_statement_timeout: int = 10  # 秒
    sql_max_rows: int = 1000

    # 摘要生成配置
    llm_enable_summary: bool = False  # 是否用 LLM 生成查询结果摘要（默认模板）

    # 服务配置
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def database_url(self) -> str:
        """异步数据库连接 URL"""
        return (
            f"mysql+aiomysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?charset=utf8mb4"
        )

    @property
    def database_url_sync(self) -> str:
        """同步数据库连接 URL（用于 schema 导出等工具）"""
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?charset=utf8mb4"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
