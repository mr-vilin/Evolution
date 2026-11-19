"""仅解析部署者维护的固定注册表；客户端只能选引用，不能指定文件或环境变量。"""
import json
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
from .errors import TencentError


class Credential(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    label: str = Field(min_length=1, max_length=128)
    secret_id: SecretStr
    secret_key: SecretStr
    token: SecretStr | None = None


class CredentialRegistry:
    def __init__(self, settings):
        import re
        try:
            raw = json.loads(settings.tencent_credentials.get_secret_value()) if settings.tencent_credentials else {}
            if not isinstance(raw, dict) or len(raw) > 100:
                raise ValueError()
            self._entries = {}
            for ref, item in raw.items():
                if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', ref):
                    raise ValueError()
                entry = Credential.model_validate(item)
                if not entry.secret_id.get_secret_value().strip() or not entry.secret_key.get_secret_value().strip():
                    raise ValueError()
                self._entries[ref] = entry
        except (ValueError, TypeError, ValidationError):
            raise TencentError('TENCENT_CREDENTIAL_CONFIG_INVALID', '腾讯云凭据注册表配置无效，请联系部署维护人员', 503) from None

    def options(self):
        return [{'value': ref, 'label': entry.label} for ref, entry in self._entries.items()]

    def resolve(self, ref):
        if ref not in self._entries:
            raise TencentError('TENCENT_CREDENTIAL_REF_INVALID', '请选择已登记的受控凭据', 422)
        return self._entries[ref]
