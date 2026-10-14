#!/usr/bin/env python3
"""更新日线缓存：为每个信号补充ZS数据(ZG/ZD/ZZ/压力/支撑/中线)。"""

from __future__ import annotations
import json, sys, time, pickle, warnings
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

DATA_DIR = ROOT / "audit_data"


def enrich_one(args):
    """Worker: 重跑单只股票的日线缠论分析，为信号补充ZS数据。"""
    market, code, category = args
    fp = DATA_DIR / f"{market.lower()}{code}_daily.json"
    if not fp.is_file():
        return {"code": code, "error": "no data"}

    rows = json.loads(fp.read_text("utf-8"))
    df = pd.DataFrame(rows)
    dt_col = "datetime" if "datetime" in df.columns else "date"
    df["datetime"] = pd.to_datetime(df[dt_col])
    df = df.sort_values("datetime").reset_index(drop=True)
    if len(df) < 60:
        return {"code": code, "error": "too short"}

    cfg = ChanlunConfig(zs_from_xd=False)
    try:
        result = ChanlunAnalyser(code=code, frequency="daily", config=cfg).process_klines(df)
    except Exception as e:
        return {"code": code, "error": str(e)}

    # 为每个信号找到所属中枢
    enriched_signals = []
    for mmd in result.mmds:
        if mmd.bi is None:
            continue
        mmd_type = mmd.mmd_type.value
        is_buy = "buy" in mmd_type
        is_sell = "sell" in mmd_type
        if not (is_buy or is_sell):
            continue

        sig_ts = mmd.bi.end.k.date
        mask = df["datetime"] == sig_ts
        if len(df.index[mask]) > 0:
            idx = int(df.index[mask][0])
        else:
            idx = int(df.index.get_indexer([sig_ts], method="nearest")[0])

        # 找包含该信号bi的中枢
        bi_idx = mmd.bi.index
        nearest_zs = None
        for zs in result.zss:
            if zs.lines:
                line_indices = [l.index for l in zs.lines]
                if min(line_indices) <= bi_idx <= max(line_indices):
                    nearest_zs = zs
                    break
        if not nearest_zs and result.zss:
            nearest_zs = min(result.zss,
                           key=lambda z: abs(z.lines[-1].index - bi_idx) if z.lines else 9999)

        zg = float(nearest_zs.zg) if nearest_zs else None
        zd = float(nearest_zs.zd) if nearest_zs else None
        zz = (zg + zd) / 2 if zg and zd else None

        enriched_signals.append({
            "idx": idx,
            "dt": sig_ts.isoformat(),
            "type": mmd_type,
            "is_buy": is_buy,
            "is_sell": is_sell,
            "confidence": round(float(mmd.confidence), 2),
            "zg": round(zg, 2) if zg else None,
            "zd": round(zd, 2) if zd else None,
            "zz": round(zz, 2) if zz else None,
        })

    # 保存年度数据
    yearly_data = {}
    for year in [2025, 2026]:
        yd = df[df["datetime"].dt.year == year].copy()
        if len(yd) < 10:
            continue
        yearly_data[str(year)] = {
            "dts": yd["datetime"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist(),
            "opens": yd["open"].astype(float).tolist() if "open" in yd.columns else yd["close"].astype(float).tolist(),
            "closes": yd["close"].astype(float).tolist(),
        }

    return {
        "code": code,
        "market": market,
        "category": category,
        "signals": enriched_signals,
        "yearly_data": yearly_data,
        "total_bars": len(df),
        "n_bi": len(result.bis),
        "n_zs": len(result.zss),
        "n_mmd": len(result.mmds),
    }


def main():
    # 加载标的列表 + 分类
    daily_cache = DATA_DIR / "hybrid_analysis_cache.pkl"
    category_map = {}
    if daily_cache.is_file():
        with open(daily_cache, "rb") as f:
            daily_analyses = pickle.load(f)
        for a in daily_analyses:
            category_map[a["code"]] = a.get("category")

    # 找所有有日线缓存的股票
    stock_list = []
    for fp in sorted(DATA_DIR.glob("*_daily.json")):
        name = fp.stem.replace("_daily", "")
        market = "SH" if name.startswith("sh") else "SZ"
        code = name[2:]
        if len(code) == 6:
            stock_list.append((market, code, category_map.get(code)))

    total = len(stock_list)
    print(f"共 {total} 只标的（已有日线缓存）")

    t0 = time.time()
    analyses = []
    with ProcessPoolExecutor(max_workers=2) as ex:
        futures = {ex.submit(enrich_one, args): args for args in stock_list}
        for i, fut in enumerate(as_completed(futures)):
            r = fut.result()
            if "error" not in r:
                analyses.append(r)
            if (i + 1) % 30 == 0 or i + 1 == total:
                print(f"  进度: {i+1}/{total} ({time.time()-t0:.0f}s)", flush=True)

    print(f"完成: {len(analyses)}/{total} ({time.time()-t0:.0f}s)")

    # 保存
    cache_file = DATA_DIR / "hybrid_analysis_cache.pkl"
    with open(cache_file, "wb") as f:
        pickle.dump(analyses, f)
    print(f"缓存已更新: {cache_file}")

    has_zs = sum(1 for a in analyses for s in a.get("signals", []) if s.get("zg"))
    total_sigs = sum(len(a.get("signals", [])) for a in analyses)
    print(f"信号总数: {total_sigs} | 有ZS数据: {has_zs} ({has_zs*100//total_sigs if total_sigs else 0}%)")


if __name__ == "__main__":
    main()
