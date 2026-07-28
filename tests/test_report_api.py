"""报表 API 端点测试"""


def test_report_endpoint_exists(client, auth_headers):
    """测试报表端点存在"""
    response = client.post(
        '/api/v1/report',
        json={'question': '测试'},
        headers=auth_headers,
    )
    assert response.status_code == 200


def test_report_response_structure(client, auth_headers):
    """测试报表响应结构"""
    response = client.post(
        '/api/v1/report',
        json={'question': '测试'},
        headers=auth_headers,
    )
    data = response.json()

    # 检查响应结构
    assert 'status' in data
    assert 'data' in data
    assert 'title' in data
    assert 'columns' in data
    assert 'message' in data
    assert 'error_code' in data
