#!/usr/bin/env python3
"""多级别缠论回测：本级别买点买，次级别卖点卖。

操作方式：
- 日线操作级别：日线买点买入，30分卖点卖出
- 60分操作级别：60分买点买入，15分卖点卖出（如有数据）
- 30分操作级别：30分买点买入，5分卖点卖出（如有数据）

原理（原文区间套）：
- 大级别买点 = 可靠的入场点（趋势转折）
- 小级别卖点 = 及时的出场点（提前锁定利润，不等大级别卖点）
- 比同级别买卖更赚：卖出更早、回撤更小、复利更多
"""
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, "src")
from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import MMDType

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

BUY_TYPES = {MMDType.BUY_1, MMDType.BUY_2, MMDType.BUY_2S, MMDType.BUY_3}
SELL_TYPES = {MMDType.SELL_1, MMDType.SELL_2, MMDType.SELL_2S, MMDType.SELL_3}

TYPE_NAMES = {
    MMDType.BUY_1: "1买", MMDType.BUY_2: "2买", MMDType.BUY_2S: "2买S",
    MMDType.BUY_3: "3买", MMDType.SELL_1: "1卖", MMDType.SELL_2: "2卖",
    MMDType.SELL_2S: "2卖S", MMDType.SELL_3: "3卖",
}

COST_COMM = 0.0005   # 万分之五（用户确认的实际佣金率）
COST_STAMP = 0.001   # 千分之一印花税（卖出，国税固定）
COST_SLIP = 0.0005   # 万分之五滑点（大盘流通股，实测合理）


@dataclass
class Signal:
    """一个买卖点信号。"""
    mmd_type: MMDType
    date: pd.Timestamp
    bar_index: int
    price: float  # 信号点对应的价格（笔端点价格）
    is_buy: bool
    bi_index: int


def load_data(cache_dir: Path, mkt: str, code: str, freq: str) -> pd.DataFrame:
    """加载缓存数据。"""
    fp = cache_dir / f"{mkt.lower()}{code}_{freq}.json"
    if not fp.is_file():
        return pd.DataFrame()
    rows = json.loads(fp.read_text("utf-8"))
    df = pd.DataFrame(rows)
    for col in ("datetime", "date"):
        if col in df.columns:
            df["datetime"] = pd.to_datetime(df[col])
            break
    return df.sort_values("datetime").reset_index(drop=True)


def extract_signals(result, df: pd.DataFrame, bis_list=None) -> list[Signal]:
    """从分析结果提取买卖点信号（含确认延迟）。

    关键修正：信号不用笔端点价格（最优价），而用**下一笔起点**的价格。
    原因：笔端点是分型，分型只有当下一个反向笔开始时才被确认。
    实际操作中你只能在确认后交易，不是在端点处。
    """
    signals = []
    klines = result.klines
    all_bis = bis_list if bis_list is not None else result.bis

    # 建立 bi.index → 下一个bi 的映射
    bi_by_idx = {bi.index: bi for bi in all_bis}
    sorted_indices = sorted(bi_by_idx.keys())

    for mmd in result.mmds:
        if not mmd.bi:
            continue
        bi = mmd.bi
        # 找下一个笔（确认当前笔端点）
        next_bi = None
        pos = sorted_indices.index(bi.index) if bi.index in sorted_indices else -1
        if pos >= 0 and pos + 1 < len(sorted_indices):
            next_bi = bi_by_idx[sorted_indices[pos + 1]]

        if next_bi is None:
            # 没有下一个笔，跳过（无法确认）
            continue

        # 确认bar = 下一笔的起点bar
        confirm_bar = next_bi.start.bar_index
        if confirm_bar < 0 or confirm_bar >= len(klines):
            continue

        date = klines[confirm_bar].date
        date = pd.Timestamp(date)

        # 确认价格 = 确认bar的收盘价（实际能交易的价格）
        price = klines[confirm_bar].close

        is_buy = mmd.mmd_type in BUY_TYPES

        signals.append(Signal(
            mmd_type=mmd.mmd_type,
            date=date,
            bar_index=confirm_bar,
            price=price,
            is_buy=is_buy,
            bi_index=bi.index,
        ))
    return signals


def backtest_multilevel(
    higher_df: pd.DataFrame,
    lower_df: pd.DataFrame,
    higher_signals: list[Signal],
    lower_signals: list[Signal],
    initial_cash: float = 100000,
) -> dict:
    """多级别回测：高级别买点买，低级别卖点卖。

    逻辑：
    1. 按时间遍历高级别买点
    2. 遇到买点 → 买入（用买点日期对应的收盘价）
    3. 持仓期间，寻找该日期之后的第一个低级别卖点
    4. 遇到低级别卖点 → 卖出
    5. 回到步骤1，等下一个高级别买点
    """
    cash = initial_cash
    position = 0.0
    entry_price = 0.0
    entry_date = None
    trades = []  # (buy_date, sell_date, buy_price, sell_price, shares, pnl)

    # 按日期排序
    higher_buys = sorted([s for s in higher_signals if s.is_buy], key=lambda s: s.date)
    lower_sells = sorted([s for s in lower_signals if not s.is_buy], key=lambda s: s.date)

    # 创建日期到收盘价的映射
    higher_dates = {}
    for _, row in higher_df.iterrows():
        d = pd.Timestamp(row["datetime"])
        higher_dates[d.normalize()] = float(row["close"])

    lower_dates = {}
    for _, row in lower_df.iterrows():
        d = pd.Timestamp(row["datetime"])
        lower_dates[d] = float(row["close"])

    for buy_sig in higher_buys:
        if position > 0:
            continue  # 已持仓，跳过

        # 买入：用买点日期当天的收盘价（实际操作中次日开盘买入更现实）
        buy_date = buy_sig.date.normalize()
        # 找买点日期对应的收盘价
        if buy_date not in higher_dates:
            # 找最近的日期
            closest = min(higher_dates.keys(), key=lambda d: abs((d - buy_date).days))
            if abs((closest - buy_date).days) > 3:
                continue
            buy_date = closest
        buy_price = higher_dates[buy_date]
        # 加上滑点
        buy_price *= (1 + COST_SLIP)

        # 计算可买股数（100的整数倍）
        shares = int(cash / (buy_price * (1 + COST_COMM)) / 100) * 100
        if shares <= 0:
            continue
        cost = shares * buy_price * (1 + COST_COMM)
        cash -= cost
        position = shares
        entry_price = buy_price
        entry_date = buy_date

        # 寻找买点日期之后的第一个低级别卖点
        sell_sig = None
        for ls in lower_sells:
            if ls.date > buy_date:
                sell_sig = ls
                break

        if sell_sig is None:
            # 没找到卖点，用数据末尾的价格平仓
            last_date = max(lower_dates.keys()) if lower_dates else buy_date
            if last_date > buy_date:
                sell_price = lower_dates.get(last_date, entry_price)
                sell_price *= (1 - COST_SLIP)
                proceeds = position * sell_price * (1 - COST_COMM - COST_STAMP)
                pnl = proceeds - cost
                cash += proceeds
                trades.append((buy_date, last_date, entry_price, sell_price, position, pnl))
                position = 0
            continue

        # 卖出
        sell_date = sell_sig.date
        # 找卖出日期对应的收盘价
        sell_price = None
        sell_key = sell_date
        if sell_key in lower_dates:
            sell_price = lower_dates[sell_key]
        else:
            # 找最近的时间
            closest = min(lower_dates.keys(), key=lambda d: abs((d - sell_date).total_seconds()))
            if abs((closest - sell_date).total_seconds()) < 3 * 3600:
                sell_price = lower_dates[closest]
                sell_date = closest

        if sell_price is None:
            continue

        sell_price *= (1 - COST_SLIP)
        proceeds = position * sell_price * (1 - COST_COMM - COST_STAMP)
        pnl = proceeds - cost
        cash += proceeds
        trades.append((buy_date, sell_date, entry_price, sell_price, position, pnl))
        position = 0

    # 如果还持仓，用最后的价格平仓
    if position > 0:
        last_date = max(higher_dates.keys()) if higher_dates else None
        if last_date:
            sell_price = higher_dates[last_date] * (1 - COST_SLIP)
            proceeds = position * sell_price * (1 - COST_COMM - COST_STAMP)
            cost = position * entry_price * (1 + COST_COMM)
            pnl = proceeds - cost
            cash += proceeds
            trades.append((entry_date, last_date, entry_price, sell_price, position, pnl))
            position = 0

    # 计算指标
    total_pnl = sum(t[5] for t in trades)
    total_return = total_pnl / initial_cash
    n_trades = len(trades)
    n_win = sum(1 for t in trades if t[5] > 0)
    win_rate = n_win / n_trades * 100 if n_trades > 0 else 0

    # 计算年化
    if higher_df is not None and len(higher_df) > 0:
        start_date = pd.Timestamp(higher_df["datetime"].iloc[0])
        end_date = pd.Timestamp(higher_df["datetime"].iloc[-1])
        n_days = (end_date - start_date).days
        n_years = n_days / 365.25
        annual_return = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0
    else:
        n_years = 0
        annual_return = 0

    # 买入持有
    if len(higher_df) > 0:
        bh_return = higher_df["close"].iloc[-1] / higher_df["close"].iloc[0] - 1
        bh_annual = (1 + bh_return) ** (1 / n_years) - 1 if n_years > 0 else 0
    else:
        bh_return = 0
        bh_annual = 0

    return {
        "initial_cash": initial_cash,
        "final_cash": cash,
        "total_return": total_return,
        "annual_return": annual_return,
        "n_trades": n_trades,
        "win_rate": win_rate,
        "n_years": n_years,
        "bh_return": bh_return,
        "bh_annual": bh_annual,
        "trades": trades,
    }


def main():
    CACHE_D = Path("audit_data")
    CACHE_MIN = Path("audit_data_min")

    print("=" * 100)
    print("  多级别缠论回测：本级别买点买，次级别卖点卖")
    print("=" * 100)

    # === 日线操作级别：日线买+30分卖 ===
    print("\n### 日线买点买入，30分卖点卖出 ###")
    print(f"{'股票':10s} | {'10万→':>10s} | {'累计收益':>10s} | {'年化':>8s} | {'交易':>4s} | {'胜率':>6s} | {'买入持有':>10s}")
    print("-" * 80)

    all_returns = []
    all_bh = []
    total_trades = 0
    for mkt, code, name in STOCKS:
        # 加载数据
        df_daily = load_data(CACHE_D, mkt, code, "daily")
        df_30min = load_data(CACHE_MIN, mkt, code, "30min")

        if df_daily.empty or df_30min.empty:
            print(f"{name:10s} | 无数据")
            continue

        # 找重叠期
        daily_start = pd.Timestamp(df_daily["datetime"].iloc[0])
        daily_end = pd.Timestamp(df_daily["datetime"].iloc[-1])
        min30_start = pd.Timestamp(df_30min["datetime"].iloc[0])
        min30_end = pd.Timestamp(df_30min["datetime"].iloc[-1])

        # 日线买点在整个日线数据范围内
        cfg = ChanlunConfig(zs_from_xd=False)
        analyser_h = ChanlunAnalyser(code=code, frequency="daily", config=cfg)
        result_h = analyser_h.process_klines(df_daily)
        higher_signals = extract_signals(result_h, df_daily)

        # 30分卖点只在重叠期内
        cfg_l = ChanlunConfig(zs_from_xd=False)
        analyser_l = ChanlunAnalyser(code=code, frequency="30min", config=cfg_l)
        result_l = analyser_l.process_klines(df_30min)
        lower_signals = extract_signals(result_l, df_30min)

        # 只保留重叠期内的信号
        overlap_start = max(daily_start, min30_start)
        higher_signals = [s for s in higher_signals if s.date >= overlap_start]
        lower_signals = [s for s in lower_signals if s.date >= overlap_start]

        # 回测
        result = backtest_multilevel(df_daily, df_30min, higher_signals, lower_signals)
        final_val = result["final_cash"]
        total_ret = result["total_return"] * 100
        ann = result["annual_return"] * 100
        n_trades = result["n_trades"]
        win = result["win_rate"]
        bh = result["bh_return"] * 100

        # 买卖持有只在重叠期
        overlap_df = df_daily[df_daily["datetime"] >= overlap_start]
        if len(overlap_df) > 1:
            bh = (overlap_df["close"].iloc[-1] / overlap_df["close"].iloc[0] - 1) * 100
            n_years = result["n_years"]
            # 重新计算重叠期年化
            overlap_days = (pd.Timestamp(overlap_df["datetime"].iloc[-1]) - pd.Timestamp(overlap_df["datetime"].iloc[0])).days
            overlap_years = overlap_days / 365.25
            ann = ((1 + result["total_return"]) ** (1 / overlap_years) - 1) * 100 if overlap_years > 0 else 0
            bh_ann = ((1 + bh / 100) ** (1 / overlap_years) - 1) * 100 if overlap_years > 0 else 0
        else:
            bh_ann = 0

        print(f"{name:10s} | {final_val:10.0f} | {total_ret:+9.1f}% | {ann:7.2f}% | {n_trades:4d} | {win:5.1f}% | {100000*(1+bh/100):10.0f}")
        sys.stdout.flush()
        all_returns.append(total_ret)
        all_bh.append(bh)
        total_trades += n_trades

    if all_returns:
        avg_ret = sum(all_returns) / len(all_returns)
        avg_bh = sum(all_bh) / len(all_bh)
        print("-" * 80)
        print(f"{'平均':10s} | {100000*(1+avg_ret/100):10.0f} | {avg_ret:+9.1f}% | {'':8s} | {total_trades/len(all_returns):4.1f} | {'':6s} | {100000*(1+avg_bh/100):10.0f}")
        print(f"\n10万本金 → 平均变成 {100000*(1+avg_ret/100):.0f} 元（累计赚 {avg_ret:.1f}%）")
        print(f"同期买入持有：{100000*(1+avg_bh/100):.0f} 元（{avg_bh:.1f}%）")

    # === 日线操作级别：日线买+60分卖 ===
    print("\n### 日线买点买入，60分卖点卖出 ###")
    print(f"{'股票':10s} | {'10万→':>10s} | {'累计收益':>10s} | {'年化':>8s} | {'交易':>4s} | {'胜率':>6s} | {'买入持有':>10s}")
    print("-" * 80)

    all_returns2 = []
    all_bh2 = []
    total_trades2 = 0
    for mkt, code, name in STOCKS:
        df_daily = load_data(CACHE_D, mkt, code, "daily")
        df_60min = load_data(CACHE_MIN, mkt, code, "60min")

        if df_daily.empty or df_60min.empty:
            print(f"{name:10s} | 无数据")
            continue

        cfg = ChanlunConfig(zs_from_xd=False)
        analyser_h = ChanlunAnalyser(code=code, frequency="daily", config=cfg)
        result_h = analyser_h.process_klines(df_daily)
        higher_signals = extract_signals(result_h, df_daily)

        cfg_l = ChanlunConfig(zs_from_xd=False)
        analyser_l = ChanlunAnalyser(code=code, frequency="60min", config=cfg_l)
        result_l = analyser_l.process_klines(df_60min)
        lower_signals = extract_signals(result_l, df_60min)

        daily_start = pd.Timestamp(df_daily["datetime"].iloc[0])
        min60_start = pd.Timestamp(df_60min["datetime"].iloc[0])
        overlap_start = max(daily_start, min60_start)
        higher_signals = [s for s in higher_signals if s.date >= overlap_start]
        lower_signals = [s for s in lower_signals if s.date >= overlap_start]

        result = backtest_multilevel(df_daily, df_60min, higher_signals, lower_signals)
        final_val = result["final_cash"]
        total_ret = result["total_return"] * 100
        ann = result["annual_return"] * 100
        n_trades = result["n_trades"]
        win = result["win_rate"]

        overlap_df = df_daily[df_daily["datetime"] >= overlap_start]
        if len(overlap_df) > 1:
            bh = (overlap_df["close"].iloc[-1] / overlap_df["close"].iloc[0] - 1) * 100
            overlap_days = (pd.Timestamp(overlap_df["datetime"].iloc[-1]) - pd.Timestamp(overlap_df["datetime"].iloc[0])).days
            overlap_years = overlap_days / 365.25
            ann = ((1 + result["total_return"]) ** (1 / overlap_years) - 1) * 100 if overlap_years > 0 else 0
        else:
            bh = 0

        print(f"{name:10s} | {final_val:10.0f} | {total_ret:+9.1f}% | {ann:7.2f}% | {n_trades:4d} | {win:5.1f}% | {100000*(1+bh/100):10.0f}")
        sys.stdout.flush()
        all_returns2.append(total_ret)
        all_bh2.append(bh)
        total_trades2 += n_trades

    if all_returns2:
        avg_ret2 = sum(all_returns2) / len(all_returns2)
        avg_bh2 = sum(all_bh2) / len(all_bh2)
        print("-" * 80)
        print(f"{'平均':10s} | {100000*(1+avg_ret2/100):10.0f} | {avg_ret2:+9.1f}% | {'':8s} | {total_trades2/len(all_returns2):4.1f} | {'':6s} | {100000*(1+avg_bh2/100):10.0f}")
        print(f"\n10万本金 → 平均变成 {100000*(1+avg_ret2/100):.0f} 元（累计赚 {avg_ret2:.1f}%）")
        print(f"同期买入持有：{100000*(1+avg_bh2/100):.0f} 元（{avg_bh2:.1f}%）")


    # === 30分操作级别：30分买+5分卖 ===
    print("\n### 30分买点买入，5分卖点卖出 ###")
    print(f"{'股票':10s} | {'10万→':>10s} | {'累计收益':>10s} | {'年化':>8s} | {'交易':>4s} | {'胜率':>6s} | {'买入持有':>10s}")
    print("-" * 80)

    all_returns3 = []
    all_bh3 = []
    total_trades3 = 0
    for mkt, code, name in STOCKS:
        prefix = "sh" if mkt == "SH" else "sz"
        df_30min = load_data(CACHE_MIN, prefix, code, "30min")
        df_5min = load_data(CACHE_MIN, prefix, code, "5min")
        if df_30min.empty or df_5min.empty:
            print(f"{name:10s} | 无数据")
            continue

        cfg = ChanlunConfig()
        analyser_h = ChanlunAnalyser(code=code, frequency="30min", config=cfg)
        result_h = analyser_h.process_klines(df_30min)
        higher_signals = extract_signals(result_h, df_30min, result_h.bis)

        cfg_l = ChanlunConfig()
        analyser_l = ChanlunAnalyser(code=code, frequency="5min", config=cfg_l)
        result_l = analyser_l.process_klines(df_5min)
        lower_signals = extract_signals(result_l, df_5min, result_l.bis)

        h_start = pd.Timestamp(df_30min["datetime"].iloc[0])
        l_start = pd.Timestamp(df_5min["datetime"].iloc[0])
        overlap_start = max(h_start, l_start)
        higher_signals = [s for s in higher_signals if s.date >= overlap_start]
        lower_signals = [s for s in lower_signals if s.date >= overlap_start]

        result = backtest_multilevel(df_30min, df_5min, higher_signals, lower_signals)
        final_val = result["final_cash"]
        total_ret = result["total_return"] * 100
        n_trades = result["n_trades"]
        win = result["win_rate"]
        overlap_df = df_30min[df_30min["datetime"] >= overlap_start]
        if len(overlap_df) > 1:
            bh = (overlap_df["close"].iloc[-1] / overlap_df["close"].iloc[0] - 1) * 100
            overlap_days = (pd.Timestamp(overlap_df["datetime"].iloc[-1]) - pd.Timestamp(overlap_df["datetime"].iloc[0])).days
            oy = overlap_days / 365.25
            ann = ((1 + result["total_return"]) ** (1 / oy) - 1) * 100 if oy > 0 else 0
        else:
            bh = 0; ann = 0
        print(f"{name:10s} | {final_val:10.0f} | {total_ret:+9.1f}% | {ann:7.2f}% | {n_trades:4d} | {win:5.1f}% | {100000*(1+bh/100):10.0f}")
        sys.stdout.flush()
        all_returns3.append(total_ret)
        all_bh3.append(bh)
        total_trades3 += n_trades

    if all_returns3:
        avg3 = sum(all_returns3) / len(all_returns3)
        abh3 = sum(all_bh3) / len(all_bh3)
        print("-" * 80)
        print(f"{'平均':10s} | {100000*(1+avg3/100):10.0f} | {avg3:+9.1f}% | {'':8s} | {total_trades3/len(all_returns3):4.1f} | {'':6s} | {100000*(1+abh3/100):10.0f}")
        print(f"\n10万本金 → 平均变成 {100000*(1+avg3/100):.0f} 元（累计赚 {avg3:.1f}%）")
        print(f"同期买入持有：{100000*(1+abh3/100):.0f} 元（{abh3:.1f}%）")

    # === 60分操作级别：60分买+15分卖 ===
    print("\n### 60分买点买入，15分卖点卖出 ###")
    print(f"{'股票':10s} | {'10万→':>10s} | {'累计收益':>10s} | {'年化':>8s} | {'交易':>4s} | {'胜率':>6s} | {'买入持有':>10s}")
    print("-" * 80)

    all_returns4 = []
    all_bh4 = []
    total_trades4 = 0
    for mkt, code, name in STOCKS:
        prefix = "sh" if mkt == "SH" else "sz"
        df_60min = load_data(CACHE_MIN, prefix, code, "60min")
        df_15min = load_data(CACHE_MIN, prefix, code, "15min")
        if df_60min.empty or df_15min.empty:
            print(f"{name:10s} | 无数据")
            continue

        cfg = ChanlunConfig()
        analyser_h = ChanlunAnalyser(code=code, frequency="60min", config=cfg)
        result_h = analyser_h.process_klines(df_60min)
        higher_signals = extract_signals(result_h, df_60min, result_h.bis)

        cfg_l = ChanlunConfig()
        analyser_l = ChanlunAnalyser(code=code, frequency="15min", config=cfg_l)
        result_l = analyser_l.process_klines(df_15min)
        lower_signals = extract_signals(result_l, df_15min, result_l.bis)

        h_start = pd.Timestamp(df_60min["datetime"].iloc[0])
        l_start = pd.Timestamp(df_15min["datetime"].iloc[0])
        overlap_start = max(h_start, l_start)
        higher_signals = [s for s in higher_signals if s.date >= overlap_start]
        lower_signals = [s for s in lower_signals if s.date >= overlap_start]

        result = backtest_multilevel(df_60min, df_15min, higher_signals, lower_signals)
        final_val = result["final_cash"]
        total_ret = result["total_return"] * 100
        n_trades = result["n_trades"]
        win = result["win_rate"]
        overlap_df = df_60min[df_60min["datetime"] >= overlap_start]
        if len(overlap_df) > 1:
            bh = (overlap_df["close"].iloc[-1] / overlap_df["close"].iloc[0] - 1) * 100
            overlap_days = (pd.Timestamp(overlap_df["datetime"].iloc[-1]) - pd.Timestamp(overlap_df["datetime"].iloc[0])).days
            oy = overlap_days / 365.25
            ann = ((1 + result["total_return"]) ** (1 / oy) - 1) * 100 if oy > 0 else 0
        else:
            bh = 0; ann = 0
        print(f"{name:10s} | {final_val:10.0f} | {total_ret:+9.1f}% | {ann:7.2f}% | {n_trades:4d} | {win:5.1f}% | {100000*(1+bh/100):10.0f}")
        sys.stdout.flush()
        all_returns4.append(total_ret)
        all_bh4.append(bh)
        total_trades4 += n_trades

    if all_returns4:
        avg4 = sum(all_returns4) / len(all_returns4)
        abh4 = sum(all_bh4) / len(all_bh4)
        print("-" * 80)
        print(f"{'平均':10s} | {100000*(1+avg4/100):10.0f} | {avg4:+9.1f}% | {'':8s} | {total_trades4/len(all_returns4):4.1f} | {'':6s} | {100000*(1+abh4/100):10.0f}")
        print(f"\n10万本金 → 平均变成 {100000*(1+avg4/100):.0f} 元（累计赚 {avg4:.1f}%）")
        print(f"同期买入持有：{100000*(1+abh4/100):.0f} 元（{abh4:.1f}%）")


if __name__ == "__main__":
    main()
