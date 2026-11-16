"""本次已授权的本地 0009→0010 迁移；先备份及隔离演练，再迁移，发布使用 release.py。"""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import re
import subprocess
import sys
import time
from cryptography.fernet import Fernet
from release import environment, validate_artifact
from release_host import Host, require_idle, write_json

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / '.cache/artifacts/release-20261026-093353-8a68260a'
ARCHIVE = ROOT / '.cache/migrations/local-0010-20261026-r3'
TEMP = 'org-migration-0010-rehearsal-20261026'


def command(args, data=None, env=None):
    p = subprocess.run(args, input=data, capture_output=True, env=env)
    if p.returncode:
        raise RuntimeError('命令失败（隐藏可能含凭据的输出）: ' + args[0])
    return p.stdout


def protect(data):
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    dest = Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(dest)):
        raise RuntimeError('DPAPI 加密失败')
    try:
        return ctypes.string_at(dest.data, dest.size)
    finally:
        ctypes.windll.kernel32.LocalFree(dest.data)


def sql(container, query):
    return command(['docker', 'exec', '-i', container, 'sh', '-c',
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql --default-character-set=utf8mb4 -uroot -N -B organization'], query.encode()).decode().strip()


def dump(container, structure=False):
    return command(['docker', 'exec', container, 'sh', '-c',
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --routines --triggers --events --set-gtid-purged=OFF --no-tablespaces --skip-comments ' + ('--no-data ' if structure else '') + 'organization'])


def metadata(container):
    queries = [
        "SELECT TABLE_NAME,ENGINE,TABLE_COLLATION,TABLE_COMMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA='organization' ORDER BY TABLE_NAME;",
        "SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA,CHARACTER_SET_NAME,COLLATION_NAME,COLUMN_COMMENT,GENERATION_EXPRESSION FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='organization' ORDER BY TABLE_NAME,ORDINAL_POSITION;",
        "SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME,COLLATION,SUB_PART,INDEX_TYPE,EXPRESSION FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='organization' ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX;",
        "SELECT TABLE_NAME,CONSTRAINT_NAME,CONSTRAINT_TYPE FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA='organization' ORDER BY TABLE_NAME,CONSTRAINT_NAME;",
        "SELECT TABLE_NAME,COLUMN_NAME,CONSTRAINT_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA='organization' ORDER BY TABLE_NAME,CONSTRAINT_NAME,ORDINAL_POSITION;",
    ]
    return [sql(container, query) for query in queries]


def snapshot(container):
    counts = sql(container, "SELECT (SELECT COUNT(*) FROM department),(SELECT COUNT(*) FROM employee),(SELECT COUNT(*) FROM employee_department),(SELECT COUNT(*) FROM store_profile),(SELECT COUNT(*) FROM admin_allowlist);")
    return {'version': sql(container, 'SELECT version_num FROM alembic_version;'), 'counts': counts,
            'state': sql(container, 'SELECT dataset_epoch,data_version,initialization_status,coverage_status FROM dataset_state WHERE id=1;'),
            'mysql': sql(container, 'SELECT VERSION(),@@character_set_database,@@collation_database;')}


def main():
    if sys.argv[1:] != ['--authorized-local-migration']:
        raise RuntimeError('需要当次明确授权参数')
    manifest = validate_artifact(ARTIFACT)
    host = Host(environment('local', 'inspect', ''))
    ARCHIVE.mkdir(parents=True, exist_ok=False)
    with host.lock():
        before = host.probe('snapshot()')
        require_idle(before)
        assert before['schema'] == '0009_operation_receipt'
        write_json(ARCHIVE / 'before.json', before)
        write_json(ARCHIVE / 'previous-images.json', host.image_config(host.images()))
        mysql = command(host.dc() + ['ps','-q','mysql']).decode().strip()
        mysql_image = command(['docker','inspect',mysql,'--format','{{.Image}}']).decode().strip()
        command(host.dc() + ['stop','app','mcp'])
        print('应用已停写，开始加密备份', flush=True)
        initial = snapshot(mysql)
        backup = dump(mysql)
        structure = dump(mysql, True)
        original_metadata = metadata(mysql)
        write_json(ARCHIVE / 'metadata-before.json', original_metadata)
        key = Fernet.generate_key()
        cipher = Fernet(key)
        encrypted = cipher.encrypt(backup)
        (ARCHIVE / 'database.sql.fernet').write_bytes(encrypted)
        keydir = ROOT / '.cache/backup-keys'
        keydir.mkdir(exist_ok=True)
        (keydir / 'local-0010-20261026-r3.dpapi').write_bytes(protect(key))
        assert cipher.decrypt(encrypted) == backup
        (ARCHIVE / 'schema-before.sql').write_bytes(structure)
        write_json(ARCHIVE / 'database-before.json', initial)
        write_json(ARCHIVE / 'backup.json', {'sha256': hashlib.sha256(encrypted).hexdigest(), 'key': 'Windows 当前用户 DPAPI，独立存储于 .cache/backup-keys', 'authorization': '用户授权备份、恢复演练、迁移及本地部署'})
        env = os.environ.copy()
        env['MYSQL_ROOT_PASSWORD'] = secrets.token_hex(24)
        env['ORG_DATABASE_URL'] = 'mysql+pymysql://root:' + env['MYSQL_ROOT_PASSWORD'] + '@127.0.0.1:3306/organization?charset=utf8mb4'
        created = False
        try:
            command(['docker','run','-d','--name',TEMP,'--network','none','--tmpfs','/var/lib/mysql:rw','-e','MYSQL_ROOT_PASSWORD',mysql_image,
                     '--character-set-server=utf8mb4','--collation-server=utf8mb4_general_ci'],env=env)
            created = True
            for _ in range(90):
                try:
                    command(['docker','exec',TEMP,'sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "SELECT 1"'])
                    break
                except RuntimeError:
                    time.sleep(2)
            else:
                raise RuntimeError('隔离 MySQL 启动超时')
            command(['docker','exec',TEMP,'sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "CREATE DATABASE organization CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"'])
            sql(TEMP, cipher.decrypt(encrypted).decode('utf-8'))
            restored = snapshot(TEMP)
            write_json(ARCHIVE / 'restored.json', restored)
            assert restored == initial, 'restored_snapshot'
            restored_schema = dump(TEMP, True)
            (ARCHIVE / 'rehearsal-schema.sql').write_bytes(restored_schema)
            assert metadata(TEMP) == original_metadata, 'restored_structure'
            print('加密备份恢复及结构校验通过，开始隔离迁移', flush=True)
            command(['docker','run','--rm','--network','container:'+TEMP,'-e','ORG_DATABASE_URL',manifest['image_id'],
                     'python','-m','alembic','upgrade','0010_initialization_wizard'],env=env)
            rehearsed = snapshot(TEMP)
            assert rehearsed['version'] == '0010_initialization_wizard'
            assert rehearsed['counts'] == initial['counts']
            restored_schema = dump(TEMP, True)
            (ARCHIVE / 'rehearsal-schema.sql').write_bytes(restored_schema)
            assert metadata(TEMP) == original_metadata, 'restored_structure'
            assert '\tpending\tunknown' in rehearsed['state']
            write_json(ARCHIVE / 'rehearsal.json', rehearsed)
        finally:
            if created:
                command(['docker','rm','-f',TEMP])
        candidate = ARCHIVE / 'candidate.json'
        write_json(candidate, host.image_config({name: manifest['image_id'] for name in ('app','mcp','migrate')}))
        print('隔离演练通过，执行授权的本地 0010 迁移', flush=True)
        command(host.dc(candidate) + ['run','--rm','--no-deps','-T','app','python','-m','alembic','upgrade','0010_initialization_wizard'])
        after = snapshot(mysql)
        assert after['version'] == '0010_initialization_wizard'
        assert after['counts'] == initial['counts']
        assert after['state'] == rehearsed['state']
        assert metadata(mysql) == original_metadata, 'migrated_structure'
        write_json(ARCHIVE / 'database-after.json', after)
        print('本地迁移成功，结构和业务数量保持；应用仍停止，交由 release.py 发布', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('MIGRATION_STOPPED: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__ + ': ' + str(exc)) + '；应用保持停止，请检查受限证据目录', file=sys.stderr)
        sys.exit(1)
