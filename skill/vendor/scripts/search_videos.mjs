#!/usr/bin/env node
/**
 * 搜索抖音「同生日合集」类视频，按评论数排序写入 videos.jsonl。
 *
 * 用法：node search_videos.mjs --config <work>/config.json [--rounds 2]
 */
import { chromium } from 'playwright-core';
import fs from 'node:fs';

for (const k of ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'all_proxy']) delete process.env[k];
process.env.NO_PROXY = '127.0.0.1,localhost';

const args = process.argv.slice(2);
const getArg = (k, d = null) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const cfgPath = getArg('--config');
if (!cfgPath) { console.error('缺少 --config'); process.exit(2); }
const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
const rounds = Number(getArg('--rounds', 2));
const CDP = cfg.paths.cdp;

const browser = await chromium.connectOverCDP(CDP, { timeout: 25000 });
const ctx = browser.contexts()[0];
const page = ctx.pages()[0] || await ctx.newPage();
await page.setViewportSize({ width: 1440, height: 900 });

const buf = [];
page.on('response', async (res) => {
  try {
    if (!/aweme\/v1\/web\/general\/search\/(single|stream)\//.test(res.url())) return;
    if (res.request().method() !== 'GET') return;
    const j = await res.json();
    for (const item of (j.data || [])) {
      const a = item.aweme_info || {};
      if (a.aweme_id) buf.push({
        aweme_id: a.aweme_id,
        desc: (a.desc || '').slice(0, 120),
        author: a.author && a.author.nickname,
        comments: (a.stats && a.stats.comment) || 0,
        digg: (a.stats && a.stats.digg_count) || 0,
      });
    }
  } catch {}
});

console.log('[search] 关键词:', cfg.keywords.join(' / '));
for (const kw of cfg.keywords) {
  console.log('  ->', kw);
  try {
    await page.goto('https://www.douyin.com/search/' + encodeURIComponent(kw),
      { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(8000);
    const probe = await page.evaluate(() => document.body.innerText.slice(0, 120)).catch(() => '');
    if (/502|Bad Gateway|Access Denied|无法访问/.test(probe)) {
      console.error('页面被拦截：' + probe.replace(/\s+/g, ' ').slice(0, 60));
      console.error('多半是代理导致。请用 --no-proxy-server 重启浏览器，或 node launch_browser.mjs --proxy <可用代理>');
      process.exit(3);
    }
    const title = await page.title().catch(() => '');
    if (/验证码|安全验证|滑动验证|captcha/i.test(title + probe)) {
      console.error('搜索页触发验证码（未登录或访问过频）。处理方式：');
      console.error('  1) 在弹出的浏览器窗口里手动完成验证 / 登录抖音，然后重跑本步；');
      console.error('  2) 或跳过搜索，直接把已知视频链接交给 pull_comments.mjs --videos <url1,url2,...>');
      process.exit(4);
    }
    for (let i = 0; i < rounds; i++) {
      await page.mouse.move(720, 500);
      await page.mouse.wheel(0, 1500);
      await page.waitForTimeout(2600);
    }
  } catch (e) {
    console.log('    页面异常:', e.message.slice(0, 50));
  }
}

const seen = new Set();
const videos = buf.filter(v => (seen.has(v.aweme_id) ? false : (seen.add(v.aweme_id), true)));
videos.sort((a, b) => b.comments - a.comments);

fs.writeFileSync(cfg.paths.videos, videos.map(v => JSON.stringify(v)).join('\n') + '\n', 'utf8');
console.log(`\n== 收录 ${videos.length} 个视频，Top 10 ==`);
videos.slice(0, 10).forEach((v, i) => console.log(`  ${i + 1}. [评${v.comments}] ${v.author || '-'} | ${v.desc.slice(0, 40)}`));
console.log('已写入', cfg.paths.videos);
await browser.close();
