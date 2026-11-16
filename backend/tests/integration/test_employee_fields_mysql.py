"""真实 MySQL 上验证初始化、定时核对与配置刷新后的人员字段。"""
from sqlalchemy import text

from test_initialization_mysql import configured
from test_sync_employee_fields import test_all_detail_fields_survive_initialization_scheduled_sync_and_event as verify_fields


def test_employee_field_pipeline_mysql(mysql_sessions):
    service, api, settings = configured(mysql_sessions)
    with mysql_sessions() as db:
        session = db.execute(text('SELECT VERSION(), @@character_set_connection, @@collation_connection')).one()
        assert session[0].startswith('8.4.')
        assert session[1:] == ('utf8mb4', 'utf8mb4_general_ci')
    verify_fields((mysql_sessions, service, api, settings))
