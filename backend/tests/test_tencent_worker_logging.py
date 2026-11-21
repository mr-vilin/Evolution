"""独立工作器进程的日志输出契约。"""
import json
import os
import subprocess
import sys


def test_worker_logging_enables_structured_info_in_new_interpreter():
    code="""from app.tencent.worker_logging import configure_logging
import logging
configure_logging()
log=logging.getLogger('evolution.tencent.cost_worker')
log.info('tencent.cost_worker_started')
log.info('tencent.cost_committed job_id=1 attempt_id=2 row_count=3')
print(log.isEnabledFor(logging.INFO), bool(logging.getLogger().handlers))
"""
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,env=os.environ.copy())
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='True True'
    rows=[json.loads(line) for line in result.stderr.splitlines()]
    assert rows[0]['severity']=='INFO' and rows[0]['event_name']=='tencent.cost_worker_started'
    assert rows[1]['event_name']=='tencent.cost_committed'
    assert rows[1]['job_id']==1 and rows[1]['attempt_id']==2
