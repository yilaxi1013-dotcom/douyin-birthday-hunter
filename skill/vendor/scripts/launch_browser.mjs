#!/usr/bin/env node
/**
 * 启动一个「可被 CDP 接管」的 Edge/Chrome。
 *
 * 背景：Edge/Chrome 136+ 用默认用户目录 + --remote-debugging-port 会直接退出
 *      （报 "DevTools remote debugging requires a non-default data directory"）。
 *      因此这里复制默认 profile 的登录凭据到独立目录，再用它启动。
 *
 * 用法（必须后台常驻，否则浏览器会被会话回收）：
 *   node launch_browser.mjs --config <work>/config.json
 */
import { spawn, execSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const args = process.argv.slice(2);
const getArg = (k, d = null) => {
  const i = args.indexOf(k);
  return i >= 0 && args[i + 1] ? args[i + 1] : d;
};

const cfgPath = getArg('--config');
if (!cfgPath) { console.error('缺少 --config'); process.exit(2); }
const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
const CDP = cfg.paths.cdp || 'http://127.0.0.1:9222';
const PROFILE = cfg.paths.profile;
// 默认直连：沙箱/公司代理常把 douyin.com 拦成 502。需要代理时用 --proxy http://host:port
const PROXY = getArg('--proxy');

const BROWSERS = [
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
];

async function cdpAlive() {
  try {
    const r = await fetch(`${CDP}/json/version`, { signal: AbortSignal.timeout(2500) });
    return r.ok;
  } catch { return false; }
}

function killBrowsers() {
  for (const name of ['msedge.exe', 'chrome.exe']) {
    try { execSync(`taskkill /F /IM ${name}`, { stdio: 'ignore' }); } catch {}
  }
}

function seedProfile() {
  const candidates = [
    path.join(os.homedir(), 'AppData/Local/Microsoft/Edge/User Data'),
    path.join(os.homedir(), 'AppData/Local/Google/Chrome/User Data'),
  ];
  const src = candidates.find(p => fs.existsSync(p));
  if (!src) { console.log('[warn] 未找到默认浏览器 profile，将以未登录状态启动'); return; }

  fs.mkdirSync(path.join(PROFILE, 'Default', 'Network'), { recursive: true });
  const files = [
    ['Local State', 'Local State'],
    ['Default/Network/Cookies', 'Default/Network/Cookies'],
    ['Default/Preferences', 'Default/Preferences'],
  ];
  for (const [from, to] of files) {
    const s = path.join(src, from);
    if (!fs.existsSync(s)) continue;
    try { fs.copyFileSync(s, path.join(PROFILE, to)); } catch (e) { console.log('[warn] 复制失败', from, e.message); }
  }
  console.log('[info] 已复制登录凭据自', src);
}

async function main() {
  if (await cdpAlive()) {
    console.log('ALREADY_RUNNING ' + CDP);
    return;
  }

  killBrowsers();
  await new Promise(r => setTimeout(r, 1500));

  if (!fs.existsSync(path.join(PROFILE, 'Local State'))) seedProfile();

  const exe = BROWSERS.find(p => fs.existsSync(p));
  if (!exe) { console.error('未找到 Edge/Chrome 可执行文件'); process.exit(2); }

  const child = spawn(exe, [
    `--remote-debugging-port=${new URL(CDP).port || 9222}`,
    `--user-data-dir=${PROFILE}`,
    PROXY ? `--proxy-server=${PROXY}` : '--no-proxy-server',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-blink-features=AutomationControlled',
    'about:blank',
  ], { detached: true, stdio: 'ignore' });
  child.unref();
  console.log('[info] 已启动浏览器 pid=' + child.pid + ' exe=' + path.basename(exe));

  let ok = false;
  for (let i = 0; i < 40; i++) {
    await new Promise(r => setTimeout(r, 1000));
    if (await cdpAlive()) { ok = true; console.log(`READY ${CDP} (${i + 1}s)`); break; }
  }
  if (!ok) { console.error('CDP 端口未就绪'); process.exit(1); }

  // 保持进程存活，避免浏览器被父会话回收
  console.log('[info] 保持常驻中，关闭本任务即释放浏览器');
  setInterval(() => {}, 1 << 30);
}

process.on('SIGTERM', () => process.exit(0));
process.on('SIGINT', () => process.exit(0));
main();
