"""认证测试"""


def test_query_without_token_returns_401(client):
    """测试无 token 访问返回 401"""
    response = client.post('/api/v1/query', json={'question': '测试'})
    assert response.status_code == 401

    data = response.json()
    assert 'detail' in data
    assert data['detail']['error_code'] == 'UNAUTHORIZED'


def test_report_without_token_returns_401(client):
    """测试无 token 访问报表返回 401"""
    response = client.post('/api/v1/report', json={'question': '测试'})
    assert response.status_code == 401


def test_query_with_token_passes_auth(client, auth_headers):
    """测试有 token 访问通过认证"""
    response = client.post(
        '/api/v1/query',
        json={'question': '测试'},
        headers=auth_headers,
    )
    # 通过认证（不是 401），但可能因为数据库未初始化返回错误
    assert response.status_code != 401


def test_report_with_token_passes_auth(client, auth_headers):
    """测试有 token 访问报表通过认证"""
    response = client.post(
        '/api/v1/report',
        json={'question': '测试'},
        headers=auth_headers,
    )
    assert response.status_code != 401
