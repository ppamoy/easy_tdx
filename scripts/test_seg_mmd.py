#!/usr/bin/env python3
"""线段级别买卖点 vs 笔级别买卖点 对比测试。

验证 use_seg_mmd=True 产出的买卖点数量、类型分布，并与 use_seg_mmd=False 对比。
"""

import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, "src")
from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig

CACHE_D = Path("audit_data")
STOCKS = [
    ("SH", "600000", "浦发银行"),
    ("SH", "600036", "招商银行"),
    ("SH", "601318", "中国平安"),
    ("SH", "600276", "恒瑞医药"),
    ("SH", "600030", "中信证券"),
    ("SZ", "000333", "美的集团"),
    ("SZ", "000651", "格力电器"),
    ("SZ", "000725", "京东方A"),
    ("SZ", "300750", "宁德时代"),
    ("SZ", "002415", "海康威视"),
]


def load_daily(mkt, code):
    fp = CACHE_D / f"{mkt.lower()}{code}_daily.json"
    if not fp.is_file():
        return None
    rows = json.loads(fp.read_text("utf-8"))
    df = pd.DataFrame(rows)
    for col in ("datetime", "date"):
        if col in df.columns:
            df["datetime"] = pd.to_datetime(df[col])
            break
    return df.sort_values("datetime").reset_index(drop=True)


def run_stock(mkt, code, name, use_seg):
    df = load_daily(mkt, code)
    if df is None:
        return None

    cfg = ChanlunConfig(
        zs_from_xd=False,  # 笔构中枢（两个主流库都这样做）
        use_seg_mmd=use_seg,
        multi_level=False,  # 关掉递归，只看本级
    )
    r = ChanlunAnalyser(code=code, frequency="daily", config=cfg).process_klines(df)

    mmds = r.mmds
    types = {}
    for m in mmds:
        t = m.mmd_type.value
        types[t] = types.get(t, 0) + 1

    return {
        "bis": len(r.bis),
        "xds": len(r.xds),
        "zss": len(r.zss),
        "mmds": len(mmds),
        "types": types,
    }


def main():
    print("=" * 90)
    print("线段级别买卖点 (seg_mmd=True) vs 笔级别买卖点 (seg_mmd=False)")
    print(f"{'股票':10s} | {'笔':>4s} {'线段':>4s} {'中枢':>4s} | "
          f"{'seg_mmd':>8s} {'类型分布':30s} | {'笔mmd':>6s} {'类型分布':30s}")
    print("-" * 90)

    tot_seg = {"mmds": 0, "types": {}}
    tot_bi = {"mmds": 0, "types": {}}
    n = 0

    for mkt, code, name in STOCKS:
        t0 = time.time()
        r_seg = run_stock(mkt, code, name, True)
        r_bi = run_stock(mkt, code, name, False)

        if r_seg is None or r_bi is None:
            print(f"{name:10s} | 跳过")
            continue

        seg_types = ",".join(f"{k}:{v}" for k, v in sorted(r_seg["types"].items())) or "无"
        bi_types = ",".join(f"{k}:{v}" for k, v in sorted(r_bi["types"].items())) or "无"

        print(f"{name:10s} | {r_seg['bis']:4d} {r_seg['xds']:4d} {r_seg['zss']:4d} | "
              f"{r_seg['mmds']:8d} {seg_types:30s} | {r_bi['mmds']:6d} {bi_types:30s}")

        tot_seg["mmds"] += r_seg["mmds"]
        for k, v in r_seg["types"].items():
            tot_seg["types"][k] = tot_seg["types"].get(k, 0) + v
        tot_bi["mmds"] += r_bi["mmds"]
        for k, v in r_bi["types"].items():
            tot_bi["types"][k] = tot_bi["types"].get(k, 0) + v
        n += 1

    print("-" * 90)
    print(f"{'平均':10s} | {'':>4s} {'':>4s} {'':>4s} | "
          f"{tot_seg['mmds']/n:8.1f} {','.join(f'{k}:{v}' for k,v in sorted(tot_seg['types'].items())):30s} | "
          f"{tot_bi['mmds']/n:6.1f} {','.join(f'{k}:{v}' for k,v in sorted(tot_bi['types'].items())):30s}")
    print()
    print(f"线段级别平均: {tot_seg['mmds']/n:.1f} 信号/股")
    print(f"笔级别平均:   {tot_bi['mmds']/n:.1f} 信号/股")


if __name__ == "__main__":
    main()
