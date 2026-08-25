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
    if closes is None or volumes is None or len(closes) < 60:
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
        is_bullish = bool(c > o)
        is_bearish = bool(c < o)

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
            prev_bearish = bool(prev_c < prev_o)
            prev_bullish = bool(prev_c > prev_o)
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
    from easy_tdx.chanlun import ChanlunAnalyser
    from easy_tdx.chanlun.mmd import _calc_atr_volatility, calc_signal_quality_report, find_mmds_v39
    from easy_tdx.MyTT import ATR, BOLL, DMI, KDJ, MA, MACD, OBV, RSI

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
        if "3buy" in signal_types and "buy" in latest_mmd.mmd_type.value:
            multi_signal_bonus += 3  # 3买确认
        elif "3sell" in signal_types and "sell" in latest_mmd.mmd_type.value:
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
            # V21: 决策辅助输出（入场/止损/止盈/仓位建议/风险提示）
            "decision_recommendation": getattr(latest_mmd, "_decision_recommendation", None) if latest_mmd else None,
            # V21: 组合信号信息
            "combo_signal": {
                "type": getattr(latest_mmd, "_signal_combo", None),
                "bonus": round(getattr(latest_mmd, "_combo_confidence_bonus", 0.0), 2),
            } if latest_mmd else None,
            # V22: 波动率双重确认
            "vol_regime_dual": getattr(latest_mmd, "_vol_regime_dual", None) if latest_mmd else None,
            # V22: 量价背离检测
            "vol_price_divergence": getattr(latest_mmd, "_vol_price_divergence", None) if latest_mmd else None,
            # V23: Fibonacci回撤位确认（条件40）
            "fib_retracement": getattr(latest_mmd, "_fib_retracement", None) if latest_mmd else None,
            # V23: RSI区域分类（条件41）
            "rsi_zone": getattr(latest_mmd, "_rsi_zone", None) if latest_mmd else None,
            # V23: MACD零轴穿越确认（条件42）
            "macd_zero_cross": getattr(latest_mmd, "_macd_zero_cross", None) if latest_mmd else None,
            # V24: 笔质量评分（条件43）
            "bi_quality": getattr(latest_mmd, "_bi_quality", None) if latest_mmd else None,
            # V24: 中枢强度分析（条件44）
            "zs_strength": getattr(latest_mmd, "_zs_strength", None) if latest_mmd else None,
            # V24: 增强背离检测（条件45）
            "enhanced_divergence": getattr(latest_mmd, "_enhanced_divergence", None) if latest_mmd else None,
            # V24: 信号交叉验证评分（条件46）
            "cross_validation": getattr(latest_mmd, "_cross_validation", None) if latest_mmd else None,
            # V25: 信号后确认验证（条件47）
            "post_signal_confirm": getattr(latest_mmd, "_post_signal_confirm", None) if latest_mmd else None,
            # V25: 动量衰减预警（条件48）
            "momentum_decay": getattr(latest_mmd, "_momentum_decay", None) if latest_mmd else None,
            # V25: 波动率自适应过滤（条件49）
            "vol_regime_filter": getattr(latest_mmd, "_vol_regime_filter", None) if latest_mmd else None,
            # V25: 综合信号质量评分（条件50）
            "composite_quality": getattr(latest_mmd, "_composite_quality", None) if latest_mmd else None,
            # V26: 信号历史验证（条件51）
            "signal_history": getattr(latest_mmd, "_signal_history", None) if latest_mmd else None,
            # V26: 动态风险收益优化（条件52）
            "dynamic_rr_optimization": getattr(latest_mmd, "_dynamic_rr_optimization", None) if latest_mmd else None,
            # V26: 多标的对比评分（条件53）
            "cross_stock_comparison": getattr(latest_mmd, "_cross_stock_comparison", None) if latest_mmd else None,
            # V27: 多级别区间套共振验证（条件54）
            "multi_tf_confluence": getattr(latest_mmd, "_multi_tf_confluence", None) if latest_mmd else None,
            # V27: 买卖点结构位置评分（条件55）
            "structure_position": getattr(latest_mmd, "_structure_position", None) if latest_mmd else None,
            # V27: 个股信号特征学习（条件56）
            "stock_profile": getattr(latest_mmd, "_stock_profile", None) if latest_mmd else None,
            # V28: BOLL带宽压缩确认（条件57）
            "boll_squeeze": getattr(latest_mmd, "_boll_squeeze", None) if latest_mmd else None,
            # V28: 突破量价确认（条件58）
            "breakout_vol_price": getattr(latest_mmd, "_breakout_vol_price", None) if latest_mmd else None,
            # V28: 动态ATR止损位（条件59）
            "dynamic_atr_stop": getattr(latest_mmd, "_dynamic_atr_stop", None) if latest_mmd else None,
            # V29: 趋势方向持续性确认（条件60）
            "trend_continuity": getattr(latest_mmd, "_trend_continuity", None) if latest_mmd else None,
            # V29: 盘整区背离预警（条件61）
            "consolidation_divergence": getattr(latest_mmd, "_consolidation_divergence", None) if latest_mmd else None,
            # V30: K线形态反向确认（条件62）
            "kline_pattern_confirm": getattr(latest_mmd, "_kline_pattern_confirm", None) if latest_mmd else None,
            # V30: 中枢突破方向确认（条件63）
            "zs_breakout_confirm": getattr(latest_mmd, "_zs_breakout_confirm", None) if latest_mmd else None,
            # V30: 近期波动区间止损优化（条件64）
            "recent_range_stop": getattr(latest_mmd, "_recent_range_stop", None) if latest_mmd else None,
            # V31: 均线排列确认（条件65）
            "ma_alignment": getattr(latest_mmd, "_ma_alignment", None) if latest_mmd else None,
            # V31: MACD柱状图加速度（条件66）
            "macd_histogram_acceleration": getattr(latest_mmd, "_macd_histogram_acceleration", None) if latest_mmd else None,
            # V31: 信号综合健康度报告（条件67）
            "signal_health_dashboard": getattr(latest_mmd, "_signal_health_dashboard", None) if latest_mmd else None,
            # V32: 量价背离检测增强（条件68）
            "vol_price_divergence_enhanced": getattr(latest_mmd, "_vol_price_divergence_enhanced", None) if latest_mmd else None,
            # V32: 信号优先级动态排序（条件69）
            "signal_priority": getattr(latest_mmd, "_signal_priority", None) if latest_mmd else None,
            # V32: 支撑阻力位突破确认（条件70）
            "sr_breakout_confirm": getattr(latest_mmd, "_sr_breakout_confirm", None) if latest_mmd else None,
            # V33: OBV能量潮趋势确认（条件71）
            "obv_trend_confirm": getattr(latest_mmd, "_obv_trend_confirm", None) if latest_mmd else None,
            # V33: MACD动能锥面积确认（条件72）
            "macd_hist_area": getattr(latest_mmd, "_macd_hist_area", None) if latest_mmd else None,
            # V33: RSI动量确认（条件73）
            "rsi_momentum_confirm": getattr(latest_mmd, "_rsi_momentum_confirm", None) if latest_mmd else None,
            # V34: 趋势动能延续确认（条件74）
            "trend_momentum_continuation": getattr(latest_mmd, "_trend_momentum_continuation", None) if latest_mmd else None,
            # V34: 多指标共振强度评分（条件75）
            "multi_indicator_resonance": getattr(latest_mmd, "_multi_indicator_resonance", None) if latest_mmd else None,
            # V34: 波动率环境自适应阈值（条件76）
            "volatility_regime": getattr(latest_mmd, '_last_vol_result', None) if latest_mmd else None,
            # V35: 市场大环境过滤（条件77）
            "market_context": getattr(find_mmds, '_last_market_context', None) if latest_mmd else None,
            # V35: 信号衰减增强（条件78）
            "enhanced_signal_decay": getattr(latest_mmd, "_enhanced_signal_decay", None) if latest_mmd else None,
            # V35: 假信号过滤（条件79）
            "false_signal_filter": getattr(latest_mmd, "_false_signal_filter", None) if latest_mmd else None,
            # V35: 动态止损止盈增强（条件80）
            "dynamic_sl_tp_enhanced": getattr(latest_mmd, "_dynamic_sl_tp_enhanced", None) if latest_mmd else None,
            # V35: 板块轮动上下文（条件81）
            "sector_rotation_context": getattr(latest_mmd, "_sector_rotation_context", None) if latest_mmd else None,
            # V35: 多维背离确认（条件82）
            "multi_dim_divergence": getattr(latest_mmd, "_multi_dim_divergence", None) if latest_mmd else None,
            # V36: 信号执行窗口优化（条件83）
            "execution_window": getattr(latest_mmd, "_execution_window", None) if latest_mmd else None,
            # V36: 多时间框架一致性（条件84）
            "tf_consistency": getattr(latest_mmd, "_tf_consistency", None) if latest_mmd else None,
            # V36: 风险调整后收益（条件85）
            "risk_adjusted_return": getattr(latest_mmd, "_risk_adjusted_return", None) if latest_mmd else None,
            # V36: 信号时效性紧急度（条件86）
            "urgency_score": getattr(latest_mmd, "_urgency_score", None) if latest_mmd else None,
            # V36: 市场环境综合评分（条件87）
            "market_composite": getattr(find_mmds, '_last_market_composite', None) if latest_mmd else None,
            # V36: 买卖点策略推荐（条件88）
            "strategy_recommendation": getattr(latest_mmd, "_strategy_recommendation", None) if latest_mmd else None,
            # V37: 连续确认过滤（条件89）
            "consecutive_confirmation": getattr(latest_mmd, "_consecutive_confirmation", None) if latest_mmd else None,
            # V37: 价格动能加速度（条件90）
            "momentum_acceleration": getattr(latest_mmd, "_momentum_acceleration", None) if latest_mmd else None,
            # V37: 波动率状态转换检测（条件91）
            "volatility_regime_change": getattr(find_mmds, '_last_vol_regime_change', None) if latest_mmd else None,
            # V37: 买卖点时间序列关联分析（条件92）
            "temporal_correlation": getattr(latest_mmd, "_temporal_correlation", None) if latest_mmd else None,
            # V37: 多时间框架动量一致性（条件93）
            "multi_tf_momentum": getattr(latest_mmd, "_multi_tf_momentum", None) if latest_mmd else None,
            # V37: 信号综合质量排名（条件94）
            "quality_ranking": getattr(latest_mmd, "_quality_ranking", None) if latest_mmd else None,
            # V38: 中枢结构完整性评分（条件95）
            "zs_structure_integrity": getattr(latest_mmd, "_zs_structure_integrity", None) if latest_mmd else None,
            # V38: 买卖点位置评分（条件96）
            "mmd_position_score": getattr(latest_mmd, "_mmd_position_score", None) if latest_mmd else None,
            # V38: 信号后收益跟踪（条件97）
            "post_signal_return": getattr(latest_mmd, "_post_signal_return", None) if latest_mmd else None,
            # V38: 中枢突破力度评估（条件98）
            "breakout_strength": getattr(latest_mmd, "_breakout_strength", None) if latest_mmd else None,
            # V38: 多指标偏离度综合评分（条件99）
            "composite_deviation": getattr(find_mmds, '_last_composite_deviation', None) if latest_mmd else None,
            # V38: 信号衰减预警（条件100）
            "signal_decay_warning": getattr(latest_mmd, "_signal_decay_warning", None) if latest_mmd else None,
            # V39: 买卖点信号一致性验证（条件101）
            "signal_consistency": getattr(latest_mmd, "_signal_consistency", None) if latest_mmd else None,
            # V39: 中枢级别匹配验证（条件102）
            "zs_level_match": getattr(latest_mmd, "_zs_level_match", None) if latest_mmd else None,
            # V39: 多时间框架背离确认（条件103）
            "multi_tf_divergence": getattr(find_mmds_v39, '_last_multi_tf_divergence', None) if latest_mmd else None,
            # V39: 独立交叉验证（条件104）
            "independent_cross_validation": getattr(latest_mmd, "_independent_cross_validation", None) if latest_mmd else None,
            # V39: 决策质量综合评分（条件105）
            "decision_quality_score": getattr(latest_mmd, "_decision_quality_score", None) if latest_mmd else None,
            # V40: 时间衰减自适应过滤（条件106）
            "time_decay_adaptive": getattr(latest_mmd, "_time_decay_adaptive", None) if latest_mmd else None,
            # V40: 中枢突破回踩验证（条件107）
            "breakout_retest_validation": getattr(latest_mmd, "_breakout_retest_validation", None) if latest_mmd else None,
            # V40: 多周期MACD共振确认（条件108）
            "multi_cycle_macd_resonance": getattr(find_mmds_v39, '_last_macd_resonance', None) if latest_mmd else None,
            # V40: K线形态综合评分（条件109）
            "kline_pattern_composite": getattr(latest_mmd, "_kline_pattern_composite", None) if latest_mmd else None,
            # V40: 置信度动态校准（条件110）
            "confidence_calibration": getattr(latest_mmd, "_confidence_calibration", None) if latest_mmd else None,
            # V41: 量价能量分布分析（条件111）
            "volume_price_energy_dist": getattr(latest_mmd, "_volume_price_energy_dist", None) if latest_mmd else None,
            # V41: 量能周期检测（条件112）
            "volume_cycle_detection": getattr(find_mmds_v39, '_last_volume_cycle', None) if latest_mmd else None,
            # V41: 走势预测（条件113）
            "post_signal_trajectory": getattr(find_mmds_v39, '_last_trajectory_prediction', None) if latest_mmd else None,
            # V41: 动态质量分层（条件114）
            "quality_tier_classification": getattr(latest_mmd, "_quality_tier_classification", None) if latest_mmd else None,
            # V41: 反转风险评估（条件115）
            "reversal_risk_assessment": getattr(find_mmds_v39, '_last_reversal_risk', None) if latest_mmd else None,
            # V42: 后确认验证（条件116）
            "post_signal_confirmation": getattr(latest_mmd, "_post_signal_confirmation", None) if latest_mmd else None,
            # V42: 突破-回调量比验证（条件117）
            "break_pullback_volume_ratio": getattr(latest_mmd, "_break_pullback_volume_ratio", None) if latest_mmd else None,
            # V42: 中枢距离验证（条件118）
            "zhongshu_distance_validation": getattr(latest_mmd, "_zhongshu_distance_validation", None) if latest_mmd else None,
            # V42: ADX趋势强度确认（条件119）
            "adx_trend_strength": getattr(latest_mmd, "_adx_trend_strength", None) if latest_mmd else None,
            # V42: 信号时效性衰减增强（条件120）
            "signal_freshness": getattr(latest_mmd, "_signal_freshness", None) if latest_mmd else None,
            # V44: 趋势方向对齐验证（条件121）
            "trend_direction_alignment": getattr(latest_mmd, "_trend_direction_alignment", None) if latest_mmd else None,
            # V44: 突破笔力度对比（条件122）
            "breakout_bi_strength_compare": getattr(latest_mmd, "_breakout_bi_strength_compare", None) if latest_mmd else None,
            # V44: 回踩时间窗口过滤（条件123）
            "pullback_time_window": getattr(latest_mmd, "_pullback_time_window", None) if latest_mmd else None,
            # V44: 波动率自适应阈值（条件124）
            "volatility_adaptive_threshold": getattr(latest_mmd, "_volatility_adaptive_threshold", None) if latest_mmd else None,
            # V44: 多指标背离共振（条件125）
            "multi_indicator_divergence_resonance": getattr(latest_mmd, "_multi_indicator_divergence_resonance", None) if latest_mmd else None,
            # V46: 趋势动能强度过滤（条件126）
            "trend_momentum_strength": getattr(latest_mmd, "_trend_momentum_strength", None) if latest_mmd else None,
            # V46: 量价背离二次确认（条件127）
            "volume_price_divergence_secondary": getattr(latest_mmd, "_volume_price_divergence_secondary", None) if latest_mmd else None,
            # V46: 中枢突破真实性验证（条件128）
            "zs_breakout_authenticity": getattr(latest_mmd, "_zs_breakout_authenticity", None) if latest_mmd else None,
            # V46: 多时间框架信号一致性（条件129）
            "multi_tf_signal_consistency": getattr(latest_mmd, "_multi_tf_signal_consistency", None) if latest_mmd else None,
            # V46: 动态市场环境适配（条件130）
            # V47: 后确认价格跟随过滤（条件131）
            "post_signal_price_follow_through": getattr(latest_mmd, "_post_signal_price_follow_through", None) if latest_mmd else None,
            # V47: 信号有效性窗口（条件132）
            "signal_validity_window": getattr(latest_mmd, "_signal_validity_window", None) if latest_mmd else None,
            # V47: 置信度动态校准（条件133）
            "confidence_v47_calibrated": getattr(latest_mmd, "_confidence_v47_calibrated", None) if latest_mmd else None,
            # V48: 量价背离二次确认（条件134）
            "volume_price_divergence_secondary_v48": getattr(latest_mmd, "_volume_price_divergence_secondary_v48", None) if latest_mmd else None,
            # V48: 趋势强度加权（条件135）
            "trend_strength_weighting": getattr(latest_mmd, "_trend_strength_weighting", None) if latest_mmd else None,
            # V48: 动态风险收益比（条件136）
            "dynamic_risk_reward_ratio": getattr(latest_mmd, "_dynamic_risk_reward_ratio", None) if latest_mmd else None,
            "dynamic_market_regime": getattr(latest_mmd, "_dynamic_market_regime", None) if latest_mmd else None,
            # V49: 突破力度二次验证（条件137）
            "breakout_strength_revalidation_v49": getattr(latest_mmd, "_breakout_strength_revalidation_v49", None) if latest_mmd else None,
            # V49: 回踩结构完整性（条件138）
            "pullback_structure_integrity_v49": getattr(latest_mmd, "_pullback_structure_integrity_v49", None) if latest_mmd else None,
            # V49: 中枢级别权重（条件139）
            "zhongshu_level_weight_v49": getattr(latest_mmd, "_zhongshu_level_weight_v49", None) if latest_mmd else None,
            # V50: 板块联动分析（条件140）
            "sector_correlation_v50": getattr(latest_mmd, "_sector_correlation_v50", None) if latest_mmd else None,
            # V50: 多时间框架共振验证（条件141）
            "multi_tf_resonance_v50": getattr(latest_mmd, "_multi_tf_resonance_v50", None) if latest_mmd else None,
            # V50: 缠论级别递归验证（条件142）
            "level_recursive_validation_v50": getattr(latest_mmd, "_level_recursive_validation_v50", None) if latest_mmd else None,
            # V50: 市场情绪指标融合（条件143）
            "market_sentiment_fusion_v50": getattr(latest_mmd, "_market_sentiment_fusion_v50", None) if latest_mmd else None,
            # V51: 突破笔力度二次确认增强（条件144）
            "breakout_bi_strength_enhanced_v51": getattr(latest_mmd, "_breakout_bi_strength_enhanced_v51", None) if latest_mmd else None,
            # V51: 回踩笔深度+时间综合验证（条件145）
            "pullback_depth_time_v51": getattr(latest_mmd, "_pullback_depth_time_v51", None) if latest_mmd else None,
            # V51: 趋势强度综合评分（条件146）
            "trend_strength_composite_v51": getattr(latest_mmd, "_trend_strength_composite_v51", None) if latest_mmd else None,
            # V51: 交易决策建议（条件147）
            "trading_decision_v51": getattr(latest_mmd, "_trading_decision_v51", None) if latest_mmd else None,
            # V52: 量价持续确认（条件148）
            "volume_sustain_after_signal_v52": getattr(latest_mmd, "_volume_sustain_after_signal_v52", None) if latest_mmd else None,
            # V52: 多指标背离共振（条件149）
            "multi_indicator_divergence_fusion_v52": getattr(latest_mmd, "_multi_indicator_divergence_fusion_v52", None) if latest_mmd else None,
            # V52: 近期极端价位检测（条件150）
            "recent_extreme_price_v52": getattr(latest_mmd, "_recent_extreme_price_v52", None) if latest_mmd else None,
            # V52: 市场环境健康评分（条件151）
            "market_regime_score_v52": getattr(latest_mmd, "_market_regime_score_v52", None) if latest_mmd else None,
            # V53: 趋势阶段识别与顺势确认（条件152）
            "trend_stage_follow_confirmation_v53": getattr(latest_mmd, "_trend_stage_follow_confirmation_v53", None) if latest_mmd else None,
            # V53: ATR自适应止损距离（条件153）
            "atr_adaptive_stop_v53": getattr(latest_mmd, "_atr_adaptive_stop_v53", None) if latest_mmd else None,
            # V53: 中枢突破力度验证（条件154）
            "zs_breakout_strength_v53": getattr(latest_mmd, "_zs_breakout_strength_v53", None) if latest_mmd else None,
            # V53: 信号质量综合分层（条件155）
            "signal_quality_tier_v53": getattr(latest_mmd, "_signal_quality_tier_v53", None) if latest_mmd else None,
            # V54: 多K线确认后确认（条件156）
            "multi_bar_confirmation_v54": getattr(latest_mmd, "_multi_bar_confirmation_v54", None) if latest_mmd else None,
            # V54: 缺口风险评估（条件157）
            "gap_risk_assessment_v54": getattr(latest_mmd, "_gap_risk_assessment_v54", None) if latest_mmd else None,
            # V54: 波动率 regime 切换检测（条件158）
            "volatility_regime_change_v54": getattr(latest_mmd, "_volatility_regime_change_v54", None) if latest_mmd else None,
            # V54: 量价配合度评分（条件159）
            "volume_price_coordination_v54": getattr(latest_mmd, "_volume_price_coordination_v54", None) if latest_mmd else None,
            # V55: 分钟级多时间框架共振过滤（条件160）
            "multi_tf_resonance_filter_v55": getattr(latest_mmd, "_multi_tf_resonance_filter_v55", None) if latest_mmd else None,
            # V55: 中枢级别权重自适应（条件161）
            "zhongshu_level_weight_v55": getattr(latest_mmd, "_zhongshu_level_weight_v55", None) if latest_mmd else None,
            # V55: 弱势股专项风险检测（条件162）
            "weak_stock_risk_v55": getattr(latest_mmd, "_weak_stock_risk_v55", None) if latest_mmd else None,
            # V55: 信号与趋势方向对齐验证（条件163）
            "signal_trend_alignment_v55": getattr(latest_mmd, "_signal_trend_alignment_v55", None) if latest_mmd else None,
            # V56: 假突破识别（条件164）
            "false_breakout_detection_v56": getattr(latest_mmd, "_false_breakout_detection_v56", None) if latest_mmd else None,
            # V56: 中枢结构复杂度分析（条件165）
            "zhongshu_structure_complexity_v56": getattr(latest_mmd, "_zhongshu_structure_complexity_v56", None) if latest_mmd else None,
            # V56: 波动率自适应仓位建议（条件166）
            "volatility_adaptive_position_v56": getattr(latest_mmd, "_volatility_adaptive_position_v56", None) if latest_mmd else None,
            # V56: 多信号共振评分（条件167）
            "multi_signal_resonance_v56": getattr(latest_mmd, "_multi_signal_resonance_v56", None) if latest_mmd else None,
            # V57: 回踩幅度与时间双重过滤（条件168）
            "pullback_filter_v57": getattr(latest_mmd, "_pullback_filter_v57", None) if latest_mmd else None,
            # V57: 突破力度验证（条件169）
            "breakout_strength_validation_v57": getattr(latest_mmd, "_breakout_strength_validation_v57", None) if latest_mmd else None,
            # V57: 中枢背驰检测（条件170）
            "zs_divergence_check_v57": getattr(latest_mmd, "_zs_divergence_check_v57", None) if latest_mmd else None,
            # V57: 信号衰减检测（条件171）
            "signal_decay_detection_v57": getattr(latest_mmd, "_signal_decay_detection_v57", None) if latest_mmd else None,
            # V58: 多时间框架趋势一致性验证（条件172）
            "multi_tf_trend_consistency_v58": getattr(latest_mmd, "_multi_tf_trend_consistency_v58", None) if latest_mmd else None,
            # V58: 成交量堆积验证（条件173）
            "volume_accumulation_validation_v58": getattr(latest_mmd, "_volume_accumulation_validation_v58", None) if latest_mmd else None,
            # V58: ATR自适应止损距离（条件174）
            "atr_adaptive_stop_v58": getattr(latest_mmd, "_atr_adaptive_stop_v58", None) if latest_mmd else None,
            # V58: 信号质量综合评分（条件175）
            "composite_quality_score_v58": getattr(latest_mmd, "_composite_quality_score_v58", None) if latest_mmd else None,
            # V59: 波动率自适应MA周期（条件176）
            "volatility_adaptive_ma_v59": getattr(latest_mmd, "_volatility_adaptive_ma_v59", None) if latest_mmd else None,
            # V59: ATR倍数自适应（条件177）
            "atr_multiplier_adapt_v59": getattr(latest_mmd, "_atr_multiplier_adapt_v59", None) if latest_mmd else None,
            # V59: 多时间框架共振信号（条件178）
            "multi_tf_resonance_signal_v59": getattr(latest_mmd, "_multi_tf_resonance_signal_v59", None) if latest_mmd else None,
            # V59: 信号衰减速度评估（条件179）
            "signal_decay_speed_v59": getattr(latest_mmd, "_signal_decay_speed_v59", None) if latest_mmd else None,
            # V60: RSI深度背离过滤（条件180）
            "rsi_deep_divergence_v60": getattr(latest_mmd, "_rsi_deep_divergence_v60", None) if latest_mmd else None,
            # V60: MA排列间距强度评分（条件181）
            "ma_spacing_strength_v60": getattr(latest_mmd, "_ma_spacing_strength_v60", None) if latest_mmd else None,
            # V60: 中枢支撑/阻力距离评分增强（条件182）
            "zs_distance_enhanced_v60": getattr(latest_mmd, "_zs_distance_enhanced_v60", None) if latest_mmd else None,
            # V60: KDJ超买超卖确认（条件183）
            "kdj_ob_os_confirm_v60": getattr(latest_mmd, "_kdj_ob_os_confirm_v60", None) if latest_mmd else None,
            # V61: MACD柱状图背离融合（条件184）
            "macd_hist_divergence_v61": getattr(latest_mmd, "_macd_hist_divergence_v61", None) if latest_mmd else None,
            # V61: 综合多信号评分（条件185）
            "composite_signal_score_v61": getattr(latest_mmd, "_composite_signal_score_v61", None) if latest_mmd else None,
            # V62: BOLL带宽突破确认（条件186）
            "boll_bandwidth_breakout_v62": getattr(latest_mmd, "_boll_bandwidth_breakout_v62", None) if latest_mmd else None,
            # V62: BOLL带宽压缩反弹确认（条件187）
            "boll_bandwidth_reversal_v62": getattr(latest_mmd, "_boll_bandwidth_reversal_v62", None) if latest_mmd else None,
            # V62: 动态阈值-波动率状态切换（条件188）
            "dynamic_threshold_volatility_regime_v62": getattr(latest_mmd, "_dynamic_threshold_volatility_regime_v62", None) if latest_mmd else None,
            # V62: 动态阈值-ATR倍数自适应（条件189）
            "dynamic_threshold_atr_multiplier_v62": getattr(latest_mmd, "_dynamic_threshold_atr_multiplier_v62", None) if latest_mmd else None,
            # V63: 中枢级别权重优化增强（条件190）
            "zhongshu_level_weight_enhanced_v63": getattr(latest_mmd, "_zhongshu_level_weight_enhanced_v63", None) if latest_mmd else None,
            # V63: 多周期信号衰减追踪（条件191）
            "multi_period_signal_decay_v63": getattr(latest_mmd, "_multi_period_signal_decay_v63", None) if latest_mmd else None,
            # V65: 量价背离二次确认增强（条件192）
            "volume_price_divergence_secondary_v65": getattr(latest_mmd, "_volume_price_divergence_secondary_v65", None) if latest_mmd else None,
            # V65: 中枢突破回踩确认（条件193）
            "breakout_retest_confirmation_v65": getattr(latest_mmd, "_breakout_retest_confirmation_v65", None) if latest_mmd else None,
            # V65: 波动率压缩突破信号（条件194）
            "volatility_compression_breakout_v65": getattr(latest_mmd, "_volatility_compression_breakout_v65", None) if latest_mmd else None,
            # V65: 买卖点时间窗口新鲜度（条件195）
            "signal_time_window_freshness_v65": getattr(latest_mmd, "_signal_time_window_freshness_v65", None) if latest_mmd else None,
            # V66: MACD动能加速确认（条件196）
            "macd_momentum_acceleration_v66": getattr(latest_mmd, "_macd_momentum_acceleration_v66", None) if latest_mmd else None,
            # V66: 量价配合深度评分（条件197）
            "volume_price_coordination_deep_v66": getattr(latest_mmd, "_volume_price_coordination_deep_v66", None) if latest_mmd else None,
            # V66: 多时间框架共振强度（条件198）
            "multi_tf_convergence_intensity_v66": getattr(latest_mmd, "_multi_tf_convergence_intensity_v66", None) if latest_mmd else None,
            # V66: 信号执行优先级（条件199）
            "signal_execution_priority_v66": getattr(latest_mmd, "_signal_execution_priority_v66", None) if latest_mmd else None,
            # V67: 中枢背驰力度量化（条件200）
            "zhongshu_divergence_strength_v67": getattr(latest_mmd, "_zhongshu_divergence_strength_v67", None) if latest_mmd else None,
            # V67: 多级别买卖点一致性验证（条件201）
            "multi_level_mmd_consistency_v67": getattr(latest_mmd, "_multi_level_mmd_consistency_v67", None) if latest_mmd else None,
            # V67: 信号后价格轨迹健康度（条件202）
            "post_signal_trajectory_health_v67": getattr(latest_mmd, "_post_signal_trajectory_health_v67", None) if latest_mmd else None,
            # V67: 动态止损止盈推荐（条件203）
            "dynamic_sl_tp_recommendation_v67": getattr(latest_mmd, "_dynamic_sl_tp_recommendation_v67", None) if latest_mmd else None,
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
            "zone": rsi_position,  # V23: RSI区域（与position相同，前端可直接使用）
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


@router.post("/diagnosis/multi-stock")
async def multi_stock_comparison(
    stocks: list[StockIdentifier],
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """多股票信号质量对比分析（V64 新增）。

    在同一请求中获取多只股票的缠论信号质量评分，便于横向比较。
    返回每只股票的信号数量、平均置信度、各条件组命中次数。
    """
    if not stocks:
        return {"error": "请提供至少一只股票"}

    from easy_tdx.backtest.chanlun_validator import ConditionGroup

    results: list[dict[str, Any]] = []
    for stock in stocks:
        try:
            bar_data = client.get_security_bars(
                category=stock.category,
                exchange=stock.exchange,
                code=stock.code,
                start=-1,
                end=-1,
                count=500,
            )
            if not bar_data:
                results.append({
                    "stock_code": stock.code,
                    "stock_name": stock.code,
                    "error": "无K线数据",
                })
                continue

            import pandas as pd
            df = pd.DataFrame(bar_data)
            if len(df) < 100:
                results.append({
                    "stock_code": stock.code,
                    "stock_name": stock.code,
                    "error": f"数据不足（{len(df)} bars）",
                })
                continue

            from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
            config = ChanlunConfig()
            analyser = ChanlunAnalyser(code=stock.code, frequency="daily", config=config)
            chanlun_result = analyser.process_klines(df)

            valid_signals = [
                mmd for mmd in chanlun_result.mmds
                if mmd.mmd_type.name in ("BUY_1", "BUY_2", "BUY_3", "SELL_1", "SELL_2", "SELL_3")
                and mmd.bi is not None
                and mmd.confidence >= 0.0
            ]

            # 条件命中统计
            condition_counts: dict[str, int] = {}
            for mmd in valid_signals:
                for g in ConditionGroup:
                    low, high = g.condition_range
                    for c in range(low, high + 1):
                        attr = f"_condition_{c}"
                        if hasattr(mmd, attr):
                            key = f"{g.value}_cond{c}"
                            condition_counts[key] = condition_counts.get(key, 0) + 1
                        # V63 特有字段
                        if c == 190 and hasattr(mmd, "_zhongshu_level_weight_enhanced_v63"):
                            condition_counts["v63_cond190"] = condition_counts.get("v63_cond190", 0) + 1
                        if c == 191 and hasattr(mmd, "_multi_period_signal_decay_v63"):
                            condition_counts["v63_cond191"] = condition_counts.get("v63_cond191", 0) + 1
                        # V65 特有字段
                        if c == 192 and hasattr(mmd, "_volume_price_divergence_secondary_v65"):
                            condition_counts["v65_cond192"] = condition_counts.get("v65_cond192", 0) + 1
                        if c == 193 and hasattr(mmd, "_breakout_retest_confirmation_v65"):
                            condition_counts["v65_cond193"] = condition_counts.get("v65_cond193", 0) + 1
                        if c == 194 and hasattr(mmd, "_volatility_compression_breakout_v65"):
                            condition_counts["v65_cond194"] = condition_counts.get("v65_cond194", 0) + 1
                        if c == 195 and hasattr(mmd, "_signal_time_window_freshness_v65"):
                            condition_counts["v65_cond195"] = condition_counts.get("v65_cond195", 0) + 1
                        if c == 196 and hasattr(mmd, "_macd_momentum_acceleration_v66"):
                            condition_counts["v66_cond196"] = condition_counts.get("v66_cond196", 0) + 1
                        if c == 197 and hasattr(mmd, "_volume_price_coordination_deep_v66"):
                            condition_counts["v66_cond197"] = condition_counts.get("v66_cond197", 0) + 1
                        if c == 198 and hasattr(mmd, "_multi_tf_convergence_intensity_v66"):
                            condition_counts["v66_cond198"] = condition_counts.get("v66_cond198", 0) + 1
                        if c == 199 and hasattr(mmd, "_signal_execution_priority_v66"):
                            condition_counts["v66_cond199"] = condition_counts.get("v66_cond199", 0) + 1
                        # V67 特有字段
                        if c == 200 and hasattr(mmd, "_zhongshu_divergence_strength_v67"):
                            condition_counts["v67_cond200"] = condition_counts.get("v67_cond200", 0) + 1
                        if c == 201 and hasattr(mmd, "_multi_level_mmd_consistency_v67"):
                            condition_counts["v67_cond201"] = condition_counts.get("v67_cond201", 0) + 1
                        if c == 202 and hasattr(mmd, "_post_signal_trajectory_health_v67"):
                            condition_counts["v67_cond202"] = condition_counts.get("v67_cond202", 0) + 1
                        if c == 203 and hasattr(mmd, "_dynamic_sl_tp_recommendation_v67"):
                            condition_counts["v67_cond203"] = condition_counts.get("v67_cond203", 0) + 1
            buy_count = sum(1 for s in valid_signals if "buy" in s.mmd_type.value)
            sell_count = sum(1 for s in valid_signals if "sell" in s.mmd_type.value)
            avg_conf = float(np.mean([s.confidence for s in valid_signals])) if valid_signals else 0.0

            results.append({
                "stock_code": stock.code,
                "stock_name": stock.code,
                "total_bars": len(df),
                "signal_count": len(valid_signals),
                "buy_count": buy_count,
                "sell_count": sell_count,
                "avg_confidence": round(avg_conf, 4),
                "condition_breakdown": condition_counts,
            })
        except Exception as e:
            results.append({
                "stock_code": stock.code,
                "error": str(e),
            })

    return {
        "stocks": results,
        "count": len(results),
    }
