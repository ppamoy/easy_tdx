#!/usr/bin/env python3
"""真·区间套（nested 布尔）信号的量化回测验证 —— 一次性统计脚本（不入库）。

V-22：按《区间套现状说明与统一方案》§九迁移——分组键从 B 伪区间套评分
（v68_range_set_multi_level.multi_level_score，仅 3 类信号、单级别中枢位置）
换成**真区间套确认标签** ``mmd.qujiantao.nested``（低周期同向背驰/买卖点确认）。

数据源：/api/v1/chanlun/multi-level（日线高级别 + 30 分钟真实低周期结构，
compute_qujiantao_cross_period 逐信号确认，时间对齐 + 防未来函数）。
关闭阈值扫描：nested 是布尔，无需阈值；两组 = 确认 vs 未确认。

对照设计：
  A_nested = 区间套确认（nested=True，任意类型信号）
  B_plain  = 未确认（nested=False 或缺失）
  仍按方向分层（buy/sell），因为买卖点的前瞻收益方向相反。

⚠️ 口径注意：/chanlun/analyze（单周期）的 qujiantao 来自**递归级别**，确认率
极低（文档 §七：3%），不能用于本验证；必须走 multi-level 的跨周期口径。

用法：.venv/bin/python scripts/nesting_backtest.py [--count 800] [--horizons 5,10,20]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

# 让脚本可直接跑（无需安装）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from easy_tdx.backtest.signal_accuracy import compute_signal_accuracy_by_type  # noqa: E402

API = "http://127.0.0.1:8000/api/v1/chanlun/multi-level"

# 与 src/easy_tdx/web/routers/verify.py 的 VERIFY_POOL 一致（20 只龙头）
POOL = [
    ("SH", "600519"), ("SH", "601318"), ("SH", "600036"), ("SH", "601166"),
    ("SH", "600900"), ("SH", "601899"), ("SH", "600030"), ("SH", "601012"),
    ("SH", "600276"), ("SH", "601888"), ("SZ", "000858"), ("SZ", "000333"),
    ("SZ", "000651"), ("SZ", "000001"), ("SZ", "000002"), ("SZ", "002594"),
    ("SH", "600887"), ("SH", "601668"), ("SZ", "000725"), ("SH", "600309"),
]


def analyze_multi(market: str, code: str, count: int, low_level: str = "MIN_30") -> dict | None:
    """取高级别信号 + 真·区间套标签（/chanlun/multi-level，POST）。"""
    payload = json.dumps(
        {"market": market, "code": code, "category": "DAY", "start": 0,
         "count": count, "low_level": low_level}
    ).encode()
    req = urllib.request.Request(
        API, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {market}{code} 多级别取数失败: {exc}")
        return None


def fetch_closes(market: str, code: str, count: int) -> list[float]:
    """取高级别收盘价序列（/bars，GET，count 上限 800）。"""
    url = (
        f"http://127.0.0.1:8000/api/v1/bars?market={market}&code={code}"
        f"&category=DAY&start=0&count={min(count, 800)}"
    )
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310
            d = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {market}{code} K线取数失败: {exc}")
        return []
    return [float(b["close"]) for b in d.get("data", [])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=800, help="每只票取多少根日线")
    ap.add_argument("--horizons", type=str, default="5,10,20")
    ap.add_argument("--low-level", type=str, default="MIN_30", help="低级别周期")
    args = ap.parse_args()
    horizons = tuple(int(x) for x in args.horizons.split(","))

    per_symbol: list[tuple[str, list[float], list[dict]]] = []
    for market, code in POOL:
        d = analyze_multi(market, code, args.count, args.low_level)
        if not d:
            continue
        closes = fetch_closes(market, code, args.count)
        if not closes:
            continue
        hi = d.get("high_level", {}).get("result", {}).get("mmds", [])
        qt = d.get("qujiantao", [])
        sigs = []
        for m, q in zip(hi, qt):
            if m.get("bar_index") is None:
                continue
            # nested：True=确认 / False=明确未确认 / 缺失=算不出。
            # 全部进样本；B 组 = 非 True（含缺失），与回测过滤口径一致
            # （require_qujiantao 只放行 nested is True）。
            nested = bool(q.get("nested")) if q else False
            sigs.append(
                {
                    "type": m["type"],
                    "bar_index": int(m["bar_index"]),
                    "_nested": nested,
                }
            )
        per_symbol.append((f"DAY:{market}{code}", closes, sigs))
        n_nest = sum(1 for s in sigs if s["_nested"])
        print(f"  {market}{code}: bars={len(closes)} mmds={len(sigs)} nested={n_nest}")

    if not per_symbol:
        print("无可用数据")
        return 1

    # 分组：A=nested 确认，B=未确认。bar_index 是标的内索引，逐标的喂自己的 closes。
    groups: dict[str, list[tuple[str, dict]]] = {
        "A_nested_确认": [],
        "B_plain_未确认": [],
    }
    for sym, _closes, sigs in per_symbol:
        for s in sigs:
            rec = {"type": s["type"], "bar_index": s["bar_index"]}
            groups["A_nested_确认" if s["_nested"] else "B_plain_未确认"].append((sym, rec))

    print("\n分组构成：")
    for name, tagged in groups.items():
        c = Counter(r["type"] for _s, r in tagged)
        buy = sum(1 for _s, r in tagged if "buy" in r["type"])
        print(f"  {name}: n={len(tagged)} BUY={buy} SELL={len(tagged)-buy} {dict(c)}")

    print("\n" + "=" * 78)
    print(f"真·区间套回测验证  count={args.count}  low_level={args.low_level}  "
          f"horizons={horizons}")
    print("=" * 78)

    closes_by_sym = {sym: c for sym, c, _ in per_symbol}

    def stats_for(tagged: list[tuple[str, dict]], direction: str | None = None):
        """对一组（标的, 信号）计算加权命中率/收益；direction 为 buy/sell/None。"""
        sel = [
            (s, r)
            for s, r in tagged
            if direction is None or (("buy" in r["type"]) == (direction == "buy"))
        ]
        if not sel:
            return None
        all_rep = []
        for sym in {s for s, _ in sel}:
            closes = closes_by_sym[sym]
            own = [r for s, r in sel if s == sym and r["bar_index"] < len(closes)]
            if not own:
                continue
            all_rep.append(
                (compute_signal_accuracy_by_type(closes, own, horizons=horizons, seed=42),
                 len(own))
            )
        out = {}
        for h in horizons:
            tot = 0
            w_hit = w_ret = w_exc = 0.0
            for rep, _n in all_rep:
                for tinfo in rep.get("by_type", {}).values():
                    st = tinfo.get("horizons", {}).get(str(h))
                    if not st:
                        continue
                    cnt = st.get("count", 0)
                    if cnt <= 0:
                        continue
                    tot += cnt
                    w_hit += st.get("hit_rate", 0.0) * cnt
                    w_ret += st.get("avg_return", 0.0) * cnt
                    w_exc += st.get("excess_hit_rate", 0.0) * cnt
            if tot == 0:
                continue
            out[h] = (tot, w_hit / tot, w_ret / tot, w_exc / tot)
        return out

    def show(name: str, st: dict | None) -> None:
        if not st:
            return
        print(f"\n[{name}]")
        for h in horizons:
            if h not in st:
                continue
            tot, hit, ret, exc = st[h]
            print(
                f"  h={h:>2}: n={tot:>3}  hit={hit:6.1%}  avg_ret={ret:+7.3f}%  "
                f"excess_hit={exc:+6.1%}"
            )

    for name, tagged in groups.items():
        show(name, stats_for(tagged))

    # ── 主结论：按方向分层对比 ──
    print("\n" + "=" * 78)
    print("分层对照（按方向分层；nested 确认 vs 未确认）")
    print("=" * 78)
    a_all, b_all = groups["A_nested_确认"], groups["B_plain_未确认"]
    for direction, label in (("buy", "BUY"), ("sell", "SELL")):
        a = stats_for(a_all, direction)
        b = stats_for(b_all, direction)
        if not a or not b:
            continue
        print(f"\n{label}:")
        for h in horizons:
            if h not in a or h not in b:
                continue
            ah, bh = a[h], b[h]
            v = "✅ 区间套占优" if ah[1] > bh[1] else "⚠️ 区间套不占优"
            print(
                f"  h={h:>2}: 确认(hit={ah[1]:.1%},ret={ah[2]:+.3f}%,n={ah[0]}) vs "
                f"未确认(hit={bh[1]:.1%},ret={bh[2]:+.3f}%,n={bh[0]})  → {v}"
            )

    print("\n注：excess_hit = 相对可复现随机入场基准（seed=42）的超额命中率。")
    print("注：B 组含 nested 缺失（算不出）的信号——与回测过滤口径一致（只放行 True）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
