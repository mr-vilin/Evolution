"""验证项目改名保持卷与镜像、阻止不安全目标并在失败时恢复。"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from deploy import release
from release_host import Host, write_json
from release_rename import LocalRename, mysql_volume, renamed_compose, require_local, require_same_data, VOLUME
import yaml


class RenameTests(unittest.TestCase):
    def test_remote_target_and_wrong_volume_are_rejected(self):
        for target in ({'environment': 'test', 'transport': 'ssh'}, {'environment': 'local', 'transport': 'ssh'}):
            with self.assertRaisesRegex(RuntimeError, 'RENAME_LOCAL_ONLY'):
                require_local(target)
        for mounts in ([], [{'Destination': '/var/lib/mysql', 'Type': 'bind', 'Name': VOLUME}],
                       [{'Destination': '/var/lib/mysql', 'Type': 'volume', 'Name': 'empty-new-volume'}]):
            with self.assertRaisesRegex(RuntimeError, 'MYSQL_VOLUME_MISMATCH'):
                mysql_volume(mounts)

    def test_stopped_unmounted_legacy_migration_is_archived_but_running_one_blocks(self):
        target = {'root': '.', 'environment': 'local', 'transport': 'local', 'project': 'organization-directory'}
        item = {'Id': 'legacy', 'Image': 'sha256:old', 'State': {'Running': False},
                'Config': {'Labels': {'com.docker.compose.service': 'migrate'}}, 'Mounts': []}
        rename = LocalRename(target)
        with patch('release_rename.run', side_effect=['legacy', json.dumps([item])]):
            self.assertEqual(rename.inventory('organization-directory'), {})
        self.assertEqual(rename.legacy_containers[0]['id'], 'legacy')
        item['State']['Running'] = True
        with patch('release_rename.run', side_effect=['legacy', json.dumps([item])]):
            with self.assertRaisesRegex(RuntimeError, 'UNMANAGED_COMPOSE_CONTAINER'):
                rename.inventory('organization-directory')

    def test_candidate_keeps_all_other_configuration_and_requires_existing_volume(self):
        original = {'name': 'organization-directory', 'services': {
            name: {'image': 'organization-directory-runtime:${ORG_IMAGE_TAG:-local}', 'env_file': '.env',
                   'command': ['original', name]} for name in ('app', 'mcp', 'migrate')},
            'volumes': {'mysql-data': None}, 'networks': {'capabilities': {'internal': True}}}
        old = deepcopy(original)
        candidate = renamed_compose(original)
        self.assertEqual(original, old)
        self.assertEqual(candidate['volumes']['mysql-data'], {'external': True, 'name': VOLUME})
        self.assertEqual(candidate['networks'], original['networks'])
        for name in ('app', 'mcp', 'migrate'):
            self.assertEqual(candidate['services'][name]['env_file'], '.env')
            self.assertEqual(candidate['services'][name]['command'], original['services'][name]['command'])

    def test_database_content_change_is_rejected_before_workers_start(self):
        state = {'schema': 'head', 'state': {'data_version': 7}, 'counts': {'employee': 25},
                 'flow_phase': 'pending', 'active_jobs': 0}
        changed = deepcopy(state)
        changed['counts']['employee'] = 0
        with self.assertRaisesRegex(RuntimeError, 'RENAME_DATA_MISMATCH'):
            require_same_data(state, changed)

    def test_server_defaults_change_is_rejected_before_workers_start(self):
        state = {'schema': 'head', 'database': {'server_collation': 'utf8mb4_0900_as_cs'},
                 'state': {}, 'counts': {}, 'flow_phase': 'complete', 'active_jobs': 0}
        changed = deepcopy(state)
        changed['database']['server_collation'] = 'utf8mb4_general_ci'
        with self.assertRaisesRegex(RuntimeError, 'RENAME_DATA_MISMATCH: database'):
            require_same_data(state, changed)

    def exercise_rename(self, fail_after_mysql=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'deploy').mkdir()
            target = {'root': directory, 'environment': 'local', 'transport': 'local',
                      'project': 'organization-directory', 'compose': 'compose.yaml', 'services': ['app', 'mcp']}
            compose = {'name': 'organization-directory', 'services': {
                name: {'image': 'organization-directory-runtime:local'} for name in ('app', 'mcp', 'migrate')},
                'volumes': {'mysql-data': None}}
            (root / 'compose.yaml').write_text(yaml.safe_dump(compose))
            write_json(root / 'deploy/environments.json', {'local': target, 'test': {'project': 'organization-directory'}})
            (root / '.cache').mkdir()
            write_json(root / '.cache/deployment-image.json', Host.image_config({'app': 'sha256:app', 'mcp': 'sha256:app'}))
            write_json(root / '.cache/deployment-source.json', {'release_id': 'release-fixture', 'image_id': 'sha256:app', 'build': {}})
            original_files = {p: (root / p).read_bytes() for p in ('compose.yaml', 'deploy/environments.json', '.cache/deployment-image.json', '.cache/deployment-source.json')}
            initial = {s: {'id': 'old-' + s, 'image': 'sha256:mysql' if s == 'mysql' else 'sha256:app',
                          'running': False, 'mounts': []} for s in ('mysql', 'app', 'mcp')}
            initial['mysql']['mounts'] = [{'Destination': '/var/lib/mysql', 'Type': 'volume', 'Name': VOLUME}]
            new = deepcopy(initial)
            for name in new:
                new[name]['id'] = 'new-' + name
            flags = {'old_mysql': False, 'new_mysql': False, 'created': False}
            calls = []
            state = {'schema': 'head', 'state': {'initialization_status': 'pending'}, 'counts': {'employee': 25},
                     'flow_phase': 'pending', 'active_jobs': 0, 'build': {}}

            def command(args, **kwargs):
                calls.append(args)
                if args[:3] == ['docker', 'context', 'inspect']:
                    return json.dumps('npipe:////./pipe/dockerDesktopLinuxEngine')
                if args[:3] == ['docker', 'ps', '-q']:
                    return 'old-mysql' if flags['old_mysql'] else 'new-mysql' if flags['new_mysql'] else ''
                if args[:2] == ['docker', 'start']:
                    flags['old_mysql'] = True
                if args[:2] == ['docker', 'stop']:
                    flags['old_mysql'] = False
                if args[:3] == ['docker', 'run', '--rm']:
                    return 'head'
                if args[:2] == ['docker', 'compose']:
                    project = args[args.index('-p') + 1]
                    if 'up' in args and args[-1] == 'mysql':
                        self.assertFalse(flags['old_mysql'], 'must stop old mysqld before starting new mysqld')
                        flags.update(new_mysql=True, created=True)
                    if 'stop' in args and project == 'evolution' and 'mysql' in args:
                        flags['new_mysql'] = False
                    if 'start' in args and project == 'organization-directory' and args[-1] == 'mysql':
                        self.assertFalse(flags['new_mysql'])
                        flags['old_mysql'] = True
                return ''

            def inventory(instance, project):
                return deepcopy(initial if project == 'organization-directory' else new if flags['created'] else {})

            def probe(host, expression):
                if fail_after_mysql and host.target['project'] == 'evolution':
                    raise RuntimeError('injected database probe failure')
                return deepcopy(state)

            rename = LocalRename(target)
            with patch('release_rename.run', side_effect=command), patch.object(LocalRename, 'inventory', inventory), \
                 patch.object(LocalRename, 'wait_mysql'), patch.object(Host, 'probe', probe), \
                 patch.object(Host, 'verify', return_value={'build': {}, 'assets': []}):
                if fail_after_mysql:
                    with self.assertRaisesRegex(RuntimeError, 'RENAME_FAILED_ROLLED_BACK'):
                        rename.execute()
                    for path, data in original_files.items():
                        self.assertEqual((root / path).read_bytes(), data)
                    self.assertFalse(flags['new_mysql'])
                    self.assertFalse(flags['old_mysql'])
                    self.assertTrue((rename.archive / 'rollback-verified.json').exists())
                else:
                    self.assertEqual(rename.execute()['status'], 'renamed')
                    settings = json.loads((root / 'deploy/environments.json').read_text())
                    self.assertEqual(settings['local']['project'], 'evolution')
                    self.assertEqual(settings['test']['project'], 'organization-directory')
                    self.assertEqual(yaml.safe_load((root / 'compose.yaml').read_text())['volumes']['mysql-data']['name'], VOLUME)
                self.assertFalse((root / '.cache/deployment.lock').exists())
            self.assertFalse(any(args[:3] == ['docker', 'volume', 'rm'] for args in calls))
            self.assertFalse(any('up' in args and args[-1] == 'migrate' for args in calls))
            self.assertFalse(any(args[:2] == ['docker', 'rm'] and '-v' in args for args in calls))

    def test_success_reuses_mysql_volume_without_running_migrations(self):
        self.exercise_rename()

    def test_database_failure_restores_files_and_original_stopped_state(self):
        self.exercise_rename(fail_after_mysql=True)


if __name__ == '__main__':
    unittest.main()
