"""股票诊断API路由。

提供单只股票的全面技术分析，帮助投资者做出买卖决策。

功能：
1. 缠论结构分析（笔/中枢/买卖点）
2. BOLL位置分析
3. MACD状态分析 + 背离检测
4. KDJ状态分析 + 背离检测
5. RSI状态分析 + 背离检测
6. ADX趋势强度分析
7. OBV能量潮分析
8. 成交量分析
9. K线形态识别（锤子/吊颈/吞没/十字星）
10. 综合评分和操作建议
11. 风险管理和仓位建议
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends

from easy_tdx.web.convert import category_from_str, market_from_str
from easy_tdx.web.deps import get_client
from easy_tdx.web.schemas import StockIdentifier

# V13: 延迟导入成交量剖面分析（避免循环导入）
def _calc_volume_profile_for_diagnosis(
    closes: list[float] | None,
    volumes: list[float] | None,
) -> dict[str, Any] | None:
    """计算成交量剖面数据，用于诊断API响应（V13新增）。"""
    if not closes or not volumes or len(closes) < 60:
        return None
    try:
        from easy_tdx.chanlun.mmd import _calc_volume_profile
        profile = _calc_volume_profile(closes, volumes, lookback=60, num_bins=20)
        return {
            "support": profile.get("high_volume_support"),
            "resistance": profile.get("high_volume_resistance"),
            "current_rank": profile.get("current_volume_rank", 0.5),
            "cluster_up": profile.get("volume_cluster_up", False),
            "cluster_down": profile.get("volume_cluster_down", False),
        }
    except Exception:
        return None

router = APIRouter(tags=["diagnosis"])
logger = logging.getLogger(__name__)


# ── 辅助函数 ────────────────────────────────────────────────────────────────────

def _detect_divergence(
    prices: list[float],
    indicators: list[float],
    lookback: int = 60,
) -> dict[str, Any]:
    """检测价格与指标的顶背离/底背离。

    顶背离：价格创新高，但指标未创新高 → 看跌信号
    底背离：价格创新低，但指标未创新低 → 看涨信号
    """
    if len(prices) < lookback or len(indicators) < lookback:
        return {"type": "none", "strength": 0, "detected": False}

    recent_prices = prices[-lookback:]
    recent_indicators = indicators[-lookback:]

    # 找最近的两个局部高点（用于顶背离检测）
    peaks_price = []
    peaks_ind = []
    troughs_price = []
    troughs_ind = []

    for i in range(2, len(recent_prices) - 2):
        # 局部高点
        if (recent_prices[i] > recent_prices[i-1] and recent_prices[i] > recent_prices[i-2]
                and recent_prices[i] > recent_prices[i+1] and recent_prices[i] > recent_prices[i+2]):
            peaks_price.append(i)
            peaks_ind.append(i)
        # 局部低点
        if (recent_prices[i] < recent_prices[i-1] and recent_prices[i] < recent_prices[i-2]
                and recent_prices[i] < recent_prices[i+1] and recent_prices[i] < recent_prices[i+2]):
            troughs_price.append(i)
            troughs_ind.append(i)

    detected_type = "none"
    strength = 0

    # 顶背离：最近高点 > 前一个高点，但指标高点 < 前一个指标高点
    if len(peaks_price) >= 2:
        last_peak = peaks_price[-1]
        prev_peak = peaks_price[-2]
        price_higher = recent_prices[last_peak] > recent_prices[prev_peak]
        ind_lower = recent_indicators[last_peak] < recent_indicators[prev_peak]
        if price_higher and ind_lower:
            detected_type = "bearish"
            price_diff = (recent_prices[last_peak] - recent_prices[prev_peak]) / recent_prices[prev_peak]
            ind_diff = (recent_indicators[prev_peak] - recent_indicators[last_peak]) / max(abs(recent_indicators[prev_peak]), 1e-10)
            strength = min(1.0, abs(price_diff) * 10 + min(ind_diff, 0.5))

    # 底背离：最近低点 < 前一个低点，但指标低点 > 前一个指标低点
    elif len(troughs_price) >= 2:
        last_trough = troughs_price[-1]
        prev_trough = troughs_price[-2]
        price_lower = recent_prices[last_trough] < recent_prices[prev_trough]
        ind_higher = recent_indicators[last_trough] > recent_indicators[prev_trough]
        if price_lower and ind_higher:
            detected_type = "bullish"
            price_diff = (recent_prices[prev_trough] - recent_prices[last_trough]) / max(abs(recent_prices[prev_trough]), 1e-10)
            ind_diff = (recent_indicators[last_trough] - recent_indicators[prev_trough]) / max(abs(recent_indicators[prev_trough]), 1e-10)
            strength = min(1.0, abs(price_diff) * 10 + min(ind_diff, 0.5))

    return {
        "type": detected_type,
        "strength": round(strength, 2),
        "detected": detected_type != "none",
    }


def _detect_candlestick_patterns(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
) -> dict[str, Any]:
    """识别K线形态，返回最近3根K线的形态信号。

    形态：锤子线、上吊线、吞没形态、十字星、纺锤线
    """
    if len(closes) < 3:
        return {"patterns": [], "signal": "none", "strength": 0}

    patterns = []
    lookback = min(5, len(closes))

    for i in range(-lookback, 0):
        o = opens[i]
        h = highs[i]
        l = lows[i]
        c = closes[i]
        body = abs(c - o)
        range_val = h - l
        upper_shadow = h - max(c, o)
        lower_shadow = min(c, o) - l

        if range_val == 0:
            continue

        body_pct = body / range_val
        upper_pct = upper_shadow / range_val
        lower_pct = lower_shadow / range_val
        is_bullish = c > o
        is_bearish = c < o

        # 十字星：实体极小
        if body_pct < 0.1:
            patterns.append({"bar_index": i, "type": "doji", "bullish": is_bullish})
        # 锤子线（看涨）：下影线长，实体小，上影线短，出现在下跌后
        elif lower_pct > 0.6 and body_pct < 0.3 and upper_pct < 0.2 and is_bullish:
            patterns.append({"bar_index": i, "type": "hammer", "bullish": True})
        # 吊颈线（看跌）：锤子线形状但出现在上涨后
        elif lower_pct > 0.6 and body_pct < 0.3 and upper_pct < 0.2 and is_bearish:
            patterns.append({"bar_index": i, "type": "hanging_leg", "bullish": False})
        # 吞没形态
        elif i < -1:
            prev_o = opens[i-1]
            prev_c = closes[i-1]
            prev_bearish = prev_c < prev_o
            prev_bullish = prev_c > prev_o
            if is_bullish and prev_bearish:
                if c > prev_o and o < prev_c:
                    patterns.append({"bar_index": i, "type": "bullish_engulfing", "bullish": True})
            elif is_bearish and prev_bullish:
                if c < prev_o and o > prev_c:
                    patterns.append({"bar_index": i, "type": "bearish_engulfing", "bullish": False})

    # 汇总信号
    bullish_signals = sum(1 for p in patterns if p["bullish"])
    bearish_signals = sum(1 for p in patterns if not p["bullish"])
    total = len(patterns)

    if total == 0:
        signal, strength = "none", 0
    elif bullish_signals > bearish_signals:
        signal = "bullish"
        strength = bullish_signals / total if total > 0 else 0
    elif bearish_signals > bullish_signals:
        signal = "bearish"
        strength = bearish_signals / total if total > 0 else 0
    else:
        signal = "neutral"
        strength = 0.5

    return {"patterns": patterns, "signal": signal, "strength": round(strength, 2)}


# ── 诊断主函数 ──────────────────────────────────────────────────────────────────


@router.post("/diagnosis/analyze")
async def diagnose_stock(
    req: StockIdentifier,
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """分析单只股票的技术面，给出买卖建议。

    请求参数：
    - market: 市场 (SZ/SH)
    - code: 6位股票代码
    """
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
    from easy_tdx.chanlun.mmd import calc_signal_quality_report, _calc_atr_volatility
    from easy_tdx.MyTT import MACD, MA, BOLL, ATR, KDJ, RSI, DMI, OBV

    market = req.market
    code = req.code
    symbol = f"{market}{code}"

    # 获取日线数据
    df = await client.get_security_bars(
        market_from_str(market),
        code,
        category_from_str("DAY"),
        0,
        500,
    )

    if df is None or len(df) < 100:
        return {
            "error": "数据不足，无法进行分析",
            "symbol": symbol,
        }

    closes = df["close"].values  # V8: 保持 numpy 数组，MyTT 函数需要数值型数组
    volumes = df["vol"].values
    highs = df["high"].values
    lows = df["low"].values
    opens = df["open"].values
    dates = [str(d)[:10] for d in df["date"].tolist()] if "date" in df.columns else []
    latest_close = closes[-1]
    latest_date = dates[-1] if dates else ""

    # ── 缠论分析 ──────────────────────────────────────────────────────
    analyser = ChanlunAnalyser(code=symbol, frequency="daily")
    result = analyser.process_klines(df)

    # ── MACD分析 ──────────────────────────────────────────────────────
    dif, dea, macd_hist = MACD(closes, SHORT=12, LONG=26, M=9)
    latest_dif = dif[-1] if len(dif) > 0 else 0
    latest_dea = dea[-1] if len(dea) > 0 else 0
    latest_macd = macd_hist[-1] if len(macd_hist) > 0 else 0

    # MACD状态
    macd_golden = bool(dif[-2] <= dea[-2] and dif[-1] > dea[-1]) if len(dif) >= 2 and len(dea) >= 2 else False
    macd_dead = bool(dif[-2] >= dea[-2] and dif[-1] < dea[-1]) if len(dif) >= 2 and len(dea) >= 2 else False

    macd_above_zero = bool(latest_dif > 0 and latest_dea > 0)
    macd_trending_up = bool(latest_macd > 0 and len(macd_hist) >= 2 and macd_hist[-1] > macd_hist[-2])
    macd_trending_down = bool(latest_macd < 0 and len(macd_hist) >= 2 and macd_hist[-1] < macd_hist[-2])

    # ── KDJ分析 ──────────────────────────────────────────────────────
    k, d, j = KDJ(closes, highs, lows, N=9, M1=3, M2=3)
    latest_k = k[-1] if len(k) > 0 else 50
    latest_d = d[-1] if len(d) > 0 else 50
    latest_j = j[-1] if len(j) > 0 else 50

    # KDJ状态
    kdj_golden = bool(k[-2] <= d[-2] and k[-1] > d[-1]) if len(k) >= 2 and len(d) >= 2 else False
    kdj_dead = bool(k[-2] >= d[-2] and k[-1] < d[-1]) if len(k) >= 2 and len(d) >= 2 else False
    kdj_overbought = bool(latest_k > 80 or latest_j > 100)
    kdj_oversold = bool(latest_k < 20 or latest_j < 0)

    # KDJ位置
    if latest_k > 80:
        kdj_position = "超买"
    elif latest_k < 20:
        kdj_position = "超卖"
    else:
        kdj_position = "中性"

    # ── RSI分析 ──────────────────────────────────────────────────────
    rsi_values = RSI(closes, N=14)
    latest_rsi = rsi_values[-1] if len(rsi_values) > 0 else 50

    # RSI状态
    rsi_overbought = bool(latest_rsi > 70)
    rsi_oversold = bool(latest_rsi < 30)
    rsi_divergence = False  # 简化：实际需比较价格和RSI走势

    # RSI位置
    if latest_rsi > 80:
        rsi_position = "极强超买"
    elif latest_rsi > 70:
        rsi_position = "超买"
    elif latest_rsi < 20:
        rsi_position = "极强超卖"
    elif latest_rsi < 30:
        rsi_position = "超卖"
    else:
        rsi_position = "中性"

    # ── BOLL分析 ──────────────────────────────────────────────────────
    boll_upper, boll_mid, boll_lower = BOLL(closes, N=20, P=2)
    latest_upper = boll_upper[-1] if len(boll_upper) > 0 else 0
    latest_mid = boll_mid[-1] if len(boll_mid) > 0 else 0
    latest_lower = boll_lower[-1] if len(boll_lower) > 0 else 0
    boll_width = (latest_upper - latest_lower) / latest_mid if latest_mid > 0 else 0
    percent_b = (latest_close - latest_lower) / (latest_upper - latest_lower) if (latest_upper - latest_lower) > 0 else 0.5

    # BOLL状态
    boll_position = "mid"  # upper/mid/lower
    if percent_b > 0.8:
        boll_position = "upper"
    elif percent_b < 0.2:
        boll_position = "lower"

    # ── 均线分析 ──────────────────────────────────────────────────────
    ma5 = MA(closes, 5)[-1] if len(closes) >= 5 else latest_close
    ma10 = MA(closes, 10)[-1] if len(closes) >= 10 else latest_close
    ma20 = MA(closes, 20)[-1] if len(closes) >= 20 else latest_close
    ma60 = MA(closes, 60)[-1] if len(closes) >= 60 else latest_close

    ma_bullish = bool(ma5 > ma10 > ma20)  # 多头排列
    ma_bearish = bool(ma5 < ma10 < ma20)  # 空头排列
    price_above_ma20 = bool(latest_close > ma20)
    price_above_ma60 = bool(latest_close > ma60)

    # ── Fibonacci 支撑阻力位 ───────────────────────────────────────────
    fib_lookback = 120
    if len(highs) >= fib_lookback and len(lows) >= fib_lookback:
        period_high = max(highs[-fib_lookback:])
        period_low = min(lows[-fib_lookback:])
        fib_range = period_high - period_low
        fib_levels: dict[str, float] = {}
        if fib_range > 0:
            fib_ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
            for r in fib_ratios:
                fib_levels[f"fib_{r}"] = round(period_high - fib_range * r, 2)
            fib_levels["resistance"] = round(period_high, 2)
            fib_levels["support"] = round(period_low, 2)
            fib_position = (latest_close - period_low) / fib_range if fib_range > 0 else 0.5
        else:
            fib_position = 0.5
    else:
        fib_levels = {}
        fib_position = 0.5

    # ── 成交量分析 ────────────────────────────────────────────────────
    vol_ma5 = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else (volumes[-1] if len(volumes) > 0 else 0)
    vol_ma20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else (volumes[-1] if len(volumes) > 0 else 0)
    vol_ratio = vol_ma5 / vol_ma20 if vol_ma20 > 0 else 1.0
    vol_expanding = bool(vol_ratio > 1.2)  # 放量
    vol_contracting = bool(vol_ratio < 0.8)  # 缩量

    # ── ATR & 止损止盈价位 ────────────────────────────────────────────
    atr_values = ATR(closes, highs, lows, N=14)
    latest_atr = atr_values[-1] if len(atr_values) > 0 else latest_close * 0.02
    atr_pct = (latest_atr / latest_close * 100) if latest_close > 0 else 0

    # 支撑阻力位（基于近期高低点）
    lookback = 60
    recent_highs = highs[-lookback:]
    recent_lows = lows[-lookback:]
    resistance_1 = max(recent_highs) if len(recent_highs) > 0 else latest_close
    support_1 = min(recent_lows) if len(recent_lows) > 0 else latest_close
    resistance_2 = max(recent_highs[-30:]) if len(recent_highs) >= 30 else resistance_1
    support_2 = min(recent_lows[-30:]) if len(recent_lows) >= 30 else support_1

    # 动态止损止盈（基于ATR倍数）
    stop_loss_price = round(latest_close - latest_atr * 1.5, 2)
    take_profit_price = round(latest_close + latest_atr * 3.0, 2)
    stop_loss_pct = round((latest_close - stop_loss_price) / latest_close * 100, 2)
    take_profit_pct = round((take_profit_price - latest_close) / latest_close * 100, 2)

    # 风险收益比
    risk_reward_ratio = round(3.0 / 1.5, 1) if stop_loss_price > 0 else 0

    # V7: 计算波动率用于信号报告
    volatility = _calc_atr_volatility(closes) if len(closes) > 0 else None

    # 波动率评级
    if atr_pct < 1.5:
        volatility_label = "低波动"
        volatility_level = "low"
    elif atr_pct < 3.0:
        volatility_label = "中等波动"
        volatility_level = "medium"
    else:
        volatility_label = "高波动"
        volatility_level = "high"

    # ── ADX 趋势强度分析 ─────────────────────────────────────────────
    pdi, mdi, adx, adxr = DMI(closes, highs, lows, M1=14, M2=6)
    latest_pdi = pdi[-1] if len(pdi) > 0 else 20
    latest_mdi = mdi[-1] if len(mdi) > 0 else 20
    latest_adx = adx[-1] if len(adx) > 0 else 25
    latest_adxr = adxr[-1] if len(adxr) > 0 else 25
    trend_direction = "up" if latest_pdi > latest_mdi else "down"
    # ADX 强度分级：>50 极强，>25 有趋势，<20 无趋势/震荡
    if latest_adx >= 50:
        adx_strength = "极强"
        adx_level = "very_strong"
    elif latest_adx >= 40:
        adx_strength = "强"
        adx_level = "strong"
    elif latest_adx >= 25:
        adx_strength = "中等"
        adx_level = "medium"
    elif latest_adx >= 20:
        adx_strength = "弱"
        adx_level = "weak"
    else:
        adx_strength = "无趋势"
        adx_level = "none"

    # ── OBV 能量潮分析 ───────────────────────────────────────────────
    obv_values = OBV(closes, volumes)
    latest_obv = obv_values[-1] if len(obv_values) > 0 else 0
    obv_ma20 = MA(obv_values, 20)[-1] if len(obv_values) >= 20 else latest_obv
    obv_trending_up = bool(latest_obv > obv_ma20 and len(obv_values) >= 2 and obv_values[-1] > obv_values[-2])
    obv_trending_down = bool(latest_obv < obv_ma20 and len(obv_values) >= 2 and obv_values[-1] < obv_values[-2])
    obv_divergence_price = "bullish" if (latest_close > closes[-20] if len(closes) >= 20 else False) and obv_trending_down else (
        "bearish" if (latest_close < closes[-20] if len(closes) >= 20 else False) and obv_trending_up else "none"
    )

    # ── 背离检测（MACD / KDJ / RSI） ─────────────────────────────────
    macd_div = _detect_divergence(closes, macd_hist, lookback=60)
    kdj_div = _detect_divergence(closes, j, lookback=60)
    rsi_div = _detect_divergence(closes, [v for v in RSI(closes, N=14)], lookback=60)

    # 综合背离信号：任意一个指标出现背离则标记
    all_divs = [macd_div, kdj_div, rsi_div]
    bullish_div_count = sum(1 for d in all_divs if d["type"] == "bullish")
    bearish_div_count = sum(1 for d in all_divs if d["type"] == "bearish")
    has_divergence = bullish_div_count > 0 or bearish_div_count > 0
    dominant_div = "bullish" if bullish_div_count >= bearish_div_count and bullish_div_count > 0 else (
        "bearish" if bearish_div_count > 0 else "none"
    )
    div_strength = max(d["strength"] for d in all_divs) if has_divergence else 0

    # ── K线形态识别 ───────────────────────────────────────────────────
    candle_result = _detect_candlestick_patterns(opens, highs, lows, closes)
    candle_signal = candle_result["signal"]
    candle_strength = candle_result["strength"]
    recent_patterns = candle_result["patterns"][:3]  # 最近3个形态

    # ── 综合评分（V8 增强版：多信号融合 + 置信度分层）────────────────────
    score = 50  # 基础分

    # V8: 缠论信号统计（按类型和置信度加权）
    buy_1_count = sum(1 for m in result.mmds if m.mmd_type.value == "1buy")
    sell_1_count = sum(1 for m in result.mmds if m.mmd_type.value == "1sell")
    buy_2_count = sum(1 for m in result.mmds if m.mmd_type.value == "2buy")
    sell_2_count = sum(1 for m in result.mmds if m.mmd_type.value == "2sell")
    buy_3_count = sum(1 for m in result.mmds if m.mmd_type.value == "3buy")
    sell_3_count = sum(1 for m in result.mmds if m.mmd_type.value == "3sell")
    latest_mmd = max(result.mmds, key=lambda m: m.bi.index if m.bi else 0) if result.mmds else None

    # V8: 多信号融合权重（按类型和置信度动态调整）
    chanlun_score = 0
    if latest_mmd:
        q = getattr(latest_mmd, "quality", None)
        grade = q.grade if q else None
        conf = latest_mmd.confidence

        # V8: 类型权重 + 置信度加成 + 质量评级加成
        type_weights = {
            "1buy": 20, "1sell": -20,
            "2buy": 15, "2sell": -15,
            "3buy": 10, "3sell": -10,
        }
        base_score = type_weights.get(latest_mmd.mmd_type.value, 0)

        # V8: 置信度加成（高置信度信号权重更高）
        conf_factor = 0.5 + conf * 0.5  # 0.5-1.0 范围
        conf_bonus = base_score * (conf_factor - 0.5) * 2

        # V8: 质量评级加成 — S/A级信号权重更高
        grade_bonus: dict[str, int] = {"S": 10, "A": 6, "B": 3, "C": 0, "D": -5}
        quality_adj = grade_bonus.get(grade, 0) if grade else 0

        chanlun_score = base_score + conf_bonus + quality_adj

        # V8: 多信号叠加加成（多种类型同时存在时额外加分）
        multi_signal_bonus = 0
        signal_types = set(m.mmd_type.value for m in result.mmds)
        if "1buy" in signal_types and "2buy" in signal_types:
            multi_signal_bonus += 5  # 1买+2买共振
        elif "1sell" in signal_types and "2sell" in signal_types:
            multi_signal_bonus -= 5  # 1卖+2卖共振
        if "3buy" in signal_types and latest_mmd.mmd_type.value.startswith("buy"):
            multi_signal_bonus += 3  # 3买确认
        elif "3sell" in signal_types and latest_mmd.mmd_type.value.startswith("sell"):
            multi_signal_bonus -= 3  # 3卖确认

        score += chanlun_score + multi_signal_bonus

    # MACD
    if macd_golden:
        score += 10
    elif macd_dead:
        score -= 10
    if macd_above_zero:
        score += 5
    else:
        score -= 5
    if macd_trending_up:
        score += 5
    elif macd_trending_down:
        score -= 5

    # BOLL
    if boll_position == "lower":
        score += 8
    elif boll_position == "upper":
        score -= 8

    # KDJ
    if kdj_golden:
        score += 8
    elif kdj_dead:
        score -= 8
    if kdj_oversold:
        score += 6
    elif kdj_overbought:
        score -= 6

    # RSI
    if latest_rsi < 30:
        score += 8
    elif latest_rsi > 70:
        score -= 8
    elif latest_rsi < 40:
        score += 3
    elif latest_rsi > 60:
        score -= 3

    # 均线
    if ma_bullish:
        score += 10
    elif ma_bearish:
        score -= 10
    if price_above_ma20 and price_above_ma60:
        score += 5
    elif not price_above_ma20 and not price_above_ma60:
        score -= 5

    # V5: Fibonacci 位置加成
    if fib_position > 0.8:
        score -= 5  # 价格接近周期高点，警惕回调
    elif fib_position < 0.2:
        score += 5  # 价格接近周期低点，支撑强劲
    elif 0.6 < fib_position < 0.7:
        score += 2  # 在61.8%回撤位附近，有一定支撑

    # 成交量
    if vol_expanding and latest_close > opens[-1]:
        score += 5  # 放量上涨
    elif vol_expanding and latest_close < opens[-1]:
        score -= 5  # 放量下跌
    elif vol_contracting and abs(latest_close - opens[-1]) < latest_close * 0.01:
        score += 2  # 缩量横盘，观望

    # ADX 趋势强度加成
    if adx_level in ("strong", "very_strong"):
        if trend_direction == "up":
            score += 5  # 强上升趋势加成
        else:
            score -= 5  # 强下降趋势扣分
    elif adx_level in ("none", "weak"):
        score -= 3  # 无明确趋势，市场震荡，轻微扣分

    # OBV 能量潮加成
    if obv_trending_up and not macd_dead:
        score += 4  # OBV上升确认上涨趋势
    elif obv_trending_down and not macd_golden:
        score -= 4  # OBV下降确认下跌趋势
    if obv_divergence_price == "bullish":
        score += 6  # OBV与价格底背离，强烈看涨信号
    elif obv_divergence_price == "bearish":
        score -= 6  # OBV与价格顶背离，强烈看跌信号

    # 背离信号加成（重要！）
    if dominant_div == "bullish":
        score += int(8 * div_strength)  # 底背离加分，强度加权
    elif dominant_div == "bearish":
        score -= int(8 * div_strength)  # 顶背离扣分，强度加权

    # K线形态加成
    if candle_signal == "bullish":
        score += int(5 * candle_strength)
    elif candle_signal == "bearish":
        score -= int(5 * candle_strength)

    score = max(0, min(100, score))

    # ── 操作建议（V8 增强：置信度分层 + 多信号融合描述）─────────────────────
    # 构建缠论信号描述
    chanlun_desc = ""
    if latest_mmd:
        mmd_type = latest_mmd.mmd_type.value
        q = getattr(latest_mmd, "quality", None)
        grade = q.grade if q else None
        conf_pct = int(latest_mmd.confidence * 100)
        chanlun_desc = f"缠论{mmd_type}({grade or '?'}级, 置信度{conf_pct}%)"
        if q and q.reasons:
            top_reason = q.reasons[0] if q.reasons else ""
            if top_reason:
                chanlun_desc += f" [{top_reason}]"

    # V8: 置信度分层 - 根据置信度和评分共同决定操作建议
    if score >= 75 and latest_mmd and latest_mmd.confidence >= 0.75:
        action = "strong_buy"
        action_label = "强烈买入"
        action_color = "#22c55e"
        extra = f"。{chanlun_desc}" if chanlun_desc else ""
        reason = f"多指标共振看涨，缠论高置信度信号确认{extra}。建议止损 {stop_loss_price} 元（-{stop_loss_pct}%），止盈 {take_profit_price} 元（+{take_profit_pct}%）"
    elif score >= 60 and latest_mmd and latest_mmd.confidence >= 0.65:
        action = "buy"
        action_label = "买入"
        action_color = "#4ade80"
        extra = f"。{chanlun_desc}" if chanlun_desc else ""
        reason = f"技术面偏多，缠论信号可参考{extra}。建议止损 {stop_loss_price} 元（-{stop_loss_pct}%），注意上方阻力 {resistance_1} 元"
    elif score >= 45:
        action = "hold"
        action_label = "持有观察"
        action_color = "#f59e0b"
        extra = f"。{chanlun_desc}" if chanlun_desc else ""
        reason = f"方向不明确，建议观望{extra}。支撑位 {support_1} 元，阻力位 {resistance_1} 元，等待突破方向"
    elif score >= 30 and latest_mmd and latest_mmd.confidence >= 0.65:
        action = "sell"
        action_label = "卖出"
        action_color = "#f97316"
        extra = f"。{chanlun_desc}" if chanlun_desc else ""
        reason = f"技术面偏空，缠论信号可参考{extra}。下方支撑 {support_1} 元，跌破可考虑止损 {stop_loss_price} 元"
    elif score >= 30:
        action = "sell"
        action_label = "卖出"
        action_color = "#f97316"
        extra = f"。{chanlun_desc}" if chanlun_desc else ""
        reason = f"技术面偏空，建议减仓{extra}。下方支撑 {support_1} 元"
    else:
        action = "strong_sell"
        action_label = "强烈卖出"
        action_color = "#ef4444"
        extra = f"。{chanlun_desc}" if chanlun_desc else ""
        reason = f"多指标共振看跌，建议清仓回避{extra}。止损位 {stop_loss_price} 元，远离多头趋势"

    # ── 仓位建议 ──────────────────────────────────────────────────────
    position_recommendation = _calculate_position_recommendation(
        score, volatility_level, atr_pct, ma_bullish, macd_golden,
        has_divergence=has_divergence, dominant_div=dominant_div, adx_level=adx_level,
    )

    # ── 返回结果 ──────────────────────────────────────────────────────
    return {
        "symbol": symbol,
        "date": latest_date,
        "close": round(latest_close, 2),
        "score": round(score, 1),
        "action": action,
        "action_label": action_label,
        "action_color": action_color,
        "reason": reason,
        "chanlun": {
            "bi_count": len(result.bis),
            "zs_count": len(result.zss),
            "mmd_count": len(result.mmds),
            "buy_1_count": buy_1_count,
            "sell_1_count": sell_1_count,
            "buy_2_count": buy_2_count,
            "sell_2_count": sell_2_count,
            "latest_mmd": {
                "type": latest_mmd.mmd_type.value if latest_mmd else None,
                "confidence": round(latest_mmd.confidence, 2) if latest_mmd else None,
                "msg": latest_mmd.msg if latest_mmd else None,
                "quality": {
                    "grade": getattr(getattr(latest_mmd, "quality", None), "grade", None),
                    "score": getattr(getattr(getattr(latest_mmd, "quality", None), "score", None), "score", None),
                    "reasons": getattr(getattr(getattr(latest_mmd, "quality", None), "reasons", None), "reasons", None),
                } if latest_mmd and getattr(latest_mmd, "quality", None) else None,
            } if latest_mmd else None,
            # V6: 最近3个高质量买卖点
            "recent_signals": [
                {
                    "type": m.mmd_type.value,
                    "confidence": round(m.confidence, 2),
                    "quality": {
                        "grade": getattr(getattr(m, "quality", None), "grade", None),
                        "score": getattr(getattr(getattr(m, "quality", None), "score", None), "score", None),
                    } if getattr(m, "quality", None) else None,
                }
                for m in sorted(result.mmds, key=lambda x: getattr(getattr(x, "quality", None), "score", 0) if getattr(x, "quality", None) else 0, reverse=True)[:3]
            ],
            # V7: 信号质量报告（入场/止损/止盈建议）
            "signal_report": calc_signal_quality_report(
                latest_mmd, closes, volumes,
                {"dif": dif, "dea": dea, "hist": macd_hist} if len(dif) > 0 else None,
                volatility,
            ) if latest_mmd else None,
            # V12: 多时间框架共振评分（如有）
            "confluence_score": round(getattr(latest_mmd, "confluence_score", 0.0), 2) if latest_mmd else None,
            # V13: 成交量剖面分析
            "volume_profile": _calc_volume_profile_for_diagnosis(closes, volumes) if latest_mmd else None,
        },
        # V12: 多级别联立分析结果（需前端传入低级别数据）
        "multi_level_confluence": None,
        "macd": {
            "dif": round(latest_dif, 4),
            "dea": round(latest_dea, 4),
            "hist": round(latest_macd, 4),
            "golden_cross": macd_golden,
            "dead_cross": macd_dead,
            "above_zero": macd_above_zero,
            "trending": "up" if macd_trending_up else ("down" if macd_trending_down else "flat"),
        },
        "boll": {
            "upper": round(latest_upper, 2),
            "mid": round(latest_mid, 2),
            "lower": round(latest_lower, 2),
            "width": round(boll_width, 4),
            "percent_b": round(percent_b, 3),
            "position": boll_position,
        },
        "moving_averages": {
            "ma5": round(ma5, 2),
            "ma10": round(ma10, 2),
            "ma20": round(ma20, 2),
            "ma60": round(ma60, 2),
            "bullish_arrangement": ma_bullish,
            "bearish_arrangement": ma_bearish,
        },
        "fibonacci": {
            "levels": fib_levels,
            "position": round(fib_position, 3),
            "period_high": round(max(highs[-fib_lookback:]), 2) if len(highs) >= fib_lookback else None,
            "period_low": round(min(lows[-fib_lookback:]), 2) if len(lows) >= fib_lookback else None,
        },
        "volume": {
            "ratio": round(vol_ratio, 2),
            "expanding": vol_expanding,
            "contracting": vol_contracting,
        },
        "kdj": {
            "k": round(latest_k, 2),
            "d": round(latest_d, 2),
            "j": round(latest_j, 2),
            "golden_cross": kdj_golden,
            "dead_cross": kdj_dead,
            "overbought": kdj_overbought,
            "oversold": kdj_oversold,
            "position": kdj_position,
        },
        "rsi": {
            "value": round(latest_rsi, 2),
            "overbought": rsi_overbought,
            "oversold": rsi_oversold,
            "position": rsi_position,
        },
        "adx": {
            "pdi": round(latest_pdi, 2),
            "mdi": round(latest_mdi, 2),
            "adx": round(latest_adx, 2),
            "adxr": round(latest_adxr, 2),
            "trend_direction": trend_direction,
            "strength": adx_strength,
            "level": adx_level,
        },
        "obv": {
            "value": round(latest_obv, 2),
            "ma20": round(obv_ma20, 2),
            "trending_up": obv_trending_up,
            "trending_down": obv_trending_down,
            "divergence_with_price": obv_divergence_price,
        },
        "divergence": {
            "macd": macd_div,
            "kdj": kdj_div,
            "rsi": rsi_div,
            "dominant": dominant_div,
            "strength": round(div_strength, 2),
            "has_divergence": has_divergence,
        },
        "candlestick": {
            "signal": candle_signal,
            "strength": round(candle_strength, 2),
            "recent_patterns": recent_patterns,
        },
        "risk": {
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "risk_reward_ratio": risk_reward_ratio,
            "atr": round(latest_atr, 2),
            "atr_pct": round(atr_pct, 2),
            "volatility_label": volatility_label,
            "support_1": round(support_1, 2),
            "resistance_1": round(resistance_1, 2),
            "support_2": round(support_2, 2),
            "resistance_2": round(resistance_2, 2),
        },
        "position_suggestion": position_recommendation,
    }


def _calculate_position_recommendation(
    score: float,
    volatility: str,
    atr_pct: float,
    ma_bullish: bool,
    macd_golden: bool,
    has_divergence: bool = False,
    dominant_div: str = "none",
    adx_level: str = "medium",
) -> dict[str, Any]:
    """计算仓位建议。

    根据综合评分、波动率、均线状态和MACD状态给出仓位建议。
    """
    # 基础仓位建议
    if score >= 75:
        base_position = 80
    elif score >= 60:
        base_position = 60
    elif score >= 45:
        base_position = 40
    elif score >= 30:
        base_position = 20
    else:
        base_position = 0

    # 波动率调整
    if volatility == "high":
        base_position = int(base_position * 0.6)
    elif volatility == "low":
        base_position = min(100, int(base_position * 1.2))

    # 趋势确认调整
    if ma_bullish and macd_golden and score >= 60:
        base_position = min(100, base_position + 10)
    elif not ma_bullish and score >= 60:
        base_position = max(0, base_position - 10)

    # 建议标签
    if base_position >= 70:
        suggestion = "重仓"
        risk_level = "中高风险"
    elif base_position >= 40:
        suggestion = "半仓"
        risk_level = "中等风险"
    elif base_position >= 20:
        suggestion = "轻仓"
        risk_level = "低风险"
    else:
        suggestion = "观望"
        risk_level = "高风险"

    return {
        "position_pct": base_position,
        "suggestion": suggestion,
        "risk_level": risk_level,
        "notes": _get_position_notes(score, volatility, ma_bullish, macd_golden),
    }


def _get_position_notes(
    score: float, volatility: str, ma_bullish: bool, macd_golden: bool,
    has_divergence: bool = False, dominant_div: str = "none", adx_level: str = "medium",
) -> str:
    """获取仓位建议说明。"""
    notes = []
    if score >= 75:
        notes.append("多指标共振看涨，可考虑重仓")
    elif score >= 60:
        notes.append("技术面偏多，建议半仓以上")
    elif score >= 45:
        notes.append("方向不明确，建议轻仓或观望")
    else:
        notes.append("技术面偏空，建议空仓观望")

    if volatility == "high":
        notes.append("高波动股票，建议降低仓位")
    elif volatility == "low":
        notes.append("低波动股票，可适当加仓")

    if ma_bullish and macd_golden:
        notes.append("趋势确认，可增加仓位")
    elif not ma_bullish:
        notes.append("均线空头排列，谨慎操作")

    if has_divergence and dominant_div == "bullish":
        notes.append("检测到指标底背离，反弹信号增强")
    elif has_divergence and dominant_div == "bearish":
        notes.append("检测到指标顶背离，注意回调风险")

    if adx_level in ("none", "weak"):
        notes.append("ADX显示无明确趋势，市场震荡，控制仓位")

    return "；".join(notes)


@router.get("/diagnosis/quick")
async def quick_diagnosis(
    market: str = "SZ",
    code: str = "",
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """快速诊断接口（GET），方便浏览器直接访问。"""
    if not code:
        return {"error": "请提供股票代码"}
    req = StockIdentifier(market=market, code=code)
    return await diagnose_stock(req, client)
