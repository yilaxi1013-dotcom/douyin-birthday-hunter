#!/usr/bin/env node
/**
 * 把 accounts.json 里的主页在「一个浏览器窗口」内以多标签页打开。
 * 仅在用户明确同意后再执行。
 *
 * 用法：node open_profiles.mjs --config <work>/config.json [--max 30] [--no-activate]
 */
import { chromium } from 'playwright-core';
import fs from 'node:fs';

for (const k of ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'all_proxy']) delete process.env[k];
process.env.NO_PROXY = '127.0.0.1,localhost';

const args = process.argv.slice(2);
const getArg = (k, d = null) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const hasFlag = (k) => args.includes(k);

const cfg = JSON.parse(fs.readFileSync(getArg('--config'), 'utf8'));
const MAX = Number(getArg('--max', 40));
const ACTIVATE = !hasFlag('--no-activate');

const accounts = JSON.parse(fs.readFileSync(cfg.paths.accounts, 'utf8'))
  .filter(a => a.profile)
  .slice(0, MAX);

if (!accounts.length) { console.error('没有可打开的主页链接'); process.exit(2); }

const browser = await chromium.connectOverCDP(cfg.paths.cdp, { timeout: 25000 });
const ctx = browser.contexts()[0];
const cdp = await browser.newBrowserCDPSession();

// 1) 关掉已有的散窗/散页，保留一个宿主
const existing = ctx.pages();
const host = existing[0] || await ctx.newPage();
for (const p of existing) if (p !== host) await p.close().catch(() => {});
for (const p of ctx.pages()) if (p !== host && !p.url().includes('douyin')) await p.close().catch(() => {});

// 2) 依次开标签页
const pages = new Map();
for (let i = 0; i < accounts.length; i++) {
  const a = accounts[i];
  let page;
  if (i === 0) {
    page = host;
    await page.goto(a.profile, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
  } else {
    page = await ctx.newPage();
    await page.goto(a.profile, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
  }
  pages.set(a.profile, page);
  console.log(`  [${i + 1}/${accounts.length}] ${a.nickname}`);
  await new Promise(r => setTimeout(r, 900));
}

// 3) 标题改成「序号 昵称」，并加守护定时器
for (const a of accounts) {
  const page = pages.get(a.profile);
  if (!page) continue;
  const title = `${String(a.no).padStart(2, '0')} ${a.nickname || '未命名'}`;
  await page.evaluate((t) => {
    document.title = t;
    if (window.__titleGuard) clearInterval(window.__titleGuard);
    window.__titleGuard = setInterval(() => { if (document.title !== t) document.title = t; }, 1500);
  }, title).catch(() => {});
}

// 4) 清登录弹窗 + 逐页激活渲染
const killOverlay = () => {
  const marks = [...document.querySelectorAll('div,section')].filter(e => {
    const t = e.innerText || '';
    return t.length > 20 && t.length < 400 && /登录后免费畅享高清视频/.test(t);
  });
  let n = 0;
  for (const m of marks) {
    let node = m, target = null;
    for (let i = 0; i < 8 && node; i++) {
      const st = getComputedStyle(node), r = node.getBoundingClientRect();
      if ((st.position === 'fixed' || st.position === 'absolute') && r.width > 500 && r.height > 300) { target = node; break; }
      node = node.parentElement;
    }
    if (target) { target.style.display = 'none'; n++; }
  }
  document.documentElement.style.overflow = '';
  document.body.style.overflow = '';
  return n;
};

let ok = 0; const bad = [];
for (let i = 0; i < accounts.length; i++) {
  const a = accounts[i];
  const page = pages.get(a.profile);
  if (!page) { bad.push(a.nickname); continue; }
  try {
    if (ACTIVATE) await page.bringToFront().catch(() => {});
    await new Promise(r => setTimeout(r, 1200));
    await page.evaluate(killOverlay).catch(() => {});
    let txt = await page.evaluate(() => document.body.innerText).catch(() => '');
    if (/服务异常/.test(txt)) {
      await page.reload({ waitUntil: 'domcontentloaded', timeout: 50000 }).catch(() => {});
      await new Promise(r => setTimeout(r, 3500));
      await page.evaluate(killOverlay).catch(() => {});
      txt = await page.evaluate(() => document.body.innerText).catch(() => '');
    }
    if (/服务异常|用户不存在/.test(txt)) { bad.push(a.nickname); }
    else { ok++; }
  } catch { bad.push(a.nickname); }
}

// 5) 回到第一个标签
if (ACTIVATE && accounts[0]) await pages.get(accounts[0].profile)?.bringToFront().catch(() => {});

const infos = (await cdp.send('Target.getTargets')).targetInfos.filter(t => t.type === 'page');
const wins = new Set();
for (const t of infos) {
  try { const r = await cdp.send('Browser.getWindowForTarget', { targetId: t.targetId }); wins.add(r.windowId); } catch {}
}
console.log(`\n== 完成 == 标签页 ${infos.length} 个，窗口 ${wins.size} 个，正常 ${ok}/${accounts.length}`);
if (bad.length) console.log('需人工看一眼:', bad.join(' | '));
await browser.close();
