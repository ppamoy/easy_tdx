#!/usr/bin/env python3
"""跨标的校验「高级别线段端点必须共享低级别转折点」——不变量巡检（不入库）。

缠论原文：级别递归不是对价格重新取点，而是用低级别走势（笔/线段）作为
高级别的「笔」再划分——因此高级别的每一个转折点，必须是低级别已经存在的
转折点（共享同一根K线、同一个价位）。若高级别端点凭空出现，即背离原文。

实现保证（V730 已核实）：recursive.py 把上一级 XD 原样当「笔」传入
find_xds；xd.py 的 _create_xd_from_bis 直接引用上一级 XD 的 start/end FX
对象，不重建 FX、不重算 bar_index。

本脚本在真实行情上批量复核该不变量（此前仅单票验证），用法：
    .venv/bin/python scripts/verify_level_endpoints.py [--pool N]
"""

from __future__ import annotations

import argparse
import json
import urllib.request

API = "http://127.0.0.1:8000/api/v1/chanlun/analyze"

POOL = [
    ("SH", "600519"), ("SH", "601318"), ("SH", "600036"), ("SH", "601166"),
    ("SH", "600900"), ("SH", "601899"), ("SH", "600030"), ("SH", "601012"),
    ("SH", "600276"), ("SH", "601888"), ("SZ", "000858"), ("SZ", "000333"),
    ("SZ", "000651"), ("SZ", "000001"), ("SZ", "000002"), ("SZ", "002594"),
    ("SH", "600887"), ("SH", "601668"), ("SZ", "000725"), ("SH", "600309"),
]


def analyze(market: str, code: str, count: int = 800) -> dict | None:
    payload = json.dumps(
        {"market": market, "code": code, "category": "DAY", "start": 0, "count": count}
    ).encode()
    req = urllib.request.Request(
        API, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {market}{code} 失败: {exc}")
        return None


def endpoints(items: list[dict]) -> set[tuple[float, int]]:
    """(价位, K线索引) 集合——前端即按此定位端点。"""
    out: set[tuple[float, int]] = set()
    for x in items:
        out.add((round(x["start_val"], 4), x["start_index"]))
        out.add((round(x["end_val"], 4), x["end_index"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", type=int, default=20)
    args = ap.parse_args()

    ok = bad = nolvl = 0
    for market, code in POOL[: args.pool]:
        d = analyze(market, code)
        if not d:
            continue
        lv = d.get("levels") or {}
        if "bi" not in lv or "xd" not in lv:
            nolvl += 1
            continue
        base = endpoints(lv["bi"]["xds"])
        miss: list[tuple[float, int]] = []
        for x in lv["xd"]["xds"]:
            for p in (
                (round(x["start_val"], 4), x["start_index"]),
                (round(x["end_val"], 4), x["end_index"]),
            ):
                if p not in base:
                    miss.append(p)
        if miss:
            bad += 1
            print(f"  ⚠️ {market}{code}: 高级别端点未共享 {len(miss)} 个 → {miss[:3]}")
        else:
            ok += 1

    print(f"\n跨级别端点共享校验：通过={ok}  失败={bad}  无高级别={nolvl}")
    if bad:
        print("→ 高级别端点出现「凭空」转折点，违反缠论级别递归定义，需排查")
        return 1
    print("✅ 全部标的的高级别线段端点均共享低级别转折点")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
