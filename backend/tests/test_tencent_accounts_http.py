"""腾讯云管理 HTTP 边界；外部腾讯云请求为唯一模拟边界。"""
from fastapi.testclient import TestClient
from app.main import app


def test_anonymous_cannot_read_tencent_accounts():
    response = TestClient(app).get('/admin/api/tencent/accounts')
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'ADMIN_SESSION_REQUIRED'
