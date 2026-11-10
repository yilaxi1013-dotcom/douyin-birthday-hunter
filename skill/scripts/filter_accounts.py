#!/usr/bin/env python3
"""对采集到的评论做判定、去重、过滤，产出 accounts.json + report.txt。

用法：python filter_accounts.py --config <work>/config.json [--include-bare]
"""
import argparse
import json
import os
import re
from collections import Counter

BASIS_ORDER = ["compact4", "compact2", "dotted", "cn_ymd", "year_join_md", "md_join_year"]
BASIS_LABEL = {
    "compact4": "八位连写",
    "compact2": "六位连写",
    "dotted": "分隔符写法",
    "cn_ymd": "年月日文字",
    "year_join_md": "年+月日",
    "md_join_year": "月日+年",
    "anchor": "锚点楼确认",
    "bare": "仅月日（存疑）",
}


def iter_comments(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--include-bare", action="store_true", help="把「只写月日」的存疑结果也并入主表")
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    P = {k: re.compile(v) for k, v in cfg["patterns"].items()}
    label = cfg["date"]["label"]

    direct_re = [P[k] for k in BASIS_ORDER]
    anchor_re = re.compile(cfg["patterns"]["anchor_year"] + "|" + cfg["patterns"]["anchor_month"])
    bare_re = P["bare_md"]
    lunar_re = P["lunar"]

    hits, bare_candidates = [], []
    total, lunar_dropped = 0, 0

    for c in iter_comments(cfg["paths"]["comments"]):
        total += 1
        text = (c.get("text") or "").strip()
        if not text:
            continue

        basis = next((k for k in BASIS_ORDER if P[k].search(text)), None)
        if basis is None and c.get("is_reply"):
            parent = c.get("parent_text") or ""
            if anchor_re.search(parent) and (bare_re.search(text) or P["bare_cn_md"].search(text)):
                basis = "anchor"

        if basis is None:
            if bare_re.search(text) or P["bare_cn_md"].search(text):
                bare_candidates.append(c)
            continue

        if lunar_re.search(text):
            lunar_dropped += 1
            continue

        hits.append({
            "cid": c.get("cid"),
            "nickname": (c.get("nickname") or "").strip(),
            "douyin_id": c.get("unique_id") or c.get("douyin_id") or "",
            "sec_uid": c.get("sec_uid") or "",
            "text": text,
            "basis": BASIS_LABEL.get(basis, basis),
            "parent": (c.get("parent_text") or "")[:40] if c.get("is_reply") else "",
            "pos": c.get("pos"),
            "digg": c.get("digg") or 0,
            "video": c.get("video") or "",
            "video_author": c.get("video_author") or "",
            "video_desc": c.get("video_desc") or "",
        })

    # 去重：同一 cid 只留一条；同人同文本只留一条
    seen_cid, seen_kv, merged = set(), set(), []
    for h in hits:
        if h["cid"] in seen_cid:
            continue
        key = (h["nickname"].lower(), h["text"].strip().lower())
        if key in seen_kv:
            continue
        seen_cid.add(h["cid"])
        seen_kv.add(key)
        if h["sec_uid"]:
            h["profile"] = f"https://www.douyin.com/user/{h['sec_uid']}"
        else:
            h["profile"] = ""
        merged.append(h)

    merged.sort(key=lambda x: (-(x["digg"] or 0), x["pos"] or 0))
    for i, h in enumerate(merged, 1):
        h["no"] = i

    if args.include_bare:
        for c in bare_candidates:
            key = ((c.get("nickname") or "").lower(), (c.get("text") or "").strip().lower())
            if key in seen_kv:
                continue
            seen_kv.add(key)
            merged.append({
                "no": len(merged) + 1,
                "cid": c.get("cid"),
                "nickname": (c.get("nickname") or "").strip(),
                "douyin_id": c.get("unique_id") or "",
                "sec_uid": c.get("sec_uid") or "",
                "profile": f"https://www.douyin.com/user/{c['sec_uid']}" if c.get("sec_uid") else "",
                "text": c.get("text") or "",
                "basis": BASIS_LABEL["bare"],
                "parent": "", "pos": c.get("pos"), "digg": c.get("digg") or 0,
                "video": c.get("video") or "", "video_author": "", "video_desc": "",
            })

    json.dump(merged, open(cfg["paths"]["accounts"], "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 统计
    by_basis = Counter(h["basis"] for h in merged)
    by_video = Counter((h["video_desc"] or h["video"])[:36] or "-" for h in merged)
    lines = [
        f"# 采集报告 {label}",
        "",
        f"扫描评论总数：{total}",
        f"确认命中：{len(merged)} 个账号",
        f"存疑（只写月日、无年份）：{len(bare_candidates)} 条{'（已并入主表）' if args.include_bare else '（未计入主表）'}",
        f"农历口径剔除：{lunar_dropped} 条",
        "",
        "## 命中依据分布",
    ]
    for k, v in by_basis.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 来源视频分布"]
    for k, v in by_video.most_common():
        lines.append(f"- {k}: {v}")
    report = "\n".join(lines)
    open(cfg["paths"]["report"], "w", encoding="utf-8").write(report + "\n")

    print(report)
    print("\naccounts.json ->", cfg["paths"]["accounts"])


if __name__ == "__main__":
    main()
