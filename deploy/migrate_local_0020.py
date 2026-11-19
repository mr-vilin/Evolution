"""已授权的本地 0013→0020 腾讯财务迁移；先加密备份和隔离恢复演练，发布仍使用 release.py。"""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
import uuid

from cryptography.fernet import Fernet
from migrate_local_0010 import command, dump, metadata, protect, snapshot, sql
from release import environment, validate_artifact
from release_host import Host, require_idle, write_json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '0013_employee_profile'
TARGET = '0020_tencent_history'
TENCENT_TABLES = {'tencent_account', 'tencent_api_call', 'tencent_sync_config', 'tencent_sync_job',
                  'tencent_sync_attempt', 'tencent_cost_period', 'tencent_cost_item'}


def unprotect(data):
    """使用当前 Windows 用户恢复独立保存的 DPAPI 密钥，不输出明文。"""
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    dest = Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(dest)):
        raise RuntimeError('DPAPI 解密失败')
    try:
        return ctypes.string_at(dest.data, dest.size)
    finally:
        ctypes.windll.kernel32.LocalFree(dest.data)


def assert_only_tencent(before, after):
    """仅允许新增七张腾讯表，原有表的列、默认值、注释、索引与约束必须原样保留。"""
    if len(before) != len(after):
        raise RuntimeError('METADATA_SECTION_CHANGED')
    old_tables = {line.split('\t', 1)[0] for line in before[0].splitlines()}
    new_tables = {line.split('\t', 1)[0] for line in after[0].splitlines()}
    if old_tables & TENCENT_TABLES or new_tables != old_tables | TENCENT_TABLES:
        raise RuntimeError('TENCENT_TABLE_SET_MISMATCH')
    for index, (old, current) in enumerate(zip(before, after)):
        original = '\n'.join(line for line in current.splitlines()
                             if line.split('\t', 1)[0] not in TENCENT_TABLES)
        if original != old:
            raise RuntimeError('EXISTING_METADATA_CHANGED: ' + str(index))


def assert_tencent_empty(container):
    for table in sorted(TENCENT_TABLES):
        if sql(container, 'SELECT COUNT(*) FROM `' + table + '`;') != '0':
            raise RuntimeError('UNEXPECTED_TENCENT_DATA: ' + table)


def schema_check_code():
    return ("import json; from app.config import get_settings; "
            "from app.persistence.database import create_mysql_engine,database_ready; "
            "from app.persistence.schema_check import check_schema; "
            "engine=create_mysql_engine(get_settings().database_url); database_ready(engine); "
            "result=check_schema(engine); "
            "print(json.dumps({'errors':result['errors'],'database':result['snapshot']['database'],"
            "'session':result['snapshot']['session']},ensure_ascii=False)); "
            "engine.dispose(); raise SystemExit(bool(result['errors']))")


def business_digest(container):
    tables = sql(container, "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='organization' AND TABLE_TYPE='BASE TABLE' AND TABLE_NAME<>'alembic_version' ORDER BY TABLE_NAME;").splitlines()
    result = {}
    for table in tables:
        if table in TENCENT_TABLES:
            continue
        columns = sql(container, "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='organization' AND TABLE_NAME='" + table + "' ORDER BY ORDINAL_POSITION;").splitlines()
        primary = sql(container, "SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA='organization' AND TABLE_NAME='" + table + "' AND CONSTRAINT_NAME='PRIMARY' ORDER BY ORDINAL_POSITION;").splitlines()
        if not primary:
            raise RuntimeError('PRIMARY_KEY_REQUIRED: ' + table)
        quote = lambda name: '`' + name.replace('`', '``') + '`'
        data = sql(container, 'SELECT ' + ','.join(map(quote, columns)) + ' FROM ' + quote(table) + ' ORDER BY ' + ','.join(map(quote, primary)) + ';')
        result[table] = hashlib.sha256(data.encode('utf-8')).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--authorized-local-migration', action='store_true', required=True)
    args = parser.parse_args()
    manifest = validate_artifact(args.artifact.resolve())
    if manifest['schema'] != TARGET:
        raise RuntimeError('ARTIFACT_SCHEMA_MISMATCH')
    for name, expected in manifest['files'].items():
        source = args.artifact.resolve() / 'source' / name
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise RuntimeError('ARTIFACT_SOURCE_MISMATCH: ' + name)
    actual_image = command(['docker', 'image', 'inspect', manifest['image'], '--format', '{{.Id}}']).decode().strip()
    if actual_image not in (manifest['image_id'], manifest.get('image_config_id')):
        raise RuntimeError('ARTIFACT_IMAGE_MISMATCH')
    identifier = datetime.now(timezone.utc).strftime('local-0020-%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:6]
    archive = ROOT / '.cache/migrations' / identifier
    temporary = 'org-migration-' + identifier
    host = Host(environment('local', 'inspect', ''))
    if host.target['transport'] != 'local' or host.target['project'] not in ('organization-directory', 'evolution'):
        raise RuntimeError('LOCAL_TARGET_MISMATCH')
    archive.mkdir(parents=True, exist_ok=False)
    write_json(archive / 'authorization.json', {
        'scope': '用户本轮明确授权：本地加密备份、隔离恢复演练、0013→0020 腾讯财务迁移及本地发布；来源为本聊天用户明确回复授权',
        'artifact': manifest['release_id'], 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'target': host.target})
    with host.lock():
        before = host.probe('snapshot()')
        require_idle(before)
        if before['schema'] != SOURCE or before['state']['initialization_status'] != 'complete':
            raise RuntimeError('SOURCE_STATE_MISMATCH')
        app_session = host.probe("__import__('builtins').exec('from sqlalchemy import text; from app.config import get_settings; from app.persistence.database import create_mysql_engine') or {'session': list(create_mysql_engine(get_settings().database_url).connect().execute(text('SELECT DATABASE(),@@character_set_database,@@collation_database,@@character_set_connection,@@collation_connection,@@session.time_zone')).one())}")
        if app_session['session'] != ['organization', 'utf8mb4', 'utf8mb4_general_ci', 'utf8mb4', 'utf8mb4_general_ci', '+00:00']:
            raise RuntimeError('APP_MYSQL_SESSION_MISMATCH')
        write_json(archive / 'app-mysql-session.json', app_session)
        write_json(archive / 'before.json', before)
        write_json(archive / 'previous-images.json', host.image_config(host.images()))
        for filename in ('deployment-source.json', 'deployment-image.json'):
            existing = ROOT / '.cache' / filename
            if existing.exists():
                write_json(archive / ('previous-' + filename), json.loads(existing.read_text(encoding='utf-8')))
        (archive / 'migration-script.py').write_bytes(Path(__file__).read_bytes())
        write_json(archive / 'candidate-manifest.json', manifest)
        mysql = command(host.dc() + ['ps', '-q', 'mysql']).decode().strip()
        mysql_image = command(['docker', 'inspect', mysql, '--format', '{{.Image}}']).decode().strip()
        command(host.dc() + ['stop', 'app', 'mcp'])
        require_idle(host.probe('snapshot()'))
        initial = snapshot(mysql)
        if initial['version'] != SOURCE or not initial['mysql'].startswith('8.4.'):
            raise RuntimeError('MYSQL_VERSION_MISMATCH')
        connection = sql(mysql, 'SELECT VERSION(),DATABASE(),@@character_set_database,@@collation_database,@@character_set_connection,@@collation_connection;')
        session = connection.split('\t')
        # mysql CLI 默认连接排序规则与应用会话不同；数据库规范按真实应用会话核验。
        if session[1:5] != ['organization', 'utf8mb4', 'utf8mb4_general_ci', 'utf8mb4']:
            raise RuntimeError('MYSQL_SESSION_MISMATCH')
        original_metadata = metadata(mysql)
        existing_tables = {line.split('\t', 1)[0] for line in original_metadata[0].splitlines()}
        if existing_tables & TENCENT_TABLES:
            raise RuntimeError('TENCENT_TABLE_ALREADY_EXISTS')
        original_digest = business_digest(mysql)
        write_json(archive / 'database-before.json', initial)
        write_json(archive / 'metadata-before.json', original_metadata)
        write_json(archive / 'data-digests-before.json', original_digest)
        write_json(archive / 'mysql-session.json', {'session': connection})
        print('应用已停写，开始加密备份', flush=True)
        backup = dump(mysql)
        key = Fernet.generate_key()
        cipher = Fernet(key)
        encrypted = cipher.encrypt(backup)
        (archive / 'database.sql.fernet').write_bytes(encrypted)
        keydir = ROOT / '.cache/backup-keys'
        keydir.mkdir(exist_ok=True)
        (keydir / (identifier + '.dpapi')).write_bytes(protect(key))
        # 恢复演练实际读取落盘密文和独立 DPAPI 密钥，验证备份可用性。
        persisted_key = unprotect((keydir / (identifier + '.dpapi')).read_bytes())
        persisted_backup = (archive / 'database.sql.fernet').read_bytes()
        cipher = Fernet(persisted_key)
        if cipher.decrypt(persisted_backup) != backup:
            raise RuntimeError('BACKUP_ENCRYPTION_MISMATCH')
        write_json(archive / 'backup.json', {
            'sha256': hashlib.sha256(encrypted).hexdigest(), 'key_file': str(keydir / (identifier + '.dpapi')),
            'encryption': 'Fernet；密钥使用当前 Windows 用户 DPAPI 单独保护', 'plaintext_saved': False, 'persisted_key_decryption_verified': True})
        env = os.environ.copy()
        env['MYSQL_ROOT_PASSWORD'] = secrets.token_hex(24)
        env['ORG_DATABASE_URL'] = 'mysql+pymysql://root:' + env['MYSQL_ROOT_PASSWORD'] + '@127.0.0.1:3306/organization?charset=utf8mb4'
        created = False
        try:
            command(['docker', 'run', '-d', '--name', temporary, '--network', 'none', '--tmpfs', '/var/lib/mysql:rw', '-e', 'MYSQL_ROOT_PASSWORD', mysql_image,
                     '--character-set-server=utf8mb4', '--collation-server=utf8mb4_general_ci'], env=env)
            created = True
            for attempt in range(60):
                try:
                    command(['docker', 'exec', temporary, 'sh', '-c', 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "SELECT 1"'])
                    break
                except RuntimeError:
                    time.sleep(1)
            else:
                raise RuntimeError('REHEARSAL_MYSQL_TIMEOUT')
            command(['docker', 'exec', temporary, 'sh', '-c', 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "CREATE DATABASE organization CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"'])
            sql(temporary, cipher.decrypt(persisted_backup).decode('utf-8'))
            restored = snapshot(temporary)
            if restored != initial or metadata(temporary) != original_metadata or business_digest(temporary) != original_digest:
                raise RuntimeError('RESTORED_DATABASE_MISMATCH')
            write_json(archive / 'restored.json', restored)
            print('加密备份恢复、全表数据摘要及结构核验通过，开始隔离迁移', flush=True)
            command(['docker', 'run', '--rm', '--network', 'container:' + temporary, '-e', 'ORG_DATABASE_URL', actual_image,
                     'python', '-m', 'alembic', 'upgrade', TARGET], env=env)
            rehearsed = snapshot(temporary)
            assert_only_tencent(original_metadata, metadata(temporary))
            if rehearsed != {**initial, 'version': TARGET} or business_digest(temporary) != original_digest:
                raise RuntimeError('REHEARSAL_DATA_CHANGED')
            assert_tencent_empty(temporary)
            rehearsal_schema = json.loads(command(['docker', 'run', '--rm', '--network', 'container:' + temporary,
                '-e', 'ORG_DATABASE_URL', actual_image, 'python', '-c', schema_check_code()], env=env))
            write_json(archive / 'rehearsal-schema-check.json', rehearsal_schema)
            write_json(archive / 'rehearsal.json', rehearsed)
        finally:
            if created:
                command(['docker', 'rm', '-f', temporary])
        candidate = archive / 'candidate.json'
        write_json(candidate, host.image_config({name: actual_image for name in ('app', 'mcp', 'migrate')}))
        command(host.dc(candidate) + ['config', '--quiet'])
        print('隔离演练通过，开始执行已授权的本地 0020 迁移', flush=True)
        command(host.dc(candidate) + ['run', '--rm', '--no-deps', '-T', 'app', 'python', '-m', 'alembic', 'upgrade', TARGET])
        after = snapshot(mysql)
        after_metadata = metadata(mysql)
        after_digest = business_digest(mysql)
        assert_only_tencent(original_metadata, after_metadata)
        if after != {**initial, 'version': TARGET} or after_digest != original_digest:
            raise RuntimeError('MIGRATED_DATA_CHANGED')
        assert_tencent_empty(mysql)
        actual_schema = json.loads(command(host.dc(candidate) + ['run', '--rm', '--no-deps', '-T', 'app',
            'python', '-c', schema_check_code()]))
        write_json(archive / 'schema-check-after.json', actual_schema)
        write_json(archive / 'database-after.json', after)
        write_json(archive / 'metadata-after.json', after_metadata)
        write_json(archive / 'data-digests-after.json', after_digest)
        write_json(archive / 'result.json', {'status': 'migrated', 'source': SOURCE, 'target': TARGET,
                   'added_tables': sorted(TENCENT_TABLES), 'original_structure_preserved': True, 'business_data_preserved': True, 'services_stopped': True})
        print(json.dumps({'status': 'migrated', 'archive': str(archive), 'schema': TARGET}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('MIGRATION_STOPPED: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__) + '；停止并检查证据，不自动恢复或重试 DDL', file=sys.stderr)
        sys.exit(1)
