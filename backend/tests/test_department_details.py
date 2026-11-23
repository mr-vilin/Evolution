from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.dependencies import get_admin_identity, get_runtime
from app.directory.details import department_details
from app.feishu.client import FeishuClient
from app.main import app
from app.persistence.models import DatasetState, Department, Employee
from app.persistence.read_service import SqlReadService


@pytest.fixture
def directory(sqlite_sessions):
    with sqlite_sessions.begin() as db:
        db.add(Department(id='0', feishu_department_id='0', name='组织', is_root=True))
        db.flush()
        db.add(Department(id='d', feishu_department_id='od_real', name='测试部门', parent_id='0', leader_user_id='main'))
        db.add(Employee(id='internal', feishu_user_id='main', name='主负责人', avatar_url='https://example.test/main.png'))
    return sqlite_sessions, SqlReadService(sqlite_sessions, 'secret')


class API:
    def __init__(self, raw, fail_chat=False):
        self.raw, self.fail_chat, self.calls = raw, fail_chat, []

    def detail(self, kind, identifier):
        self.calls.append((kind, identifier))
        if kind == 'department':
            assert identifier == 'od_real'
            return self.raw
        return {'user_id': identifier, 'name': '副负责人', 'avatar': {'avatar_72': 'https://example.test/vice.png'}}

    def chat(self, identifier):
        self.calls.append(('chat', identifier))
        if self.fail_chat:
            raise RuntimeError('FEISHU_API_ERROR')
        return {'name': '部门沟通群', 'owner_id': 'vice'}


@pytest.mark.parametrize('id_key,type_key', [('leaderID', 'leaderType'), ('leader_id', 'leader_type')])
def test_multiple_leaders_and_chat_owner_are_resolved_without_writes(directory, id_key, type_key):
    sessions, reads = directory
    api = API({'leaders': [{id_key: 'vice', type_key: 2}, {id_key: 'main', type_key: 1}], 'chat_id': 'oc_real'})
    data, _ = reads.get_department('d')
    result = department_details(data, sessions, api)
    assert [item['leader_type'] for item in result['leaders']] == [1, 2]
    assert result['leaders'][0]['name'] == '主负责人'
    assert result['leaders'][0]['avatar_url'] == 'https://example.test/main.png'
    assert result['chat_name'] == '部门沟通群'
    assert result['chat_id'] == 'oc_real'
    assert result['chat_owner']['name'] == '副负责人'
    assert result['parent_name'] == '本组织'
    assert result['detail_warnings'] == []
    assert api.calls.count(('user', 'vice')) == 1
    with sessions() as db:
        assert db.get(DatasetState, 1).data_version == 1
        assert db.get(Department, 'd').leader_user_id == 'main'


@pytest.mark.parametrize('raw,status', [({'chat_id': ''}, 'not_set'), ({}, 'unavailable'), ({'chat_id': None}, 'unavailable')])
def test_missing_chat_permission_is_distinct_from_explicit_no_chat(directory, raw, status):
    sessions, reads = directory
    result = department_details(reads.get_department('d')[0], sessions, API({'leaders': [], **raw}))
    assert result['chat_status'] == status
    assert bool(result['detail_warnings']) == (status == 'unavailable')


def test_chat_failure_preserves_leaders_and_department_failure_falls_back(directory):
    sessions, reads = directory
    data = reads.get_department('d')[0]
    result = department_details(data, sessions, API({'leaders': [{'leaderID': 'main', 'leaderType': 1}], 'chat_id': 'oc'}, True))
    assert result['leaders'][0]['name'] == '主负责人'
    assert result['chat_status'] == 'unavailable' and result['detail_warnings']
    assert result['chat_id'] == 'oc'
    result = department_details(data, sessions, None)
    assert result['leaders'][0]['user_id'] == 'main'
    assert result['detail_warnings'] and result['chat_status'] == 'unavailable'


def test_chat_request_uses_matching_user_id_namespace_and_escapes_path():
    def respond(request):
        assert request.method == 'GET'
        assert request.url.params['user_id_type'] == 'user_id'
        assert request.url.raw_path.startswith(b'/open-apis/im/v1/chats/oc%2Ftest?')
        return httpx.Response(200, json={'code': 0, 'data': {'name': '沟通群', 'owner_id': 'main'}})
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        api = FeishuClient('app', 'secret', http)
        api._token = lambda _: 'token'
        assert api.chat('oc/test')['owner_id'] == 'main'


def test_chat_permission_denial_is_explicit_and_does_not_echo_response():
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(400,
            json={'code': 99991672, 'msg': 'private response'}))) as http:
        api = FeishuClient('app', 'secret', http)
        api._token = lambda _: 'token'
        with pytest.raises(RuntimeError, match='^FEISHU_PERMISSION_REQUIRED$'):
            api.chat('oc')


def test_details_http_requires_admin_and_preserves_404(directory):
    sessions, reads = directory
    app.dependency_overrides[get_runtime] = lambda: SimpleNamespace(sessions=sessions, reads=reads)
    app.dependency_overrides[get_settings] = lambda: Settings()
    try:
        client = TestClient(app)
        assert client.get('/admin/api/departments/d/details').status_code == 401
        app.dependency_overrides[get_admin_identity] = lambda: SimpleNamespace(open_id='admin')
        assert client.get('/admin/api/departments/missing/details').status_code == 404
        response = client.get('/admin/api/departments/d/details')
        assert response.status_code == 200
        assert response.json()['data']['feishu_department_id'] == 'od_real'
    finally:
        app.dependency_overrides.clear()
