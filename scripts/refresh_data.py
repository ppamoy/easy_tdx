#!/usr/bin/env python3
"""收盘后自动刷新 K线 + 指数数据到缓存。

## 做什么
1. 刷新全部股票池的日线（audit_data/{code}_daily.json）
2. 刷新全部股票池的 30分/60分线（audit_data_min/{code}_{N}min.json）
3. 刷新上证指数日线（audit_data/sh000001_daily.json）—— 春夏秋冬判断用

## 数据源
UnifiedTdxClient（MAC 协议，同步），每只取 1 页 3000 根日线 / 2 页分钟线。

## 用法
    # 全量刷新（cron 用）
    .venv/bin/python scripts/refresh_data.py

    # 只刷新前 5 只（冒烟）
    .venv/bin/python scripts/refresh_data.py --limit 5

    # 只刷日线不刷分钟（快速）
    .venv/bin/python scripts/refresh_data.py --no-minute

## 定时（手动加 crontab 或用 dsh-task-board）
    # 每个交易日 16:30 收盘后跑
    30 16 * * 1-5  cd /home/skp/workspace/easy_tdx && .venv/bin/python scripts/refresh_data.py >> /tmp/refresh_data.log 2>&1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd  # noqa: E402

from _concurrency import resolve_workers  # noqa: E402
from easy_tdx.mac.enums import Period  # noqa: E402
from easy_tdx.unified import UnifiedTdxClient  # noqa: E402

DAILY_DIR = ROOT / "audit_data"
MIN_DIR = ROOT / "audit_data_min"
EXCLUDE = {"sh000300", "sh000001"}
PAGE = 3000


def _market_code(code: str) -> tuple[int, str]:
    """sh600000 -> (1, '600000')；sz000001 -> (0, '000001')。"""
    return (1, code[2:]) if code.startswith("sh") else (0, code[2:])


def _save_json(df: pd.DataFrame, out_path: Path, keep_cols: list[str]) -> int:
    """DataFrame → JSON 文件，返回行数。"""
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.drop_duplicates(subset=["datetime"]).sort_values("datetime")
    cols = [c for c in keep_cols if c in df.columns]
    df = df[cols]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for _, r in df.iterrows():
        row = {"datetime": str(r["datetime"])}
        for c in cols:
            if c != "datetime":
                row[c] = float(r[c]) if pd.notna(r[c]) else 0.0
        rows.append(row)
    out_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return len(rows)


def _fetch_kline(code: str, period: Period, pages: int) -> pd.DataFrame | None:
    """抓一只一个周期的 K线，返回拼接后的 DataFrame。"""
    mkt, pure = _market_code(code)
    frames: list[pd.DataFrame] = []
    try:
        c = UnifiedTdxClient()
        c.connect()
        for p in range(pages):
            df = c.get_stock_kline(mkt, pure, period, p * PAGE, PAGE)
            if df is None or df.empty:
                break
            frames.append(df)
            if len(df) < PAGE:
                break
        try:
            c.close()
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        return None

    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def _fetch_one_daily(code: str) -> tuple[str, int, str]:
    """刷新一只日线。"""
    df = _fetch_kline(code, Period.DAILY, 1)
    if df is None:
        return (code, 0, "取数失败")
    n = _save_json(df, DAILY_DIR / f"{code}_daily.json",
                   ["datetime", "open", "high", "low", "close", "vol"])
    return (code, n, "OK")


def _fetch_one_minute(code: str, period: int) -> tuple[str, int, str]:
    """刷新一只分钟线。"""
    per = Period.MIN_30 if period == 30 else Period.MIN_60
    df = _fetch_kline(code, per, 2)
    if df is None:
        return (code, 0, "取数失败")
    n = _save_json(df, MIN_DIR / f"{code}_{period}min.json",
                   ["datetime", "open", "high", "low", "close", "vol"])
    return (code, n, "OK")


def _fetch_index() -> tuple[str, int, str]:
    """刷新上证指数日线。"""
    try:
        c = UnifiedTdxClient()
        c.connect()
        # 上证指数 market=1, code='000001'
        df = c.get_stock_kline(1, "000001", Period.DAILY, 0, 3000)
        try:
            c.close()
        except Exception:  # noqa: BLE001
            pass
        if df is None or df.empty:
            return ("sh000001", 0, "指数取数为空")
        n = _save_json(df, DAILY_DIR / "sh000001_daily.json",
                       ["datetime", "open", "high", "low", "close", "vol"])
        return ("sh000001", n, "OK")
    except Exception as e:  # noqa: BLE001
        return ("sh000001", 0, f"{type(e).__name__}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="刷新 K线+指数缓存")
    ap.add_argument("--limit", type=int, default=0, help="只刷前 N 只（0=全部）")
    ap.add_argument("--no-minute", action="store_true", help="跳过分钟线")
    ap.add_argument("--no-daily", action="store_true", help="跳过日线")
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args()

    workers = resolve_workers(a.workers)

    # 股票池来自已有日线缓存
    codes = sorted({
        p.name.split("_daily")[0]
        for p in DAILY_DIR.glob("*_daily.json")
        if p.stem not in EXCLUDE
    })
    if a.limit:
        codes = codes[: a.limit]

    from concurrent.futures import ProcessPoolExecutor

    t0 = time.time()
    print(f"=== 数据刷新 {len(codes)} 只 ===")
    print(f"workers={workers}, daily={'否' if a.no_daily else '是'}, "
          f"minute={'否' if a.no_minute else '是'}\n")

    # ── 1. 上证指数 ──
    print("[指数] 上证指数日线...", end=" ", flush=True)
    _, n, st = _fetch_index()
    print(f"{st} ({n} bars)")
    index_ok = st == "OK"

    # ── 2. 日线 ──
    daily_ok = daily_fail = 0
    if not a.no_daily:
        print(f"\n[日线] {len(codes)} 只...", flush=True)
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for i, (code, n, st) in enumerate(ex.map(_fetch_one_daily, codes, chunksize=1)):
                if st == "OK":
                    daily_ok += 1
                else:
                    daily_fail += 1
                if (i + 1) % 20 == 0 or i + 1 == len(codes):
                    print(f"  日线进度 {i+1}/{len(codes)}  OK={daily_ok} FAIL={daily_fail}", flush=True)

    # ── 3. 分钟线 ──
    min_ok = min_fail = 0
    if not a.no_minute:
        for period in (30, 60):
            print(f"\n[{period}min] {len(codes)} 只...", flush=True)
            jobs = [(c, period) for c in codes]
            with ProcessPoolExecutor(max_workers=workers) as ex:
                for i, (code, n, st) in enumerate(
                    ex.map(_fetch_one_minute, [j[0] for j in jobs], chunksize=1)
                ):
                    if st == "OK":
                        min_ok += 1
                    else:
                        min_fail += 1
                    if (i + 1) % 20 == 0 or i + 1 == len(codes):
                        print(f"  {period}min进度 {i+1}/{len(codes)}  OK={min_ok} FAIL={min_fail}", flush=True)

    el = time.time() - t0
    print(f"\n=== 完成 ({el:.0f}s) ===")
    print(f"  指数: {'✅' if index_ok else '❌'}")
    print(f"  日线: ✅{daily_ok} ❌{daily_fail}")
    if not a.no_minute:
        print(f"  分钟: ✅{min_ok} ❌{min_fail}")

    return 0 if (index_ok or daily_ok > 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
