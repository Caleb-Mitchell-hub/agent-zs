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

    # 查询沙箱配置
    sql_statement_timeout: int = 10  # 秒
    sql_max_rows: int = 1000

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
