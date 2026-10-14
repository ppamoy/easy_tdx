"""预填充缠论分析 SQLite 缓存。

对每只标的从 JSON K 线缓存读取数据，运行缠论分析，
将完整结果（笔/线段/中枢/买卖点/背驰/分型/MACD + bars）存入 SQLite。
后续打开图表时毫秒级返回。

用法::

    .venv/bin/python scripts/prepopulate_chanlun_cache.py [--category MIN_30] [--workers 2]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

# 确保项目根目录在 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
from easy_tdx.web.chanlun_cache import ChanlunCache
from easy_tdx.web.schemas import DataFrameResponse

KLINE_DIR_30M = ROOT / "audit_data" / "kline_30min"
KLINE_DIR_DAY = ROOT / "audit_data"


def _list_stocks(category: str = "MIN_30") -> list[tuple[str, str]]:
    """从 K 线缓存目录列出所有标的 (market, code)。"""
    if category == "MIN_30":
        d = KLINE_DIR_30M
        suffix = "_30min.json"
    else:
        d = KLINE_DIR_DAY
        suffix = "_daily.json"
    if not d.is_dir():
        return []
    stocks = []
    for f in sorted(d.glob(f"*{suffix}")):
        name = f.name.replace(suffix, "")
        if len(name) >= 8:
            market = name[:2].upper()
            code = name[2:]
            stocks.append((market, code))
    return stocks


def _read_kline(market: str, code: str, category: str) -> pd.DataFrame | None:
    if category == "MIN_30":
        fp = KLINE_DIR_30M / f"{market.lower()}{code}_30min.json"
    else:
        fp = KLINE_DIR_DAY / f"{market.lower()}{code}_daily.json"
    if not fp.is_file():
        return None
    rows = json.loads(fp.read_text("utf-8"))
    df = pd.DataFrame(rows)
    dt_col = "datetime" if "datetime" in df.columns else "date"
    df["datetime"] = pd.to_datetime(df[dt_col])
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


def _analyze_one(args: tuple[str, str, str]) -> dict:
    """分析单只标的并存入 SQLite。"""
    market, code, category = args
    cache = ChanlunCache()

    # 已缓存则跳过
    if cache.get(market, code, category) is not None:
        cache.close()
        return {"code": code, "status": "cached"}

    df = _read_kline(market, code, category)
    if df is None or len(df) < 60:
        cache.close()
        return {"code": code, "status": "no_data"}

    freq = "30min" if category == "MIN_30" else "daily"
    cfg = ChanlunConfig(zs_from_xd=False)
    try:
        result = ChanlunAnalyser(code=f"{market}{code}", frequency=freq, config=cfg).process_klines(df)
    except Exception as e:
        cache.close()
        return {"code": code, "status": "error", "error": str(e)[:100]}

    d = result.to_dict()
    d["bars"] = DataFrameResponse.from_dataframe(df).data
    d["fractals"] = [
        {
            "fx_type": fx.fx_type.value,
            "date": result._fmt_dt(result._fx_anchor_datetime(fx)),
            "val": round(fx.val, 2),
            "index": fx.index,
            "bar_index": fx.bar_index,
        }
        for fx in result.fractals
    ]
    d["valid_fractals"] = result.valid_fractals_to_dict()

    try:
        cache.put(market, code, category, d)
    except Exception as e:
        cache.close()
        return {"code": code, "status": "cache_error", "error": str(e)[:100]}

    cache.close()
    return {"code": code, "status": "ok", "bars": len(d.get("bars", [])), "mmds": len(d.get("mmds", []))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="MIN_30", choices=["MIN_30", "DAY"])
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()

    stocks = _list_stocks(args.category)
    print(f"共 {len(stocks)} 只标的（{args.category}）")

    # 过滤已缓存的
    cache = ChanlunCache()
    todo = []
    skipped = 0
    for m, c in stocks:
        if cache.get(m, c, args.category) is not None:
            skipped += 1
        else:
            todo.append((m, c, args.category))
    cache.close()
    print(f"已缓存: {skipped} | 待分析: {len(todo)}")

    if not todo:
        print("全部已缓存，无需处理")
        return

    t0 = time.time()
    ok = err = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_analyze_one, t): t for t in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            r = fut.result()
            if r["status"] == "ok":
                ok += 1
            elif r["status"] == "cached":
                skipped += 1
            else:
                err += 1
                print(f"  ERROR {r['code']}: {r.get('error', r['status'])}")
            if i % 20 == 0 or i == len(todo):
                elapsed = int(time.time() - t0)
                print(f"  进度: {i}/{len(todo)} ({elapsed}s) ok={ok} err={err}")

    elapsed = int(time.time() - t0)
    cache = ChanlunCache()
    total = cache.count(args.category)
    cache.close()
    print(f"\n完成: ok={ok} err={err} skipped={skipped} ({elapsed}s)")
    print(f"SQLite缓存总数: {total} ({args.category})")
    print(f"数据库: {Path('audit_data/chanlun_cache.db').absolute()}")


if __name__ == "__main__":
    main()
