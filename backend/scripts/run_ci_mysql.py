"""复用测试 Compose，在全新专库中执行 CI MySQL 回归；不接收业务库连接。"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys

import yaml
from sqlalchemy import text
from sqlalchemy.engine import URL

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.persistence.database import create_mysql_engine, database_ready

DATABASE = 'tencent_ci_test'


def run_command(command: list[str], env: dict[str, str], password: str) -> int:
    """实时保留测试输出，同时避免失败断言把测试连接凭据写入 CI 日志。"""
    with subprocess.Popen(
        command, cwd=BACKEND, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
    ) as process:
        for line in process.stdout:
            line = re.sub(r"mysql\+pymysql://[^\s'\"<>]+", '[数据库连接已脱敏]', line)
            if password:
                line = line.replace(password, '[测试密码已脱敏]')
            print(line, end='', flush=True)
        return process.wait()


def main() -> int:
    # 连接只由版本库中的测试 Compose 推导，不继承开发/测试/生产连接。
    compose = yaml.safe_load((ROOT / 'deploy/compose.mysql-test.yaml').read_text(encoding='utf-8'))
    mysql = compose['services']['mysql']
    if mysql['image'] != 'mysql:8.4' or mysql['ports'] != ['127.0.0.1:13306:3306']:
        raise RuntimeError('测试 Compose 的 MySQL 版本或本机端口变化，需先复核 CI 目标')
    if mysql.get('tmpfs') != ['/var/lib/mysql']:
        raise RuntimeError('CI 仅允许使用 tmpfs 临时 MySQL')
    admin_url = URL.create(
        'mysql+pymysql', username='root', password=mysql['environment']['MYSQL_ROOT_PASSWORD'],
        host='127.0.0.1', port=13306, query={'charset': 'utf8mb4'},
    )
    admin = create_mysql_engine(admin_url.render_as_string(hide_password=False))
    try:
        with admin.connect() as connection:
            actual = connection.execute(text(
                'SELECT VERSION(), @@character_set_connection, @@collation_connection, '
                '@@time_zone, @@transaction_isolation'
            )).one()
            print('测试目标: 127.0.0.1:13306 /', DATABASE, flush=True)
            print('实际版本/字符集/排序规则/时区/隔离级别:', tuple(actual), flush=True)
            if not actual[0].startswith('8.4.') or tuple(actual[1:]) != (
                'utf8mb4', 'utf8mb4_general_ci', '+00:00', 'REPEATABLE-READ',
            ):
                raise RuntimeError('实际 MySQL 版本或连接会话不符，禁止建库')
            # 不复用、不清空已有库；重复执行须先销毁本次临时容器。
            connection.execute(text(
                f'CREATE DATABASE `{DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci'
            ))
    finally:
        admin.dispose()

    target = admin_url.set(database=DATABASE).render_as_string(hide_password=False)
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('ORG_')}
    env.update(
        ORG_DATABASE_URL=target,
        ORG_TEST_DATABASE_URL=target,
        ORG_MIGRATION_TEST_DATABASE_URL=target,
        PYTHONUTF8='1',
        PYTHONIOENCODING='utf-8',
    )
    print('执行迁移: alembic upgrade head', flush=True)
    password = admin_url.password or ''
    result = run_command([sys.executable, '-m', 'alembic', 'upgrade', 'head'], env, password)
    if result:
        return result
    engine = create_mysql_engine(target)
    try:
        print('迁移后检查:', database_ready(engine), flush=True)
        with engine.connect() as connection:
            schema = connection.execute(text(
                'SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME '
                'FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=DATABASE()'
            )).one()
            if tuple(schema) != ('utf8mb4', 'utf8mb4_general_ci'):
                raise RuntimeError('实际测试库字符集或排序规则不符')
            print('实际库字符集/排序规则:', tuple(schema), flush=True)
    finally:
        engine.dispose()
    return run_command(
        [sys.executable, '-m', 'pytest', 'tests/integration', 'tests/evaluation', '--require-mysql', '-q', '-rs'],
        env, password,
    )


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
