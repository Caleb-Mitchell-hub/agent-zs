"""测试配置"""

import os
import pytest
from fastapi.testclient import TestClient

# 设置测试环境变量
os.environ['LLM_API_KEY'] = 'test-key'
os.environ['LLM_PROVIDER'] = 'deepseek'
os.environ['LLM_MODEL'] = 'deepseek-chat'
os.environ['LLM_BASE_URL'] = 'https://api.deepseek.com'
os.environ['DB_HOST'] = '172.177.3.43'
os.environ['DB_PORT'] = '3309'
os.environ['DB_USER'] = 'wms'
os.environ['DB_PASSWORD'] = 'Zsds2604!'
os.environ['DB_NAME'] = 'wms'


@pytest.fixture
def client():
    """创建测试客户端"""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """认证头"""
    return {'Authorization': 'Bearer test-token-1234567890'}
