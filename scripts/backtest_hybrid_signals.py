#!/usr/bin/env python3
"""Hybrid 回测：缠论信号 + 树粮草过滤，测 2025/2026 累计收益。

优化：每只股票只跑一次缠论分析，提取全部信号后按年度切分。
并行：ProcessPoolExecutor workers=2（4核机）。
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from datetime import date
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

DATA_DIR = ROOT / "audit_data"
COMMISSION = 0.0003
STAMP_TAX = 0.001
SLIPPAGE = 0.002


def _analyze_one(args):
    """Worker: 分析单只股票，返回信号列表 + 树粮草分类。"""
    market, code = args
    fp = DATA_DIR / f"{market.lower()}{code}_daily.json"
    if not fp.is_file():
        return {"code": code, "error": "no file"}

    rows = json.loads(fp.read_text("utf-8"))
    df = pd.DataFrame(rows)
    dt_col = "datetime" if "datetime" in df.columns else "date"
    df["datetime"] = pd.to_datetime(df[dt_col])
    df = df.sort_values("datetime").reset_index(drop=True)
    if len(df) < 60:
        return {"code": code, "error": "too short"}

    # 缠论分析（笔构中枢，信号更多）
    cfg = ChanlunConfig(zs_from_xd=False)
    try:
        result = ChanlunAnalyser(code=code, frequency="daily", config=cfg).process_klines(df)
    except Exception as e:
        return {"code": code, "error": str(e)}

    # 提取信号
    signals = []
    for mmd in result.mmds:
        if mmd.bi is None:
            continue
        sig_date = mmd.bi.end.k.date
        mmd_type = mmd.mmd_type.value
        is_buy = "buy" in mmd_type
        is_sell = "sell" in mmd_type
        if not (is_buy or is_sell):
            continue
        sig_ts = pd.Timestamp(sig_date)
        mask = df["datetime"] == sig_ts
        idx = df.index[mask][0] if len(df.index[mask]) > 0 else \
              df.index.get_indexer([sig_ts], method="nearest")[0]
        signals.append({"idx": int(idx), "date": sig_date, "type": mmd_type,
                        "is_buy": is_buy, "is_sell": is_sell})

    # 树粮草分类（用 gpcw）
    category = None
    try:
        from easy_tdx.fundamental.indicators import load_all_periods_frame, pick_report
        from easy_tdx.fundamental.screener import screen_stock
        from easy_tdx.fundamental.pipeline import pick_report_zips
        zips = pick_report_zips(date.today())
        frame = load_all_periods_frame(zips)
        if frame is not None and not frame.empty:
            for target in [date(2025,6,30), date(2026,6,30)]:
                row = pick_report(frame, code, target, market=market)
                if row is not None:
                    row_dict = row.to_dict() if hasattr(row, "to_dict") else dict(row)
                    sr = screen_stock({"code": code, "market": market, "close": 10.0, **row_dict})
                    if sr and sr.category in ("tree", "grain", "vegetable"):
                        category = sr.category
                        break
    except Exception:
        pass

    # 保存 df 的 open/close 价格序列（按年度）
    yearly_data = {}
    for year in [2025, 2026]:
        yd = df[df["datetime"].dt.year == year].copy()
        if len(yd) < 5:
            continue
        yearly_data[year] = {
            "dates": yd["datetime"].dt.strftime("%Y-%m-%d").tolist(),
            "opens": yd["open"].astype(float).tolist(),
            "closes": yd["close"].astype(float).tolist(),
        }

    return {
        "code": code, "market": market, "category": category,
        "signals": signals, "yearly_data": yearly_data,
        "total_bars": len(df),
    }


def simulate_year(analysis: dict, year: int) -> dict:
    """对单只股票在指定年度模拟交易。"""
    yd = analysis.get("yearly_data", {}).get(str(year)) or \
         analysis.get("yearly_data", {}).get(year)
    if not yd:
        return {"code": analysis["code"], "error": f"no {year} data"}

    dates = yd["dates"]
    opens = yd["opens"]
    closes = yd["closes"]
    n_bars = len(dates)

    # 该年度的信号（按 idx 映射到年度内位置）
    signals = []
    for sig in analysis["signals"]:
        sig_date = sig["date"]
        if hasattr(sig_date, "year") and sig_date.year != year:
            continue
        sig_date_str = sig_date.strftime("%Y-%m-%d") if hasattr(sig_date, "strftime") else str(sig_date)
        # 找在年度数据中的位置
        try:
            pos = dates.index(sig_date_str)
        except ValueError:
            continue
        signals.append({"pos": pos, "type": sig["type"],
                        "is_buy": sig["is_buy"], "is_sell": sig["is_sell"]})

    signals.sort(key=lambda s: s["pos"])

    category = analysis.get("category")
    cash = 100000.0
    position = 0
    entry_price = 0.0
    trades = []

    for sig in signals:
        exec_pos = sig["pos"] + 1  # 次日执行
        if exec_pos >= n_bars:
            continue

        if sig["is_buy"] and position == 0:
            if category not in ("tree", "grain"):
                continue  # vegetable 不买
            buy_price = opens[exec_pos] * (1 + SLIPPAGE)
            if buy_price <= 0:
                continue
            shares = int(cash * (1 - COMMISSION) / (buy_price * 100)) * 100
            if shares <= 0:
                continue
            cash -= shares * buy_price * (1 + COMMISSION)
            position = shares
            entry_price = buy_price
            trades.append({"action": "buy", "date": dates[exec_pos], "price": buy_price, "signal": sig["type"]})

        elif sig["is_sell"] and position > 0:
            sell_price = opens[exec_pos] * (1 - SLIPPAGE)
            if sell_price <= 0:
                continue
            cash += position * sell_price * (1 - COMMISSION - STAMP_TAX)
            pnl = (sell_price / entry_price - 1) * 100
            trades.append({"action": "sell", "date": dates[exec_pos], "price": sell_price,
                          "signal": sig["type"], "pnl_pct": pnl})
            position = 0
            entry_price = 0.0

    # 年末清仓
    if position > 0:
        sell_price = closes[-1] * (1 - SLIPPAGE)
        cash += position * sell_price * (1 - COMMISSION - STAMP_TAX)
        pnl = (sell_price / entry_price - 1) * 100
        trades.append({"action": "sell", "date": "year_end", "price": sell_price,
                      "signal": "year_end", "pnl_pct": pnl})
        position = 0

    # 买入持有
    bh_open = opens[0]
    bh_close = closes[-1]
    bh_ret = (bh_close / bh_open - 1) * 100 if bh_open > 0 else 0

    ret = (cash / 100000.0 - 1) * 100
    wins = sum(1 for t in trades if t["action"] == "sell" and t.get("pnl_pct", 0) > 0)
    sells = sum(1 for t in trades if t["action"] == "sell")

    return {
        "code": analysis["code"], "category": category,
        "return_pct": ret, "bh_return_pct": bh_ret, "excess": ret - bh_ret,
        "trades": len(trades), "wins": wins, "sells": sells,
        "n_signals": len(signals),
    }


def main():
    stock_files = sorted(DATA_DIR.glob("*_daily.json"))
    stock_list = []
    for f in stock_files:
        name = f.stem.replace("_daily", "")
        market = "SH" if name.startswith("sh") else "SZ"
        code = name[2:]
        if len(code) == 6:
            stock_list.append((market, code))

    total = len(stock_list)
    print(f"共 {total} 只标的")
    print(f"策略: 笔构中枢(zs_from_xd=False) + 树粮草过滤(只买tree/grain)")
    print(f"执行: 信号次日开盘价 | 成本: 佣金{COMMISSION*100}%+滑点{SLIPPAGE*100}%+印花税{STAMP_TAX*100}%")
    print(f"并行: workers=2\n")

    # 并行分析（带缓存）
    cache_file = ROOT / "audit_data" / "hybrid_analysis_cache.pkl"
    if cache_file.is_file():
        print("加载缓存分析结果...", end=" ", flush=True)
        import pickle
        with open(cache_file, "rb") as f:
            analyses = pickle.load(f)
        print(f"✅ {len(analyses)} 只")
    else:
        t0 = time.time()
        analyses = []
        with ProcessPoolExecutor(max_workers=2) as ex:
            futures = {ex.submit(_analyze_one, (m, c)): (m, c) for m, c in stock_list}
            for i, fut in enumerate(as_completed(futures)):
                r = fut.result()
                if "error" not in r:
                    analyses.append(r)
                if (i + 1) % 50 == 0 or i + 1 == total:
                    print(f"  分析进度: {i+1}/{total} ({time.time()-t0:.0f}s)", flush=True)
        print(f"  分析完成: {len(analyses)}/{total} ({time.time()-t0:.0f}s)")
        # 保存缓存
        import pickle
        with open(cache_file, "wb") as f:
            pickle.dump(analyses, f)
        print(f"  缓存已保存: {cache_file}")

    # 分类统计
    from collections import Counter
    cats = Counter(a.get("category") for a in analyses)
    print(f"  树粮草: {dict(cats)}")

    # 分年度模拟
    for year in [2025, 2026]:
        print(f"\n{'='*70}")
        print(f"  {year} 年回测")
        print(f"{'='*70}")

        results = []
        for a in analyses:
            r = simulate_year(a, year)
            if "error" not in r:
                results.append(r)

        traded = [r for r in results if r["trades"] > 0]
        tg_traded = [r for r in traded if r["category"] in ("tree", "grain")]

        if tg_traded:
            avg_ret = sum(r["return_pct"] for r in tg_traded) / len(tg_traded)
            avg_bh = sum(r["bh_return_pct"] for r in tg_traded) / len(tg_traded)
            avg_excess = avg_ret - avg_bh
            total_wins = sum(r["wins"] for r in tg_traded)
            total_sells = sum(r["sells"] for r in tg_traded)
            wr = total_wins / total_sells * 100 if total_sells else 0
            positive = sum(1 for r in tg_traded if r["return_pct"] > 0)
            beat_bh = sum(1 for r in tg_traded if r["excess"] > 0)
        else:
            avg_ret = avg_bh = avg_excess = wr = 0
            positive = beat_bh = total_wins = total_sells = 0

        # 等权组合（含空仓的 tree/grain）
        tg_all = [r for r in results if r["category"] in ("tree", "grain")]
        if tg_all:
            port_ret = sum(r["return_pct"] for r in tg_all) / len(tg_all)
            port_bh = sum(r["bh_return_pct"] for r in tg_all) / len(tg_all)
        else:
            port_ret = port_bh = 0

        print(f"  总标的: {len(results)} | 有交易: {len(traded)} | tree/grain有交易: {len(tg_traded)}")
        print(f"  总交易: {sum(r['trades'] for r in tg_traded)} | 总卖出: {total_sells} | 胜率: {wr:.1f}%")
        print(f"")
        print(f"  📊 有交易标的平均:  收益 {avg_ret:+.2f}% | BH {avg_bh:+.2f}% | 超额 {avg_excess:+.2f}%")
        print(f"  📊 等权组合(含空仓): 收益 {port_ret:+.2f}% | BH {port_bh:+.2f}% | 超额 {port_ret-port_bh:+.2f}%")
        print(f"  📊 正收益: {positive}/{len(tg_traded)} | 跑赢BH: {beat_bh}/{len(tg_traded)}")

        if tg_traded:
            sr = sorted(tg_traded, key=lambda r: r["return_pct"], reverse=True)
            print(f"\n  🏆 Top 5:")
            for r in sr[:5]:
                print(f"    {r['code']} cat={r['category']} 收益={r['return_pct']:+.2f}% BH={r['bh_return_pct']:+.2f}% 交易={r['trades']}")
            print(f"  💀 Bottom 5:")
            for r in sr[-5:]:
                print(f"    {r['code']} cat={r['category']} 收益={r['return_pct']:+.2f}% BH={r['bh_return_pct']:+.2f}% 交易={r['trades']}")


if __name__ == "__main__":
    main()
