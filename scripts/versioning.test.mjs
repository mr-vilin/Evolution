import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { parseVersion, compareVersions, releaseRecords, checkRepository, buildInfo } from './versioning.mjs';

function fixture(t, version = '0.1.0', entries = '') {
  const root = mkdtempSync(join(tmpdir(), 'organization-version-test-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  writeFileSync(join(root, 'version.json'), JSON.stringify({ version }));
  writeFileSync(join(root, 'CHANGELOG.md'), `# 产品版本\n\n## [Unreleased]\n\n开发改动\n\n${entries}`);
  return root;
}

test('遵循官方预发布优先级，编译信息不影响排序，大整数不丢失精度', () => {
  const versions = ['1.0.0-alpha', '1.0.0-alpha.1', '1.0.0-alpha.beta', '1.0.0-beta', '1.0.0-beta.2', '1.0.0-beta.11', '1.0.0-rc.1', '1.0.0'];
  for (let i = 1; i < versions.length; i++) assert.equal(compareVersions(versions[i - 1], versions[i]), -1);
  assert.equal(compareVersions('1.0.0+001', '1.0.0+sha.abc'), 0);
  assert.equal(compareVersions('1.0.0-9007199254740992', '1.0.0-9007199254740993'), -1);
});

test('拒绝前导零、v 前缀和无效标识，允许合法构建信息', () => {
  for (const value of ['v0.1.0', '0.1', '01.1.0', '0.01.0', '0.1.00', '0.1.0-01', '0.1.0-', '0.1.0+']) assert.throws(() => parseVersion(value));
  for (const value of ['0.1.0', '0.1.0-alpha.1', '0.1.0-01a', '0.1.0+001']) assert.doesNotThrow(() => parseVersion(value));
});

test('版本倒序排列，允许同日记录，但拒绝重复版本和非法日期', () => {
  const header = '## [Unreleased]\n\n';
  assert.equal(releaseRecords(header + '## [0.1.1] — 2026-10-24\n修复\n## [0.1.0] — 2026-10-24\n初始').length, 2);
  for (const entries of [
    '## [0.1.0] — 2026-10-24\n## [0.1.0] — 2026-10-23',
    '## [0.1.0] — 2026-02-30',
    '## [0.1.0] — 2026-10-23\n## [0.1.1] — 2026-10-24',
    '## [0.1.0] — 2026-10-24\n## [Unreleased]',
  ]) assert.throws(() => releaseRecords(header + entries));
});

test('历史台账仅校验版本顺序，不按当前递增策略追溯判定旧记录', t => {
  const root = fixture(t, '1.4.5', '## [1.4.5] — 2026-10-25\n现有交付\n## [1.4.3] — 2026-10-24\n历史记录');
  assert.doesNotThrow(() => checkRepository(root));
  assert.throws(() => releaseRecords('## [Unreleased]\n## [1.4.5+new]\n## [1.4.5+old]'), /版本倒序/);
});

test('开发基线和已准备的发布记录都不会把普通构建误标为已发布', t => {
  const root = fixture(t);
  assert.equal(checkRepository(root).version, '0.1.0');
  assert.throws(() => checkRepository(root, { release: true }), /最新版本记录/);
  writeFileSync(join(root, 'CHANGELOG.md'), '## [Unreleased]\n## [0.1.0] — 2026-10-24\n初始');
  const info = buildInfo(root, {});
  assert.equal(info.stage, 'development');
  assert.equal(info.releaseDate, null);
  assert.equal(info.commit, 'unknown');
  assert.equal(info.dirty, null);
});

test('发行产物要求 tag、版本记录、提交和干净源码状态一致', t => {
  const root = fixture(t, '0.1.0-rc.1', '## [0.1.0-rc.1] — 2026-10-24\n候选');
  assert.throws(() => checkRepository(root, { tag: 'v0.1.0' }), /tag/);
  const env = { RELEASE_TAG: 'v0.1.0-rc.1', COMMIT_SHA: 'a'.repeat(40), SOURCE_DIRTY: 'false' };
  const info = buildInfo(root, env);
  assert.equal(info.stage, 'prerelease');
  assert.equal(info.releaseDate, '2026-10-24');
  assert.throws(() => buildInfo(root, { ...env, SOURCE_DIRTY: 'true' }), /干净/);
  assert.throws(() => buildInfo(root, { ...env, COMMIT_SHA: 'unknown' }), /真实提交/);
});

test('PR 基准检查允许补正既有说明和日期，保留版本历史与发行制品检查', t => {
  const root = fixture(t, '0.1.0', '## [0.1.0] — 2026-10-24\n原始说明\n');
  const run = args => execFileSync('git', args, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  run(['init', '--quiet']);
  run(['add', '.']);
  run(['-c', 'user.name=Version Test', '-c', 'user.email=version-test@example.invalid', 'commit', '--quiet', '-m', 'fixture']);
  const baseRef = run(['rev-parse', 'HEAD']);
  assert.doesNotThrow(() => checkRepository(root, { baseRef }));
  run(['tag', 'v0.1.0']);
  assert.doesNotThrow(() => checkRepository(root, { tag: 'v0.1.0' }));
  writeFileSync(join(root, 'CHANGELOG.md'), '## [Unreleased]\n## [0.1.0] — 2026-10-25\n补正说明及遗漏\n');
  assert.doesNotThrow(() => checkRepository(root, { baseRef }));
  assert.throws(() => checkRepository(root, { tag: 'v0.1.0' }), /干净/);
  writeFileSync(join(root, 'CHANGELOG.md'), '## [Unreleased]\n');
  assert.throws(() => checkRepository(root, { baseRef }), /不得移除/);
  writeFileSync(join(root, 'CHANGELOG.md'), '## [Unreleased]\n## [0.1.0] — 2026-10-25\n补正说明及遗漏\n');
  writeFileSync(join(root, 'version.json'), JSON.stringify({ version: '0.2.0' }));
  assert.doesNotThrow(() => checkRepository(root, { baseRef }));
  writeFileSync(join(root, 'version.json'), JSON.stringify({ version: '0.1.1' }));
  assert.doesNotThrow(() => checkRepository(root, { baseRef }));
  writeFileSync(join(root, 'version.json'), JSON.stringify({ version: '0.0.9' }));
  assert.throws(() => checkRepository(root, { baseRef }), /低于/);
  writeFileSync(join(root, 'version.json'), JSON.stringify({ version: '0.1.0' }));
  writeFileSync(join(root, 'CHANGELOG.md'), '## [Unreleased]\n');
  run(['add', '.']);
  run(['-c', 'user.name=Version Test', '-c', 'user.email=version-test@example.invalid', 'commit', '--quiet', '-m', 'baseline without numbered entries']);
  writeFileSync(join(root, 'version.json'), JSON.stringify({ version: '0.0.9' }));
  assert.throws(() => checkRepository(root, { baseRef: run(['rev-parse', 'HEAD']) }), /低于基准/);
});

test('首次引入版本台账允许空基准体系，但拒绝无效基准和部分缺失', t => {
  const root = fixture(t);
  const run = args => execFileSync('git', args, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  run(['init', '--quiet']);
  run(['-c', 'user.name=Version Test', '-c', 'user.email=version-test@example.invalid', 'commit', '--allow-empty', '--quiet', '-m', 'empty baseline']);
  const baseRef = run(['rev-parse', 'HEAD']);
  assert.doesNotThrow(() => checkRepository(root, { baseRef }));
  assert.throws(() => checkRepository(root, { baseRef: 'f'.repeat(40) }), /无法读取基准/);
  run(['add', 'version.json']);
  run(['-c', 'user.name=Version Test', '-c', 'user.email=version-test@example.invalid', 'commit', '--quiet', '-m', 'incomplete baseline']);
  assert.throws(() => checkRepository(root, { baseRef: run(['rev-parse', 'HEAD']) }), /无法读取基准/);
});

test('候选版本暂缺日期仍可开发校验，但不能用于发行构建', t => {
  const root = fixture(t, '0.2.0', '## [0.2.0]\n候选');
  assert.equal(checkRepository(root).version, '0.2.0');
  assert.equal(buildInfo(root, {}).releaseDate, null);
  assert.throws(() => checkRepository(root, { release: true }), /已确认版本日期/);
  assert.doesNotThrow(() => releaseRecords('## [Unreleased]\n## [0.2.0] — 2026-11-16\n## [0.1.0]\n日期待补正'));
  assert.doesNotThrow(() => releaseRecords('## [Unreleased]\n## [0.2.0] — 2026-11-15\n## [0.1.0] — 2026-11-16\n补正历史日期'));
});
