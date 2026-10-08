#!/usr/bin/env python3
"""覆盖率差距报告——把「测了什么/哪里薄」从一次性分析变成可复用机制。

读 pytest --cov 的 JSON 报告（先跑：pytest tests/unit --cov=src/easy_tdx
--cov-report=json:/tmp/cov.json -q），按模块聚合覆盖率并列出最低的 N 个，
供 openspec 任务 2.5「定位剩余低覆盖模块」与 4.5 门禁复跑使用。

用法：pytest tests/unit -q --cov=src/easy_tdx --cov-report=json:/tmp/cov.json
      .venv/bin/python scripts/coverage_gaps.py /tmp/cov.json [--top 15]
"""
from __future__ import annotations
import argparse, json

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report", nargs="?", default="/tmp/cov.json")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()
    try:
        data = json.load(open(args.report, encoding="utf-8"))
    except FileNotFoundError:
        print(f"未找到 {args.report}——先跑 pytest --cov-report=json:{args.report}")
        return 2
    files = data.get("files", {})
    rows = []
    for path, info in files.items():
        s = info.get("summary", {})
        if s.get("num_statements", 0) < 20:  # 忽略过小的文件
            continue
        rows.append((s.get("percent_covered", 0.0), path, s.get("num_statements", 0)))
    rows.sort()
    total = data.get("totals", {}).get("percent_covered", 0.0)
    print(f"总覆盖率: {total:.1f}%（门槛 70）  文件数: {len(rows)}\n")
    print(f"最低 {args.top} 个模块（≥20 语句）:")
    for pct, path, ns in rows[: args.top]:
        print(f"  {pct:5.1f}%  {ns:5d}语句  {path}")
    below = [r for r in rows if r[0] < 70.0]
    print(f"\n低于 70% 的模块数: {len(below)}/{len(rows)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
