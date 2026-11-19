"""在合成账户与历史数据上检查真实 worker / 看板 SQL 的 MySQL 执行计划。"""
from sqlalchemy import event, text

from test_tencent_accounts_mysql import tencent_http
from test_tencent_cost_mysql import cost_http, enable_cost, run_job


def _background_data(sessions):
    accounts = range(10001, 10033)
    months = [f'{year}-{month:02d}' for year in range(2023, 2026) for month in range(1, 13)]
    with sessions.begin() as db:
        db.execute(text("""
            INSERT INTO tencent_account (id, uin, alias, credential_ref, verification_status, verified_at)
            VALUES (:id, :uin, '合成账号', 'fixture', 'verified', CURRENT_TIMESTAMP)
        """), [{'id': account, 'uin': str(200000 + account)} for account in accounts])
        db.execute(text("""
            INSERT INTO tencent_sync_config (id, account_id, business, frequency, currency)
            VALUES (:id, :id, 'cost', 'manual', 'CNY')
        """), [{'id': account} for account in accounts])
        periods = [
            {'id': account * 100 + i, 'account': account, 'month': month}
            for account in accounts for i, month in enumerate(months)
        ]
        db.execute(text("""
            INSERT INTO tencent_sync_job
                (id, config_id, account_id, dataset_epoch, idempotency_key, month, status, snapshot, request_id)
            VALUES (:id, :account, :account, 'fixture', :month, :month, 'succeeded', JSON_OBJECT('currency','CNY'), 'fixture')
        """), periods)
        db.execute(text("""
            INSERT INTO tencent_sync_attempt
                (id, job_id, attempt_no, generation, owner, status, execution_input, started_at)
            VALUES (:id, :id, 1, 1, 'fixture', 'succeeded', JSON_OBJECT(), CURRENT_TIMESTAMP)
        """), periods)
        db.execute(text("""
            INSERT INTO tencent_cost_period (id, account_id, month, period_key, currency, total, coverage, latest_job_id, latest_attempt_id)
            VALUES (:id, :account, :month, :month, 'CNY', 8, JSON_OBJECT(), :id, :id)
        """), periods)
        db.execute(text("""
            INSERT INTO tencent_cost_item (period_id, row_no, source_name, mapping_status, amount)
            VALUES (:id, :row_no, '合成产品', 'unmapped', 1)
        """), [{'id': period['id'], 'row_no': n} for period in periods for n in range(8)])
    # 使用临时测试库的真实表统计，避免空表计划。
    with sessions.kw['bind'].connect() as db:
        db.exec_driver_sql(
            'ANALYZE TABLE tencent_sync_job, tencent_sync_attempt, tencent_cost_period, tencent_cost_item'
        ).all()


def test_actual_claim_and_dashboard_query_plans(cost_http):
    client, sessions, account = cost_http
    enable_cost(client, account)
    base = f"/admin/api/tencent/accounts/{account['id']}"
    _background_data(sessions)
    engine = sessions.kw['bind']
    captured = {}

    def capture(conn, cursor, sql, params, context, executemany):
        if 'row_number() OVER' in sql and 'tencent_sync_attempt' in sql:
            captured['claim'] = (sql, params)
        elif 'FROM tencent_cost_period' in sql and 'ORDER BY tencent_cost_period.month' in sql:
            captured['periods'] = (sql, params)
        elif 'FROM tencent_cost_item INNER JOIN tencent_cost_period' in sql:
            captured['items'] = (sql, params)
        elif 'FROM tencent_sync_job' in sql and 'JSON_EXTRACT' in sql:
            captured['jobs'] = (sql, params)

    event.listen(engine, 'before_cursor_execute', capture)
    try:
        assert run_job(client, sessions, account, 'query-plan', month='2026-08')['status'] == 'succeeded'
        response = client.get(base + '/cost-dashboard?start_month=2026-08&end_month=2026-09')
        assert response.status_code == 200
        assert response.json()['data']['known_total'] == '12.00000000'
    finally:
        event.remove(engine, 'before_cursor_execute', capture)

    assert captured.keys() == {'claim', 'periods', 'items', 'jobs'}
    with engine.connect() as db:
        plans = {
            name: db.exec_driver_sql('EXPLAIN ' + sql, params).mappings().all()
            for name, (sql, params) in captured.items()
        }
    for name, rows in plans.items():
        print(name, [(row['table'], row['type'], row['key'], row['rows'], row['Extra']) for row in rows])

    assert any(row['key'] == 'idx_tencent_period_month' and row['type'] in {'ref','range'} for row in plans['periods'])
    assert any(
        row['table'] == 'tencent_cost_period' and row['type'] in {'ref', 'range'}
        and row['key'] in {'idx_tencent_period_month', 'uk_tencent_period_scope'}
        for row in plans['items']
    )
    assert any(row['type'] == 'ref' and row['key'] == 'uk_tencent_item_row' for row in plans['items'])
    assert any(row['key'] and row['type'] in {'ref','range'} for row in plans['jobs'])
    assert any(row['key'] in {'idx_tencent_job_claim', 'idx_tencent_job_priority'} for row in plans['claim'])
