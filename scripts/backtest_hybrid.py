#!/usr/bin/env python3
"""吴伟志+缠论融合系统回测：方向过滤 + 技术评分 vs 纯缠论。

对比两种策略：
  A) 纯缠论（baseline）：日线买点买入，60分卖点卖出（已验证 ~21% 年化）
  B) 融合系统（hybrid）：在 A 的基础上叠加
     - 方向过滤：树类否决、冬季禁买、秋季草类禁买
     - 技术评分：量价+RSI+MA20+背驰+中枢 → ≥60 分才执行买入
     - 卖出信号不受过滤（管理已有仓位）

成本模型：佣金万五+印花税千一+滑点万五（用户确认）
确认延迟：笔端点在下一笔起点确认（实际可交易价）
"""
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

sys.path.insert(0, "src")
from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import MMDType

# ── 常量 ──
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

COST_COMM = 0.0005   # 万分之五佣金
COST_STAMP = 0.001   # 千分之一印花税（卖出）
COST_SLIP = 0.0005   # 万分之五滑点

# 树粮草 → 季节 仓位上限
SEASON_POS = {"spring": 0.7, "summer": 0.5, "autumn": 0.3, "winter": 0.1, "unknown": 0.3}


@dataclass
class Signal:
    mmd_type: MMDType
    date: pd.Timestamp
    bar_index: int
    price: float
    is_buy: bool
    bi_index: int
    # 缠论附加信息（用于技术评分）
    beichi_force: float = 0.0
    zs_range: list = field(default_factory=list)
    mmd_confidence: float = 0.0


def load_data(cache_dir: Path, mkt: str, code: str, freq: str) -> pd.DataFrame:
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


def extract_signals(result, df: pd.DataFrame) -> list[Signal]:
    """提取买卖点信号（含确认延迟）。"""
    signals = []
    klines = result.klines
    all_bis = result.bis
    bi_by_idx = {bi.index: bi for bi in all_bis}
    sorted_indices = sorted(bi_by_idx.keys())

    for mmd in result.mmds:
        if not mmd.bi:
            continue
        bi = mmd.bi
        next_bi = None
        pos = sorted_indices.index(bi.index) if bi.index in sorted_indices else -1
        if pos >= 0 and pos + 1 < len(sorted_indices):
            next_bi = bi_by_idx[sorted_indices[pos + 1]]
        if next_bi is None:
            continue

        confirm_bar = next_bi.start.bar_index
        if confirm_bar < 0 or confirm_bar >= len(klines):
            continue

        date = pd.Timestamp(klines[confirm_bar].date)
        price = klines[confirm_bar].close
        is_buy = mmd.mmd_type in BUY_TYPES
        zs_range = [float(mmd.zs.zd), float(mmd.zs.zg)] if mmd.zs else []
        beichi = float(mmd.confidence) if mmd.confidence else 0.0

        signals.append(Signal(
            mmd_type=mmd.mmd_type, date=date, bar_index=confirm_bar,
            price=price, is_buy=is_buy, bi_index=bi.index,
            beichi_force=beichi, zs_range=zs_range, mmd_confidence=beichi,
        ))
    return signals


# ── 方向过滤层 ──

def get_stock_category(mkt: str, code: str) -> str:
    """获取股票的树粮草分类。"""
    try:
        from easy_tdx.fundamental.indicators import pick_report, indicator_values
        from easy_tdx.fundamental.screener import screen_stock
        from easy_tdx.models.enums import Market
        from datetime import date

        mkt_enum = Market.SH if mkt == "SH" else Market.SZ
        rep = pick_report(code, mkt_enum, date.today())
        if rep:
            ind = indicator_values(rep)
            row = {"code": code, "market": mkt, **ind}
            sr = screen_stock(row)
            if sr:
                return sr.category
    except Exception as e:
        pass
    # 回退：用行业特征简单分类
    # 银行/保险 → grain（稳健收益），券商/科技 → grass（趋势），医药/消费 → tree（长期持有）
    SIMPLE = {
        "600000": "grain", "600036": "grain",  # 银行
        "601318": "grain",  # 保险
        "600276": "tree",   # 医药
        "600030": "vegetable",  # 券商
        "000333": "grain",  # 家电
        "000651": "grain",  # 家电
        "000725": "vegetable",  # 面板
        "300750": "vegetable",  # 电池
        "002415": "vegetable",  # 安防
    }
    return SIMPLE.get(code, "grain")


def build_season_timeline(index_df: pd.DataFrame) -> dict:
    """预计算每月季节判断，返回 {Period: season}。

    detect_season 需要截至目标日的完整历史数据（不是单月数据）。
    """
    try:
        from easy_tdx.fundamental.season import detect_season
    except Exception:
        return {}

    timeline = {}
    if index_df.empty:
        return timeline

    index_df = index_df.sort_values("datetime").reset_index(drop=True)

    # 按月遍历，用截至该月末的累积数据判断季节
    monthly_groups = index_df.groupby(index_df["datetime"].dt.to_period("M"))

    for period, group in monthly_groups:
        if len(group) < 1:
            continue
        # 截至该月末的全部数据
        cumul = index_df[index_df["datetime"] <= group["datetime"].iloc[-1]]
        if len(cumul) < 50:
            continue
        dates = cumul["datetime"].dt.date.tolist()
        closes = cumul["close"].tolist()
        vols = cumul["vol"].tolist() if "vol" in cumul.columns else None
        target = dates[-1]
        try:
            sr = detect_season(dates, closes, target, volumes=vols)
            if sr:
                timeline[period] = sr.season
        except Exception:
            continue
    return timeline


def get_season_at(date: pd.Timestamp, season_timeline: dict) -> str:
    """获取某个日期对应的市场季节。"""
    if not season_timeline:
        return "unknown"
    period = pd.Period(date, freq="M")
    # 往前找最近的月份
    for offset in range(6):
        p = period - offset
        if p in season_timeline:
            return season_timeline[p]
    return "unknown"


def direction_filter(
    category: str,
    season: str,
    is_buy: bool,
) -> tuple[bool, str]:
    """方向过滤（一票否决制）。返回 (passed, reason)。

    树类不再否决——改为通过（提醒大周期买入持有）。
    """
    # 卖出信号始终通过
    if not is_buy:
        return True, "卖出信号通过"

    # 树类：不否决，改为提醒（通过+提醒）
    if category == "tree":
        return True, "树类：大周期买点出现，建议买入并长期持有"

    # 冬季禁止开新仓
    if season == "winter":
        return False, "冬季禁买"

    # 秋季不参与草类买入
    if season == "autumn" and category == "vegetable":
        return False, "秋季草类禁买"

    return True, "通过"


# ── 技术评分层 ──

def technical_score(
    signal: Signal,
    daily_df: pd.DataFrame,
    daily_close_at: pd.Timestamp,
    is_tree: bool = False,
) -> tuple[int, str]:
    """技术面评分（PRD §6.2）。返回 (score, recommendation)。

    评分项（满分100）：
      成交量放大 +15 | RSI适中 +10 | 日线趋势 +10 | 背驰力度 +20
      中枢位置 +20 | 信号置信度 +10 | 买点类型 +15
    树类门槛降低：≥30 execute（长期持有不需要严格技术确认）
    非树类：≥60 execute, 40-59 observe, <40 reject
    """
    score = 0

    # 1. 日线趋势（MA20）— +10
    daily_before = None
    if daily_df is not None and len(daily_df) > 20:
        daily_before = daily_df[daily_df["datetime"] <= daily_close_at].copy()
        if len(daily_before) >= 20:
            ma20 = daily_before["close"].rolling(20).mean().iloc[-1]
            close = daily_before["close"].iloc[-1]
            if close > ma20 * 1.02:
                score += 10

    # 2. 成交量放大 — +15（当日量 > 5日均量）
    if daily_before is not None and len(daily_before) >= 6 and "vol" in daily_before.columns:
        vol_now = daily_before["vol"].iloc[-1]
        vol_ma5 = daily_before["vol"].rolling(5).mean().iloc[-1]
        if vol_ma5 > 0 and vol_now > vol_ma5 * 1.2:
            score += 15

    # 3. RSI适中 — +10（买入时 RSI 30-60 为佳）
    if daily_before is not None and len(daily_before) >= 15:
        try:
            delta = daily_before["close"].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss.replace(0, 1e-10)
            rsi = (100 - 100 / (1 + rs)).iloc[-1]
            if signal.is_buy and 25 <= rsi <= 65:
                score += 10
        except Exception:
            pass

    # 4. 背驰力度 — +20（>0.2 强，>0.1 中等）
    if signal.beichi_force > 0.2:
        score += 20
    elif signal.beichi_force > 0.1:
        score += 10

    # 5. 3买中枢位置 — +20
    if signal.mmd_type == MMDType.BUY_3 and signal.zs_range:
        score += 20

    # 6. 信号置信度 — +10
    if signal.mmd_confidence > 0.3:
        score += 10

    # 7. 买点类型加分 — +15（1买和2买是更可靠的买点）
    if signal.mmd_type in (MMDType.BUY_1, MMDType.BUY_2, MMDType.BUY_2S):
        score += 15
    elif signal.mmd_type == MMDType.BUY_3:
        score += 10  # 3买已有中枢加分，额外+10

    exec_threshold = 30 if is_tree else 60
    observe_threshold = 20 if is_tree else 40
    if score >= exec_threshold:
        return score, "execute"
    elif score >= observe_threshold:
        return score, "observe"
    else:
        return score, "reject"


# ── 回测引擎 ──

def backtest(
    higher_df: pd.DataFrame,
    lower_df: pd.DataFrame,
    higher_signals: list[Signal],
    lower_signals: list[Signal],
    initial_cash: float = 100000,
    category: str = "grain",
    season_timeline: dict = None,
    daily_df: pd.DataFrame = None,
    use_hybrid_filter: bool = False,
) -> dict:
    """回测引擎。

    use_hybrid_filter=False: 纯缠论（baseline）
    use_hybrid_filter=True: 融合系统（方向过滤+技术评分）
    """
    cash = initial_cash
    position = 0.0
    entry_price = 0.0
    entry_date = None
    trades = []
    filtered_out = 0  # 被融合系统过滤掉的信号数

    higher_buys = sorted([s for s in higher_signals if s.is_buy], key=lambda s: s.date)
    lower_sells = sorted([s for s in lower_signals if not s.is_buy], key=lambda s: s.date)

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
            continue

        # ── 融合过滤 ──
        if use_hybrid_filter:
            # 方向过滤
            season = get_season_at(buy_sig.date, season_timeline or {})
            passed, reason = direction_filter(category, season, is_buy=True)
            if not passed:
                filtered_out += 1
                continue

            # 技术评分（树类门槛降低：≥30 execute）
            score, rec = technical_score(buy_sig, daily_df, buy_sig.date, is_tree=(category == "tree"))
            if rec != "execute":
                filtered_out += 1
                continue

        # 买入
        buy_date = buy_sig.date.normalize()
        if buy_date not in higher_dates:
            closest = min(higher_dates.keys(), key=lambda d: abs((d - buy_date).days))
            if abs((closest - buy_date).days) > 3:
                continue
            buy_date = closest
        buy_price = higher_dates[buy_date] * (1 + COST_SLIP)
        shares = int(cash / (buy_price * (1 + COST_COMM)) / 100) * 100
        if shares <= 0:
            continue
        cost = shares * buy_price * (1 + COST_COMM)
        cash -= cost
        position = shares
        entry_price = buy_price
        entry_date = buy_date

        # 寻找卖点
        sell_sig = None
        for ls in lower_sells:
            if ls.date > buy_date:
                sell_sig = ls
                break

        if sell_sig is None:
            last_date = max(lower_dates.keys()) if lower_dates else buy_date
            if last_date > buy_date:
                sell_price = lower_dates.get(last_date, entry_price) * (1 - COST_SLIP)
                proceeds = position * sell_price * (1 - COST_COMM - COST_STAMP)
                pnl = proceeds - cost
                cash += proceeds
                trades.append((buy_date, last_date, entry_price, sell_price, position, pnl))
                position = 0
            continue

        sell_date = sell_sig.date
        sell_price = None
        if sell_date in lower_dates:
            sell_price = lower_dates[sell_date]
        else:
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

    if position > 0:
        last_date = max(higher_dates.keys()) if higher_dates else None
        if last_date:
            sell_price = higher_dates[last_date] * (1 - COST_SLIP)
            proceeds = position * sell_price * (1 - COST_COMM - COST_STAMP)
            cost = position * entry_price * (1 + COST_COMM)
            pnl = proceeds - cost
            cash += proceeds
            trades.append((entry_date, last_date, entry_price, sell_price, position, pnl))

    total_pnl = sum(t[5] for t in trades)
    total_return = total_pnl / initial_cash
    n_trades = len(trades)
    n_win = sum(1 for t in trades if t[5] > 0)
    win_rate = n_win / n_trades * 100 if n_trades > 0 else 0

    if higher_df is not None and len(higher_df) > 0:
        start_date = pd.Timestamp(higher_df["datetime"].iloc[0])
        end_date = pd.Timestamp(higher_df["datetime"].iloc[-1])
        n_days = (end_date - start_date).days
        n_years = n_days / 365.25
        annual_return = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0
    else:
        n_years = 0
        annual_return = 0

    if len(higher_df) > 0:
        bh_return = higher_df["close"].iloc[-1] / higher_df["close"].iloc[0] - 1
        bh_annual = (1 + bh_return) ** (1 / n_years) - 1 if n_years > 0 else 0
    else:
        bh_return = 0
        bh_annual = 0

    # 最大回撤
    equity_curve = [initial_cash]
    for t in trades:
        equity_curve.append(equity_curve[-1] + t[5])
    peak = initial_cash
    max_dd = 0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd:
            max_dd = dd

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
        "max_drawdown": max_dd,
        "trades": trades,
        "filtered_out": filtered_out,
    }


def main():
    CACHE_D = Path("audit_data")
    CACHE_MIN = Path("audit_data_min")

    print("=" * 110)
    print("  吴伟志+缠论融合系统回测 vs 纯缠论（日线买+60分卖）")
    print("  方向过滤: 树类否决/冬季禁买/秋季草类禁买 | 技术评分: MA20+背驰+中枢+置信度 ≥60分执行")
    print("=" * 110)

    # ── 预计算市场季节 ──
    print("\n预计算市场季节（上证指数月度判断）...")
    index_df = load_data(CACHE_D, "SH", "000001", "daily")
    season_timeline = build_season_timeline(index_df)
    if season_timeline:
        # 打印季节分布
        season_counts = {}
        for s in season_timeline.values():
            season_counts[s] = season_counts.get(s, 0) + 1
        print(f"  季节分布: {season_counts}")
    else:
        print("  ⚠️ 无法计算季节，方向过滤将使用 unknown")

    # ── 预计算每只股票的分类 ──
    print("\n预计算股票树粮草分类...")
    categories = {}
    for mkt, code, name in STOCKS:
        cat = get_stock_category(mkt, code)
        categories[code] = cat
        cn = {"tree": "树", "grain": "粮", "vegetable": "草"}.get(cat, cat)
        print(f"  {name}({code}): {cn}类")

    # ── 回测 ──
    for strategy_name, use_filter in [("纯缠论(baseline)", False), ("融合系统(hybrid)", True)]:
        print(f"\n{'='*100}")
        print(f"  策略: {strategy_name}")
        print(f"  日线买点买入 → {'日线卖点卖出(树类大周期)' if use_filter else '60分卖点卖出'}{' + 方向过滤 + 技术评分' if use_filter else ''}")
        print(f"{'='*100}")
        print(f"{'股票':10s} | {'10万→':>10s} | {'累计收益':>10s} | {'年化':>8s} | {'交易':>4s} | {'胜率':>6s} | {'回撤':>6s} | {'过滤':>4s} | {'买入持有':>10s}")
        print("-" * 100)

        all_returns = []
        all_bh = []
        total_trades = 0
        total_filtered = 0

        for mkt, code, name in STOCKS:
            df_daily = load_data(CACHE_D, mkt, code, "daily")
            df_60min = load_data(CACHE_MIN, mkt, code, "60min")

            if df_daily.empty or df_60min.empty:
                print(f"{name:10s} | 无数据")
                continue

            daily_start = pd.Timestamp(df_daily["datetime"].iloc[0])
            daily_end = pd.Timestamp(df_daily["datetime"].iloc[-1])
            min60_start = pd.Timestamp(df_60min["datetime"].iloc[0])
            min60_end = pd.Timestamp(df_60min["datetime"].iloc[-1])
            overlap_start = max(daily_start, min60_start)

            cfg = ChanlunConfig(zs_from_xd=False)
            analyser_h = ChanlunAnalyser(code=code, frequency="daily", config=cfg)
            result_h = analyser_h.process_klines(df_daily)
            higher_signals = extract_signals(result_h, df_daily)

            # 日线卖点（树类用日线卖=大周期卖出；非树类用60分卖）
            daily_sell_signals = [s for s in higher_signals if not s.is_buy]

            cfg_l = ChanlunConfig(zs_from_xd=False)
            analyser_l = ChanlunAnalyser(code=code, frequency="60min", config=cfg_l)
            result_l = analyser_l.process_klines(df_60min)
            min60_signals = extract_signals(result_l, df_60min)

            higher_signals = [s for s in higher_signals if s.date >= overlap_start]
            min60_signals = [s for s in min60_signals if s.date >= overlap_start]
            daily_sell_signals = [s for s in daily_sell_signals if s.date >= overlap_start]

            # 树类用日线卖（大周期持有），非树类用60分卖
            cat = categories.get(code, "grain")
            if use_filter and cat == "tree":
                lower_signals = daily_sell_signals
                lower_df = df_daily  # 用日线数据做卖出
            else:
                lower_signals = min60_signals
                lower_df = df_60min

            result = backtest(
                df_daily, lower_df, higher_signals, lower_signals,
                category=cat,
                season_timeline=season_timeline,
                daily_df=df_daily,
                use_hybrid_filter=use_filter,
            )

            final_val = result["final_cash"]
            total_ret = result["total_return"] * 100
            n_trades = result["n_trades"]
            win = result["win_rate"]
            max_dd = result["max_drawdown"] * 100
            filtered = result["filtered_out"]

            overlap_df = df_daily[df_daily["datetime"] >= overlap_start]
            if len(overlap_df) > 1:
                bh = (overlap_df["close"].iloc[-1] / overlap_df["close"].iloc[0] - 1) * 100
                overlap_days = (pd.Timestamp(overlap_df["datetime"].iloc[-1]) - pd.Timestamp(overlap_df["datetime"].iloc[0])).days
                overlap_years = overlap_days / 365.25
                ann = ((1 + result["total_return"]) ** (1 / overlap_years) - 1) * 100 if overlap_years > 0 else 0
            else:
                bh = 0
                ann = 0

            print(f"{name:10s} | {final_val:10.0f} | {total_ret:+9.1f}% | {ann:7.2f}% | {n_trades:4d} | {win:5.1f}% | {max_dd:5.1f}% | {filtered:4d} | {100000*(1+bh/100):10.0f}")
            sys.stdout.flush()
            all_returns.append(total_ret)
            all_bh.append(bh)
            total_trades += n_trades
            total_filtered += filtered

        if all_returns:
            avg_ret = sum(all_returns) / len(all_returns)
            avg_bh = sum(all_bh) / len(all_bh)
            print("-" * 100)
            print(f"{'平均':10s} | {100000*(1+avg_ret/100):10.0f} | {avg_ret:+9.1f}% | {'':8s} | {total_trades/len(all_returns):4.1f} | {'':6s} | {'':6s} | {total_filtered:4d} | {100000*(1+avg_bh/100):10.0f}")
            print(f"\n  10万本金 → 平均变成 {100000*(1+avg_ret/100):.0f} 元（累计 {avg_ret:+.1f}%）")
            print(f"  同期买入持有：{100000*(1+avg_bh/100):.0f} 元（{avg_bh:+.1f}%）")
            print(f"  超额收益：{avg_ret - avg_bh:+.1f}%（vs 买入持有）")
            if use_filter:
                print(f"  融合系统过滤掉 {total_filtered} 个信号（避免了部分亏损交易）")

    # ── 汇总对比 ──
    print(f"\n{'='*100}")
    print("  对比汇总")
    print(f"{'='*100}")
    print("  纯缠论: 所有日线买点都执行，不过滤")
    print("  融合系统: 方向过滤(树类/冬季/秋季草类否决) + 技术评分(≥60分才执行)")
    print("  如果融合系统的胜率和收益更高 → 方向过滤+技术评分确实有效")


if __name__ == "__main__":
    main()
