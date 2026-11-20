"""测试子进程的环境变量隔离。"""

import os


def isolated_test_env(settings_cls) -> dict[str, str]:
    """测试子进程只使用验收脚本显式注入的连接和服务配置。"""
    names = {name.upper() for name in settings_cls.model_fields}
    names.update(("TEST_DATABASE_URL", "MIGRATION_TEST_DATABASE_URL",
                  "EVALUATION_MODEL_ALIAS", "EVALUATION_MAX_TOKENS"))
    return {key: value for key, value in os.environ.items()
            if key.upper() not in names and not key.upper().startswith("MCP_")}
