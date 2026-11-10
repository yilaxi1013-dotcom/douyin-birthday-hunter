#!/usr/bin/env node
/**
 * 依赖自举：确保 vendor/node_modules/playwright-core 可用。
 *
 * 三级策略：
 *   1. 已随包提供 → 直接通过
 *   2. 用 npm 从官方源安装
 *   3. npm 不可用/被墙 → 从 GitHub 拉源码构建（耗时较长）
 *
 * 用法：
 *   node setup_deps.mjs            # 自动（1→2→3）
 *   node setup_deps.mjs --github   # 强制走 GitHub
 *   node setup_deps.mjs --check    # 只检查，不安装
 */
import { execSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const VENDOR = path.resolve(HERE, '..');
const PW_DIR = path.join(VENDOR, 'node_modules', 'playwright-core');
const PW_PKG = path.join(PW_DIR, 'package.json');

const args = process.argv.slice(2);
const FORCE_GITHUB = args.includes('--github');
const CHECK_ONLY = args.includes('--check');

function has(cmd) {
  const r = spawnSync(cmd, ['--version'], { shell: true, encoding: 'utf8' });
  return r.status === 0;
}

function version() {
  try {
    return JSON.parse(fs.readFileSync(PW_PKG, 'utf8')).version;
  } catch {
    return null;
  }
}

async function importOK() {
  try {
    const { createRequire } = await import('node:module');
    const require = createRequire(import.meta.url);
    const p = require.resolve('playwright-core');
    return !!p;
  } catch {
    return false;
  }
}

function run(cmd, cwd = VENDOR) {
  console.log('  $ ' + cmd);
  try {
    execSync(cmd, { cwd, stdio: 'inherit', shell: true });
    return true;
  } catch {
    return false;
  }
}

async function main() {
  console.log('检查 playwright-core …');
  if (fs.existsSync(PW_PKG) && (await importOK())) {
    console.log(`  已就绪 v${version()}（随包提供，无需联网）`);
    return 0;
  }
  if (CHECK_ONLY) {
    console.log('  缺失，需要安装');
    return 1;
  }

  if (!has('node')) {
    console.error('未找到 Node.js，请先安装 Node.js 18+：https://nodejs.org');
    return 1;
  }

  if (!FORCE_GITHUB && has('npm')) {
    console.log('\n[1/2] 尝试用 npm 安装 …');
    if (run('npm install playwright-core@^1.65.0 --no-audit --no-fund --omit=dev')) {
      if (fs.existsSync(PW_PKG)) {
        console.log(`\n完成，playwright-core v${version()}`);
        return 0;
      }
    }
    console.log('  npm 安装未成功，转入 GitHub 方案');
  } else if (!has('npm') && !FORCE_GITHUB) {
    console.log('\nnpm 不可用，转入 GitHub 方案');
  }

  // GitHub 兜底
  console.log('\n[2/2] 从 GitHub 获取 …');
  if (!has('git')) {
    console.error('未找到 git。请任选其一：');
    console.error('  A. 安装 Node.js 后执行：npm install playwright-core');
    console.error('  B. 安装 git 后重跑本脚本');
    console.error('  C. 手动下载 playwright-core 目录放入 vendor/node_modules/');
    return 1;
  }

  const tmp = path.join(VENDOR, '.pw-src');
  fs.rmSync(tmp, { recursive: true, force: true });

  const cloned =
    run(`git clone --depth 1 --branch v1.65.0 https://github.com/microsoft/playwright.git "${tmp}"`) ||
    run(`git clone --depth 1 https://github.com/microsoft/playwright.git "${tmp}"`);

  if (!cloned) {
    console.error('GitHub 克隆失败（网络受限）。可手动将 playwright-core 目录放入：');
    console.error('  ' + PW_DIR);
    return 1;
  }

  console.log('  构建中（可能需要数分钟）…');
  const built = run('npm ci --no-audit --no-fund && npm run build', tmp);
  const pkgSrc = path.join(tmp, 'packages', 'playwright-core');
  if (!built || !fs.existsSync(pkgSrc)) {
    console.error('构建未成功。可改用手动方式：把 packages/playwright-core 复制到 vendor/node_modules/');
    return 1;
  }

  fs.mkdirSync(path.join(VENDOR, 'node_modules'), { recursive: true });
  fs.cpSync(pkgSrc, PW_DIR, { recursive: true });
  fs.rmSync(tmp, { recursive: true, force: true });

  if (fs.existsSync(PW_PKG)) {
    console.log(`\n完成，playwright-core v${version()}（来自 GitHub）`);
    return 0;
  }
  console.error('复制后仍未找到包，请手动检查 vendor/node_modules/playwright-core');
  return 1;
}

main().then(code => process.exit(code)).catch(e => {
  console.error('失败：', e.message);
  process.exit(1);
});
