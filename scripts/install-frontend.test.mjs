import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { gzipSync } from 'node:zlib';
import { installDependencies, runNpm, installArgs } from './install-frontend.mjs';

test('网络错误重试有上限，耗尽后保留 npm 退出码', async () => {
  let attempts = 0;
  const waits = [];
  const code = await installDependencies({
    run: async () => { attempts++; return { code: 7, stderr: 'npm error code ECONNRESET\nnpm error network aborted\n' }; },
    wait: async ms => waits.push(ms), log: () => {},
  });
  assert.equal(code, 7);
  assert.equal(attempts, 3);
  assert.deepEqual(waits, [5000, 10000]);
});

test('依赖冲突、脚本错误与信号中断不重试', async () => {
  for (const failure of [
    { code: 1, stderr: 'npm error code ERESOLVE\n' },
    { code: 1, stderr: 'npm error code ECONNRESET\nnpm error code 1\nnpm error command failed\n' },
    { code: 1, signal: 'SIGTERM', stderr: 'npm error code ECONNRESET\n' },
  ]) {
    let attempts = 0;
    const code = await installDependencies({
      run: async () => { attempts++; return failure; },
      wait: async () => assert.fail('不应等待重试'), log: () => {},
    });
    assert.equal(code, 1);
    assert.equal(attempts, 1);
  }
});

// 最小 npm tarball：不访问公网，在真实 npm ci 下载过程中注入一次断连。
function packageArchive() {
  const content = Buffer.from(JSON.stringify({ name: 'network-fixture', version: '1.0.0' }));
  const header = Buffer.alloc(512);
  header.write('package/package.json');
  for (const [offset, length, value] of [[100, 8, 0o644], [108, 8, 0], [116, 8, 0], [124, 12, content.length], [136, 12, 0]]) {
    header.write(value.toString(8).padStart(length - 1, '0') + '\0', offset, length);
  }
  header.fill(32, 148, 156);
  header.write('0', 156);
  header.write('ustar\0', 257);
  header.write('00', 263);
  const checksum = header.reduce((sum, byte) => sum + byte, 0);
  header.write(checksum.toString(8).padStart(6, '0') + '\0 ', 148, 8);
  return gzipSync(Buffer.concat([header, content, Buffer.alloc((512 - content.length % 512) % 512 + 1024)]));
}

test('真实 npm 下载中断后重装成功，再次安装可从缓存完成', { timeout: 30000 }, async t => {
  const directory = mkdtempSync(join(tmpdir(), 'evolution-npm-network-'));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const archive = packageArchive();
  let requests = 0;
  let offline = false;
  const server = createServer((_req, res) => {
    requests++;
    if (offline) { res.destroy(); return; }
    res.writeHead(200, { 'Content-Type': 'application/octet-stream', 'Content-Length': archive.length, 'Cache-Control': 'public, max-age=3600' });
    if (requests === 1) { res.write(archive.subarray(0, 16)); setTimeout(() => res.destroy(), 30); }
    else res.end(archive);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const url = `http://127.0.0.1:${server.address().port}/fixture.tgz`;
  const dependencies = { 'network-fixture': url };
  writeFileSync(join(directory, 'package.json'), JSON.stringify({ name: 'network-test', version: '1.0.0', dependencies }));
  writeFileSync(join(directory, 'package-lock.json'), JSON.stringify({
    name: 'network-test', version: '1.0.0', lockfileVersion: 3,
    packages: { '': { name: 'network-test', version: '1.0.0', dependencies }, 'node_modules/network-fixture': { version: '1.0.0', resolved: url } },
  }));
  const args = [...installArgs, '--fetch-retries=0', '--fetch-timeout=2000', '--cache', join(directory, 'cache')];
  let attempts = 0;
  const outcomes = [];
  const code = await installDependencies({ run: async () => {
    attempts++;
    const outcome = await runNpm(args, { cwd: directory });
    outcomes.push(outcome);
    return outcome;
  }, wait: async () => {}, log: () => {} });
  assert.equal(code, 0);
  assert.equal(attempts, 2);
  assert.match(outcomes[0].stderr, /ECONNRESET/);
  assert.equal(JSON.parse(readFileSync(join(directory, 'node_modules/network-fixture/package.json'))).version, '1.0.0');
  const beforeOffline = requests;
  offline = true;
  assert.equal((await runNpm([...args, '--offline'], { cwd: directory })).code, 0);
  assert.equal(requests, beforeOffline);
});
