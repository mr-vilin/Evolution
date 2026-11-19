"""腾讯迁移必须保留原有结构，并将全部原业务列纳入数据摘要。"""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import migrate_local_0020 as migration


def metadata_pair():
    before = ['employee\toriginal-' + str(index) for index in range(5)]
    after = ['\n'.join(sorted([section] + [table + '\tnew' for table in migration.TENCENT_TABLES]))
             for section in before]
    return before, after


def test_accepts_only_the_seven_new_tables():
    before, after = metadata_pair()
    migration.assert_only_tencent(before, after)


@pytest.mark.parametrize('section', range(5))
def test_rejects_any_existing_metadata_change(section):
    before, after = metadata_pair()
    after[section] = after[section].replace('original-', 'changed-')
    with pytest.raises(RuntimeError, match='EXISTING_METADATA_CHANGED'):
        migration.assert_only_tencent(before, after)


@pytest.mark.parametrize('case', ['missing', 'unexpected', 'already_exists'])
def test_rejects_partial_or_unexpected_table_sets(case):
    before, after = metadata_pair()
    if case == 'missing':
        after[0] = '\n'.join(line for line in after[0].splitlines() if not line.startswith('tencent_account\t'))
    elif case == 'unexpected':
        after[0] += '\nother_table\tunexpected'
    else:
        before[0] += '\ntencent_account\told'
    with pytest.raises(RuntimeError, match='TENCENT_TABLE_SET_MISMATCH'):
        migration.assert_only_tencent(before, after)


def test_digest_covers_existing_avatar_and_join_columns(monkeypatch):
    selects = []

    def sql(_container, query):
        if 'information_schema.TABLES' in query:
            return 'employee\ntencent_account'
        if 'information_schema.COLUMNS' in query:
            return 'id\navatar_url\njoin_time'
        if 'information_schema.KEY_COLUMN_USAGE' in query:
            return 'id'
        selects.append(query)
        return '1\thttps://example.invalid/avatar\t0'

    monkeypatch.setattr(migration, 'sql', sql)
    assert set(migration.business_digest('synthetic')) == {'employee'}
    assert selects == ['SELECT `id`,`avatar_url`,`join_time` FROM `employee` ORDER BY `id`;']


def test_nonempty_tencent_table_stops_verification(monkeypatch):
    monkeypatch.setattr(migration, 'sql', lambda _container, _query: '1')
    with pytest.raises(RuntimeError, match='UNEXPECTED_TENCENT_DATA'):
        migration.assert_tencent_empty('synthetic')
