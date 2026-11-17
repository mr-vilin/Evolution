"""腾讯云模块局部实际请求审计；只保存服务端元信息，不接触请求/财务正文。"""
from contextlib import contextmanager
from datetime import datetime, timezone
import logging
import time
import uuid
from app.persistence.models import TencentApiCall

log = logging.getLogger('organization.tencent.audit')

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@contextmanager
def outgoing_call(sessions, request_id, action, target):
    evidence = {}
    if sessions is None:
        yield evidence
        return
    event_id, started = str(uuid.uuid4()), time.monotonic()
    with sessions.begin() as db:
        db.add(TencentApiCall(id=event_id, request_id=request_id or str(uuid.uuid4()), direction='outbound',
            action=action, method='POST', route=action, outcome='running', target_id=target, started_at=now()))
    try:
        yield evidence
    except BaseException as exc:
        evidence['reason_code'] = getattr(exc, 'code', 'TENCENT_UPSTREAM_FAILED')
        raise
    finally:
        with sessions.begin() as db:
            row = db.get(TencentApiCall, event_id)
            row.finished_at = now()
            row.returned_at = row.finished_at if evidence.get('upstream_request_id') else None
            row.duration_ms = int((time.monotonic()-started)*1000)
            row.outcome = 'failed' if evidence.get('reason_code') else 'succeeded'
            row.reason_code = evidence.get('reason_code')
            row.upstream_request_id = evidence.get('upstream_request_id')


class TencentAuditMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith('/admin/api/tencent/'):
            return await self.app(scope, receive, send)
        from app.dependencies import get_runtime
        app = scope['app']
        runtime = app.dependency_overrides.get(get_runtime, get_runtime)()
        sessions = runtime.sessions if runtime else None
        request_id, started = str(uuid.uuid4()), time.monotonic()
        scope.setdefault('state', {})['tencent_request_id'] = request_id
        event_id = request_id
        if sessions:
            with sessions.begin() as db:
                db.add(TencentApiCall(id=event_id, request_id=request_id, direction='inbound', action='unknown',
                    method=scope['method'], route='/admin/api/tencent/unknown', outcome='running', started_at=now()))
        status, returned, finalized = None, None, False
        async def finish(outcome):
            nonlocal finalized
            if finalized:
                return
            finalized = True
            state = scope.get('state', {})
            route = getattr(scope.get('route'), 'path', '/admin/api/tencent/unknown')
            if sessions:
                with sessions.begin() as db:
                    row = db.get(TencentApiCall, event_id)
                    row.action = state.get('tencent_action') or _route_action(scope['method'], route)
                    row.permission_code = state.get('tencent_action')
                    row.reason_code = state.get('tencent_reason')
                    row.actor_id = state.get('tencent_actor')
                    row.target_id = state.get('tencent_target')
                    row.route, row.status_code = route, status
                    row.outcome = outcome
                    row.returned_at, row.finished_at = returned, now()
                    row.duration_ms = int((time.monotonic()-started)*1000)
            else:
                log.warning('tencent.audit_unavailable request_id=%s status=%s', request_id, status)
        async def audited_send(message):
            nonlocal status, returned
            if message['type'] == 'http.response.start':
                status = message['status']
                message['headers'] = [(k,v) for k,v in message.get('headers',[]) if k.lower() not in {b'cache-control',b'x-request-id'}]
                message['headers'].extend([(b'cache-control',b'no-store'),(b'x-request-id',request_id.encode())])
                # 先保存已观察到的应用状态，真实发送结果尚未知；不复制响应正文。
                if sessions:
                    with sessions.begin() as db:
                        row = db.get(TencentApiCall, event_id)
                        row.status_code = status
                        row.outcome = 'unknown'
            await send(message)
            if message['type'] == 'http.response.body' and not message.get('more_body', False):
                returned = now()
                try:
                    await finish('succeeded' if status is not None and status < 400 else 'failed')
                except Exception:
                    # 已发送结果不能因审计收尾失败变成业务失败；可靠开始记录保留 unknown，缺口显式可查。
                    log.error('tencent.audit_finish_failed request_id=%s', request_id)
        try:
            await self.app(scope, receive, audited_send)
        finally:
            await finish('unknown')


def _route_action(method, route):
    return {('GET','/admin/api/tencent/accounts/{account_id}/balance'):'tencent.balance.query',
            ('GET','/admin/api/tencent/accounts'):'tencent.account.read',
            ('GET','/admin/api/tencent/credential-options'):'tencent.account.read',
            ('POST','/admin/api/tencent/accounts'):'tencent.account.create',
            ('POST','/admin/api/tencent/accounts/validate'):'tencent.account.validate',
            ('GET','/admin/api/tencent/accounts/{account_id}/cost-config'):'tencent.cost.read',
            ('PUT','/admin/api/tencent/accounts/{account_id}/cost-config'):'tencent.config.update',
            ('POST','/admin/api/tencent/accounts/{account_id}/cost-jobs'):'tencent.cost.rerun',
            ('GET','/admin/api/tencent/accounts/{account_id}/cost-jobs'):'tencent.job.read',
            ('GET','/admin/api/tencent/cost-jobs/{job_id}'):'tencent.job.read',
            ('GET','/admin/api/tencent/accounts/{account_id}/cost-periods/{month}'):'tencent.cost.read',
            ('GET','/admin/api/tencent/accounts/{account_id}/cost-dashboard'):'tencent.cost.read',
            ('GET','/admin/api/tencent/accounts/{account_id}/cost-export'):'tencent.cost.export'}.get((method,route),'unknown')
