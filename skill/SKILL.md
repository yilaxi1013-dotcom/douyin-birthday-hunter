---
name: douyin-birthday-hunter
description: 抖音「同一天生日」账号批量采集工作台。当用户给出一个生辰日期（如 1999-12-03、99年12月3日、12月3日生日），要求在抖音上找出同一天出生的人、收集其抖音号或主页时使用。流程：搜索同生日合集视频 → 评论接口并发拉取 → 识别「同年级包厢/集合」锚点楼并拉回复 → 按「年份+月日」判定去重 → 输出横版 A4 表格 → 询问用户是否需要把主页在浏览器打开。
agent_created: true
---

# 抖音同生日账号采集

## 免责声明（使用前必读）

本技能仅用于对**公开可见信息**的技术性整理，不提供任何账号破解、私信获取或非公开数据抓取能力。

1. 采集对象限于用户在公开评论区**主动发布**的内容，属用户自行公开的信息。
2. 使用者须自行确保用途合法合规，遵守《中华人民共和国网络安全法》《个人信息保护法》《数据安全法》及抖音平台用户协议等相关规定。
3. **严禁**将结果用于骚扰、跟踪、营销骚扰、诈骗、人肉搜索或任何侵害他人权益的行为。
4. 作者仅提供技术方法，**不对使用者的使用行为及由此产生的任何后果承担法律责任**；因使用本技能引发的纠纷、处罚或损失，由使用者自行承担。
5. 采集结果应仅用于正当目的，使用完毕后建议及时删除相关数据，不得擅自公开、转卖或与他人共享。
6. 若权利人提出异议，应立即停止使用并删除相关数据。

继续使用即视为已阅读并同意上述条款。

## 用途

用户给一个生日，产出「当天出生的抖音账号名单」。适用于：找同生日的人、找同年同月同日生的群体、按生日做人群筛选。

## 输入

必填：**出生日期**。接受 `1999-12-03` / `1999.12.03` / `99年12月3` / `1999年12月3日` / `12月3日`。
只给月日时先向用户确认年份——年份决定匹配口径，不能猜。
选填：输出目录、采集上限、是否输出「只写月日」的宽口径结果（默认不含）。

## 执行流程

建议把工作目录放在临时区（如系统临时目录或用户指定目录），命名为 `dy_hunt_<日期>`；中间产物全部放这里，最终表格由用户指定保存位置。下文用 `<SKILL_DIR>` 指代本技能所在目录，`<WORK>` 指代工作目录，`<PY>` 指代当前环境中已安装 `python-docx` 的 Python 解释器。

### 第 -1 步：环境自检与依赖自举（新用户首次使用必做）

先跑自检，它会逐项检查 Python、Node、npm、浏览器与 `playwright-core`：

```bash
"<PY>" "<SKILL_DIR>/scripts/check_env.py"
```

- 若提示 Python 包缺失，可加 `--fix` 自动执行 `pip install python-docx openpyxl`。
- 若提示 `playwright-core` 缺失（使用者没有预装浏览器操控依赖），执行：

```bash
node "<SKILL_DIR>/vendor/scripts/setup_deps.mjs"
```

该脚本按**三级策略**补齐依赖，可直接执行，无需人工判断：

| 顺序 | 方式 | 说明 |
|---|---|---|
| 1 | 使用随包自带 | `vendor/node_modules/playwright-core` 已随压缩包提供，通常无需联网 |
| 2 | npm 安装 | `npm install playwright-core@^1.65.0`（官方源） |
| 3 | 从 GitHub 获取 | npm 不可用或被墙时，克隆 `https://github.com/microsoft/playwright` 并构建，将 `packages/playwright-core` 复制到 `vendor/node_modules/`（耗时数分钟） |

若 Node / npm / git 都不可用，按脚本输出提示先安装 Node.js 18+（`https://nodejs.org`），再重跑；极端情况下可手动把任意来源的 `playwright-core` 目录放入 `vendor/node_modules/`，脚本的 `--check` 会验证是否可用。

自检全部通过（最后一行显示「全部就绪」）后再进入下一步。**不要跳过自检直接开抓**，否则会在第 1 步因缺少依赖反复失败。

### 第 0 步：初始化任务

```bash
"<PY>" "<SKILL_DIR>/scripts/init_task.py" --date "1999-12-03" --out "<WORK>"
```

生成 `config.json`（年/月/日、搜索关键词、全部匹配正则）。后续脚本一律读这个文件，**不要手写日期正则**。

### 第 1 步：启动可调试浏览器

```bash
node "<SKILL_DIR>/vendor/scripts/launch_browser.mjs" --config "<WORK>/config.json"
```

要点：
- Edge/Chrome 136+ **不允许用默认用户目录开调试端口**（会直接退出），必须用独立 profile。脚本首次运行会把默认 profile 的 `Local State` + `Default/Network/Cookies` 复制到 `<WORK>/edge-profile`，从而带上登录态。
- 必须以**后台常驻任务**启动（`run_in_background: true`），否则浏览器进程会被会话回收。
- 若 `http://127.0.0.1:9222/json/version` 已有响应，说明浏览器已在跑，跳过本步。
- 脚本默认给浏览器加 `--no-proxy-server`：**系统代理常把抖音拦成 502**。若所在网络确实需要代理，改用 `--proxy http://host:port`。

### 第 2 步：搜索生日合集视频

```bash
node "<SKILL_DIR>/vendor/scripts/search_videos.mjs" --config "<WORK>/config.json"
```

拦截 `aweme/v1/web/general/search/single/` 响应收集视频（`aweme_id` / 描述 / 评论数），按评论数排序写入 `videos.jsonl`。
大评论区视频是主矿，「同年级集合 / 同年级包厢」这类合集视频是关键入口。

**搜索被验证码拦住时**（未登录或访问过频，脚本会以退出码 4 提示）：
1. 在弹出的浏览器窗口里手动完成验证或登录抖音，然后重跑本步；
2. 或跳过搜索，直接把已知视频链接交给下一步：

```bash
node "<SKILL_DIR>/vendor/scripts/pull_comments.mjs" --config "<WORK>/config.json" \
  --videos "https://www.douyin.com/video/<id1>,https://www.douyin.com/video/<id2>"
```

### 第 3 步：批量拉评论 + 锚点楼回复

```bash
node "<SKILL_DIR>/vendor/scripts/pull_comments.mjs" --config "<WORK>/config.json" --top 12 --cap 40000
```

- 先捕获一条真实评论请求作模板，之后在页面内 `fetch` 改 `aweme_id` / `cursor` 并发翻页（8 路 × 20 条/批）。实测服务端不校验签名参数。
- 主评论写入 `comments.jsonl`；同时识别锚点楼层（「<年份>年集合 / 包厢」等）。
- 对回复数 ≥2 的锚点楼层调 `/comment/list/reply/` 拉全回复，写入同一文件并标记 `parent_cid`。

### 第 4 步：判定、去重、过滤

```bash
"<PY>" "<SKILL_DIR>/scripts/filter_accounts.py" --config "<WORK>/config.json"
```

规则（详见 `references/matching-rules.md`）：
- **只认「年份+月日」同时出现**：`991203`、`99.12.03`、`99年12月3`、`1999 12.03`、`99/12/03`。
- 在「99年12月」锚点楼下回复 `12.3`、`1203` 的，按上下文命中计入，依据标注为「锚点确认」。
- 含「农历 / 阴历 / 旧历」的命中剔除（农历与公历不是同一天）。
- 同一人多条命中按 `cid` + `文本+昵称` 去重。

产出 `accounts.json`（结构化名单）与 `report.txt`（命中分布、剔除原因统计）。

### 第 5 步：生成表格

```bash
"<PY>" "<SKILL_DIR>/scripts/build_docx.py" --config "<WORK>/config.json" --out "<用户指定路径>/<日期>生日_抖音账号汇总.docx"
```

输出**横版 A4** Word：封面 → 结论摘要 → 账号明细表（序号/昵称/抖音号/评论原文/评论位置/点赞/来源视频）→ 主页链接表 → 采集方法说明 → 免责声明。
表头跨页重复，两个表各自另起一页，列宽按内容分配。需要 Excel 时加 `--xlsx`。

### 第 6 步：交付 + 必须询问

先用 `present_files` 交付表格，然后在回复里**明确问用户**：

> 需不需要我把这 N 个主页在浏览器里打开？（一个窗口、N 个标签页、按表格序号排列）

用户同意后才执行：

```bash
node "<SKILL_DIR>/vendor/scripts/open_profiles.mjs" --config "<WORK>/config.json"
```

脚本会：关掉散窗 → 单窗口建标签页 → 逐个激活渲染并清除登录弹窗 → 把标签标题改成「序号 昵称」。

**不要跳过询问直接开页面**——几十个标签页占内存，且属于用户可视行为，必须先确认。

## 交付内容

| 文件 | 说明 |
|---|---|
| `<用户指定路径>/<日期>生日_抖音账号汇总.docx` | 主交付物，横版 A4 表格 |
| `<WORK>/accounts.json` | 结构化名单（含 sec_uid / 抖音号 / 命中依据） |
| `<WORK>/comments.jsonl` | 全量评论原始数据，便于复核 |
| `<WORK>/report.txt` | 命中与剔除统计 |

## 判定口径速查

| 写法 | 是否计入 | 说明 |
|---|---|---|
| `991203` / `19991203` | 是 | 六位/八位连写，最高置信 |
| `99.12.03` / `99-12-03` / `99/12/03` | 是 | 分隔符写法 |
| `99年12月3` / `1999年12月3日` | 是 | 文字写法 |
| `1999 12.03` / `12.03 1999` | 是 | 年份与月日分离 |
| 锚点楼下回 `12.3` / `1203` | 是（标注依据） | 上下文推定，注明来源楼层 |
| 只写 `1203` / `12月3日` 无年份 | 否 | 存疑，单独统计，不混入主表 |
| 含「农历」 | 否 | 农历与公历不同日 |

## 注意事项

- 单账号连续拉取超过约 8 万条会限流（返回 `status_code != 0`）。脚本内置 `blocked` 检测，触发即停该视频、换下一个。
- 并发开 20+ 个主页会触发「服务异常，重新刷新」，`open_profiles.mjs` 已做逐个激活 + 重试。
- 评论区位置（第 N 条）是**采集时刻**热门排序快照，会随时间变化，表格里必须标注。
- 交付时须再次提醒用户：结果来自公开评论区，仅用于正当用途，互动注意礼貌与隐私，用后及时删除。

## 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 页面显示 `502 Bad Gateway` | 浏览器继承了系统代理 | 用 `--no-proxy-server` 重启浏览器；确需代理则 `--proxy <地址>` |
| 搜索页是「验证码中间页」 | 未登录或访问过频 | 在窗口里手动完成验证/登录后重跑；或改用 `--videos` 指定视频 |
| 评论接口 `status_code != 0` | 单账号拉太多被限流 | 停该视频换下一个，隔时间再补 |
| 主页显示「用户不存在」 | 账号注销或改名 | 表格里标注，不重试 |
| 主页「服务异常，重新刷新」 | 并发打开过多 | `open_profiles.mjs` 会逐个激活并自动刷新 |
| 自检提示缺 playwright-core | 解压时未带 `vendor/node_modules` | 跑 `vendor/scripts/setup_deps.mjs` |

## 依赖

- Python：`python-docx`（必需）、`openpyxl`（仅 `--xlsx` 时需要）
- Node：`playwright-core`（已随 `vendor/` 打包，无需联网安装）
- 浏览器：本机 Edge 或 Chrome，已登录抖音（仅影响能否看到完整主页）

## 参考文档

- `references/matching-rules.md` — 日期写法全集与正则设计
- `references/douyin-api.md` — 评论/回复/搜索接口参数与重放方法
- `references/pitfalls.md` — 环境与反爬踩坑记录
- `references/REPORT.md` — 本技能制作说明（用了什么、写了什么）
