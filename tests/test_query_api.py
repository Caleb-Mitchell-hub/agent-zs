"""查询 API 端点测试"""


def test_query_endpoint_exists(client, auth_headers):
    """测试查询端点存在"""
    response = client.post(
        '/api/v1/query',
        json={'question': '测试'},
        headers=auth_headers,
    )
    # 应该返回 200（即使内部有错误）
    assert response.status_code == 200


def test_query_response_structure(client, auth_headers):
    """测试查询响应结构"""
    response = client.post(
        '/api/v1/query',
        json={'question': '测试'},
        headers=auth_headers,
    )
    data = response.json()

    # 检查响应结构
    assert 'status' in data
    assert 'data' in data
    assert 'sql' in data
    assert 'message' in data
    assert 'error_code' in data


def test_query_stream_endpoint_requires_auth(client):
    """测试流式查询端点需要认证"""
    response = client.get('/api/v1/query/stream?question=测试')
    assert response.status_code == 401
