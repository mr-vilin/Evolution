"""官方 SDK 签名和原始传输边界；金额从原始 JSON 解析，不经过 float。"""
import json
import logging
from decimal import Decimal
from .errors import TencentError


def get_tencent_transport():
    return sdk_transport


def sdk_transport(credential, action, params):
    from tencentcloud.common.credential import Credential as SdkCredential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.common.retry import NoopRetryer
    from tencentcloud.billing.v20180709.billing_client import BillingClient
    # SDK DEBUG 会输出签名请求及完整财务正文，禁止被应用 root DEBUG 意外开启。
    logger = logging.getLogger('tencentcloud_sdk_common')
    logger.disabled = True
    logger.propagate = False
    client = BillingClient(SdkCredential(credential.secret_id.get_secret_value(), credential.secret_key.get_secret_value(),
        credential.token.get_secret_value() if credential.token else None), '', ClientProfile(httpProfile=HttpProfile(reqTimeout=10), retryer=NoopRetryer()))
    return client.call(action, params)


class TencentGateway:
    def __init__(self, transport, sessions=None, request_id=None):
        self.transport, self.sessions, self.request_id = transport, sessions, request_id

    def call(self, credential, action, params, *, target=None):
        from .audit import outgoing_call
        with outgoing_call(self.sessions, self.request_id, action, target) as evidence:
            try:
                raw = self.transport(credential, action, params)
                value = json.loads(raw, parse_float=Decimal)
                response = value['Response']
                if not isinstance(response, dict):
                    raise ValueError()
                if 'Error' in response:
                    raise TencentError('TENCENT_PERMISSION_DENIED' if str(response['Error'].get('Code','')).startswith(('AuthFailure','UnauthorizedOperation')) else 'TENCENT_UPSTREAM_FAILED', '腾讯云拒绝本次查询，请核查凭据权限和账号', 502)
                request_id = response.get('RequestId')
                if not isinstance(request_id, str) or not 0 < len(request_id) <= 128:
                    raise ValueError()
                evidence['upstream_request_id'] = request_id
                return response
            except TencentError:
                raise
            except (TimeoutError, ConnectionError):
                raise TencentError('TENCENT_TIMEOUT', '腾讯云查询超时，请稍后重试', 504) from None
            except Exception as exc:
                code = exc.get_code() if hasattr(exc, 'get_code') else ''
                if str(code).startswith(('AuthFailure', 'UnauthorizedOperation')):
                    raise TencentError('TENCENT_PERMISSION_DENIED', '腾讯云凭据权限不足', 502) from None
                if str(code).startswith('ClientNetworkError'):
                    raise TencentError('TENCENT_TIMEOUT', '腾讯云查询超时或网络不可用', 504) from None
                raise TencentError('TENCENT_UPSTREAM_INVALID', '腾讯云返回无法核验的结果', 502) from None

    def verify_uin(self, credential, uin):
        response = self.call(credential, 'DescribeAccountBalance', {}, target=uin)
        actual = response.get('Uin')
        if isinstance(actual, bool) or not isinstance(actual, (str, int)) or str(actual) != uin:
            raise TencentError('TENCENT_ACCOUNT_MISMATCH', '凭据归属与账号 UIN 不一致', 422)
        return response['RequestId']
