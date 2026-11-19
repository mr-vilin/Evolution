from copy import deepcopy
from decimal import Decimal

import pytest

from app.tencent.cost_collector import collect_period
from app.tencent.errors import TencentError


def collect_sample(period, row_count, mutate):
    label = f"{period}{'-01' if len(period) == 7 else ''} 00:00:00"

    def amounts(value):
        return {'Total': str(value), 'TimeDetail': [{'Time': label, 'Money': str(value)}]}

    rows = [{'Name': f'product-{i}', **amounts('1.23456789')} for i in range(row_count)]
    total = row_count * Decimal('1.23456789')
    calls = []

    class Gateway:
        def call(self, credential, action, params, *, target):
            assert target == '10001'
            if action == 'DescribeAccountBalance':
                return {'Uin': 10001, 'RequestId': 'identity'}
            assert action == 'DescribeCostExplorerSummary'
            page_no = params['PageNo']
            calls.append(page_no)
            start = (page_no - 1) * params['PageSize']
            response = {
                'RequestId': f'request-{len(calls)}',
                'Total': row_count,
                'Header': {'HeadDetail': [{'Name': label}]},
                'TotalDetail': amounts(total),
                'Detail': deepcopy(rows[start:start + params['PageSize']]),
                'ConditionValue': {'Business': [{'BusinessCode': 'p_sample', 'BusinessCodeName': 'product-0'}]},
            }
            mutate(response, page_no, len(calls))
            return response

    result = collect_period(Gateway(), object(), {
        'uin': '10001', 'month': period[:7], 'period_key': period,
        'granularity': 'month' if len(period) == 7 else 'day',
        'begin': label, 'end_exclusive': '2026-11-01 00:00:00' if len(period) == 7 else '2026-11-19 00:00:00',
        'upstream_params': {},
    })
    return result, calls


@pytest.mark.parametrize(('period', 'row_count', 'expected_calls', 'changed_at'), [
    ('2026-10', 18, [1, 2, 1], 2),  # Empty tail page.
    ('2026-11-18', 13, [1, 2, 1], 3),  # First page reread.
    ('2026-10', 101, [1, 2, 3, 1], 2),  # Additional populated page.
])
def test_filter_options_can_change_without_changing_the_bill(period, row_count, expected_calls, changed_at):
    def mutate(response, page_no, call_no):
        if call_no == changed_at:
            response['ConditionValue'] = {'Business': [{'BusinessCode': 'other', 'BusinessCodeName': 'product-0'}]}

    result, calls = collect_sample(period, row_count, mutate)
    assert calls == expected_calls
    assert result['coverage']['row_count'] == row_count
    assert result['total'] == row_count * Decimal('1.23456789')
    assert result['rows'][0]['business_code'] == 'p_sample'
    assert result['rows'][0]['mapping_status'] == 'mapped'
    assert result['rows'][-1]['mapping_status'] == 'unmapped'


@pytest.mark.parametrize('field', ['Total', 'Header', 'TotalDetail', 'Detail'])
def test_bill_changes_on_first_page_reread_are_still_rejected(field):
    def mutate(response, page_no, call_no):
        if call_no == 3:
            response.pop('ConditionValue')
            if field == 'Total':
                response['Total'] += 1
            elif field == 'Header':
                response['Header']['HeadDetail'][0]['Name'] = '2026-09-01 00:00:00'
            elif field == 'TotalDetail':
                response['TotalDetail']['Total'] = response['TotalDetail']['TimeDetail'][0]['Money'] = '1.00'
            else:
                # Same count and amount, but different product detail.
                response['Detail'][0]['Name'] = 'changed-product'

    with pytest.raises(TencentError) as error:
        collect_sample('2026-10', 18, mutate)
    assert error.value.code == 'TENCENT_COST_SOURCE_CHANGED'
