# 环境与反爬踩坑记录

## 浏览器

### 1. 默认用户目录不能开调试端口

Edge/Chrome 136+ 会直接报错退出：

```
DevTools remote debugging requires a non-default data directory.
```

**解决**：复制默认 profile 的登录凭据到独立目录再启动。

```
<默认>/Local State                    → <工作目录>/edge-profile/Local State
<默认>/Default/Network/Cookies        → <工作目录>/edge-profile/Default/Network/Cookies
<默认>/Default/Preferences            → <工作目录>/edge-profile/Default/Preferences
```

`launch_browser.mjs` 已自动完成。

### 2. 浏览器必须挂常驻进程

从工具会话里启动的 GUI 进程，会随启动它的 shell 结束被回收。表现：启动后能连上 9222，几秒后连接被拒。

**解决**：用后台任务运行 `launch_browser.mjs`（脚本内部 `setInterval` 保活），会话期间不要停它。

### 3. `--new-window` 对已运行实例无效

对已经跑着的 Edge 执行 `msedge.exe --new-window <url>`，实际只会在现有窗口开标签页。
需要真正独立窗口只能用 CDP：`Target.createTarget({ newWindow: true })`。

### 4. 一个窗口塞几十个标签页会看不清

标签宽度被压缩到只剩 favicon。两个缓解办法：

- 把 `document.title` 改成「序号 昵称」，至少能看到序号；鼠标悬停看全名
- 或用 Edge 的垂直标签页（`Ctrl+Shift+,`）在左侧竖排显示

### 5. 窗口被遮挡导致截图看不到

自动化截图经常拍到别的窗口。校验排版优先用「导出 PDF + 渲染成图」，比截屏可靠：

```python
# Word COM 导出
$doc.SaveAs2("check.pdf", 17)
# PyMuPDF 渲染
pymupdf.open("check.pdf")[i].get_pixmap(dpi=110).save("p.png")
```

## 代理

环境里常有 `http_proxy` 指向本地代理，会把到 `127.0.0.1:9222` 的请求也劫持，导致 CDP 502。

所有 node 脚本开头统一清理：

```js
for (const k of ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','all_proxy']) delete process.env[k];
process.env.NO_PROXY = '127.0.0.1,localhost';
```

**注意**：清理环境变量只能让**脚本自身**直连，浏览器是 GUI 程序，读的是 Windows 系统代理设置。
若启动后页面返回 `502 Bad Gateway`（常见响应头为 `kngx`），说明浏览器走了系统代理，用 `--no-proxy-server` 启动即可；
确需代理的环境改用 `--proxy http://host:port`。

## 验证码

搜索页在未登录或访问过频时会跳到「验证码中间页」，标题就是「验证码中间页」，正文几乎为空。
处理：让用户在可见窗口里手动完成验证/登录后重跑；或跳过搜索，用 `pull_comments.mjs --videos <链接>` 直接采集已知视频。

视频页通常不受影响，仍能正常加载与抓评论。

## 文件占用

`.docx` 被预览进程打开时无法覆盖（`WinError 5 / 32`）。定位占用者：

```python
import psutil
for p in psutil.process_iter(['pid','name']):
    for f in p.open_files():
        if '关键词' in f.path: print(p.pid, p.info['name'])
```

WPS 的后台预览进程可能**没有可见窗口**，需要 `Stop-Process -Id <pid> -Force` 结束。

## Windows 工具限制

- PowerShell 的 `Add-Type`（编译 .NET）和 WMI `Win32_Process Create` 会被安全策略拦截
- 需要枚举窗口 / 发按键时，用 Python `ctypes` 调 `user32`：`EnumWindows`、`GetWindowThreadProcessId`、`SetForegroundWindow`、`keybd_event`
- 跨盘移动文件用 `shutil.move` / 先复制再替换，`os.replace` 跨盘会报 `WinError 17`

## 抖音侧

| 现象 | 原因 | 处理 |
|---|---|---|
| 评论接口 `status_code != 0` | 拉太多被限流 | 停该视频，换下一个，别原地重试 |
| 主页「服务异常，重新刷新」 | 并发打开太多 | 逐个激活 + 刷新 |
| 主页「用户不存在」 | 账号注销/改名 | 标注出来，不重试 |
| 登录弹窗遮挡 | 未登录 | 用 JS 清除遮罩（脚本已内置），不要点登录 |
| 评论数为 0 | 评论关闭 | 跳过该视频 |
