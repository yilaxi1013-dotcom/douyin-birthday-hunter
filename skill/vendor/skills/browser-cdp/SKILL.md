---
name: browser-cdp
description: 用 playwright-core + CDP 接管本机 Edge/Chrome 的浏览器会话，做打开页面、读正文、点击、填表、截图等操作。当需要驱动浏览器操作网页（登录后的页面、后台系统、表单提交）时使用。
---

# 浏览器驱动（CDP 接管）

本目录仅包含说明文档；可执行脚本与依赖见所属技能包的 `vendor/scripts/` 与 `vendor/node_modules/`。

## 依赖

- `playwright-core`（Node 包，随技能包提供）
- 本机已安装的 Edge 或 Chrome

## 接管步骤

1. **确认浏览器可被调试**。访问 `http://127.0.0.1:9222/json/version`，有 JSON 返回即已就绪。

2. **若未就绪，启动一个带调试端口的实例**：

```bash
node launch_browser.mjs --config <工作目录>/config.json
```

注意：Edge/Chrome 136+ 拒绝对**默认用户目录**开启调试端口（进程会直接退出）。必须使用独立 profile 目录；如需保留登录态，可在首次启动前把默认 profile 的以下文件复制进去：

```
Local State
Default/Network/Cookies
Default/Preferences
```

3. **后台常驻**。启动脚本要以后台任务方式运行并保持存活，否则浏览器进程会随父进程结束被回收。

## 常用操作（Playwright over CDP）

```js
import { chromium } from 'playwright-core';
const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
const ctx = browser.contexts()[0];
const page = ctx.pages()[0] || await ctx.newPage();

await page.goto('https://example.com', { waitUntil: 'domcontentloaded' });
console.log(await page.title());
await page.screenshot({ path: 'shot.png' });
await browser.close();   // 只断开连接，不关闭用户浏览器
```

| 目的 | 写法 |
|---|---|
| 列出标签页 | `ctx.pages()` |
| 新开标签 | `ctx.newPage()` |
| 新开独立窗口 | CDP `Target.createTarget({ newWindow: true, url })` |
| 读正文 | `page.evaluate(() => document.body.innerText)` |
| 点击 | `page.getByText('登录').click()` 或 `page.click(css)` |
| 填表 | `page.fill(selector, value)` |
| 截图 | `page.screenshot({ path })` |

## 注意事项

- 通过 `connectOverCDP` 连接的浏览器，`browser.close()` 只断开连接，不会关闭用户窗口。
- 环境变量里若有 `http_proxy` 指向本地代理，会拦截到 `127.0.0.1` 的请求导致连接失败；调用前应清空代理变量并设置 `NO_PROXY=127.0.0.1,localhost`。
- 页面崩溃或标签过多时优先「逐个激活」而不是并发打开，减少触发平台风控。
- 自动化操作应遵守目标站点服务条款，仅用于合法用途。
