from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app.persistence.models import AdminSession, ApiClient, Department, StoreProfile


def test_business_tables_and_source_ids_inherit_the_project_collation():
    department_ddl = str(CreateTable(Department.__table__).compile(dialect=mysql.dialect()))
    store_ddl = str(CreateTable(StoreProfile.__table__).compile(dialect=mysql.dialect()))
    client_ddl = str(CreateTable(ApiClient.__table__).compile(dialect=mysql.dialect()))

    for ddl in (department_ddl, store_ddl, client_ddl):
        assert "ENGINE=InnoDB" in ddl
        assert "CHARSET=utf8mb4" in ddl
        assert "COLLATE utf8mb4_general_ci" in ddl
        assert "utf8mb4_bin" not in ddl


def test_revoked_sessions_can_be_retained_after_allowlist_entry_is_deleted():
    ddl = str(CreateTable(AdminSession.__table__).compile(dialect=mysql.dialect()))
    assert "FOREIGN KEY(open_id)" not in ddl
    assert any(index.name == "ix_admin_session_open_id" for index in AdminSession.__table__.indexes)
