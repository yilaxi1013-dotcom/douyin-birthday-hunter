# 抖音 Web 接口说明（评论 / 回复 / 搜索）

> 仅用于采集用户自己公开发布的评论信息。接口可能随时变化，失效时按下方「重新捕获」流程处理。

## 1. 评论列表

```
GET https://www.douyin.com/aweme/v1/web/comment/list/
```

关键参数：

| 参数 | 说明 |
|---|---|
| `aweme_id` | 视频 ID，换视频只改这个 |
| `cursor` | 偏移量，每页步长 = `count`（一般 20） |
| `count` | 每页条数，最大实测 20 |
| `item_id` | 与 aweme_id 相同，可保留 |
| `a_bogus` / `msToken` | 签名参数，**重放时不需要重新计算** |

返回：`status_code=0` 表示成功，`comments[]` 为评论数组，`total` 为总条数，`has_more` 表示是否还有。

字段：`cid`、`text`、`digg_count`、`reply_comment_total`、`create_time`、`user.{nickname,sec_uid,unique_id,douyin_id}`。

## 2. 回复列表

```
GET https://www.douyin.com/aweme/v1/web/comment/list/reply/
```

参数在评论列表基础上：

- 路径把 `/comment/list/` 换成 `/comment/list/reply/`
- 增加 `comment_id`（父评论 cid）
- **删除** `item_id`、`whale_cut_token`、`cut_version`、`rcFT`（这几个会导致返回空）

返回结构同上，`comments[]` 即该楼回复。

## 3. 搜索

```
GET https://www.douyin.com/aweme/v1/web/general/search/single/
```

不是 `search/item`。拦截该接口响应即可拿到 `data[].aweme_info`（含 `aweme_id`、`desc`、`statistics.comment_count`）。
搜索页需要滚动才会持续加载，脚本里滚动 2 轮即可拿到足够候选。

## 重放方法（为什么快）

正常抓取要模拟滚动、等懒加载，单视频 3000 条要一小时。
实测：把一条真实请求 URL 拿到手后，在**页面上下文**里直接 `fetch`，只改 `aweme_id` 和 `cursor`，服务端照常返回 —— 签名参数不校验 query 变化。

于是可以 8 路并发、每路 20 条，单视频 7 万条约 3–5 分钟，比滚动快 50 倍以上。

```js
await page.evaluate(async ({ url0, awemeId, cursor }) => {
  const [base, qs] = url0.split('?');
  const P = new URLSearchParams(qs);
  P.set('aweme_id', awemeId); P.set('cursor', cursor); P.set('count', '20');
  const j = await (await fetch(base + '?' + P.toString(), { credentials: 'include' })).json();
  return j.comments;
}, { url0: template, awemeId, cursor: 40 });
```

## 重新捕获模板

接口或参数变化导致 404/空返回时：

1. 打开任意有评论的视频页
2. 监听 `page.on('request')`，匹配 `/comment\/list\/\?/`
3. 滚动触发评论加载，取第一条命中的 URL 作为模板

`pull_comments.mjs` 的 `grabTemplate()` 就是这个流程。

## 限流表现

- 连续拉取约 7–8 万条后，返回 `status_code != 0`（常见 `status_code=2154` 或空 body）
- 处理：立即停止该视频，间隔 1–2 分钟再换下一个视频；不要原地重试
- 并发开 20+ 个**主页**（不是接口）会触发页面级「服务异常，重新刷新拉取数据」，刷新即可恢复
