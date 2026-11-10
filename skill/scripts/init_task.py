#!/usr/bin/env python3
"""初始化抖音同生日采集任务：解析日期 -> 生成 config.json（含全部匹配正则）。

用法：
    python init_task.py --date 1999-12-03 --out <工作目录>
    python init_task.py --date "99年12月3" --out <工作目录> --keywords "同年同月同日生,99年包厢"
"""
import argparse
import json
import os
import re
import sys

DATE_RE = [
    re.compile(r"^\s*(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*[日号]?\s*$"),
    re.compile(r"^\s*(\d{4})(\d{2})(\d{2})\s*$"),
    re.compile(r"^\s*(\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*[日号]?\s*$"),
    re.compile(r"^\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*[日号]?\s*$"),
]


def parse_date(text):
    """返回 (year|None, month, day)。两位年份按 19xx/20xx 推断：<= 当前两位年份视为 2000+。"""
    s = text.strip()
    for i, rx in enumerate(DATE_RE):
        m = rx.match(s)
        if not m:
            continue
        g = m.groups()
        if i == 3:  # 只有月日
            return None, int(g[0]), int(g[1])
        if i == 0 or i == 1:
            return int(g[0]), int(g[1]), int(g[2])
        # 两位年份
        yy = int(g[0])
        year = 2000 + yy if yy <= 30 else 1900 + yy
        return year, int(g[1]), int(g[2])
    raise SystemExit(f"无法解析日期：{text!r}（示例：1999-12-03 / 99年12月3 / 12月3日）")


def build_patterns(y, m, d):
    """生成同时兼容 Python re 与 JS RegExp 的正则（只用定长 lookbehind）。"""
    y4 = str(y)
    y2 = f"{y % 100:02d}"
    y2n = str(y % 100)
    m2, mn = f"{m:02d}", str(m)
    d2, dn = f"{d:02d}", str(d)
    def alt(*vals):
        """去重后拼成 a|b|c，避免月份/日期两位数时出现 12|12 这种重复分支。"""
        out = []
        for v in vals:
            if v not in out:
                out.append(v)
        return "|".join(out)

    year_alt = alt(y4, y2, y2n)
    month_alt = alt(m2, mn)
    day_alt = alt(d2, dn)

    return {
        # 连写：八位 / 六位（如 19991203 / 991203）
        "compact4": rf"(?<!\d)({y4}{m2}{d2})(?!\d)",
        "compact2": rf"(?<!\d)({y2}{m2}{d2})(?!\d)",
        # 分隔符：点 / 横线 / 斜杠（如 99.12.03）
        "dotted": rf"(?<![\d.])({year_alt})[.\-/]({month_alt})[.\-/]({day_alt})(?![\d.])",
        # 文字：中文年月日（如 99年12月3 / 1999年12月3日）
        "cn_ymd": rf"(?<!\d)({year_alt})\s*年[^\n]{{0,12}}?({month_alt})\s*月\s*({day_alt})\s*[日号]?",
        # 年+数字月日（如 99年 12.03）
        "year_join_md": rf"(?<!\d)({year_alt})\s*年?\s*[^\n]{{0,4}}?({month_alt})\s*[月.\-/]\s*({day_alt})(?![\d.])",
        # 月日在前、年份在后
        "md_join_year": rf"({month_alt})\s*[月.\-/]\s*({day_alt})\s*[日号]?[^\n]{{0,8}}?({year_alt})\s*年",
        # 只有月日，用于宽口径统计（默认不计入主表）
        "bare_md": rf"(?<!\d)({m2}{d2}|{m2}[.\-/]{d2})(?!\d)",
        "bare_cn_md": rf"({month_alt})\s*月\s*({day_alt})\s*[日号]",
        # 锚点楼层：年份 + 集合 / 包厢 / 报到的来
        "anchor_year": rf"(?<!\d)({year_alt})\s*年[^\n]{{0,20}}?(集合|包厢|来这|来此地|报道|报到|集合啦|同年的来|的来|加个微信)",
        # 锚点楼层：年份 + 月份
        "anchor_month": rf"(?<!\d)({year_alt})\s*年[^\n]{{0,12}}({month_alt})\s*月",
        "lunar": r"农历|阴历|旧历|老历",
    }


def default_keywords(y, m, d):
    y2 = f"{y % 100:02d}"
    m2, mn = f"{m:02d}", str(m)
    d2, dn = f"{d:02d}", str(d)
    return [
        f"{y2}年{mn}月{dn}日",
        f"{y2}年{mn}月",
        f"{y2}年集合",
        f"{y2}年包厢",
        "同年同月同日生",
        "同一天生日的人",
        f"{mn}月{dn}日生日",
        "同生日集合",
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="出生日期，如 1999-12-03")
    ap.add_argument("--out", required=True, help="工作目录")
    ap.add_argument("--keywords", default="", help="搜索关键词，逗号分隔；留空用默认组合")
    ap.add_argument("--year", type=int, default=None, help="只给月日时补充年份")
    ap.add_argument("--top", type=int, default=12, help="深度采集的视频数")
    ap.add_argument("--cap", type=int, default=40000, help="每个视频最多拉多少条评论")
    args = ap.parse_args()

    year, month, day = parse_date(args.date)
    if year is None:
        if args.year is None:
            raise SystemExit("日期缺年份，请补 --year 1999 或直接给完整日期")
        year = args.year

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    kws = [k.strip() for k in args.keywords.split(",") if k.strip()] or default_keywords(year, month, day)

    cfg = {
        "date": {
            "year": year, "month": month, "day": day,
            "label": f"{year:04d}-{month:02d}-{day:02d}",
            "y2": f"{year % 100:02d}", "m2": f"{month:02d}", "d2": f"{day:02d}",
        },
        "keywords": kws,
        "patterns": build_patterns(year, month, day),
        "limits": {
            "top_videos": args.top,
            "max_comments_per_video": args.cap,
            "max_replies_per_anchor": 2000,
            "concurrency": 8,
        },
        "paths": {
            "work_dir": out,
            "videos": os.path.join(out, "videos.jsonl"),
            "comments": os.path.join(out, "comments.jsonl"),
            "accounts": os.path.join(out, "accounts.json"),
            "report": os.path.join(out, "report.txt"),
            "profile": os.path.join(out, "edge-profile"),
            "cdp": "http://127.0.0.1:9222",
        },
    }

    cfg_path = os.path.join(out, "config.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "config": cfg_path,
        "date": cfg["date"]["label"],
        "keywords": kws,
        "patterns": len(cfg["patterns"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
