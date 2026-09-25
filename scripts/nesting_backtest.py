#!/usr/bin/env python3
"""区间套（多级别共振）信号的量化回测验证 —— 一次性统计脚本（不入库）。

缠论原文：区间套 = 各级别走势「套」在一起共振，是背驰/买卖点的最强确认。
本脚本验证这个理论断言在真实行情上是否成立：

  分组：A=有区间套确认（multi_level_score >= 阈值）
        B=无区间套确认
        C=全部信号（基线）
  指标：未来 5/10/20 根的 hit_rate（命中率=方向正确）、avg_return（平均收益）、
        profit_factor（盈亏比）、excess_hit_rate（相对随机入场基准的超额命中率）

数据取自在跑的本地服务（/api/v1/chanlun/analyze），标的 = verify.VERIFY_POOL
20 只沪深龙头，日线 800 根。随机基准 seed=42，结果可复现。

用法：.venv/bin/python scripts/nesting_backtest.py [--count N] [--threshold T]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

# 让脚本可直接跑（无需安装）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from easy_tdx.backtest.signal_accuracy import compute_signal_accuracy_by_type  # noqa: E402

API = "http://127.0.0.1:8000/api/v1/chanlun/analyze"

# 与 src/easy_tdx/web/routers/verify.py 的 VERIFY_POOL 一致（20 只龙头）
POOL = [
    ("SH", "600519"), ("SH", "601318"), ("SH", "600036"), ("SH", "601166"),
    ("SH", "600900"), ("SH", "601899"), ("SH", "600030"), ("SH", "601012"),
    ("SH", "600276"), ("SH", "601888"), ("SZ", "000858"), ("SZ", "000333"),
    ("SZ", "000651"), ("SZ", "000001"), ("SZ", "000002"), ("SZ", "002594"),
    ("SH", "600887"), ("SH", "601668"), ("SZ", "000725"), ("SH", "600309"),
]


def analyze(market: str, code: str, count: int) -> dict | None:
    """取信号（/chanlun/analyze，POST）。"""
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
        print(f"  ! {market}{code} 信号取数失败: {exc}")
        return None


def fetch_closes(market: str, code: str, count: int) -> list[float]:
    """取收盘价序列（/bars，GET + query 参数，count 上限 800）。"""
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


def nesting_score(mmd: dict) -> float | None:
    """区间套评分；非 3 类信号未计算（返回 None）。"""
    v = mmd.get("v68_range_set_multi_level")
    if not v:
        return None
    sc = v.get("multi_level_score")
    return float(sc) if sc is not None else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=800, help="每只票取多少根日线")
    ap.add_argument("--threshold", type=float, default=0.5, help="区间套确认阈值")
    ap.add_argument("--horizons", type=str, default="5,10,20")
    args = ap.parse_args()
    horizons = tuple(int(x) for x in args.horizons.split(","))

    # 逐标的收集：bar_index 不可跨标的拼接，需各自留 closes
    per_symbol: list[tuple[str, list[float], list[dict]]] = []
    for market, code in POOL:
        d = analyze(market, code, args.count)
        if not d:
            continue
        closes = fetch_closes(market, code, args.count)
        if not closes:
            continue
        sigs = []
        for m in d.get("mmds", []):
            if m.get("bar_index") is None:
                continue
            sigs.append(
                {
                    "type": m["type"],
                    "bar_index": int(m["bar_index"]),
                    "_nesting": nesting_score(m),
                }
            )
        per_symbol.append((f"{market}{code}", closes, sigs))
        n_nest = sum(1 for s in sigs if (s["_nesting"] or 0) >= args.threshold)
        print(f"  {market}{code}: bars={len(closes)} mmds={len(sigs)} 有区间套={n_nest}")

    if not per_symbol:
        print("无可用数据")
        return 1

    # 分组统计：分组时保留所属标的，逐标的只喂自己的信号
    # （bar_index 是标的内的索引，跨标的拼接会张冠李戴；且同一信号被多个
    #  标的重复计入会虚增样本量 n，误导显著性判断）。
    #
    # 对照组设计（关键）：区间套字段 _range_set_multi_level_v68 仅对 3 类买卖点
    # 计算（mmd.py:5157），若直接拿「有区间套」对比「全部无区间套」，B 组会混入
    # 大量 1/2 类信号——两组类型构成不同，差异无法归因于区间套。因此主对照限定在
    # 3 类信号内部：A3 = 3类且有区间套确认，B3 = 3类但无区间套确认。
    groups: dict[str, list[tuple[str, dict]]] = {
        "A3_三类有区间套": [],
        "B3_三类无区间套": [],
        "C_全部基线": [],
    }
    for sym, _closes, sigs in per_symbol:
        for s in sigs:
            sc = s["_nesting"]
            rec = {"type": s["type"], "bar_index": s["bar_index"]}
            groups["C_全部基线"].append((sym, rec))
            if "3" not in s["type"]:  # 仅 1/2 类：不进主对照
                continue
            if sc is not None and sc >= args.threshold:
                groups["A3_三类有区间套"].append((sym, rec))
            else:
                groups["B3_三类无区间套"].append((sym, rec))

    # 打印各组类型/方向构成，便于核验两组可比性
    print("\n分组构成：")
    for name, tagged in groups.items():
        from collections import Counter

        c = Counter(r["type"] for _s, r in tagged)
        buy = sum(1 for _s, r in tagged if "buy" in r["type"])
        sell = len(tagged) - buy
        print(f"  {name}: n={len(tagged)} BUY={buy} SELL={sell} {dict(c)}")

    print("\n" + "=" * 78)
    print(f"区间套回测验证  count={args.count}  阈值={args.threshold}  "
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
        # 按标的切片，各自用自己的 closes 计算（bar_index 为标的内索引）
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
            pfs: list[float] = []
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
                    # pf = 平均盈利/平均亏损，无亏损时引擎取 999（截断值），
                    # 线性平均会被带飞 → 只做中位数与截断计数。
                    pfs.append(st.get("profit_factor", 0.0))
            if tot == 0:
                continue
            med_pf = sorted(pfs)[len(pfs) // 2] if pfs else 0.0
            out[h] = (tot, w_hit / tot, w_ret / tot, w_exc / tot, med_pf,
                      sum(1 for p in pfs if p >= 999.0))
        return out

    def show(name: str, st: dict | None) -> None:
        if not st:
            return
        print(f"\n[{name}]")
        for h in horizons:
            if h not in st:
                continue
            tot, hit, ret, exc, pf, ntr = st[h]
            print(
                f"  h={h:>2}: n={tot:>3}  hit={hit:6.1%}  avg_ret={ret:+7.3f}%  "
                f"pf(med)={pf:5.2f}{f' [含{ntr}组无亏损]' if ntr else ''}  "
                f"excess_hit={exc:+6.1%}"
            )

    summary = {}
    for name, tagged in groups.items():
        st = stats_for(tagged)
        if st:
            summary[name] = st
        show(name, st)

    # ── 主结论：按方向分层对比（A3/B3 方向构成相反，必须分层才可比）──
    print("\n" + "=" * 78)
    print("分层对照（同为 3 类信号，按方向分层）")
    print("=" * 78)
    for direction, label in (("buy", "BUY(3buy)"), ("sell", "SELL(3sell)")):
        a = stats_for(groups["A3_三类有区间套"], direction)
        b = stats_for(groups["B3_三类无区间套"], direction)
        if not a or not b:
            continue
        print(f"\n{label}:")
        for h in horizons:
            if h not in a or h not in b:
                continue
            ah, bh = a[h], b[h]
            v = "✅ 区间套占优" if ah[1] > bh[1] else "⚠️ 区间套不占优"
            print(
                f"  h={h:>2}: 有区间套(hit={ah[1]:.1%},ret={ah[2]:+.3f}%,n={ah[0]}) vs "
                f"无(hit={bh[1]:.1%},ret={bh[2]:+.3f}%,n={bh[0]})  → {v}"
            )

    # 结论
    print("\n" + "-" * 78)
    for h in horizons:
        a = summary.get(("A3_三类有区间套", h))
        b = summary.get(("B3_三类无区间套", h))
        if not a or not b:
            continue
        verdict = "✅ 区间套占优" if a[1] > b[1] else "⚠️ 区间套不占优"
        print(
            f"h={h:>2}: A3(hit={a[1]:.1%},ret={a[2]:+.3f}%,n={a[0]}) vs "
            f"B3(hit={b[1]:.1%},ret={b[2]:+.3f}%,n={b[0]})  → {verdict}"
        )
    print("-" * 78)
    print("注：excess_hit = 相对可复现随机入场基准（seed=42）的超额命中率。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
