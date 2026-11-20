from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    agent_service_token: SecretStr | None = None
    agent_environment: Literal["production", "test"] = "production"
    tencent_credentials: SecretStr | None = None
    database_url: str | None = None
    session_secret: SecretStr | None = None
    feishu_app_id: str | None = None
    feishu_app_secret: SecretStr | None = None
    feishu_redirect_uri: str | None = None
    feishu_tenant_key: str | None = None
    feishu_scopes: str = ""
    feishu_reconcile_on_startup: bool = False
    feishu_reconcile_on_reconnect: bool = False
    coverage_acceptance_reference: str = ""
    coverage_all_members_verified: bool = False
    coverage_departmentless_verified: bool = False
    initial_admin_open_ids: str = ""

    @property
    def admin_open_ids(self) -> set[str]:
        return {value.strip() for value in self.initial_admin_open_ids.split(",") if value.strip()}

    @property
    def identity_ready(self) -> bool:
        return all((self.session_secret, self.feishu_app_id, self.feishu_app_secret, self.feishu_redirect_uri, self.feishu_tenant_key))


@lru_cache
def get_settings() -> Settings:
    return Settings()
