from datetime import datetime, timezone

import pytest

from app.persistence.models import Employee
from app.persistence.read_service import SqlReadService
from app.sync.collector import Candidate, optional_user_facts, normalize_user
from app.sync.publisher import Publisher


@pytest.mark.parametrize('raw,expected,state', [
    ({}, None, 'not_collected'), ({'join_time': None}, None, 'readable'),
    ({'join_time': 0}, 0, 'readable'), ({'join_time': True}, None, 'unreadable'),
    ({'join_time': 1700000000000}, None, 'unreadable'), ({'join_time': -1}, None, 'unreadable'),
    ({'join_time': 1700000000}, 1700000000, 'readable'),
])
def test_join_time_preserves_missing_empty_and_unreadable(raw, expected, state):
    facts = optional_user_facts(raw)
    assert facts['join_time'] == expected
    assert facts['field_readability']['join_time'] == state


def test_avatar_only_accepts_https_and_falls_back_between_sizes():
    facts = optional_user_facts({'avatar': {'avatar_240': 'javascript:alert(1)', 'avatar_72': 'https://example.test/avatar.png'}})
    assert facts['avatar_url'] == 'https://example.test/avatar.png'
    assert facts['field_readability']['avatar_url'] == 'readable'
    assert optional_user_facts({'avatar': {'avatar_240': 'file:///private'}})['field_readability']['avatar_url'] == 'unreadable'
    assert optional_user_facts({})['field_readability']['avatar_url'] == 'not_collected'
    assert optional_user_facts({'avatar': {}})['field_readability']['avatar_url'] == 'readable'


def test_profile_publishes_and_reads_leader_avatar_and_shanghai_date(sqlite_sessions):
    joined = int(datetime(2026, 11, 6, 16, tzinfo=timezone.utc).timestamp())
    normalized = normalize_user({'user_id': 'u', 'name': '人员', 'department_ids': [],
        'status': {'is_resigned': False}, 'leader_user_id': 'leader', 'join_time': joined,
        'avatar': {'avatar_240': 'https://example.test/person.png'}})
    with sqlite_sessions.begin() as db:
        db.add(Employee(id='leader', feishu_user_id='leader', name='上级', avatar_url='https://example.test/leader.png'))
    publisher = Publisher(sqlite_sessions)
    publisher.publish(Candidate(employees={'u': normalized}))
    reads = SqlReadService(sqlite_sessions, 's' * 32)
    data, _ = reads.get_employee('u')
    assert data['join_date'] == '2026-11-07'
    assert data['avatar_url'] == 'https://example.test/person.png'
    assert data['leader_avatar_url'] == 'https://example.test/leader.png'
    # 缺省的新资料不能被误标成可读的历史资料。
    cleared = normalize_user({'user_id': 'u', 'name': '人员', 'department_ids': [], 'status': {'is_resigned': False}})
    publisher.publish(Candidate(employees={'u': cleared}))
    data, _ = reads.get_employee('u')
    assert data['join_date'] is None and data['avatar_url'] is None
    assert data['field_readability']['join_time'] == 'not_collected'
