// Docker 构建专用：保留严格安装，仅在 npm 明确报告网络故障时重试整次安装。
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const installArgs = ['ci', '--strict-peer-deps', '--include=optional', '--fetch-retries=5', '--prefer-offline', '--no-audit', '--no-fund'];
const networkCodes = new Set(['ECONNRESET', 'ETIMEDOUT', 'ESOCKETTIMEDOUT', 'ERR_SOCKET_TIMEOUT', 'EAI_AGAIN', 'ECONNREFUSED', 'ENETUNREACH', 'EHOSTUNREACH']);

export function runNpm(args = installArgs, { cwd = process.cwd(), env = process.env } = {}) {
  // Windows 的 npm.cmd 需要 shell；直接调用同一 Node 安装中的 npm CLI，避免 shell 转义。
  const command = process.platform === 'win32' ? process.execPath : 'npm';
  const commandArgs = process.platform === 'win32' ? [join(dirname(process.execPath), 'node_modules/npm/bin/npm-cli.js'), ...args] : args;
  return new Promise((accept, reject) => {
    const child = spawn(command, commandArgs, { cwd, env, stdio: ['ignore', 'inherit', 'pipe'] });
    let stderr = '';
    child.stderr.on('data', chunk => {
      process.stderr.write(chunk);
      stderr = (stderr + chunk.toString()).slice(-65536);
    });
    child.on('error', reject);
    child.on('close', (code, signal) => accept({ code: code ?? 1, signal, stderr }));
  });
}

export async function installDependencies({ run = runNpm, wait = delay, log = console.error } = {}) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    const result = await run();
    if (result.code === 0) return 0;
    const codes = [...result.stderr.matchAll(/^npm (?:error|ERR!) code (\S+)\s*$/gm)];
    const code = codes.at(-1)?.[1];
    if (result.signal || !networkCodes.has(code) || attempt === 3) return result.code;
    const milliseconds = attempt * 5000;
    log(`npm 下载发生 ${code}，${milliseconds / 1000} 秒后重试安装（${attempt + 1}/3），复用已下载缓存。`);
    await wait(milliseconds);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.exitCode = await installDependencies(); }
  catch (error) { console.error(`前端依赖安装无法启动：${error.message}`); process.exitCode = 1; }
}
