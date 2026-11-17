"""已授权隔离 MySQL 的实际迁移/恢复演练，不连接业务环境。"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from test_tencent_accounts_mysql import tencent_http


def test_account_maintenance_migration_backfills_and_preserves_account_binding(tencent_http):
    client, sessions, calls = tencent_http
    config = Config(str(Path(__file__).parents[2] / 'alembic.ini'))
    config.set_main_option('script_location', str(Path(__file__).parents[2] / 'migrations'))
    # fixture 已核实13306、专用测试库、MySQL8.4、字符集会话及全部worker静默。
    command.downgrade(config, '0016_tencent_recovery')
    try:
        with sessions.begin() as db:
            db.execute(text("INSERT INTO tencent_account(uin,alias,credential_ref,credential_revision,is_enabled,verification_status,verified_at) VALUES('10001','迁移前账号','finance-a',9,1,'verified',UTC_TIMESTAMP())"))
    finally:
        command.upgrade(config, 'head')
    with sessions() as db:
        row = db.execute(text("SELECT uin,alias,credential_ref,credential_revision,revision FROM tencent_account WHERE uin='10001'")).one()
        assert tuple(row) == ('10001','迁移前账号','finance-a',9,1)
        actual = inspect(db.get_bind())
        column = next(value for value in actual.get_columns('tencent_account') if value['name'] == 'revision')
        assert column['type'].unsigned and column['nullable'] is False
        assert column['comment'] == '账号维护并发修订号，每次有效维护递增'
        assert actual.get_foreign_keys('tencent_account') == []
        from app.persistence.schema_check import check_schema
        assert check_schema(db.get_bind())['errors'] == []
    # 静默条件下恢复演练，不删除账号、绑定、安全修订及历史。
    command.downgrade(config, '0016_tencent_recovery')
    command.upgrade(config, 'head')
    assert client.get('/admin/api/tencent/accounts').json()['data'][0]['credential_revision'] == 9
