#!/usr/bin/env python3
"""历史财报回填打标 —— 对过去多个日期批量计算树粮草分类。

用途：
  为回测提供 point-in-time 的树粮草分类数据。每个历史日期都用当时
  已披露的最新财报（通过 pick_report 的 point-in-time 裁剪），避免未来函数。

存储：
  存入 SQLite 的 changying_marks_history 表（与 changying_marks 并列），
  按 (trade_date, symbol) 唯一，支持多日期共存。

用法：
    # 回填最近4个季末日期
    .venv/bin/python scripts/backfill_marks.py --quarters 4

    # 回填指定日期范围
    .venv/bin/python scripts/backfill_marks.py --start 2025-01-01 --end 2025-12-31

    # 手动指定日期列表
    .venv/bin/python scripts/backfill_marks.py --dates 2025-06-30,2025-12-31,2026-03-31
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DB_PATH = ROOT / "audit_data" / "changying_marks.db"


def _quarter_end_dates(quarters: int) -> list[date]:
    """取最近 N 个季报截止日（3/31, 6/30, 9/30, 12/31）。"""
    today = date.today()
    ends = []
    y, m = today.year, today.month
    for _ in range(quarters * 3):  # 多回溯一些，筛出季末
        m -= 1
        if m <= 0:
            m += 12
            y -= 1
        last_day = {1:31, 2:28, 3:31, 4:30, 5:31, 6:30, 7:31, 8:31, 9:30, 10:31, 11:30, 12:31}
        if m in (3, 6, 9, 12):
            d = date(y, m, last_day[m])
            if d <= today:
                ends.append(d)
    return sorted(ends[:quarters])


def _ensure_history_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS changying_marks_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            market TEXT NOT NULL,
            code TEXT NOT NULL,
            category TEXT NOT NULL,
            score REAL NOT NULL,
            total_mcap_yi REAL,
            report_date TEXT,
            scores_json TEXT,
            details_json TEXT,
            indicators_json TEXT,
            UNIQUE(trade_date, symbol)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_marks_history_date"
        " ON changying_marks_history(trade_date)"
    )
    conn.commit()


def backfill_one(target: date) -> dict:
    """对单个日期跑树粮草分类，存入 history 表。

    使用缓存的 gpcw 财报 + 缓存 K线价格（不连 TDX），只扫已有缓存的股票。
    这比 scan_market 全市场扫描快得多，且不压垮 TDX 服务器。
    """
    import pandas as pd
    from easy_tdx.fundamental.indicators import load_all_periods_frame, pick_report
    from easy_tdx.fundamental.screener import screen_stock
    from easy_tdx.fundamental.pipeline import pick_report_zips

    print(f"  扫描 {target} ...", end=" ", flush=True)

    # 1. 加载 gpcw 财报数据
    zips = pick_report_zips(target)
    if not zips:
        print("❌ 无 gpcw 数据")
        return {"date": str(target), "count": 0, "by_category": {}}

    # 2. 找出所有有缓存的股票
    cache_dir = ROOT / "audit_data"
    stock_files = list(cache_dir.glob("sh*_daily.json")) + list(cache_dir.glob("sz*_daily.json"))

    frame = load_all_periods_frame(zips)
    if frame.empty:
        print("❌ gpcw frame 为空")
        return {"date": str(target), "count": 0, "by_category": {}}

    results = []
    for f in stock_files:
        market = "SH" if f.name.startswith("sh") else "SZ"
        code = f.stem.replace("_daily", "")[2:]  # strip "sh"/"sz" prefix + "_daily" suffix
        try:
            row = pick_report(frame, code, target, market=market)
            if row is None:
                continue
            row_dict = row.to_dict() if hasattr(row, "to_dict") else dict(row)
            # 从缓存取历史收盘价
            import json as _json
            klines = _json.loads(f.read_text("utf-8"))
            # 找 <= target 的最后一条 K线
            closes = [k.get("close", 0) for k in klines if k.get("datetime", k.get("date", "")) <= str(target)]
            if not closes:
                continue
            close = closes[-1]
            screen_row = {"code": code, "market": market, "close": close, **row_dict}
            sr = screen_stock(screen_row)
            if sr and sr.category in ("tree", "grain", "grass"):
                results.append({
                    "market": market,
                    "code": code,
                    "category": sr.category,
                    "score": sr.scores.get(sr.category, 0),
                    "total_mcap_yi": row_dict.get("total_mcap_yi"),
                    "report_date": row_dict.get("report_date"),
                    "scores": sr.scores,
                    "details": sr.as_dict() if hasattr(sr, "as_dict") else {},
                    "indicators": {},
                })
        except Exception:
            continue

    by_cat = {}
    for r in results:
        c = r.get("category", "")
        by_cat[c] = by_cat.get(c, 0) + 1

    conn = sqlite3.connect(str(DB_PATH))
    try:
        _ensure_history_table(conn)
        # 先删该日期旧数据（幂等）
        conn.execute(
            "DELETE FROM changying_marks_history WHERE trade_date = ?",
            (str(target),),
        )
        for r in results:
            conn.execute(
                """INSERT OR REPLACE INTO changying_marks_history
                (trade_date, symbol, market, code, category, score,
                 total_mcap_yi, report_date, scores_json, details_json, indicators_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(target),
                    f"{r.get('market', '')}:{r.get('code', '')}",
                    r.get("market", ""),
                    r.get("code", ""),
                    r.get("category", ""),
                    float(r.get("score", 0)),
                    r.get("total_mcap_yi"),
                    r.get("report_date"),
                    json.dumps(r.get("scores", {}), ensure_ascii=False),
                    json.dumps(r.get("details", {}), ensure_ascii=False),
                    json.dumps(r.get("indicators", {}), ensure_ascii=False),
                ),
            )
        conn.commit()
    finally:
        conn.close()

    print(f"✅ {len(results)} 只 (树={by_cat.get('tree',0)} 粮={by_cat.get('grain',0)} 草={by_cat.get('grass',0)})")
    return {"date": str(target), "count": len(results), "by_category": by_cat}


def list_history() -> None:
    """列出已回填的日期。"""
    if not DB_PATH.exists():
        print("无历史标记数据库")
        return
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            "SELECT trade_date, COUNT(*) as cnt FROM changying_marks_history"
            " GROUP BY trade_date ORDER BY trade_date"
        ).fetchall()
        if not rows:
            print("历史标记表为空")
            return
        print(f"已回填 {len(rows)} 个日期：")
        for d, cnt in rows:
            print(f"  {d}: {cnt} 只")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="历史财报回填打标")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--quarters", type=int, help="回填最近 N 个季报截止日")
    g.add_argument("--dates", type=str, help="逗号分隔的日期列表 (YYYY-MM-DD)")
    g.add_argument("--start", type=str, help="起始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="结束日期 (与 --start 配合)")
    parser.add_argument("--list", action="store_true", help="列出已回填的日期")
    args = parser.parse_args()

    if args.list:
        list_history()
        return

    if args.quarters:
        dates = _quarter_end_dates(args.quarters)
    elif args.dates:
        dates = [date.fromisoformat(d.strip()) for d in args.dates.split(",")]
    elif args.start:
        end = date.fromisoformat(args.end) if args.end else date.today()
        start = date.fromisoformat(args.start)
        # 每月一个日期
        dates = []
        y, m = start.year, start.month
        while date(y, m, 1) <= end:
            last_day = {1:31,2:28,3:31,4:30,5:31,6:30,7:31,8:31,9:30,10:31,11:30,12:31}
            d = date(y, m, min(28, last_day[m]))
            if d <= end:
                dates.append(d)
            m += 1
            if m > 12:
                m = 1
                y += 1
    else:
        parser.print_help()
        return

    print(f"回填 {len(dates)} 个日期：{[str(d) for d in dates]}")
    print()
    summary = []
    for d in dates:
        try:
            summary.append(backfill_one(d))
        except Exception as e:
            print(f"❌ {d} 失败: {e}")
    print()
    print(f"完成：{len(summary)}/{len(dates)} 个日期成功")
    list_history()


if __name__ == "__main__":
    main()
