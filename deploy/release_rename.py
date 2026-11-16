"""本地 Compose 项目改名：同一镜像、同一数据卷，不执行迁移。"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid

import yaml
from release_host import Host, require_idle, require_schema, run, write_json

OLD_PROJECT = 'organization-directory'
NEW_PROJECT = 'evolution'
VOLUME = 'organization-directory_mysql-data'
IMAGE_REPOSITORY = 'evolution-runtime'


def require_local(target):
    if target.get('environment') != 'local' or target.get('transport') != 'local':
        raise RuntimeError('RENAME_LOCAL_ONLY: 只允许本地 Docker 改名')
    if target.get('project') not in (OLD_PROJECT, NEW_PROJECT):
        raise RuntimeError('UNEXPECTED_SOURCE_PROJECT')


def mysql_volume(mounts):
    volumes = [m for m in mounts if m.get('Destination') == '/var/lib/mysql']
    if len(volumes) != 1 or volumes[0].get('Type') != 'volume' or volumes[0].get('Name') != VOLUME:
        raise RuntimeError('MYSQL_VOLUME_MISMATCH: 不创建或替换数据库卷')
    return volumes[0]['Name']


def renamed_compose(original):
    result = deepcopy(original)
    result['name'] = NEW_PROJECT
    for service in ('app', 'mcp', 'migrate'):
        image = result['services'][service]['image']
        if not image.startswith(('organization-directory-runtime:', IMAGE_REPOSITORY + ':')):
            raise RuntimeError('UNEXPECTED_IMAGE_REPOSITORY')
        result['services'][service]['image'] = IMAGE_REPOSITORY + ':' + image.split(':', 1)[1]
    result['volumes']['mysql-data'] = {'external': True, 'name': VOLUME}
    return result


def require_same_data(before, after):
    for key in ('schema', 'database', 'state', 'counts', 'flow_phase'):
        if before.get(key) != after.get(key):
            raise RuntimeError('RENAME_DATA_MISMATCH: ' + key)
    require_idle(after)


class LocalRename:
    def __init__(self, target):
        require_local(target)
        self.target = deepcopy(target)
        self.root = Path(target['root']).resolve()
        self.old = Host({**target, 'project': OLD_PROJECT})
        self.new = None
        self.receipt = {'status': 'preparing', 'environment': 'local', 'events': []}
        self.archive = None
        self.initial = {}
        self.legacy_containers = []
        self.backups = {}
        self.started_mysql = False
        self.switch_started = False
        self.writers_stopped = False

    def event(self, phase, **fields):
        event = {'timestamp': datetime.now(timezone.utc).isoformat(), 'event_name': 'docker.rename.' + phase, **fields}
        self.receipt['events'].append(event)
        write_json(self.archive / 'rename.json', self.receipt)
        print(json.dumps(event, ensure_ascii=False), flush=True)

    def inventory(self, project):
        ids = run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=' + project]).split()
        if not ids:
            return {}
        records = json.loads(run(['docker', 'inspect', *ids]))
        result = {}
        for item in records:
            labels = item['Config'].get('Labels') or {}
            service = labels.get('com.docker.compose.service')
            if not labels.get('com.docker.compose.container-number'):
                # 早期失败的手工迁移容器只有项目/服务标签，不能作为活动服务使用。
                if project == OLD_PROJECT and service == 'migrate' and not item['State']['Running'] and not item.get('Mounts'):
                    self.legacy_containers.append({'id': item['Id'], 'image': item['Image'], 'running': False, 'mounts': []})
                    continue
                raise RuntimeError('UNMANAGED_COMPOSE_CONTAINER')
            if labels.get('com.docker.compose.oneoff', '').lower() == 'true':
                raise RuntimeError('ACTIVE_ONE_OFF_CONTAINER: 先核实一次性容器')
            if service not in ('app', 'mcp', 'mysql', 'migrate') or service in result:
                raise RuntimeError('UNEXPECTED_COMPOSE_CONTAINERS')
            result[service] = {'id': item['Id'], 'image': item['Image'],
                               'running': item['State']['Running'], 'mounts': item.get('Mounts', [])}
        return result

    def wait_mysql(self, cid):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            state = json.loads(run(['docker', 'inspect', cid, '--format', '{{json .State}}']))
            if state.get('Health', {}).get('Status') == 'healthy':
                return
            if not state['Running']:
                raise RuntimeError('MYSQL_NOT_RUNNING')
            time.sleep(1)
        raise RuntimeError('MYSQL_HEALTH_TIMEOUT')

    def backup_files(self):
        for relative in ('compose.yaml', 'deploy/environments.json', '.cache/deployment-image.json', '.cache/deployment-source.json'):
            path = self.root / relative
            self.backups[relative] = path.read_bytes() if path.exists() else None
            if path.exists():
                (self.archive / ('previous-' + Path(relative).name)).write_bytes(self.backups[relative])

    def restore_files(self):
        for relative, data in self.backups.items():
            path = self.root / relative
            if data is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_bytes(data)

    def restore(self):
        if self.switch_started:
            # 两个 mysqld 绝不同时挂载同一数据卷。
            run(self.new.dc(self.candidate_images) + ['stop', 'app', 'mcp', 'mysql'], cwd=self.root)
            ids = self.inventory(NEW_PROJECT)
            if ids:
                run(['docker', 'rm', *[x['id'] for x in ids.values()]])
        self.restore_files()
        if self.switch_started:
            run(self.old.dc() + ['start', 'mysql'], cwd=self.root)
            self.wait_mysql(self.initial['mysql']['id'])
            restored = self.old.probe('snapshot()')
            require_schema(restored, self.stopped['schema'])
            if self.stopped['state']['initialization_status'] != 'complete':
                require_same_data(self.stopped, restored)
            write_json(self.archive / 'rollback-verified.json', restored)
        if self.writers_stopped and self.initial['app']['running']:
            self.old.up()
            self.old.verify(self.image_id)
        if (self.switch_started or self.started_mysql) and not self.initial['mysql']['running']:
            run(['docker', 'stop', self.initial['mysql']['id']])
        self.receipt['status'] = 'rolled_back'
        self.event('rolled_back')

    def execute(self):
        with self.old.lock():
            if self.target['project'] == NEW_PROJECT:
                found = self.inventory(NEW_PROJECT)
                if set(found) >= {'mysql', 'app', 'mcp'}:
                    mysql_volume(found['mysql']['mounts'])
                    evidence = Host(self.target).verify(found['app']['image'])
                    return {'status': 'already_renamed', 'project': NEW_PROJECT, 'assets': len(evidence['assets'])}
                raise RuntimeError('RENAME_ALREADY_CONFIGURED: 核实新项目状态，不覆盖配置')
            context = run(['docker', 'context', 'inspect', '--format', '{{json .Endpoints.docker.Host}}']).strip()
            if not json.loads(context).startswith('npipe://'):
                raise RuntimeError('RENAME_REQUIRES_LOCAL_DOCKER_DESKTOP')
            if self.inventory(NEW_PROJECT):
                raise RuntimeError('TARGET_PROJECT_EXISTS')
            self.initial = self.inventory(OLD_PROJECT)
            if not set(self.initial) >= {'mysql', 'app', 'mcp'}:
                raise RuntimeError('SOURCE_SERVICES_MISSING')
            mysql_volume(self.initial['mysql']['mounts'])
            if self.initial['app']['running'] != self.initial['mcp']['running']:
                raise RuntimeError('SOURCE_SERVICE_STATES_DIFFER')
            self.image_id = self.initial['app']['image']
            if self.initial['mcp']['image'] != self.image_id:
                raise RuntimeError('SOURCE_IMAGES_DIFFER')
            volume_users = run(['docker', 'ps', '-q', '--filter', 'volume=' + VOLUME]).split()
            if any(cid != self.initial['mysql']['id'] and not self.initial['mysql']['id'].startswith(cid) for cid in volume_users):
                raise RuntimeError('MYSQL_VOLUME_IN_USE_BY_OTHER_CONTAINER')
            rename_id = datetime.now(timezone.utc).strftime('rename-%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
            self.archive = self.old.archive_root / rename_id
            self.archive.mkdir(parents=True, exist_ok=False)
            self.backup_files()
            source = json.loads(self.backups['.cache/deployment-source.json']) if self.backups['.cache/deployment-source.json'] else {}
            if source.get('image_id') not in (None, self.image_id) and source.get('image_config_id') != self.image_id:
                raise RuntimeError('DEPLOYMENT_SOURCE_IMAGE_MISMATCH')
            alias = IMAGE_REPOSITORY + ':' + source.get('release_id', rename_id)
            original = yaml.safe_load(self.backups['compose.yaml'].decode('utf-8'))
            candidate = renamed_compose(original)
            self.candidate_compose = self.archive / 'candidate-compose.yaml'
            self.candidate_compose.write_text(yaml.safe_dump(candidate, allow_unicode=True, sort_keys=False), encoding='utf-8')
            self.candidate_images = self.archive / 'candidate-images.json'
            images = {name: alias for name in ('app', 'mcp', 'migrate')}
            images['mysql'] = self.initial['mysql']['image']
            write_json(self.candidate_images, Host.image_config(images))
            self.new = Host({**self.target, 'project': NEW_PROJECT, 'compose': str(self.candidate_compose)})
            write_json(self.archive / 'inventory.json', {'services': self.initial, 'legacy_containers': self.legacy_containers})
            write_json(self.archive / 'source.json', {'git_commit': run(['git', 'rev-parse', 'HEAD'], cwd=self.root).strip(),
                       'git_status': run(['git', 'status', '--porcelain'], cwd=self.root), 'deployed_build': source.get('build'),
                       'image_id': self.image_id, 'mysql_image_id': self.initial['mysql']['image'], 'volume': VOLUME})
            self.receipt.update({'rename_id': rename_id, 'project': NEW_PROJECT, 'image': alias, 'image_id': self.image_id, 'volume': VOLUME})
            self.event('started')
            try:
                # 标签仅指向原镜像；不构建工作区、不启动 migrate。
                existing = run(['docker', 'image', 'ls', '-q', alias]).strip()
                if existing and run(['docker', 'image', 'inspect', alias, '--format', '{{.Id}}']).strip() != self.image_id:
                    raise RuntimeError('TARGET_IMAGE_TAG_EXISTS')
                run(['docker', 'tag', self.image_id, alias])
                run(self.new.dc(self.candidate_images) + ['config', '--quiet'], cwd=self.root)
                if not self.initial['mysql']['running']:
                    run(['docker', 'start', self.initial['mysql']['id']])
                    self.started_mysql = True
                self.wait_mysql(self.initial['mysql']['id'])
                before = self.old.probe('snapshot()')
                require_idle(before)
                expected = run(['docker', 'run', '--rm', '--network', 'none', self.image_id, 'python', '-c',
                                'from app.persistence.database import CURRENT_SCHEMA_HEAD; print(CURRENT_SCHEMA_HEAD)']).strip()
                require_schema(before, expected)
                write_json(self.archive / 'before.json', before)
                self.event('preflight_passed', schema=before['schema'], counts=before['counts'])
                self.writers_stopped = True
                run(self.old.dc() + ['stop', 'app', 'mcp'], cwd=self.root)
                self.stopped = self.old.probe('snapshot()')
                require_idle(self.stopped)
                write_json(self.archive / 'stopped.json', self.stopped)
                self.switch_started = True
                run(['docker', 'stop', self.initial['mysql']['id']])
                if run(['docker', 'ps', '-q', '--filter', 'volume=' + VOLUME]).strip():
                    raise RuntimeError('MYSQL_VOLUME_STILL_ACTIVE')
                run(self.new.dc(self.candidate_images) + ['up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '120', 'mysql'], cwd=self.root)
                new_inventory = self.inventory(NEW_PROJECT)
                mysql_volume(new_inventory['mysql']['mounts'])
                if new_inventory['mysql']['image'] != self.initial['mysql']['image']:
                    raise RuntimeError('MYSQL_IMAGE_CHANGED')
                restored = self.new.probe('snapshot()')
                require_same_data(self.stopped, restored)
                write_json(self.archive / 'before-workers.json', restored)
                self.event('database_verified', schema=restored['schema'], counts=restored['counts'])
                # Host.up 固定 --no-deps，不创建或执行迁移服务。
                run(self.new.dc(self.candidate_images) + ['up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '120', 'app', 'mcp'], cwd=self.root)
                evidence = self.new.verify(self.image_id)
                if before['build'] != evidence['build']:
                    raise RuntimeError('RENAME_BUILD_CHANGED')
                after = self.new.probe('snapshot()')
                require_schema(after, before['schema'])
                if before['state']['initialization_status'] != 'complete':
                    require_same_data(self.stopped, after)
                write_json(self.archive / 'after.json', after)
                write_json(self.archive / 'verification.json', evidence)
                # 验收通过才提交默认入口；失败按原始字节恢复配置。
                (self.root / 'compose.yaml').write_text(self.candidate_compose.read_text(encoding='utf-8'), encoding='utf-8')
                environments = json.loads(self.backups['deploy/environments.json'])
                environments['local']['project'] = NEW_PROJECT
                environments['local']['image_repository'] = IMAGE_REPOSITORY
                write_json(self.root / 'deploy/environments.json', environments)
                write_json(self.old.override, Host.image_config(images))
                if source:
                    source.update({'runtime_image': alias, 'compose_project': NEW_PROJECT, 'rename_receipt': str(self.archive / 'rename.json')})
                    write_json(self.root / '.cache/deployment-source.json', source)
                self.receipt['status'] = 'renamed'
                self.event('verified', assets=len(evidence['assets']), build=evidence['build'])
            except Exception as failure:
                self.event('failed', error_code=str(failure).split(':', 1)[0] if isinstance(failure, RuntimeError) else type(failure).__name__)
                try:
                    self.restore()
                except Exception as rollback_failure:
                    self.receipt['rollback_error_code'] = str(rollback_failure).split(':', 1)[0] if isinstance(rollback_failure, RuntimeError) else type(rollback_failure).__name__
                    self.receipt['status'] = 'rollback_failed'
                    self.event('rollback_failed')
                    raise RuntimeError('RENAME_AND_ROLLBACK_FAILED: ' + str(self.archive)) from None
                raise RuntimeError('RENAME_FAILED_ROLLED_BACK: ' + str(self.archive)) from None
            # 验收后仅移除旧容器和无端点网络；从不删除数据卷。
            leftovers = []
            for item in [*self.initial.values(), *self.legacy_containers]:
                try:
                    run(['docker', 'rm', item['id']])
                except RuntimeError:
                    leftovers.append(item['id'])
            networks = run(['docker', 'network', 'ls', '-q', '--filter', 'label=com.docker.compose.project=' + OLD_PROJECT]).split()
            for network in networks:
                try:
                    if not json.loads(run(['docker', 'network', 'inspect', network]))[0].get('Containers'):
                        run(['docker', 'network', 'rm', network])
                except RuntimeError:
                    leftovers.append(network)
            self.event('completed', leftover_resources=leftovers)
            return {'status': 'renamed', 'project': NEW_PROJECT, 'image': alias, 'image_id': self.image_id,
                    'volume': VOLUME, 'archive': str(self.archive), 'assets': len(evidence['assets']), 'leftovers': leftovers}
