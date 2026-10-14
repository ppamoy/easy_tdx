#!/usr/bin/env python3
"""30分钟级别 Hybrid 回测——TDX 实时取数 + 缠论30min分析 + 树粮草过滤。

用户要求："30分钟级别买，次级别卖"
本脚本用 30min 缠论买卖点信号做交易，测 2025/2026 累计收益。

流程：
1. 从 TDX API 取 30min K线（2025-01-01 ~ 2026-09-30），缓存到本地
2. 对每只跑缠论分析（zs_from_xd=False 笔构中枢）
3. 用缓存的树粮草分类做过滤（只买 tree/grain）
4. 模拟交易：买入信号次根K线开盘买，卖出信号次根K线开盘卖
5. 分年度统计收益

成本：佣金0.03% + 滑点0.2% + 印花税0.1%（卖出）
"""

from __future__ import annotations

import json
import sys
import time
import pickle
import urllib.request
import warnings
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

DATA_DIR = ROOT / "audit_data"
CACHE_30M = DATA_DIR / "kline_30min"
COMMISSION = 0.0003
STAMP_TAX = 0.001
SLIPPAGE = 0.002
API_BASE = "http://127.0.0.1:8001/api/v1"


def fetch_30min(market: str, code: str) -> pd.DataFrame | None:
    """从 TDX API 取 30min K线，缓存到本地。"""
    cache_file = CACHE_30M / f"{market.lower()}{code}_30min.json"
    if cache_file.is_file():
        rows = json.loads(cache_file.read_text("utf-8"))
    else:
        url = f"{API_BASE}/bars?market={market}&code={code}&category=MIN_30&start_date=2025-01-01&end_date=2026-09-30"
        try:
            data = json.loads(urllib.request.urlopen(url, timeout=15).read())
            rows = data.get("data", [])
            if not rows:
                return None
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(rows), "utf-8")
        except Exception:
            return None

    df = pd.DataFrame(rows)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"])
    elif "date" in df.columns:
        df["datetime"] = pd.to_datetime(df["date"])
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


def analyze_30min(args):
    """Worker: 取30min数据 + 跑缠论分析，返回信号 + 树粮草分类。"""
    market, code, category = args

    df = fetch_30min(market, code)
    if df is None or len(df) < 60:
        return {"code": code, "error": "no 30min data"}

    cfg = ChanlunConfig(zs_from_xd=False)
    try:
        result = ChanlunAnalyser(code=code, frequency="30min", config=cfg).process_klines(df)
    except Exception as e:
        return {"code": code, "error": str(e)}

    # 提取信号
    signals = []
    for mmd in result.mmds:
        if mmd.bi is None:
            continue
        sig_ts = mmd.bi.end.k.date  # datetime
        mmd_type = mmd.mmd_type.value
        is_buy = "buy" in mmd_type
        is_sell = "sell" in mmd_type
        if not (is_buy or is_sell):
            continue
        # 找信号在 df 中的 index
        mask = df["datetime"] == sig_ts
        if len(df.index[mask]) > 0:
            idx = int(df.index[mask][0])
        else:
            idx = int(df.index.get_indexer([sig_ts], method="nearest")[0])
        signals.append({
            "idx": idx,
            "dt": sig_ts.isoformat(),
            "type": mmd_type,
            "is_buy": is_buy,
            "is_sell": is_sell,
        })

    # 保存年度数据（opens/closes 按 30min bar）
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
        "signals": signals,
        "yearly_data": yearly_data,
        "total_bars": len(df),
        "n_bi": len(result.bis),
        "n_zs": len(result.zss),
        "n_mmd": len(result.mmds),
    }


def simulate_year_30min(analysis: dict, year: int) -> dict:
    """对单只股票在指定年度模拟30min级别交易。"""
    yd = analysis.get("yearly_data", {}).get(str(year))
    if not yd:
        return {"code": analysis["code"], "error": f"no {year} data"}

    dts = yd["dts"]
    opens = yd["opens"]
    closes = yd["closes"]
    n_bars = len(dts)

    # 该年度的信号
    signals = []
    for sig in analysis["signals"]:
        sig_dt = sig["dt"]
        if str(year) not in sig_dt:
            continue
        try:
            pos = dts.index(sig_dt)
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
        exec_pos = sig["pos"] + 1  # 次根K线执行
        if exec_pos >= n_bars:
            continue

        if sig["is_buy"] and position == 0:
            if category not in ("tree", "grain"):
                continue
            buy_price = opens[exec_pos] * (1 + SLIPPAGE)
            if buy_price <= 0:
                continue
            shares = int(cash * (1 - COMMISSION) / (buy_price * 100)) * 100
            if shares <= 0:
                continue
            cash -= shares * buy_price * (1 + COMMISSION)
            position = shares
            entry_price = buy_price
            trades.append({"action": "buy", "dt": dts[exec_pos], "price": buy_price, "signal": sig["type"]})

        elif sig["is_sell"] and position > 0:
            sell_price = opens[exec_pos] * (1 - SLIPPAGE)
            if sell_price <= 0:
                continue
            cash += position * sell_price * (1 - COMMISSION - STAMP_TAX)
            pnl = (sell_price / entry_price - 1) * 100
            trades.append({"action": "sell", "dt": dts[exec_pos], "price": sell_price,
                          "signal": sig["type"], "pnl_pct": pnl})
            position = 0
            entry_price = 0.0

    # 年末清仓（最后一根K线收盘）
    if position > 0:
        sell_price = closes[-1] * (1 - SLIPPAGE)
        cash += position * sell_price * (1 - COMMISSION - STAMP_TAX)
        pnl = (sell_price / entry_price - 1) * 100
        trades.append({"action": "sell", "dt": "year_end", "price": sell_price,
                      "signal": "year_end", "pnl_pct": pnl})
        position = 0

    # 买入持有（年度第一根open到最后一根close）
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
    # 加载标的列表
    stock_files = sorted(DATA_DIR.glob("*_daily.json"))
    stock_list = []
    for f in stock_files:
        name = f.stem.replace("_daily", "")
        market = "SH" if name.startswith("sh") else "SZ"
        code = name[2:]
        if len(code) == 6:
            stock_list.append((market, code))

    # 加载树粮草分类（从缓存的日线分析中取）
    daily_cache = DATA_DIR / "hybrid_analysis_cache.pkl"
    category_map = {}
    if daily_cache.is_file():
        with open(daily_cache, "rb") as f:
            daily_analyses = pickle.load(f)
        for a in daily_analyses:
            category_map[a["code"]] = a.get("category")

    total = len(stock_list)
    print(f"共 {total} 只标的")
    print(f"策略: 30min级别缠论(zs_from_xd=False) + 树粮草过滤(只买tree/grain)")
    print(f"执行: 信号次根K线开盘价 | 成本: 佣金{COMMISSION*100}%+滑点{SLIPPAGE*100}%+印花税{STAMP_TAX*100}%")
    print(f"数据源: TDX API (30min K线)")
    print(f"分类: {sum(1 for v in category_map.values() if v)} 只有分类\n")

    # 准备参数（market, code, category）
    args_list = [(m, c, category_map.get(c)) for m, c in stock_list]

    # 并行分析（带缓存）
    cache_file = DATA_DIR / "hybrid_30min_cache.pkl"
    if cache_file.is_file():
        print("加载缓存30min分析结果...", end=" ", flush=True)
        with open(cache_file, "rb") as f:
            analyses = pickle.load(f)
        print(f"✅ {len(analyses)} 只")
    else:
        t0 = time.time()
        analyses = []
        with ProcessPoolExecutor(max_workers=2) as ex:
            futures = {ex.submit(analyze_30min, args): args for args in args_list}
            for i, fut in enumerate(as_completed(futures)):
                r = fut.result()
                if "error" not in r:
                    analyses.append(r)
                if (i + 1) % 30 == 0 or i + 1 == total:
                    print(f"  分析进度: {i+1}/{total} ({time.time()-t0:.0f}s)", flush=True)
        print(f"  分析完成: {len(analyses)}/{total} ({time.time()-t0:.0f}s)")
        with open(cache_file, "wb") as f:
            pickle.dump(analyses, f)
        print(f"  缓存已保存: {cache_file}")

    # 统计
    from collections import Counter
    cats = Counter(a.get("category") for a in analyses)
    total_bars = sum(a.get("total_bars", 0) for a in analyses)
    total_signals = sum(a.get("n_mmd", 0) for a in analyses)
    print(f"  树粮草: {dict(cats)}")
    print(f"  总30min bars: {total_bars} | 总信号: {total_signals}\n")

    # 分年度模拟
    for year in [2025, 2026]:
        print(f"{'='*70}")
        print(f"  {year} 年 30min 级别回测")
        print(f"{'='*70}")

        results = []
        for a in analyses:
            r = simulate_year_30min(a, year)
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
                print(f"    {r['code']} cat={r['category']} 收益={r['return_pct']:+.2f}% BH={r['bh_return_pct']:+.2f}% 交易={r['trades']} 信号={r['n_signals']}")
            print(f"  💀 Bottom 5:")
            for r in sr[-5:]:
                print(f"    {r['code']} cat={r['category']} 收益={r['return_pct']:+.2f}% BH={r['bh_return_pct']:+.2f}% 交易={r['trades']} 信号={r['n_signals']}")


if __name__ == "__main__":
    main()
