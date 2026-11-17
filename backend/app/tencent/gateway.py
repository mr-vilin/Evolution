"""官方 SDK 签名和原始传输边界；金额从原始 JSON 解析，不经过 float。"""
import json
import logging
import re
from decimal import Decimal
from .errors import TencentError


def get_tencent_transport():
    return sdk_transport


def safe_request_id(value):
    return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value) else None


def upstream_error(code, request_id=None):
    """仅接受稳定分类与已校验请求标识，永不保留上游Message。"""
    if str(code).startswith(('AuthFailure','UnauthorizedOperation')):
        mapped,message,status='TENCENT_PERMISSION_DENIED','腾讯云凭据权限不足',502
    elif str(code).startswith(('RequestLimitExceeded','LimitExceeded')):
        mapped,message,status='TENCENT_RATE_LIMITED','腾讯云查询受到限流，请稍后重试',502
    elif str(code).startswith(('InvalidParameter','MissingParameter','UnknownParameter')):
        mapped,message,status='TENCENT_PARAMETER_INVALID','腾讯云拒绝查询参数，请联系维护人员',502
    elif str(code).startswith(('InternalError','ServiceUnavailable')):
        mapped,message,status='TENCENT_UNAVAILABLE','腾讯云暂时无法处理查询',502
    elif str(code).startswith('ClientNetworkError'):
        mapped,message,status='TENCENT_TIMEOUT','腾讯云查询超时或网络不可用',504
    else:
        mapped,message,status='TENCENT_UPSTREAM_FAILED','腾讯云拒绝本次查询，请核查账号及查询范围',502
    error=TencentError(mapped,message,status)
    error.upstream_request_id=safe_request_id(request_id)
    error.upstream_response_state='ERROR' if error.upstream_request_id else 'UNKNOWN'
    return error


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
                request_id = safe_request_id(response.get('RequestId'))
                if request_id:
                    evidence['upstream_request_id'] = request_id
                if 'Error' in response:
                    if not isinstance(response['Error'],dict):raise ValueError()
                    raise upstream_error(response['Error'].get('Code',''),request_id)
                if not request_id:
                    raise ValueError()
                return response
            except TencentError:
                raise
            except (TimeoutError, ConnectionError):
                raise TencentError('TENCENT_TIMEOUT', '腾讯云查询超时，请稍后重试', 504) from None
            except Exception as exc:
                code = exc.get_code() if hasattr(exc, 'get_code') else ''
                if code:
                    request_id=safe_request_id(exc.get_request_id() if hasattr(exc,'get_request_id') else None)
                    if request_id:evidence['upstream_request_id']=request_id
                    raise upstream_error(code,request_id) from None
                raise TencentError('TENCENT_UPSTREAM_INVALID', '腾讯云返回无法核验的结果', 502) from None

    def verify_uin(self, credential, uin):
        response = self.call(credential, 'DescribeAccountBalance', {}, target=uin)
        actual = response.get('Uin')
        if isinstance(actual, bool) or not isinstance(actual, (str, int)) or str(actual) != uin:
            raise TencentError('TENCENT_ACCOUNT_MISMATCH', '凭据归属与账号 UIN 不一致', 422)
        return response['RequestId']
