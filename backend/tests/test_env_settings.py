from app.config import Settings
from app.env import isolated_test_env
from app.mcp.config import MCPSettings


def test_database_and_mcp_settings_use_canonical_keys(monkeypatch):
    values = {
        "DATABASE_URL": "fixture-database",
        "FEISHU_RECONCILE_ON_STARTUP": "true",
        "MCP_SERVICE_TOKEN": "fixture-mcp",
        "AGENT_SERVICE_TOKEN": "fixture-agent",
        "AGENT_ENVIRONMENT": "test",
        "MCP_CAPABILITY_BASE_URL": "http://localhost:8000",
        "MCP_ACTOR_TYPE": "ci_agent",
        "MCP_ACTOR_ID": "fixture-agent",
        "MCP_RUN_ID": "test-fixture",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ORG_DATABASE_URL", "retired-database")
    monkeypatch.setenv("ORG_MCP_ACTOR_ID", "retired-actor")
    assert Settings().database_url == "fixture-database"
    assert Settings().feishu_reconcile_on_startup
    assert MCPSettings().principal().actor_id == "fixture-agent"


def test_old_database_key_is_ignored_without_a_new_key(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ORG_DATABASE_URL", "retired-database")
    assert Settings().database_url is None


def test_mysql_test_environment_strips_application_settings(monkeypatch):
    names = ("DATABASE_URL", "FEISHU_APP_SECRET", "SESSION_SECRET",
             "MCP_SERVICE_TOKEN", "MIGRATION_TEST_DATABASE_URL")
    for name in names:
        monkeypatch.setenv(name, "fixture")
    assert not set(isolated_test_env(Settings)).intersection(names)
