#!/usr/bin/env python3
"""批量抓取分钟线（30min / 60min），供**多级别缠论**回测使用。

## 为什么必须抓这个
此前所有缠论回测都只用了**日线同级别配对**（本级别买点进、本级别卖点出）。
而缠论真正的操作法是**级别配合**：本级别（日线）定方向/找买点，
次级别（30min）找精确卖点 —— 例如「本级别 3买 买入，次级别 一卖 卖出」。
这类方案**一分钟都没测过**，因为仓库里只有 daily 数据。

## 数据能力（实测 2026-10-10）
- `get_stock_kline(market, code, Period.MIN_30, start, count)`，单只 3000 根约 0.3s
- 分页：start=0 → 近 3000 根（约 1.5 年）；start=3000 → 再往前（实测回溯到 2024-09）
- 本脚本每只抓 `--pages` 页 × 3000 根，去重后按时间升序落盘

## 用法
    .venv/bin/python scripts/fetch_minute_data.py --period 30 --pages 2 --workers 2
    .venv/bin/python scripts/fetch_minute_data.py --period 30 --limit 10   # 冒烟

输出：audit_data_min/{code}_30min.json（列：datetime,open,high,low,close,vol）
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

OUT_DIR = ROOT / "audit_data_min"
DAILY_DIR = ROOT / "audit_data"
EXCLUDE = {"sh000300", "sh000001"}
PERIOD_MAP = {"30": Period.MIN_30, "60": Period.MIN_60}
PAGE = 3000


def _market_code(code: str) -> tuple[int, str]:
    """sh600000 -> (1, '600000')；sz000001 -> (0, '000001')。"""
    return (1, code[2:]) if code.startswith("sh") else (0, code[2:])


def _fetch_one(args: tuple[str, int, int]) -> tuple[str, int, str]:
    """抓一只：返回 (code, 根数, 状态说明)。"""
    code, period, pages = args
    mkt, pure = _market_code(code)
    per = PERIOD_MAP[str(period)]
    frames: list[pd.DataFrame] = []
    try:
        c = UnifiedTdxClient()
        c.connect()
        for p in range(pages):
            df = c.get_stock_kline(mkt, pure, per, p * PAGE, PAGE)
            if df is None or df.empty:
                break
            frames.append(df)
            if len(df) < PAGE:
                break
        try:
            c.close()
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        return (code, 0, f"{type(e).__name__}: {e}")

    if not frames:
        return (code, 0, "空")

    df = pd.concat(frames, ignore_index=True)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.drop_duplicates(subset=["datetime"]).sort_values("datetime")
    keep = ["datetime", "open", "high", "low", "close", "vol"]
    df = df[[c for c in keep if c in df.columns]]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{code}_{period}min.json"
    out.write_text(
        json.dumps(
            [{"datetime": str(r["datetime"]), **{k: r[k] for k in df.columns if k != "datetime"}}
             for _, r in df.iterrows()],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return (code, len(df), "OK")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=int, default=30, choices=(30, 60))
    ap.add_argument("--pages", type=int, default=2, help="每只抓几页(每页3000根)")
    ap.add_argument("--limit", type=int, default=0, help="只抓前 N 只（0=全部）")
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args()

    workers = resolve_workers(a.workers)
    codes = [p.name.split("_")[0] for p in sorted(DAILY_DIR.glob("*.json"))]
    codes = [c for c in codes if c not in EXCLUDE]
    if a.limit:
        codes = codes[: a.limit]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"抓取 {len(codes)} 只 × {a.period}min × {a.pages} 页   并行度 {workers}")
    print(f"输出目录 {OUT_DIR}\n")

    jobs = [(c, a.period, a.pages) for c in codes]
    t0 = time.time()
    ok = fail = 0
    rows = []
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, (code, n, st) in enumerate(
            ex.map(_fetch_one, jobs, chunksize=1)
        ):
            rows.append((code, n, st))
            if st == "OK":
                ok += 1
            else:
                fail += 1
            if (i + 1) % 20 == 0 or i + 1 == len(jobs):
                print(f"  进度 {i+1}/{len(jobs)}  成功 {ok}  失败 {fail}", flush=True)

    el = time.time() - t0
    total = sum(n for _, n, _ in rows)
    print(f"\n完成：成功 {ok} / 失败 {fail}，共 {total} 根，耗时 {el:.0f}s")
    if fail:
        bad = [(c, s) for c, n, s in rows if s != "OK"][:5]
        print("失败示例：")
        for c, s in bad:
            print(f"  {c}: {s}")
    if ok == 0:
        print("❌ 一只都没成功 —— 数据地基没建起来，后续多级别回测无从谈起")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
