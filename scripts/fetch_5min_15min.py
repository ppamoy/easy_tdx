#!/usr/bin/env python3
"""批量抓取 5分/15分线，供多级别缠论回测使用。

用法：
    .venv/bin/python scripts/fetch_5min_15min.py --period 5 --pages 4 --workers 2
    .venv/bin/python scripts/fetch_5min_15min.py --period 15 --pages 4 --workers 2
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd
from _concurrency import resolve_workers
from easy_tdx.mac.enums import Period
from easy_tdx.unified import UnifiedTdxClient

OUT_DIR = ROOT / "audit_data_min"
STOCKS = [
    (1, "600000"), (1, "600036"), (1, "601318"), (1, "600276"), (1, "600030"),
    (0, "000333"), (0, "000651"), (0, "000725"), (0, "300750"), (0, "002415"),
]
PERIOD_MAP = {"5": Period.MIN_5, "15": Period.MIN_15}
PAGE = 3000


def _fetch_one(args):
    mkt, code, period, pages = args
    per = PERIOD_MAP[str(period)]
    frames = []
    try:
        c = UnifiedTdxClient()
        c.connect()
        for p in range(pages):
            df = c.get_stock_kline(mkt, code, per, p * PAGE, PAGE)
            if df is None or df.empty:
                break
            frames.append(df)
            if len(df) < PAGE:
                break
        try:
            c.close()
        except Exception:
            pass
    except Exception as e:
        return (code, 0, f"{type(e).__name__}: {e}")

    if not frames:
        return (code, 0, "空")

    df = pd.concat(frames, ignore_index=True)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.drop_duplicates(subset=["datetime"]).sort_values("datetime")
    keep = ["datetime", "open", "high", "low", "close", "vol"]
    df = df[[c for c in keep if c in df.columns]]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prefix = "sh" if mkt == 1 else "sz"
    out = OUT_DIR / f"{prefix}{code}_{period}min.json"
    out.write_text(
        json.dumps(
            [{"datetime": str(r["datetime"]), **{k: r[k] for k in df.columns if k != "datetime"}}
             for _, r in df.iterrows()],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return (code, len(df), "OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=int, default=5, choices=(5, 15))
    ap.add_argument("--pages", type=int, default=4, help="每只抓几页(每页3000根)")
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args()

    workers = resolve_workers(a.workers)
    jobs = [(m, c, a.period, a.pages) for m, c in STOCKS]
    print(f"抓取 {len(STOCKS)} 只 × {a.period}min × {a.pages} 页   并行度 {workers}")
    print(f"输出目录 {OUT_DIR}\n")

    t0 = time.time()
    ok = fail = 0
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, (code, n, st) in enumerate(ex.map(_fetch_one, jobs, chunksize=1)):
            if st == "OK":
                ok += 1
                print(f"  {code}: {n} bars ✅", flush=True)
            else:
                fail += 1
                print(f"  {code}: {st} ❌", flush=True)

    el = time.time() - t0
    print(f"\n完成：成功 {ok} / 失败 {fail}，耗时 {el:.0f}s")


if __name__ == "__main__":
    raise SystemExit(main())
