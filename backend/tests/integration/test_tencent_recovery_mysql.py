"""公开 seam：HTTP 任务受理/查询 → 实际 worker → 独立 MySQL 连接。"""
from datetime import datetime, timedelta, timezone
import json
import pytest

from app.main import app
from app.config import get_settings
from app.tencent.cost_worker import TencentCostWorker
from test_tencent_accounts_mysql import tencent_http
from test_tencent_cost_mysql import cost_http, enable_cost, wire


def submit(client, account, key, month='2026-10'):
    response = client.post(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs",
        json={'month': month, 'idempotency_key': key})
    assert response.status_code == 202, response.text
    return response.headers['location']


def successful_wire(credential, action, params):
    if action == 'DescribeAccountBalance':
        return b'{"Response":{"Uin":10001,"RequestId":"recovery-identity"}}'
    value = wire()
    if params['PageNo'] > 1:
        value['Response']['Detail'] = []
    return json.dumps(value).encode()


def test_network_retry_keeps_job_scope_and_independent_attempt_evidence_after_restart(cost_http):
    client, sessions, account = cost_http
    enable_cost(client, account)
    url = submit(client, account, 'retry-network')
    current = [datetime.now(timezone.utc).replace(tzinfo=None)]
    failed = [False]
    def transport(credential, action, params):
        if not failed[0]:
            failed[0] = True
            raise TimeoutError('synthetic secret must never be retained')
        if action == 'DescribeAccountBalance':
            return b'{"Response":{"Uin":10001,"RequestId":"retry-identity"}}'
        value = wire()
        if params['PageNo'] > 1:
            value['Response']['Detail'] = []
        return json.dumps(value).encode()
    worker = TencentCostWorker(sessions, app.dependency_overrides[get_settings](), transport, now=lambda: current[0])
    assert worker.run_once()
    first = client.get(url).json()['data']
    assert first['status'] == 'retry_wait'
    assert first['attempts'][0]['status'] == 'failed'
    assert first['attempts'][0]['return_state'] == 'NOT_RETURNED'
    assert first['attempts'][0]['execution_output'] is None
    assert worker.run_once() is False
    current[0] += timedelta(minutes=2)
    restarted = TencentCostWorker(sessions, app.dependency_overrides[get_settings](), transport, now=lambda: current[0])
    assert restarted.run_once()
    result = client.get(url).json()['data']
    assert result['id'] == first['id']
    assert result['status'] == 'succeeded'
    assert [row['attempt_no'] for row in result['attempts']] == [1, 2]
    assert result['attempts'][1]['return_state'] == 'VALUE'
    assert result['attempts'][0]['execution_input']['month'] == result['attempts'][1]['execution_input']['month'] == '2026-10'
    assert result['attempts'][0]['execution_input']['config_revision'] == result['attempts'][1]['execution_input']['config_revision']
    assert result['attempts'][1]['execution_output']['status'] == 'committed'
    assert 'synthetic secret' not in json.dumps(result)


def test_editing_runtime_policy_does_not_change_an_accepted_retry_and_invalid_budgets_are_rejected(cost_http):
    client, sessions, account = cost_http
    enable_cost(client, account)
    config_url = f"/admin/api/tencent/accounts/{account['id']}/cost-config"
    first = client.get(config_url).json()['data']
    assert first['run_policy']['max_attempts'] == 3
    url = submit(client, account, 'frozen-policy')
    current = [datetime.now(timezone.utc).replace(tzinfo=None)]
    failures = [1]
    def transport(credential, action, params):
        if failures[0]:
            failures[0] -= 1
            raise TimeoutError()
        if action == 'DescribeAccountBalance':
            return b'{"Response":{"Uin":10001,"RequestId":"identity"}}'
        value = wire()
        if params['PageNo'] > 1:
            value['Response']['Detail'] = []
        return json.dumps(value).encode()
    worker = TencentCostWorker(sessions, app.dependency_overrides[get_settings](), transport, now=lambda: current[0])
    assert worker.run_once()
    body = {'revision': first['revision'], 'is_enabled': True, 'frequency': 'manual', 'currency': 'CNY',
        'run_policy': {**first['run_policy'], 'max_attempts': 1}}
    saved = client.put(config_url, json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()['data']['revision'] > first['revision']
    current[0] += timedelta(minutes=2)
    assert worker.run_once()
    result = client.get(url).json()['data']
    assert result['status'] == 'succeeded'
    assert result['attempts'][1]['execution_input']['policy']['max_attempts'] == 3
    invalid = client.put(config_url, json={**body, 'revision': saved.json()['data']['revision'],
        'run_policy': {**first['run_policy'], 'heartbeat_seconds': 120}})
    assert invalid.status_code == 422


@pytest.mark.parametrize('official_sdk', [False, True])
def test_rate_limit_is_bounded_and_each_attempt_links_the_actual_returned_error(cost_http, monkeypatch, official_sdk):
    from sqlalchemy import select
    from app.persistence.models import TencentApiCall
    client, sessions, account = cost_http
    enable_cost(client, account)
    url = submit(client, account, 'limited')
    current = [datetime.now(timezone.utc).replace(tzinfo=None)]
    raw = b'{"Response":{"Error":{"Code":"RequestLimitExceeded","Message":"do not retain sensitive wire text"},"RequestId":"limited-upstream"}}'
    def transport(*args):
        return raw
    if official_sdk:
        import requests
        from app.tencent.gateway import sdk_transport
        def send(self, **kwargs):
            response = requests.Response()
            response.status_code = 200
            response._content = raw
            return response
        monkeypatch.setattr(requests.Session, 'request', send)
        transport = sdk_transport
    worker = TencentCostWorker(sessions, app.dependency_overrides[get_settings](), transport, now=lambda: current[0])
    for number in range(3):
        assert worker.run_once()
        result = client.get(url).json()['data']
        assert result['status'] == ('retry_wait' if number < 2 else 'failed')
        assert result['attempts'][number]['error_code'] == 'TENCENT_RATE_LIMITED'
        assert result['attempts'][number]['failure_evidence']['upstream_request_id'] == 'limited-upstream'
        current[0] += timedelta(minutes=2)
    assert len({row['request_id'] for row in result['attempts']}) == 3
    with sessions() as db:
        audit = list(db.scalars(select(TencentApiCall).where(TencentApiCall.direction=='outbound',
            TencentApiCall.request_id.in_([row['request_id'] for row in result['attempts']]))))
        assert len(audit) == 3
        assert all(row.returned_at is not None and row.upstream_request_id == 'limited-upstream' for row in audit)
    assert 'do not retain' not in json.dumps(result)
    assert worker.run_once() is False



def test_expired_owner_is_fenced_before_restart_retries_and_late_executor_cannot_publish(cost_http):
    client, sessions, account = cost_http
    enable_cost(client, account)
    url = submit(client, account, 'lost-executor')
    current = [datetime.now(timezone.utc).replace(tzinfo=None)]
    outgoing = []
    def transport(credential, action, params):
        outgoing.append(action)
        return successful_wire(credential, action, params)
    settings = app.dependency_overrides[get_settings]()
    old = TencentCostWorker(sessions, settings, transport, now=lambda: current[0])
    lost = old.claim()
    try:
        current[0] += timedelta(seconds=121)
        restarted = TencentCostWorker(sessions, settings, transport, now=lambda: current[0])
        replacement = restarted.claim()
        assert replacement is not None
        assert replacement.job_id == lost.job_id
        history = client.get(url).json()['data']
        assert history['attempts'][0]['status'] == 'unknown'
        assert history['attempts'][0]['return_state'] == 'UNKNOWN'
        assert history['attempts'][0]['finished_at'] is None
        assert old.execute(lost) is None
        assert outgoing == []
        assert restarted.execute(replacement)['status'] == 'committed'
        result = client.get(url).json()['data']
        assert result['status'] == 'succeeded'
        assert [row['attempt_no'] for row in result['attempts']] == [1, 2]
        assert result['attempts'][0]['return_state'] == 'UNKNOWN'
    finally:
        old.execute(lost)
        if 'replacement' in locals() and replacement:
            restarted.execute(replacement)


def test_commit_acknowledgement_loss_is_verified_without_recollecting(cost_http):
    from sqlalchemy import event
    from app.persistence.models import TencentSyncJob
    client,sessions,account=cost_http
    enable_cost(client,account)
    url=submit(client,account,'commit-ack-lost')
    outgoing=[]
    def transport(*args):
        outgoing.append(args[1])
        return successful_wire(*args)
    injected=[]
    def before_commit(db):
        if not injected and any(isinstance(row,TencentSyncJob) and row.status=='succeeded' for row in db.dirty):
            db.info['lose_ack']=True
    def after_commit(db):
        if db.info.pop('lose_ack',False):
            injected.append(True)
            raise ConnectionError('synthetic acknowledgement loss')
    event.listen(sessions.class_,'before_commit',before_commit)
    event.listen(sessions.class_,'after_commit',after_commit)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport)
    try:
        claim=worker.claim()
        result=worker.execute(claim)
    finally:
        event.remove(sessions.class_,'before_commit',before_commit)
        event.remove(sessions.class_,'after_commit',after_commit)
    assert injected==[True]
    assert result and result['status']=='committed'
    assert worker.execute(claim)==result
    assert len(outgoing)==4
    history=client.get(url).json()['data']
    assert history['status']=='succeeded'
    assert len(history['attempts'])==1
    assert history['attempts'][0]['execution_output']==result


def test_missing_attempt_archive_repairs_from_original_transaction_receipt_without_outbound(cost_http):
    from app.persistence.models import TencentSyncAttempt
    client,sessions,account=cost_http
    enable_cost(client,account)
    url=submit(client,account,'archive-repair')
    outgoing=[]
    def transport(*args):
        outgoing.append(args[1])
        return successful_wire(*args)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport)
    claim=worker.claim()
    original=worker.execute(claim)
    with sessions.begin() as db:
        attempt=db.get(TencentSyncAttempt,claim.attempt_id)
        attempt.execution_output=None
        # 已观察到返回，但归档丢失；返回事实仍保持 VALUE。
        attempt.return_state='VALUE'
    restarted=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport)
    restarted.recover()
    history=client.get(url).json()['data']
    assert len(outgoing)==4
    assert history['attempts'][0]['execution_output']==original
    assert history['attempts'][0]['return_state']=='VALUE'
    assert history['attempts'][0]['failure_evidence']['archive_repaired'] is True


def test_new_epoch_accepts_same_manual_key_and_never_rebinds_old_job(cost_http):
    from app.persistence.models import DatasetState
    client,sessions,account=cost_http
    enable_cost(client,account)
    old=submit(client,account,'epoch-scoped-key')
    with sessions.begin() as db:db.get(DatasetState,1).dataset_epoch='new-finance-epoch'
    fresh=submit(client,account,'epoch-scoped-key')
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),successful_wire)
    try:
        assert fresh!=old
        worker.run_once()  # 最早旧任务先被当前世代拒绝，下一次轮询领取新任务。
        assert worker.run_once()
        assert client.get(old).json()['data']['status']=='failed'
        history=client.get(fresh).json()['data']
        assert history['status']=='succeeded'
        assert history['attempts'][0]['execution_input']['dataset_epoch']=='new-finance-epoch'
        assert client.get(old).json()['data']['attempts']==[]
    finally:
        while worker.run_once():pass


def test_queue_limit_and_queue_wait_are_separate_from_first_execution_budget(cost_http):
    client,sessions,account=cost_http
    enable_cost(client,account)
    config_url=f"/admin/api/tencent/accounts/{account['id']}/cost-config"
    config=client.get(config_url).json()['data']
    saved=client.put(config_url,json={'revision':config['revision'],'is_enabled':True,'frequency':'manual','currency':'CNY',
        'run_policy':{**config['run_policy'],'queue_limit':1}})
    assert saved.status_code==200
    url=submit(client,account,'first-queued')
    second=client.post(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs",json={'month':'2026-10','idempotency_key':'over-queue'})
    current=datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(minutes=30)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),successful_wire,now=lambda:current)
    try:
        assert second.status_code==429
        assert second.json()['error']['code']=='TENCENT_COST_QUEUE_FULL'
        assert worker.run_once()
        history=client.get(url).json()['data']
        assert history['status']=='succeeded'
        assert datetime.fromisoformat(history['deadline_at'].replace('Z','+00:00')).replace(tzinfo=None)>current
        assert history['queue_deadline_at'] is not None
    finally:
        while worker.run_once():pass


def second_account(client):
    from app.tencent.gateway import get_tencent_transport
    app.dependency_overrides[get_tencent_transport]=lambda:lambda *_:b'{"Response":{"Uin":20002,"RequestId":"other-account"}}'
    response=client.post('/admin/api/tencent/accounts',json={'uin':'20002','alias':'独立配置 B','credential_ref':'finance-b'})
    assert response.status_code==201,response.text
    result=response.json()['data']
    enable_cost(client,result)
    return result


def both_accounts_wire(credential,action,params):
    if action=='DescribeAccountBalance':
        return json.dumps({'Response':{'Uin':20002 if credential.secret_id.get_secret_value().endswith('-b') else 10001,'RequestId':'identity'}}).encode()
    return successful_wire(credential,action,params)


def test_one_configuration_backlog_does_not_starve_other_configuration(cost_http):
    client,sessions,account=cost_http
    enable_cost(client,account)
    other=second_account(client)
    for index in range(101):submit(client,account,'backlog-'+str(index))
    other_url=submit(client,other,'independent-backlog')
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),both_accounts_wire)
    busy=worker.claim()
    try:
        assert worker.run_once()
        assert client.get(other_url).json()['data']['status']=='succeeded'
    finally:
        worker.execute(busy)
        config_url=f"/admin/api/tencent/accounts/{account['id']}/cost-config"
        config=client.get(config_url).json()['data']
        assert client.put(config_url,json={'revision':config['revision'],'is_enabled':False,'frequency':'manual','currency':'CNY'}).status_code==200
        while worker.run_once():pass


def test_production_loop_advances_other_config_while_a_blocks_and_drains_on_stop(cost_http):
    import threading,time
    client,sessions,account=cost_http
    enable_cost(client,account)
    other=second_account(client)
    a_url=submit(client,account,'production-a')
    b_url=submit(client,other,'production-b')
    entered,release,b_called,stop=(threading.Event() for _ in range(4))
    def transport(credential,action,params):
        if credential.secret_id.get_secret_value().endswith('-b'):b_called.set()
        elif action=='DescribeAccountBalance':
            entered.set()
            assert release.wait(8),'test did not release blocked call'
        return both_accounts_wire(credential,action,params)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport)
    failures=[]
    def run():
        try:worker.run(stop,max_concurrency=2,poll_seconds=.02)
        except BaseException as exc:failures.append(type(exc).__name__)
    thread=threading.Thread(target=run)
    thread.start()
    try:
        assert entered.wait(5),failures
        assert b_called.wait(5),failures
        until=time.monotonic()+5
        while time.monotonic()<until and client.get(b_url).json()['data']['status']!='succeeded':time.sleep(.02)
        assert client.get(b_url).json()['data']['status']=='succeeded'
        assert client.get(a_url).json()['data']['status']=='running'
        stop.set()
        extra=submit(client,other,'after-stop')
        release.set()
    finally:
        stop.set();release.set();thread.join(8)
    try:
        assert not thread.is_alive()
        assert not failures
        assert client.get(a_url).json()['data']['status']=='succeeded'
        assert client.get(extra).json()['data']['status']=='pending'
    finally:
        worker.run_once()


def test_heartbeat_keeps_live_owner_during_blocked_transport_without_allowing_takeover(cost_http):
    import threading,time
    client,sessions,account=cost_http
    enable_cost(client,account)
    config_url=f"/admin/api/tencent/accounts/{account['id']}/cost-config"
    config=client.get(config_url).json()['data']
    assert client.put(config_url,json={'revision':config['revision'],'is_enabled':True,'frequency':'manual','currency':'CNY',
        'run_policy':{**config['run_policy'],'lease_seconds':30,'heartbeat_seconds':5}}).status_code==200
    url=submit(client,account,'live-heartbeat')
    current=[datetime.now(timezone.utc).replace(tzinfo=None)]
    entered,release=threading.Event(),threading.Event()
    def transport(*args):
        if not entered.is_set():
            entered.set()
            assert release.wait(10)
        return successful_wire(*args)
    settings=app.dependency_overrides[get_settings]()
    worker=TencentCostWorker(sessions,settings,transport,now=lambda:current[0])
    other=TencentCostWorker(sessions,settings,successful_wire,now=lambda:current[0])
    claim=worker.claim()
    execution=threading.Thread(target=worker.execute,args=(claim,))
    execution.start()
    try:
        assert entered.wait(3)
        current[0]+=timedelta(seconds=29)
        time.sleep(5.3)
        current[0]+=timedelta(seconds=2)
        replacement=other.claim()
        assert replacement is None
    finally:
        release.set()
        execution.join(5)
        if 'replacement' in locals() and replacement:other.execute(replacement)
        while other.run_once():pass
    assert not execution.is_alive()
    history=client.get(url).json()['data']
    assert history['status']=='succeeded'
    assert len(history['attempts'])==1


def test_manual_rerun_creates_linked_job_with_current_policy_and_preserves_history(cost_http):
    client,sessions,account=cost_http
    enable_cost(client,account)
    url=submit(client,account,'source-rerun')
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),successful_wire)
    assert worker.run_once()
    original=client.get(url).json()['data']
    config_url=f"/admin/api/tencent/accounts/{account['id']}/cost-config"
    config=client.get(config_url).json()['data']
    assert client.put(config_url,json={'revision':config['revision'],'is_enabled':True,'frequency':'manual','currency':'CNY',
        'run_policy':{**config['run_policy'],'max_attempts':1}}).status_code==200
    body={'idempotency_key':'linked-rerun','reason':'refresh_result'}
    response=client.post(url+'/rerun',json=body)
    try:
        assert response.status_code==202,response.text
        rerun=response.json()['data']
        assert rerun['id']!=original['id']
        assert rerun['source_job_id']==original['id']
        repeated=client.post(url+'/rerun',json=body)
        assert repeated.status_code==202
        assert repeated.json()['data']['id']==rerun['id']
        assert worker.run_once()
        result=client.get(response.headers['location']).json()['data']
        assert result['attempts'][0]['execution_input']['policy']['max_attempts']==1
        assert result['attempts'][0]['execution_input']['source_job_id']==original['id']
        assert client.get(url).json()['data']==original
    finally:
        while worker.run_once():pass


def test_cost_routes_audit_trusted_account_uin_for_config_jobs_period_and_rerun(cost_http):
    from sqlalchemy import select
    from app.persistence.models import TencentApiCall
    client,sessions,account=cost_http
    responses=[]
    base=f"/admin/api/tencent/accounts/{account['id']}"
    responses.append(client.get(base+'/cost-config'))
    responses.append(client.put(base+'/cost-config',json={'revision':0,'is_enabled':True,'frequency':'manual','currency':'CNY'}))
    response=client.post(base+'/cost-jobs',json={'month':'2026-10','idempotency_key':'audit-target'})
    responses.append(response)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),successful_wire)
    worker.run_once()
    responses.extend([client.get(response.headers['location']),client.get(base+'/cost-jobs'),client.get(base+'/cost-periods/2026-10')])
    responses.append(client.post(response.headers['location']+'/rerun',json={'idempotency_key':'audit-rerun','reason':'after_fix'}))
    worker.run_once()
    with sessions() as db:
        audit=list(db.scalars(select(TencentApiCall).where(TencentApiCall.id.in_([item.headers['x-request-id'] for item in responses]))))
        assert len(audit)==7
        assert all(row.target_id=='10001' and row.permission_code and row.actor_id=='tencent-admin' for row in audit)


def test_unfinished_initialization_keeps_worker_idle_then_resumes_without_fake_attempt(cost_http):
    from app.persistence.models import DatasetState
    client,sessions,account=cost_http
    enable_cost(client,account)
    url=submit(client,account,'idle-initialization')
    with sessions.begin() as db:db.get(DatasetState,1).initialization_status='pending'
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),successful_wire)
    try:
        assert worker.run_once() is False
    finally:
        with sessions.begin() as db:db.get(DatasetState,1).initialization_status='complete'
    history=client.get(url).json()['data']
    assert history['status']=='pending'
    assert history['attempts']==[]
    assert worker.run_once()
    assert client.get(url).json()['data']['status']=='succeeded'


def test_disable_then_enable_fences_old_pending_job_and_new_manual_job_can_run(cost_http):
    client,sessions,account=cost_http
    enable_cost(client,account)
    old=submit(client,account,'before-toggle')
    path=f"/admin/api/tencent/accounts/{account['id']}/cost-config"
    for enabled in (False,True):
        config=client.get(path).json()['data']
        assert client.put(path,json={'revision':config['revision'],'is_enabled':enabled,'frequency':'manual','currency':'CNY'}).status_code==200
    new=submit(client,account,'after-toggle')
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),successful_wire)
    worker.run_once()
    assert worker.run_once()
    original=client.get(old).json()['data']
    assert original['status']=='failed' and original['attempts']==[]
    assert original['error_code']=='TENCENT_COST_CONFIG_CHANGED'
    assert client.get(new).json()['data']['status']=='succeeded'


def test_queue_expiry_has_no_attempt_or_outbound_and_retry_wait_blocks_public_reset(cost_http):
    import os
    from app.evaluation.fixtures import reset_test_database
    client,sessions,account=cost_http
    enable_cost(client,account)
    expired=submit(client,account,'expired-queue')
    outgoing=[]
    def transport(*args):
        outgoing.append(args[1])
        return successful_wire(*args)
    current=[datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(days=2)]
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport,now=lambda:current[0])
    assert worker.run_once() is False
    history=client.get(expired).json()['data']
    assert history['status']=='failed' and history['error_code']=='TENCENT_COST_QUEUE_DEADLINE'
    assert history['attempts']==[] and outgoing==[]
    current[0]=datetime.now(timezone.utc).replace(tzinfo=None)
    waiting=submit(client,account,'protected-backoff')
    failures=[True]
    def temporarily_down(*args):
        if failures.pop() if failures else False:raise TimeoutError()
        return successful_wire(*args)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),temporarily_down,now=lambda:current[0])
    assert worker.run_once()
    try:
        assert client.get(waiting).json()['data']['status']=='retry_wait'
        with pytest.raises(RuntimeError,match='EVALUATION_WORKER_NOT_QUIET'):reset_test_database(os.environ['ORG_TEST_DATABASE_URL'])
        assert client.get(waiting).json()['data']['status']=='retry_wait'
    finally:
        current[0]+=timedelta(minutes=2)
        worker.run_once()
