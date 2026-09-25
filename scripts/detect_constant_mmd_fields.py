#!/usr/bin/env python3
"""检测「用序列最新状态标注历史信号」类缺陷 —— 一次性巡检脚本（不入库）。

原理：若某条件字段对**同一标的的所有信号**取恒定值，说明它与信号自身无关
（典型成因：用 closes[-1] / highs[-20:] 等「序列末尾」状态标注每一个历史
信号，或引用了未来信息）。这类字段既无区分度，又常是未来函数。

用法：.venv/bin/python scripts/detect_constant_mmd_fields.py [--pool N]
输出：每个字段的「恒定的标的数 / 有信号标的数」，恒定比例高即疑似缺陷。
"""

from __future__ import annotations

import argparse
import json
import urllib.request

API = "http://127.0.0.1:8000/api/v1/chanlun/analyze"

# 与 verify.VERIFY_POOL 一致的 20 只龙头
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", type=int, default=10, help="检测多少只标的")
    args = ap.parse_args()

    stat: dict[str, list[int]] = {}  # field -> [恒定标的数, 有信号标的数]
    for market, code in POOL[: args.pool]:
        d = analyze(market, code)
        if not d or not d.get("mmds"):
            continue
        for f in d["mmds"][0]:
            if f in ("type", "date", "bar_index", "anchor_val", "msg"):
                continue  # 天然逐信号不同
            vals = [
                json.dumps(m.get(f), sort_keys=True, default=str)
                for m in d["mmds"]
                if m.get(f) is not None
            ]
            if len(vals) < 3:
                continue
            stat.setdefault(f, [0, 0])
            stat[f][1] += 1
            if len(set(vals)) == 1:
                stat[f][0] += 1

    print(f"巡检标的数={args.pool}（恒定标的数 / 有信号标的数）")
    print("-" * 62)
    suspicious = []
    for f, (c, t) in sorted(stat.items(), key=lambda kv: -kv[1][0] / max(kv[1][1], 1)):
        ratio = c / t if t else 0
        flag = "⚠️ 疑似缺陷" if ratio >= 0.8 else ("部分恒定" if ratio > 0 else "ok")
        if ratio >= 0.8:
            suspicious.append(f)
        print(f"  {f:32s} {c:>2}/{t:<2} ({ratio:5.0%})  {flag}")
    print("-" * 62)
    if suspicious:
        print("疑似缺陷字段：", ", ".join(suspicious))
        print("→ 逐一确认语义：若本应逐信号不同，则是「用最新状态标注历史信号」"
              "或未来函数，参照 V730 对条件205/248/249 的修复方式处理。")
    else:
        print("✅ 未发现恒定字段")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
