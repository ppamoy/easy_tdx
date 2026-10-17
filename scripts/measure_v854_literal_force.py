"""V854 实测：第61课字面「力度大于前者」MACD 面积对比在真实日线+30min 上的影响。

对比同一批信号在两种口径下的区间套状态分布：
  - 代理口径（closes=None）：REJECTED 用「有结构无背驰」代理（V853 既有行为）。
  - 字面口径（closes=<daily closes>）：REJECTED 优先用 MACD 面积 curr>prev，
    force 不可得时回退代理。

输出：两种口径的 ASSUMED/CONFIRMED/REJECTED 计数 + 字面口径下 REJECTED 的
literal/代理 细分 + 若干带 force 值的 REJECTED 样本（证明字面分支真的在真数据
上触发，而非只在单测 fixture 上）。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

D = ROOT / "audit_data"            # {code}_daily.json
DM = ROOT / "audit_data_min"       # {code}_30min.json
EXCLUDE = {"sh000300", "sh000001"}

import pandas as pd  # noqa: E402

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402
from easy_tdx.chanlun.qujiantao import compute_qujiantao_cross_period  # noqa: E402


def _analyze(code: str) -> dict:
    try:
        d = pd.DataFrame(json.loads((D / f"{code}_daily.json").read_text()))
        s = pd.DataFrame(json.loads((DM / f"{code}_30min.json").read_text()))
    except FileNotFoundError:
        return {}
    if len(d) < 100 or len(s) < 100:
        return {}
    cfg = ChanlunConfig()
    rh = ChanlunAnalyser(code=code, frequency="daily", config=cfg).process_klines(d)
    rs = ChanlunAnalyser(code=code, frequency="30min", config=cfg).process_klines(s)
    if not rh.mmds:
        return {}
    hi_closes = [k.close for k in rh.klines]
    common = dict(bis_low=rs.bis, zss_low=rs.zss, bcs_low=rs.bcs, mmds_low=rs.mmds)
    qt_proxy = compute_qujiantao_cross_period(rh.mmds, **common)            # closes=None
    qt_literal = compute_qujiantao_cross_period(rh.mmds, **common, closes=hi_closes)
    return {
        "code": code,
        "n": len(rh.mmds),
        "proxy": [q["state"] if q else "NONE" for q in qt_proxy],
        "literal": [q["state"] if q else "NONE" for q in qt_literal],
        "literal_chains": [q["chain"][0] if q else None for q in qt_literal],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()

    codes = sorted({p.name.split("_")[0] for p in DM.glob("*_30min.json")})
    codes = [c for c in codes if c not in EXCLUDE][: a.limit]
    print(f"样本 {len(codes)} 只（日线+30min）  workers={a.workers}\n")

    from concurrent.futures import ProcessPoolExecutor
    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for r in ex.map(_analyze, codes, chunksize=1):
            if r:
                results.append(r)

    # 汇总状态分布
    proxy_states = Counter()
    literal_states = Counter()
    literal_rejected_reasons = Counter()  # literal / 代理 / None
    samples: list[tuple] = []
    for r in results:
        for st in r["proxy"]:
            proxy_states[st] += 1
        for st in r["literal"]:
            literal_states[st] += 1
        for ch in r["literal_chains"]:
            if ch and ch.get("state") == "REJECTED":
                reason = ch.get("rejected_reason") or ""
                kind = "字面" if "字面" in reason else ("代理" if "代理" in reason else "其他")
                literal_rejected_reasons[kind] += 1
                if len(samples) < 6 and kind == "字面":
                    samples.append((r["code"], ch.get("force_curr"), ch.get("force_prev"),
                                    ch.get("force_ratio"), reason))

    tot_p = sum(proxy_states.values()) or 1
    tot_l = sum(literal_states.values()) or 1
    print("── 区间套状态分布（真实日线+30min）──")
    print(f"{'状态':<12} {'代理口径':>10} {'字面口径':>10}")
    for st in ("CONFIRMED", "REJECTED", "ASSUMED", "NONE"):
        p, l = proxy_states.get(st, 0), literal_states.get(st, 0)
        print(f"{st:<12} {p:>5} ({p/tot_p*100:4.1f}%) {l:>5} ({l/tot_l*100:4.1f}%)")

    print(f"\n── 字面口径 REJECTED 细分（共 {sum(literal_rejected_reasons.values())}）──")
    for k, v in literal_rejected_reasons.most_common():
        print(f"  {k}: {v}")

    # 力度比分布（判断退化 prev 占比，用于选 guard 阈值）
    ratios: list[float] = []
    for r in results:
        for ch in r["literal_chains"]:
            if ch and ch.get("state") == "REJECTED" and ch.get("force_ratio") is not None:
                rr = ch["force_ratio"]
                if ("字面" in (ch.get("rejected_reason") or "")):
                    ratios.append(rr)
    if ratios:
        import statistics
        ratios.sort()
        n = len(ratios)
        print(f"\n── 字面 REJECTED 力度比分布（n={n}）──")
        print(f"  min={ratios[0]:.3f}  p25={ratios[n//4]:.3f}  median={statistics.median(ratios):.3f}"
              f"  p75={ratios[3*n//4]:.3f}  max={ratios[-1]:.3f}")
        # 桶
        for lo, hi in [(1, 1.5), (1.5, 2), (2, 3), (3, 5), (5, 10), (10, 50), (50, 1e9)]:
            c = sum(1 for x in ratios if lo <= x < hi)
            print(f"  ratio[{lo},{hi}): {c} ({c/n*100:.1f}%)")

    print("\n── 字面 REJECTED 样本（force 真值，证明字面分支在真数据触发）──")
    if not samples:
        print("  （本批无字面 REJECTED —— 多为 CONFIRMED 或无前者可对比）")
    for code, fc, fp, fr, reason in samples:
        print(f"  {code}  curr={fc} prev={fp} ratio={fr}")
        print(f"    {reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
