"""V855 实测：走势段级力度对比（第61课原义）在真数据上的 REJECTED 率。

背景（§2.5→§2.5.1）：V854 字面「笔级力度」实测过发 4%→34%（背驰笔=走势段
最弱笔，比值失真）。第61课原义是**走势段级** MACD 面积对比（整段，非末笔）。
本脚本量：对每个高级别买卖点，找其所属走势段(curr) + 前一同向走势段(prev)，
用 _calc_bi_force（复用于 Line，走 start/end.bar_index）算两段 MACD 面积，
看 curr>prev（力度未衰减 ⇒ REJECTED）的占比——对照笔级 34% 是否收敛。

§3：先量再定论。若走势段级 REJECTED 率合理（接近代理 4% 或更低）→ 可接线启用；
若仍过发 → 保持休眠 + 记录。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

D = ROOT / "audit_data"  # {code}_daily.json
DM = ROOT / "audit_data_min"
EXCLUDE = {"sh000300", "sh000001"}

import pandas as pd  # noqa: E402

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402
from easy_tdx.chanlun.mmd_conditions import _calc_bi_force  # noqa: E402


def _find_curr_prev_qsd(mmd, qsds):
    """找 mmd 所属走势段(curr) + 前一同向走势段(prev)。

    curr: [start,end].bar_index 包含 mmd.bi 的同向走势段；无精确包含时取
          end.bar_index ≤ bi.end.bar_index 的最近同向段（背驰笔常为段末笔）。
    prev: curr 之前最近同向走势段。
    """
    if not qsds or mmd.bi is None:
        return None, None
    bi_s = mmd.bi.start.bar_index
    bi_e = mmd.bi.end.bar_index
    bi_dir = mmd.bi.direction.value
    curr = None
    curr_idx = -1
    # 优先：包含 bi 的同向段
    for i, q in enumerate(qsds):
        if q.end is None or q.start is None:
            continue
        if q.direction.value != bi_dir:
            continue
        if q.start.bar_index <= bi_s and q.end.bar_index >= bi_e:
            curr, curr_idx = q, i
            break
    # 回退：end ≤ bi_e 的最近同向段
    if curr is None:
        for i, q in enumerate(qsds):
            if q.end is None or q.direction.value != bi_dir:
                continue
            if q.end.bar_index <= bi_e + 2:
                curr, curr_idx = q, i
    if curr is None:
        return None, None
    prev = None
    for j in range(curr_idx - 1, -1, -1):
        q = qsds[j]
        if q.end is None or q.direction.value != bi_dir:
            continue
        prev = q
        break
    return curr, prev


def _measure(code: str) -> dict:
    try:
        d = pd.DataFrame(json.loads((D / f"{code}_daily.json").read_text()))
        s = pd.DataFrame(json.loads((DM / f"{code}_30min.json").read_text()))
    except FileNotFoundError:
        return {}
    if len(d) < 100 or len(s) < 100:
        return {}
    cfg = ChanlunConfig()
    rh = ChanlunAnalyser(code=code, frequency="daily", config=cfg).process_klines(d)
    if not rh.mmds:
        return {}
    hi_closes = [k.close for k in rh.klines]
    qsds = rh.zsds or rh.qsds or []
    ratios = []
    rejected = 0
    total = 0
    samples = []
    for m in rh.mmds:
        curr, prev = _find_curr_prev_qsd(m, qsds)
        if curr is None or prev is None:
            continue
        total += 1
        try:
            cf = _calc_bi_force(curr, hi_closes, curr.end.bar_index, normalize_by_bars=True)
            pf = _calc_bi_force(prev, hi_closes, prev.end.bar_index, normalize_by_bars=True)
        except Exception:
            continue
        if pf is None or pf <= 0 or cf is None:
            continue
        ratio = cf / pf
        ratios.append(ratio)
        is_rej = cf > pf  # 力度未衰减 ⇒ REJECTED
        if is_rej:
            rejected += 1
        if len(samples) < 6 and (is_rej or len(samples) < 3):
            samples.append({
                "code": code, "type": m.mmd_type.value,
                "curr_end": curr.end.bar_index, "prev_end": prev.end.bar_index,
                "cf": round(cf, 3), "pf": round(pf, 3), "ratio": round(ratio, 3),
                "rejected": is_rej,
            })
    return {
        "code": code, "total_mmd": len(rh.mmds), "qsd_pairs": total,
        "rejected": rejected, "rejected_pct": round(100 * rejected / total, 1) if total else 0,
        "ratio_median": round(statistics.median(ratios), 3) if ratios else None,
        "ratio_gt10": sum(1 for r in ratios if r > 10),
        "samples": samples,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    a = ap.parse_args()
    codes = sorted({p.stem.replace("_daily", "") for p in D.glob("*_daily.json")})[: a.limit]
    codes = [c for c in codes if c.lower() not in EXCLUDE]
    agg = []
    for c in codes:
        r = _measure(c)
        if r:
            agg.append(r)
    n = len(agg)
    tot_pairs = sum(r["qsd_pairs"] for r in agg)
    tot_rej = sum(r["rejected"] for r in agg)
    all_ratios = [r["ratio_median"] for r in agg if r["ratio_median"] is not None]
    print(f"V855 走势段级力度实测：{n} 标的，{tot_pairs} 个 mmd 有(curr,prev)走势段对")
    print(f"  REJECTED(curr>prev 力度未衰减): {tot_rej}/{tot_pairs} = {round(100*tot_rej/max(tot_pairs,1),1)}%")
    print(f"  比值中位(各标的)中位: {statistics.median(all_ratios):.3f}" if all_ratios else "  无比值")
    print(f"  对照：笔级(V854) REJECTED 34.7%，代理(V853) 4.4%")
    print("  样本：")
    for r in agg[:3]:
        for s in r["samples"][:2]:
            print(f"    {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
