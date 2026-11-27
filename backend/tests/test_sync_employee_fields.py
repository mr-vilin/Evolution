"""验证真实初始化、定时任务、事件采集到人员详情的字段闭环。"""
from datetime import datetime

import pytest
from sqlalchemy import select

from app.initialization.validation import validate_definitions, validate_user
from app.persistence.models import Employee, SyncJob
from app.persistence.read_service import SqlReadService
from app.sync.collector import Collector, normalize_user
from app.sync.publisher import Publisher
from app.sync.settings import ScheduleService
from app.feishu.binding import custom_attrs, put_custom_attrs
from test_initialization_wizard import Feishu, MAPPINGS, ready, setup, worker_for


@pytest.mark.parametrize('type_value', [1, '1', {'id': '1', 'name': '旧名称'}])
def test_regular_sync_resolves_employee_type_from_configured_options(type_value):
    raw = Feishu().users['u']
    raw['employee_type'] = type_value
    value = normalize_user(raw, MAPPINGS, set(MAPPINGS['employee_type_options']))
    assert (value['employee_type_id'], value['employee_type_name']) == ('1', '正式员工')


def test_unknown_employee_type_keeps_identifier_without_inventing_name():
    raw = Feishu().users['u']
    raw['employee_type'] = 99
    value = normalize_user(raw, MAPPINGS)
    assert value['employee_type_id'] == '99'
    assert value['employee_type_name'] is None
    assert value['sync_quality'] == 'complete'


@pytest.mark.parametrize('type_value', [True, 1.5, [], {'id': []}])
def test_invalid_employee_type_is_not_published_as_an_empty_value(type_value):
    raw = Feishu().users['u']
    raw['employee_type'] = type_value
    value = normalize_user(raw, MAPPINGS)
    assert value['sync_quality'] == 'complete'
    assert set(value['optional_field_issues']) == {'employee_type_id', 'employee_type_name'}


def test_preflight_reports_avatar_and_join_date_even_when_omitted():
    api = Feishu()
    definitions = validate_definitions(next(api.pages('custom_attrs'))['items'], MAPPINGS)
    results = []
    validate_user(api.users['u'], MAPPINGS, definitions, field_results=results)
    by_field = {item['field']: item for item in results}
    for key in ('avatar_url', 'join_time'):
        assert by_field[key]['status'] == 'passed'
        assert by_field[key]['readability'] == 'not_collected'


def test_all_detail_fields_survive_initialization_scheduled_sync_and_event(setup):
    sessions, service, api, _ = setup
    api.users['u'].update(
        open_id='ou_u', employee_no='E001', mobile='+8613800000000',
        email='person@example.test', job_title='工程师', leader_user_id='v',
        avatar={'avatar_240': 'https://example.test/avatar.png'}, join_time=1786032000,
    )
    api.users['u']['custom_attrs'][1]['value'] = {'option_id': 'manager', 'option_value': '店长'}
    ready(service)
    service.start('admin:ou')
    worker = worker_for(setup)
    assert worker.step()
    assert service.status()['complete']
    reads = SqlReadService(sessions, 's' * 32)
    expected = {
        'user_id': 'u', 'employee_no': 'E001', 'mobile': '+8613800000000',
        'email': 'person@example.test', 'job_title': '工程师', 'leader_user_id': 'v',
        'leader_name': 'v', 'avatar_url': 'https://example.test/avatar.png',
        'employee_type_id': '1', 'employee_type_name': '正式员工',
        'permission_role_id': 'manager', 'permission_role_name': '店长',
        'store_attribute_id': 'manager', 'store_attribute_name': '店长',
        'primary_department_id': 'd', 'department_ids': ['d'],
    }

    def assert_fields():
        actual, _ = reads.get_employee('u')
        assert {key: actual[key] for key in expected} == expected
        assert actual['join_date'] == '2026-08-07'
        with sessions() as db:
            assert db.get(Employee, 'u').open_id == 'ou_u'

    assert_fields()
    schedule = ScheduleService(sessions)
    schedule.put({'enabled': True, 'local_time': '03:00', 'timezone': 'Asia/Shanghai'}, 'test')
    assert schedule.due(datetime(2030, 1, 1, 19))
    assert worker.step()
    with sessions() as db:
        scheduled = list(db.scalars(select(SyncJob).where(SyncJob.trigger_source == 'schedule')))
        assert scheduled and all(job.status == 'succeeded' for job in scheduled)
    assert_fields()

    put_custom_attrs(sessions, {'employee_type_options': {'1': '自定义正式人员'}})
    expected['employee_type_name'] = '自定义正式人员'
    assert custom_attrs(sessions)['permission_role'] == MAPPINGS['permission_role']
    assert custom_attrs(sessions)['store_attribute'] == MAPPINGS['store_attribute']
    # 配置保存不直接改写人员；下次真实调度链路应刷新映射并入库。
    assert reads.get_employee('u')[0]['employee_type_name'] == '正式员工'
    assert ScheduleService(sessions).due(datetime(2030, 1, 2, 19))
    assert worker.step()
    assert_fields()

    api.users['u']['job_title'] = '高级工程师'
    expected['job_title'] = '高级工程师'
    Publisher(sessions).publish(Collector(api, custom_mappings=custom_attrs(sessions)).event('contact.user.updated_v3', 'u'))
    assert_fields()


@pytest.mark.parametrize('options', [None, [], {'': '名称'}, {'1': ' '}, {'x' * 192: '名称'}, {'1': '名' * 256}, {'1': '名称', ' 1 ': '重复'}])
def test_invalid_config_does_not_replace_existing_mapping(setup, options):
    sessions, _, _, _ = setup
    with pytest.raises(ValueError, match='VALIDATION_ERROR'):
        put_custom_attrs(sessions, {'employee_type_options': options})
    assert custom_attrs(sessions) == MAPPINGS


@pytest.mark.parametrize('value', [None, ''])
def test_explicit_empty_type_does_not_fall_back_to_old_fields(value):
    raw = Feishu().users['u']
    raw.update(employee_type=value, employee_type_id='1', employee_type_name='旧名称')
    normalized = normalize_user(raw, MAPPINGS)
    assert normalized['employee_type_id'] is None
    assert normalized['employee_type_name'] is None
