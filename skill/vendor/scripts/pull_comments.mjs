#!/usr/bin/env node
/**
 * 批量拉取抖音评论区：主评论并发翻页 + 锚点楼层（同年级集合/包厢）回复。
 *
 * 用法：node pull_comments.mjs --config <work>/config.json [--top 12] [--cap 40000]
 *
 * 原理：先捕获一条真实的 /comment/list/ 请求作为模板，之后在页面上下文里
 *      直接 fetch 并替换 aweme_id / cursor 并发翻页。实测服务端不校验签名参数，
 *      单视频 7 万条评论约 3-5 分钟。
 */
import { chromium } from 'playwright-core';
import fs from 'node:fs';

for (const k of ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'all_proxy']) delete process.env[k];
process.env.NO_PROXY = '127.0.0.1,localhost';

const args = process.argv.slice(2);
const getArg = (k, d = null) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const cfg = JSON.parse(fs.readFileSync(getArg('--config'), 'utf8'));
const TOP = Number(getArg('--top', cfg.limits.top_videos));
const CAP = Number(getArg('--cap', cfg.limits.max_comments_per_video));
const CONC = Number(cfg.limits.concurrency || 8);
const CDP = cfg.paths.cdp;

const videos = (() => {
  const manual = getArg('--videos');   // 手动指定：逗号分隔的视频链接或 ID，用于搜索被验证码拦住时的降级
  if (manual) {
    return manual.split(',').map(s => s.trim()).filter(Boolean).map(s => {
      const id = (s.match(/(\d{15,})/) || [])[1] || s;
      return { aweme_id: id, desc: '（手动指定）', author: '', comments: 0 };
    });
  }
  return fs.existsSync(cfg.paths.videos)
    ? fs.readFileSync(cfg.paths.videos, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l))
    : [];
})();
if (!videos.length) { console.error('没有可用视频：videos.jsonl 为空，也没传 --videos'); process.exit(2); }

const browser = await chromium.connectOverCDP(CDP, { timeout: 25000 });
const ctx = browser.contexts()[0];
let page = ctx.pages()[0] || await ctx.newPage();
await page.setViewportSize({ width: 1440, height: 900 });

// ---------- 1. 捕获评论请求模板 ----------
async function grabTemplate(seedVideo) {
  for (const url of [`https://www.douyin.com/video/${seedVideo}`, `https://www.douyin.com/note/${seedVideo}`]) {
    let tpl = null;
    const onReq = r => { const u = r.url(); if (!tpl && /comment\/list\/\?/.test(u) && u.includes('aweme_id=')) tpl = u; };
    page.on('request', onReq);
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 50000 });
      await page.waitForTimeout(7000);
      await page.mouse.move(1100, 450);
      await page.mouse.wheel(0, 1200);
      await page.waitForTimeout(3000);
    } catch {}
    page.off('request', onReq);
    if (tpl) return tpl;
  }
  return null;
}

const tpl = await grabTemplate(videos[0].aweme_id);
if (!tpl) { console.error('未能捕获评论请求，检查视频是否可访问 / 是否已登录'); process.exit(1); }
console.log('[template] OK');

// ---------- 2. 页面内通用翻页 ----------
async function pullComments(awemeId, cap, startCursor = 0) {
  return await page.evaluate(async ({ url0, awemeId, cap, startCursor, conc }) => {
    const [base, qs] = url0.split('?');
    const P = new URLSearchParams(qs);
    P.set('aweme_id', awemeId); P.set('cursor', String(startCursor)); P.set('count', '20');
    const all = [];
    let first;
    try { first = await (await fetch(base + '?' + P.toString(), { credentials: 'include' })).json(); }
    catch (e) { return { err: 'net' }; }
    if (first.status_code !== 0) return { err: 'sc=' + first.status_code };
    all.push(...(first.comments || []));
    const end = Math.min(first.total || 0, cap);
    let cursor = startCursor + 20, empty = 0;
    while (cursor < end && all.length < end - startCursor) {
      const batch = [];
      for (let i = 0; i < conc && cursor < end; i++, cursor += 20) {
        const P2 = new URLSearchParams(P); P2.set('cursor', String(cursor));
        batch.push(base + '?' + P2.toString());
      }
      const rs = await Promise.all(batch.map(u => fetch(u, { credentials: 'include' }).then(r => r.json()).catch(() => null)));
      let fresh = 0, blocked = 0;
      for (const j of rs) {
        if (j && j.comments) { all.push(...j.comments); fresh += j.comments.length; }
        if (j && j.status_code !== 0) blocked++;
      }
      if (blocked >= Math.ceil(batch.length * 0.75)) return { err: 'blocked', n: all.length };
      if (!fresh) { if (++empty >= 2) break; } else empty = 0;
    }
    return { n: all.length, total: first.total, all };
  }, { url0: tpl, awemeId, cap, startCursor, conc: CONC });
}

async function pullReplies(awemeId, commentId, cap) {
  return await page.evaluate(async ({ url0, awemeId, commentId, cap, conc }) => {
    const [base0, qs] = url0.split('?');
    const base = base0.replace(/\/comment\/list\/$/, '/comment/list/reply/');
    const P = new URLSearchParams(qs);
    P.set('aweme_id', awemeId); P.set('comment_id', commentId);
    P.set('cursor', '0'); P.set('count', '20');
    P.delete('item_id'); P.delete('whale_cut_token'); P.delete('cut_version'); P.delete('rcFT');
    const all = [];
    let first;
    try { first = await (await fetch(base + '?' + P.toString(), { credentials: 'include' })).json(); }
    catch (e) { return { err: 'net' }; }
    if (first.status_code !== 0) return { err: 'sc=' + first.status_code };
    all.push(...(first.comments || []));
    const total = Math.min(first.total || 0, cap);
    let cursor = 20, empty = 0;
    while (cursor < total && all.length < total) {
      const batch = [];
      for (let i = 0; i < Math.min(6, conc) && cursor < total; i++, cursor += 20) {
        const P2 = new URLSearchParams(P); P2.set('cursor', String(cursor));
        batch.push(base + '?' + P2.toString());
      }
      const rs = await Promise.all(batch.map(u => fetch(u, { credentials: 'include' }).then(r => r.json()).catch(() => null)));
      let fresh = 0;
      for (const j of rs) if (j && j.comments) { all.push(...j.comments); fresh += j.comments.length; }
      if (!fresh) { if (++empty >= 2) break; } else empty = 0;
    }
    return { n: all.length, total: first.total, all };
  }, { url0: tpl, awemeId, commentId, cap, conc: CONC });
}

// ---------- 3. 主评论 ----------
const fh = fs.createWriteStream(cfg.paths.comments, { flags: 'a' });
const anchorRe = new RegExp(cfg.patterns.anchor_year);
const anchorMonthRe = new RegExp(cfg.patterns.anchor_month);
const anchors = [];
let total = 0;

const targets = videos.slice(0, TOP);
for (let vi = 0; vi < targets.length; vi++) {
  const v = targets[vi];
  const seen = new Set();
  let pos = 0, got = 0;
  for (let start = 0; start < CAP; start += 8000) {
    const r = await pullComments(v.aweme_id, start + 8000, start);
    if (r.err === 'blocked') { console.log(`  [${vi + 1}] 触发限流，停止该视频（已取 ${got}）`); break; }
    if (r.err) { console.log(`  [${vi + 1}] ${r.err}`); break; }
    let fresh = 0;
    for (const c of (r.all || [])) {
      if (seen.has(c.cid)) continue;
      seen.add(c.cid); fresh++; pos++; got++; total++;
      const rec = {
        cid: c.cid, text: c.text, digg: c.digg_count, reply_n: c.reply_comment_total, time: c.create_time,
        nickname: c.user && c.user.nickname, sec_uid: c.user && c.user.sec_uid,
        unique_id: c.user && (c.user.unique_id || ''), douyin_id: c.user && (c.user.douyin_id || ''),
        pos, video: v.aweme_id, video_desc: (v.desc || '').slice(0, 60), video_author: v.author || '',
        is_reply: false,
      };
      fh.write(JSON.stringify(rec) + '\n');
      const isAnchor = anchorRe.test(rec.text) || anchorMonthRe.test(rec.text);
      if (isAnchor && (rec.reply_n || 0) >= 2) {
        anchors.push({ cid: rec.cid, text: rec.text.slice(0, 60), video: v.aweme_id, reply_n: rec.reply_n, digg: rec.digg });
      }
    }
    if (!fresh) break;
  }
  console.log(`  [${vi + 1}/${targets.length}] ${(v.desc || '').slice(0, 26)} | 拉取 ${got}`);
}

// ---------- 4. 锚点楼回复 ----------
console.log(`[replies] 锚点楼层 ${anchors.length} 个`);
anchors.sort((a, b) => (b.reply_n || 0) - (a.reply_n || 0));
const maxAnchors = Math.min(anchors.length, 150);
for (let i = 0; i < maxAnchors; i++) {
  const a = anchors[i];
  try {
    const r = await pullReplies(a.video, a.cid, cfg.limits.max_replies_per_anchor);
    if (r.err) continue;
    const seen = new Set();
    let pos = 0;
    for (const c of (r.all || [])) {
      if (seen.has(c.cid)) continue;
      seen.add(c.cid); pos++;
      fh.write(JSON.stringify({
        cid: c.cid, text: c.text, digg: c.digg_count, time: c.create_time,
        nickname: c.user && c.user.nickname, sec_uid: c.user && c.user.sec_uid,
        unique_id: c.user && (c.user.unique_id || ''), douyin_id: c.user && (c.user.douyin_id || ''),
        pos, video: a.video, video_desc: '', video_author: '',
        is_reply: true, parent_cid: a.cid, parent_text: a.text,
      }) + '\n');
    }
    if (i % 20 === 0) console.log(`  [${i + 1}/${maxAnchors}] 回复 ${r.n}/${r.total ?? '-'}`);
  } catch {}
}
fh.end();

console.log(`\n== 完成 == 主评论累计 ${total}，锚点 ${anchors.length}，原始数据 ${cfg.paths.comments}`);
await browser.close();
