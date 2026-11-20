"""在现有本地 Docker 卷内切换 MySQL 库和应用账号，保留原库作回退。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import unquote, urlsplit

from cryptography.fernet import Fernet
from migrate_local_0010 import command, protect
from migrate_local_0020 import unprotect
from release import environment
from release_host import Host, require_idle, write_json

OLD = 'organization'
NEW = 'evolution'
VOLUME = 'organization-directory_mysql-data'


def mysql(container, statement, database='mysql'):
    return command(['docker', 'exec', '-i', container, 'sh', '-c',
                    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql --default-character-set=utf8mb4 '
                    '-uroot -N -B "$1"', 'mysql', database], data=statement)


def sql(container, statement, database='mysql'):
    return mysql(container, statement.encode('utf-8'), database).decode('utf-8').strip()


def dump(container, database):
    return command(['docker', 'exec', container, 'sh', '-c',
                    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --default-character-set=utf8mb4 '
                    '--single-transaction --routines --triggers --events --set-gtid-purged=OFF '
                    '--no-tablespaces --skip-comments --skip-dump-date --order-by-primary "$1"',
                    'mysqldump', database])


def column_metadata(container, database):
    return sql(container, f"""
SELECT TABLE_NAME,COLUMN_NAME,ORDINAL_POSITION,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,
       CHARACTER_SET_NAME,COLLATION_NAME,EXTRA,COLUMN_COMMENT,GENERATION_EXPRESSION
FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='{database}'
ORDER BY TABLE_NAME,ORDINAL_POSITION;
""")


def comparable_dump(data):
    # SHOW CREATE TABLE 可能显式输出可由 COLLATE 唯一确定的字符集。
    return re.sub(rb'(?m)^(  `[^`\r\n]+` [a-z]+(?:\([0-9,]+\))?) CHARACTER SET utf8mb4 (?=COLLATE utf8mb4_)',
                  rb'\1 ', data)


def create_destination(container, backup, password, columns):
    # 秘密经 stdin 传入，避免进入命令参数。此会话以 SQL 标准方式转义单引号。
    quoted = "'" + password.replace("'", "''") + "'"
    sql(container, f'CREATE DATABASE `{NEW}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;')
    mysql(container, backup, NEW)
    if comparable_dump(dump(container, NEW)) != comparable_dump(backup):
        raise RuntimeError('RESTORED_DUMP_MISMATCH')
    if column_metadata(container, NEW) != columns:
        raise RuntimeError('RESTORED_COLUMN_METADATA_MISMATCH')
    sql(container, "SET SESSION sql_mode='NO_BACKSLASH_ESCAPES';"
        f"CREATE USER '{NEW}'@'%' IDENTIFIED WITH caching_sha2_password BY {quoted};"
        f"GRANT ALL PRIVILEGES ON `{NEW}`.* TO '{NEW}'@'%';")
    expected = sql(container, f"SHOW GRANTS FOR '{NEW}'@'%';")
    require_schema_only_grants(expected, NEW)


def require_schema_only_grants(grants, name):
    expected = {f'GRANT USAGE ON *.* TO `{name}`@`%`',
                f'GRANT ALL PRIVILEGES ON `{name}`.* TO `{name}`@`%`'}
    if set(grants.splitlines()) != expected:
        raise RuntimeError('UNEXPECTED_ACCOUNT_GRANTS')


def update_dotenv(original):
    # 保留密码的原始 URL 编码、引号、BOM、换行和其余配置字节。
    updated, count = re.subn(
        rb'(?m)^(DATABASE_URL=[\x22\x27]?mysql\+pymysql://)organization(:[^\r\n]*@mysql:3306/)organization(?=\?)',
        rb'\g<1>evolution\g<2>evolution', original,
    )
    if count != 1:
        raise RuntimeError('UNEXPECTED_LOCAL_DATABASE_URL_FORMAT')
    return updated.replace('沿用现有卷中的账号和库名 organization。'.encode(),
                           '本地 Docker 的库名和应用账号均为 evolution。'.encode())


def atomic_env_write(path, content):
    temp = path.with_name(f'.env.rename-{secrets.token_hex(8)}')
    try:
        temp.write_bytes(content)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def start_rehearsal(image, name):
    env = {**os.environ, 'MYSQL_ROOT_PASSWORD': secrets.token_urlsafe(24)}
    return command(['docker', 'run', '-d', '--name', name, '--network', 'none',
                    '--tmpfs', '/var/lib/mysql', '-e', 'MYSQL_ROOT_PASSWORD', image,
                    '--character-set-server=utf8mb4', '--collation-server=utf8mb4_general_ci'], env=env).decode().strip()


def wait_mysql(container):
    for _ in range(60):
        try:
            # 入口脚本初始化期间只通过 Unix socket 服务，等待正式监听后再写入。
            command(['docker', 'exec', container, 'sh', '-c',
                     'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -h127.0.0.1 -uroot -N -B -e "SELECT 1"'])
            return
        except RuntimeError:
            time.sleep(1)
    raise RuntimeError('REHEARSAL_MYSQL_NOT_READY')


def preflight(host, mysql_id):
    mounted = command(['docker', 'inspect', mysql_id, '--format',
                       '{{range .Mounts}}{{if eq .Destination "/var/lib/mysql"}}{{.Name}}{{end}}{{end}}']).decode().strip()
    if mounted != VOLUME:
        raise RuntimeError('UNEXPECTED_MYSQL_VOLUME')
    actual = sql(mysql_id, f"""
SELECT VERSION();
SELECT DEFAULT_CHARACTER_SET_NAME,DEFAULT_COLLATION_NAME
  FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='{OLD}';
SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='{NEW}';
SELECT COUNT(*) FROM mysql.user WHERE User='{NEW}';
SELECT Host,plugin,account_locked FROM mysql.user WHERE User='{OLD}';
SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='{OLD}'
  AND (TABLE_TYPE<>'BASE TABLE' OR ENGINE<>'InnoDB');
SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA='{OLD}'
  AND REFERENCED_TABLE_SCHEMA IS NOT NULL AND REFERENCED_TABLE_SCHEMA<>'{OLD}';
SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='{OLD}';
SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA='{OLD}';
SELECT COUNT(*) FROM information_schema.EVENTS WHERE EVENT_SCHEMA='{OLD}';
""").splitlines()
    if len(actual) != 10 or not actual[0].startswith('8.4.') or actual[1:] != [
        'utf8mb4\tutf8mb4_general_ci', '0', '0', '%\tcaching_sha2_password\tN',
        '0', '0', '0', '0', '0',
    ]:
        raise RuntimeError('UNEXPECTED_SOURCE_OR_DESTINATION_DATABASE')
    require_schema_only_grants(sql(mysql_id, f"SHOW GRANTS FOR '{OLD}'@'%';"), OLD)
    resolved = json.loads(command(host.dc() + ['config', '--format', 'json']))['services']
    db = urlsplit(resolved['app']['environment']['DATABASE_URL'])
    password = unquote(db.password or '')
    if (db.scheme, db.username, db.hostname, db.port, db.path) != (
        'mysql+pymysql', OLD, 'mysql', 3306, f'/{OLD}',
    ) or not password or password != resolved['mysql']['environment']['MYSQL_PASSWORD']:
        raise RuntimeError('UNEXPECTED_SOURCE_CONNECTION')
    return password


def drain_source_connections(container):
    # 旧账号已锁，仅回收该账号无活动事务的空闲连接。
    for _ in range(12):
        idle = sql(container, f"""
SELECT p.ID FROM information_schema.PROCESSLIST p
LEFT JOIN information_schema.INNODB_TRX t ON t.trx_mysql_thread_id=p.ID
WHERE p.USER='{OLD}' AND p.COMMAND='Sleep' AND p.TIME >= 5
  AND t.trx_mysql_thread_id IS NULL;
""")
        for connection in idle.splitlines():
            try:
                sql(container, f'KILL CONNECTION {int(connection)};')
            except RuntimeError:
                # 客户端可能自行断开，下一次查询重新确认。
                pass
        if sql(container, f"SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE DB='{OLD}' OR USER='{OLD}';") == '0':
            return
        time.sleep(1)
    raise RuntimeError('SOURCE_WRITERS_PRESENT')


def cutover(host, mysql_id, rehearsal_id, archive, key_path):
    env_file = host.root / '.env'
    old_env = env_file.read_bytes()
    new_env = update_dotenv(old_env)
    password = preflight(host, mysql_id)
    before = host.probe('snapshot()')
    require_idle(before)
    write_json(archive / 'before.json', before)
    write_json(archive / 'images.json', host.images())
    key_path.write_bytes(protect(Fernet.generate_key()))
    cipher = Fernet(unprotect(key_path.read_bytes()))
    (archive / 'original-env.fernet').write_bytes(cipher.encrypt(old_env))

    stopped = False
    old_locked = False
    switched = False
    attempted_start = False
    try:
        stopped = True
        command(host.dc() + ['stop', *host.target['services']])
        frozen = host.probe('snapshot()')
        require_idle(frozen)
        sql(mysql_id, f"ALTER USER '{OLD}'@'%' ACCOUNT LOCK;")
        old_locked = True
        drain_source_connections(mysql_id)
        backup = dump(mysql_id, OLD)
        columns = column_metadata(mysql_id, OLD)
        backup_file = archive / 'database.sql.fernet'
        backup_file.write_bytes(cipher.encrypt(backup))
        write_json(archive / 'backup.json', {
            'encrypted_sha256': hashlib.sha256(backup_file.read_bytes()).hexdigest(),
            'sql_sha256': hashlib.sha256(backup).hexdigest(),
            'key': key_path.name,
        })
        sealed = cipher.decrypt(backup_file.read_bytes())
        if sealed != backup:
            raise RuntimeError('ENCRYPTED_BACKUP_CHECK_FAILED')
        create_destination(rehearsal_id, sealed, password, columns)
        print('隔离恢复演练通过，开始导入本地 evolution', flush=True)
        create_destination(mysql_id, sealed, password, columns)
        if dump(mysql_id, OLD) != sealed:
            raise RuntimeError('SOURCE_CHANGED_DURING_COPY')
        write_json(archive / 'restore-check.json', {
            'matching_data_and_ddl': True, 'matching_column_metadata': True, 'schema_and_account': NEW,
        })
        if env_file.read_bytes() != old_env:
            raise RuntimeError('CONCURRENT_DOTENV_EDIT')
        atomic_env_write(env_file, new_env)
        switched = True
        target = host.probe("snapshot() | {'connection': connection_identity()}")
        if target.pop('connection') != [NEW, f'{NEW}@%', 'utf8mb4', 'utf8mb4_general_ci']:
            raise RuntimeError('WRONG_APPLICATION_CONNECTION')
        if target != frozen:
            raise RuntimeError('APPLICATION_DATA_CHANGED_BEFORE_START')
        attempted_start = True
        host.up()
        result = host.verify()
        write_json(archive / 'verification.json', {**result, 'assets': len(result['assets'])})
        write_json(archive / 'after.json', host.probe("snapshot() | {'connection': connection_identity()}"))
        print(f'本地库及账号切换完成，发布与备份记录 {archive.name}', flush=True)
    except Exception:
        if stopped:
            if attempted_start:
                command(host.dc() + ['stop', *host.target['services']])
                if comparable_dump(dump(mysql_id, NEW)) != comparable_dump(sealed):
                    raise RuntimeError('NEW_DATABASE_CHANGED_SERVICES_STOPPED') from None
            if switched:
                if env_file.read_bytes() != new_env:
                    raise RuntimeError('CONCURRENT_DOTENV_EDIT_SERVICES_STOPPED') from None
                atomic_env_write(env_file, cipher.decrypt((archive / 'original-env.fernet').read_bytes()))
            if old_locked:
                sql(mysql_id, f"ALTER USER '{OLD}'@'%' ACCOUNT UNLOCK;")
            host.up()
            host.verify()
            write_json(archive / 'rollback.json', {'verified': True, 'restored_database': OLD})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorized-local-cutover', action='store_true', required=True)
    parser.parse_args()
    if os.name != 'nt':
        raise RuntimeError('WINDOWS_DPAPI_REQUIRED')
    host = Host(environment('local', 'inspect', ''))
    if host.target['transport'] != 'local' or host.target['project'] != NEW or not host.override.is_file():
        raise RuntimeError('UNEXPECTED_LOCAL_TARGET')
    label = datetime.now(timezone.utc).strftime('db-evolution-%Y%m%d-%H%M%S-') + secrets.token_hex(4)
    archive = host.root / '.cache/migrations' / label
    keydir = host.root / '.cache/backup-keys'
    with host.lock():
        mysql_id = command(host.dc() + ['ps', '-q', 'mysql']).decode().strip()
        preflight(host, mysql_id)
        image = command(['docker', 'inspect', mysql_id, '--format', '{{.Image}}']).decode().strip()
        archive.mkdir(parents=True)
        keydir.mkdir(exist_ok=True)
        rehearsal_id = start_rehearsal(image, label)
        try:
            wait_mysql(rehearsal_id)
            cutover(host, mysql_id, rehearsal_id, archive, keydir / f'{label}.dpapi')
        finally:
            command(['docker', 'rm', '-f', rehearsal_id])


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'DATABASE_CUTOVER_FAILED: {exc if isinstance(exc, RuntimeError) else type(exc).__name__}',
              file=sys.stderr)
        sys.exit(1)
