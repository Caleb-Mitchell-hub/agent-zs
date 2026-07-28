"""健康检查端点测试"""


def test_health_check(client):
    """测试健康检查端点"""
    response = client.get('/health')
    assert response.status_code == 200

    data = response.json()
    assert 'status' in data
    assert 'service' in data
    assert 'version' in data
    assert data['service'] == 'Agent-Zs'


def test_health_check_has_database_info(client):
    """测试健康检查包含数据库信息"""
    response = client.get('/health')
    data = response.json()

    assert 'database' in data
    assert 'status' in data['database']
