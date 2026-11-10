#!/usr/bin/env python3
"""环境自检：检查运行本技能所需的 Python / Node / 浏览器 / 依赖。

用法：
    python check_env.py            # 只检查
    python check_env.py --fix      # 缺 Python 依赖时自动 pip 安装
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(SKILL_DIR, "vendor")
PW = os.path.join(VENDOR, "node_modules", "playwright-core", "package.json")


def run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:
        return 1, "", str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="缺 Python 依赖时自动安装")
    args = ap.parse_args()

    rows = []
    blocking = []

    # Python
    rows.append(("Python", f"{sys.version.split()[0]}  {sys.executable}", True, ""))

    # Python 依赖
    for mod, pkg, required in [("docx", "python-docx", True), ("openpyxl", "openpyxl", False)]:
        try:
            __import__(mod)
            rows.append((f"Python 包 {pkg}", "已安装", True, ""))
        except ImportError:
            if args.fix:
                code, out, err = run([sys.executable, "-m", "pip", "install", pkg], timeout=180)
                ok = code == 0
                rows.append((f"Python 包 {pkg}", "自动安装" + ("成功" if ok else "失败"), ok, "" if ok else err[:120]))
                if not ok and required:
                    blocking.append(f"pip install {pkg}")
            else:
                rows.append((f"Python 包 {pkg}", "缺失", not required,
                             f"{sys.executable} -m pip install {pkg}"))
                if required:
                    blocking.append(f"pip install {pkg}")

    # Node
    node = shutil.which("node")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if node:
        code, out, _ = run([node, "--version"])
        rows.append(("Node.js", out or "已安装", True, ""))
    else:
        rows.append(("Node.js", "未安装", False, "安装 Node.js 18+ 后重试：https://nodejs.org"))
        blocking.append("安装 Node.js")

    rows.append(("npm", "可用" if npm else "未安装", bool(npm),
                 "" if npm else "随 Node.js 一起安装"))

    # playwright-core
    if os.path.exists(PW):
        try:
            version = json.load(open(PW, encoding="utf-8")).get("version", "?")
        except Exception:
            version = "?"
        rows.append(("playwright-core", f"已随包提供 v{version}", True, ""))
    else:
        rows.append(("playwright-core", "缺失", False,
                     f'node "{os.path.join(VENDOR, "scripts", "setup_deps.mjs")}"'))
        blocking.append("补装 playwright-core")

    # 浏览器
    browsers = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    found = next((b for b in browsers if os.path.exists(b)), None)
    rows.append(("浏览器", os.path.basename(found) if found else "未找到 Edge/Chrome",
                 bool(found), "" if found else "安装 Edge 或 Chrome"))
    if not found:
        blocking.append("安装浏览器")

    # 输出
    print("环境自检")
    print("-" * 62)
    for name, value, ok, hint in rows:
        mark = "OK  " if ok else "FAIL"
        print(f"[{mark}] {name:<18} {value}")
        if hint:
            print(f"         → {hint}")
    print("-" * 62)

    if blocking:
        print("需要处理：")
        for b in blocking:
            print("  -", b)
        print("\n提示：Node 依赖缺失时，先跑 vendor/scripts/setup_deps.mjs；"
              "若 npm 不可用，按该脚本输出的 GitHub 方案处理。")
        return 1

    print("全部就绪，可以开始采集。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
