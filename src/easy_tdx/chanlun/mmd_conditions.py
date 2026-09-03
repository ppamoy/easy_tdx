"""V76-V82 缠论增强条件簇（条件236-263）。

从 mmd.py 抽出的独立模块（V393 模块治理第二阶段）：价格结构完整性、趋势方向对齐、
波动率自适应置信度、最终有效性评分、量能分布深度、中枢结构权重、信号新鲜度、
价格动能加速度、周期位置、多信号一致性、波动率压缩突破、资金流向背离、分型稳定性、
距离安全、多级别一致性、动能持续性、中枢距离、量能配合、均线排列、盈亏比、
波动率状态转换、支撑阻力强度、量价能量分布、执行窗口、信号衰减、突破回踩、
多周期MACD共振、波动率压缩突破。

mmd.py 顶层通过惰性再导出保持既有导入兼容。
"""

from __future__ import annotations

from typing import Any

from easy_tdx.chanlun.types import MMD
from easy_tdx.MyTT import MA


def _calc_atr_volatility(closes: list[float] | None, lookback: int = 20) -> float:
    """计算近期ATR波动率，用于动态调整阈值。

    Returns:
        ATR/价格比率（波动率），0-1之间。越高表示市场越波动，阈值应更宽松。
    """
    if closes is None:
        return 0.0
    if len(closes) < lookback + 1:
        return 0.02  # 默认低波动

    highs = []
    lows = []
    prev_closes = []
    for i in range(-lookback, 0):
        idx = len(closes) + i
        highs.append(closes[idx])
        lows.append(closes[idx])
        prev_closes.append(closes[idx - 1])

    tr = []
    for h, low, pc in zip(highs, lows, prev_closes):
        tr.append(max(h - low, abs(h - pc), abs(low - pc)))

    atr = sum(tr) / len(tr) if tr else 0
    avg_price = sum(closes[-lookback:]) / lookback if len(closes) > 0 else 1
    return atr / avg_price if avg_price > 0 else 0.02


# V76: 条件 236-239（价格结构完整性+趋势方向对齐+波动率自适应置信度+买卖点最终有效性）


def _calc_price_structure_integrity_v76(
    mmd: MMD,
    closes: list[float],
    volumes: list[float] | None,
) -> dict[str, Any]:
    """价格结构完整性验证（V76 条件236）。

    评估买入/卖出信号前的价格结构是否完整：
    - 上涨趋势中应有清晰的中枢+突破结构
    - 下跌趋势中应有清晰的下跌笔+支撑结构
    - 通过价格序列的连续性和结构评分判断信号可靠性

    返回：structure_score, trend_structure, key_levels_valid, confirm_signal, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "structure_score": 0.0,
        "trend_structure": "unknown",
        "key_levels_valid": False,
        "confirm_signal": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 30:
            result["msg"] = "数据不足（需≥30根）"
            return result

        is_buy = "buy" in mmd.mmd_type.value

        # 计算近期高低点
        lookback = min(30, n)
        recent_high = max(closes[-lookback:])
        recent_low = min(closes[-lookback:])
        price_range = recent_high - recent_low

        if price_range <= 0:
            result["msg"] = "价格区间为零"
            return result

        current_price = closes[-1]
        price_position = (current_price - recent_low) / price_range  # 0~1 之间

        # 判断趋势结构完整性
        if is_buy:
            if price_position < 0.3:
                trend_struct = "bottom_accumulation"
                score = 0.8
            elif price_position < 0.5:
                trend_struct = "mid_recovery"
                score = 0.6
            elif price_position < 0.7:
                trend_struct = "breakout_attempt"
                score = 0.5
            else:
                trend_struct = "overextended"
                score = 0.3
        else:
            if price_position > 0.7:
                trend_struct = "top_distribution"
                score = 0.8
            elif price_position > 0.5:
                trend_struct = "mid_pullback"
                score = 0.6
            elif price_position > 0.3:
                trend_struct = "breakdown_attempt"
                score = 0.5
            else:
                trend_struct = "oversold"
                score = 0.3

        # 关键价位有效性
        high_dist = (recent_high - current_price) / recent_high
        low_dist = (current_price - recent_low) / recent_low
        key_levels_valid = high_dist < 0.1 or low_dist < 0.1

        # 成交量确认
        if volumes and len(volumes) >= 20:
            avg_vol = sum(volumes[-20:]) / 20
            vol_ratio = volumes[-1] / max(avg_vol, 1e-10)
            if is_buy and vol_ratio > 1.2:
                score = min(score + 0.1, 1.0)
            elif not is_buy and vol_ratio > 1.5:
                score = min(score + 0.05, 1.0)

        result["structure_score"] = round(score, 3)
        result["trend_structure"] = trend_struct
        result["key_levels_valid"] = key_levels_valid
        result["confirm_signal"] = score >= 0.5 and key_levels_valid
        result["confidence_adjust"] = round(score * 0.05 - 0.02, 3)
        result["msg"] = (
            f"结构评分={score:.0%} {trend_struct} "
            f"价格位置={price_position:.0%} 关键位={'✅' if key_levels_valid else '⚠️'} "
            f"置信度{score * 0.05 - 0.02:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_trend_alignment_validation_v76(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """趋势方向对齐验证（V76 条件237）。

    验证当前信号的 trend direction 与多周期均线方向是否一致。
    趋势对齐→信号更可靠；趋势背离→信号需谨慎。

    返回：alignment_status, ma_alignment, trend_direction, confirm_signal, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "alignment_status": "unknown",
        "ma_alignment": [],
        "trend_direction": "unknown",
        "confirm_signal": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 60:
            result["msg"] = "数据不足（需≥60根）"
            return result

        is_buy = "buy" in mmd.mmd_type.value

        # 计算多周期均线
        mas: dict[int, dict[str, str]] = {}
        for period in [5, 10, 20, 60]:
            if n >= period:
                ma_val = sum(closes[-period:]) / period
                ma_prev = sum(closes[-period - 1 : -1]) / period if n >= period + 1 else ma_val
                ma_trend = (
                    "up"
                    if closes[-1] > ma_val and ma_val > ma_prev
                    else ("down" if closes[-1] < ma_val and ma_val < ma_prev else "flat")
                )
                mas[period] = {"trend": ma_trend}

        up_count = sum(1 for m in mas.values() if m["trend"] == "up")
        down_count = sum(1 for m in mas.values() if m["trend"] == "down")
        total = len(mas)

        if up_count >= total * 0.7:
            trend_dir = "bullish"
        elif down_count >= total * 0.7:
            trend_dir = "bearish"
        elif up_count > down_count:
            trend_dir = "weak_bullish"
        elif down_count > up_count:
            trend_dir = "weak_bearish"
        else:
            trend_dir = "neutral"

        if is_buy:
            aligned = trend_dir in ("bullish", "weak_bullish")
            alignment_pct = up_count / max(total, 1)
        else:
            aligned = trend_dir in ("bearish", "weak_bearish")
            alignment_pct = down_count / max(total, 1)

        if aligned and alignment_pct >= 0.7:
            status = "strong_aligned"
        elif aligned:
            status = "moderately_aligned"
        else:
            status = "diverged"

        result["alignment_status"] = status
        result["ma_alignment"] = [{"period": k, "trend": v["trend"]} for k, v in mas.items()]
        result["trend_direction"] = trend_dir
        result["confirm_signal"] = aligned and alignment_pct >= 0.5
        result["confidence_adjust"] = round(alignment_pct * 0.06 - 0.03, 3)
        result["msg"] = f"趋势对齐={status} {trend_dir} 置信度{alignment_pct * 0.06 - 0.03:+.0%}"
        return result
    except Exception:
        return result


def _calc_volatility_adaptive_confidence_v76(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """波动率自适应置信度（V76 条件238）。

    根据当前市场波动率环境调整信号置信度：
    - 低波动环境→突破信号更可靠
    - 高波动环境→信号需要更强确认

    返回：vol_level, atr_ratio, adaptive_confidence, confirm_signal, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "vol_level": "unknown",
        "atr_ratio": 0.0,
        "adaptive_confidence": 0.0,
        "confirm_signal": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 30:
            result["msg"] = "数据不足（需≥30根）"
            return result

        _ = "buy" in mmd.mmd_type.value

        # 计算简化 ATR（使用负索引兼容 Python）
        trs: list[float] = []
        for i in range(-20, 0):
            if i >= -n and i - 1 >= -n:
                tr = abs(closes[i] - closes[i - 1])
                trs.append(tr)
        if not trs:
            result["msg"] = "无法计算波动率"
            return result

        atr = sum(trs) / len(trs)
        current_price = closes[-1]
        atr_ratio = atr / max(current_price, 1e-10)

        # 波动率百分位
        if n >= 60:
            trs_full: list[float] = []
            for i in range(-60, 0):
                if i >= 0 and i - 1 >= 0:
                    trs_full.append(abs(closes[i] - closes[i - 1]))
            avg_tr_full = sum(trs_full) / len(trs_full) if trs_full else atr
            vol_percentile = atr / max(avg_tr_full, 1e-10)
        else:
            vol_percentile = 1.0

        if vol_percentile < 0.5:
            vol_level = "low"
        elif vol_percentile < 1.0:
            vol_level = "normal"
        elif vol_percentile < 1.5:
            vol_level = "high"
        else:
            vol_level = "extreme"

        base_confidence = mmd.confidence if mmd.confidence else 0.5
        if vol_level == "low":
            adaptive_conf = min(base_confidence + 0.08, 1.0)
            adjust = 0.05
        elif vol_level == "normal":
            adaptive_conf = base_confidence
            adjust = 0.0
        elif vol_level == "high":
            adaptive_conf = max(base_confidence - 0.05, 0.0)
            adjust = -0.03
        else:
            adaptive_conf = max(base_confidence - 0.10, 0.0)
            adjust = -0.06

        confirm = adaptive_conf >= 0.5
        result["vol_level"] = vol_level
        result["atr_ratio"] = round(atr_ratio, 4)
        result["adaptive_confidence"] = round(adaptive_conf, 3)
        result["confirm_signal"] = confirm
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"波动率={vol_level} ATR比={atr_ratio:.2%} "
            f"自适应置信度={adaptive_conf:.0%} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_signal_final_validity_v76(
    mmd: MMD,
) -> dict[str, Any]:
    """买卖点最终有效性评分（V76 条件239）。

    综合所有已计算的 V75 和 V76 条件评分，给出最终信号有效性判断。
    这是整个缠论条件体系的"终审判决"。

    返回：final_validity, validity_score, recommendation, confirm_signal, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "final_validity": "unknown",
        "validity_score": 0.0,
        "recommendation": "观望",
        "confirm_signal": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        _ = "buy" in mmd.mmd_type.value

        adjustments: list[float] = []
        adjust_fields = [
            "_pullback_depth_validation_v75",
            "_zhongshu_retracement_confirm_v75",
            "_volume_peak_duration_v75",
            "_multi_signal_time_consistency_v75",
            "_price_structure_integrity_v76",
            "_trend_alignment_validation_v76",
            "_volatility_adaptive_confidence_v76",
        ]
        for field in adjust_fields:
            val = getattr(mmd, field, None)
            if val and isinstance(val, dict):
                adj = val.get("confidence_adjust", 0.0)
                if adj != 0.0:
                    adjustments.append(adj)

        base_conf = mmd.confidence if mmd.confidence else 0.5
        total_adjust = sum(adjustments)
        final_score = max(0.0, min(1.0, base_conf + total_adjust))

        if final_score >= 0.7:
            validity = "strong"
            rec = "强信号"
            confirm = True
            adj = 0.05
        elif final_score >= 0.5:
            validity = "moderate"
            rec = "中性信号"
            confirm = True
            adj = 0.02
        elif final_score >= 0.3:
            validity = "weak"
            rec = "弱信号"
            confirm = False
            adj = -0.02
        else:
            validity = "invalid"
            rec = "不建议操作"
            confirm = False
            adj = -0.05

        result["final_validity"] = validity
        result["validity_score"] = round(final_score, 3)
        result["recommendation"] = rec
        result["confirm_signal"] = confirm
        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = (
            f"有效性={validity} 得分={final_score:.0%} "
            f"建议:{rec} 基础={base_conf:.0%} 调整{total_adjust:+.0%}"
        )
        return result
    except Exception:
        return result


# ── V77: 条件 240-243（量能分布深度+中枢结构权重+信号新鲜度+价格动能加速度）────────────


def _calc_volume_distribution_depth_v77(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """量能分布深度分析（V76 条件240）。

    分析成交量在价格区间的分布深度，识别筹码集中区：
    - 底部放量堆积 → 筹码收集，看涨信号强化
    - 顶部放量堆积 → 筹码派发，看跌信号强化
    - 量价背离 → 信号需谨慎

    返回：energy_zone, volume_rank, support_distance, resistance_distance, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "energy_zone": "unknown",
        "volume_rank": 0.5,
        "support_distance": 0.0,
        "resistance_distance": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 40 or not volumes or len(volumes) < 40:
            result["msg"] = "数据不足（需≥40根）"
            return result

        is_buy = "buy" in mmd.mmd_type.value
        current_price = closes[-1]

        # 计算近期高低点及成交量分布
        lookback = min(60, n)
        recent_closes = closes[-lookback:]
        recent_vols = (
            volumes[-lookback:] if len(volumes) >= lookback else volumes[-len(recent_closes) :]
        )

        high_price = max(recent_closes)
        low_price = min(recent_closes)
        price_range = high_price - low_price
        if price_range <= 0:
            result["msg"] = "价格区间为零"
            return result

        # 计算成交量加权价格分位
        total_vol = sum(recent_vols)
        if total_vol <= 0:
            result["msg"] = "无成交量数据"
            return result

        # 计算各价格区间的成交量占比（简化的能量分布）
        n_bins = 10
        bin_width = price_range / n_bins
        vol_by_bin: list[float] = [0.0] * n_bins

        for i, p in enumerate(recent_closes):
            bin_idx = min(int((p - low_price) / bin_width), n_bins - 1)
            vol_by_bin[bin_idx] += recent_vols[i] if i < len(recent_vols) else 0.0

        # 当前价格所在成交量分位
        current_bin = min(int((current_price - low_price) / bin_width), n_bins - 1)
        current_vol_ratio = vol_by_bin[current_bin] / max(total_vol, 1e-10)
        volume_rank = sum(vol_by_bin[: current_bin + 1]) / max(total_vol, 1e-10)

        # 支撑/阻力距离
        support_dist = (current_price - low_price) / current_price
        resistance_dist = (high_price - current_price) / current_price

        # 判断能量区域
        avg_vol_ratio = sum(vol_by_bin) / n_bins
        if current_vol_ratio > avg_vol_ratio * 1.5 and volume_rank < 0.4:
            energy_zone = "accumulation"
            adjust = 0.03 if is_buy else -0.02
        elif current_vol_ratio > avg_vol_ratio * 1.5 and volume_rank > 0.6:
            energy_zone = "distribution"
            adjust = -0.03 if is_buy else 0.02
        elif volume_rank < 0.3:
            energy_zone = "low_zone"
            adjust = 0.02 if is_buy else -0.01
        elif volume_rank > 0.7:
            energy_zone = "high_zone"
            adjust = -0.02 if is_buy else 0.01
        else:
            energy_zone = "neutral"
            adjust = 0.0

        result["energy_zone"] = energy_zone
        result["volume_rank"] = round(volume_rank, 3)
        result["support_distance"] = round(support_dist, 4)
        result["resistance_distance"] = round(resistance_dist, 4)
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"能量区={energy_zone} 量分位={volume_rank:.0%} "
            f"支撑距={support_dist:.1%} 阻力距={resistance_dist:.1%} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_zhongshu_structure_weight_v77(
    mmd: MMD,
    zss: list[Any],
    closes: list[float],
) -> dict[str, Any]:
    """中枢结构权重评估（V77 条件241）。

    评估当前买卖点最近的中枢对信号的支撑/压制作用：
    - 买入点在下方中枢上方 → 中枢支撑强，信号更可靠
    - 卖出点在上方中枢下方 → 中枢阻力强，信号更可靠
    - 远离中枢 → 信号缺乏结构支撑

    返回：weight_score, nearest_zs_dist, zs_level, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "weight_score": 0.0,
        "nearest_zs_dist": 0.0,
        "zs_level": "none",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not zss or len(closes) < 10:
            result["msg"] = "无中枢数据或数据不足"
            return result

        is_buy = "buy" in mmd.mmd_type.value
        current_price = closes[-1]

        # 找最近的中枢
        nearest_zs = None
        nearest_dist = float("inf")
        nearest_level = 0

        for zs in zss:
            zg = getattr(zs, "zg", 0.0)
            zd = getattr(zs, "zd", 0.0)
            if zg <= 0 or zd <= 0:
                continue
            zs_center = (zg + zd) / 2
            _ = (zg - zd) / 2
            dist = abs(current_price - zs_center) / max(zs_center, 1e-10)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_zs = zs
                nearest_level = getattr(zs, "level", 0)

        if nearest_zs is None:
            result["msg"] = "未找到有效中枢"
            result["confidence_adjust"] = -0.02
            return result

        result["nearest_zs_dist"] = round(nearest_dist, 4)
        result["zs_level"] = f"L{nearest_level}" if nearest_level > 0 else "1F"

        # 评估结构权重
        if is_buy:
            # 买入：价格在中枢上方且距离适中
            if current_price > getattr(nearest_zs, "zg", 0) and nearest_dist < 0.15:
                weight_score = 0.9
                adjust = 0.04
            elif current_price > getattr(nearest_zs, "zd", 0) and nearest_dist < 0.25:
                weight_score = 0.7
                adjust = 0.02
            elif nearest_dist < 0.10:
                weight_score = 0.5
                adjust = 0.0
            else:
                weight_score = 0.3
                adjust = -0.02
        else:
            # 卖出：价格在中枢下方且距离适中
            if current_price < getattr(nearest_zs, "zd", 0) and nearest_dist < 0.15:
                weight_score = 0.9
                adjust = 0.04
            elif current_price < getattr(nearest_zs, "zg", 0) and nearest_dist < 0.25:
                weight_score = 0.7
                adjust = 0.02
            elif nearest_dist < 0.10:
                weight_score = 0.5
                adjust = 0.0
            else:
                weight_score = 0.3
                adjust = -0.02

        result["weight_score"] = weight_score
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"权重={weight_score:.0%} 最近中枢{result['zs_level']} "
            f"距离={nearest_dist:.1%} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_signal_freshness_validation_v77(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """信号新鲜度验证（V77 条件242）。

    根据信号产生后的K线数量和价格漂移评估信号新鲜度：
    - 新鲜信号（≤5根K线）→ 完整置信度
    - 半新鲜（6-15根）→ 线性衰减
    - 陈旧信号（>15根）→ 显著衰减或失效

    返回：freshness_score, bars_since_signal, age_label, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "freshness_score": 1.0,
        "bars_since_signal": 0,
        "age_label": "fresh",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 10:
            result["msg"] = "数据不足（需≥10根）"
            return result

        # 计算信号后经过的K线数
        if mmd.bi and hasattr(mmd.bi, "end") and hasattr(mmd.bi.end, "k_index"):
            bi_end_idx = mmd.bi.end.k_index
            bars_since = n - 1 - bi_end_idx
        else:
            # 无笔信息，使用最后5根K线作为近似
            bars_since = min(5, n - 1)

        result["bars_since_signal"] = bars_since

        # 新鲜度评分
        if bars_since <= 3:
            freshness = 1.0
            age_label = "very_fresh"
            adjust = 0.03
        elif bars_since <= 7:
            freshness = max(0.6, 1.0 - (bars_since - 3) * 0.05)
            age_label = "fresh"
            adjust = 0.01
        elif bars_since <= 15:
            freshness = max(0.3, 0.6 - (bars_since - 7) * 0.03)
            age_label = "aging"
            adjust = -0.02
        else:
            freshness = max(0.0, 0.3 - (bars_since - 15) * 0.01)
            age_label = "stale"
            adjust = -0.05

        result["freshness_score"] = round(freshness, 3)
        result["age_label"] = age_label
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"新鲜度={freshness:.0%} 信号后{bars_since}根K线 年龄={age_label} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_price_momentum_acceleration_v77(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """价格动能加速度（V77 条件243）。

    分析信号附近的 price acceleration/deceleration：
    - 加速度为正且持续 → 动能增强，信号更可信
    - 加速度为负 → 动能减弱，信号需谨慎
    - 加速度接近零 → 动能衰竭，观望

    返回：acceleration, momentum_direction, acceleration_strength, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "acceleration": 0.0,
        "momentum_direction": "unknown",
        "acceleration_strength": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 20:
            result["msg"] = "数据不足（需≥20根）"
            return result

        is_buy = "buy" in mmd.mmd_type.value

        # 计算价格加速度（二阶差分）
        # 短期速度
        short_vel = closes[-1] - closes[-3] if n >= 3 else 0.0
        # 中期速度
        mid_vel = closes[-5] - closes[-10] if n >= 10 else short_vel
        # 加速度 = 短期速度变化
        accel = short_vel - mid_vel
        current_price = closes[-1]

        # 归一化加速度
        norm_accel = accel / max(abs(current_price), 1e-10)

        # 判断方向
        if norm_accel > 0.005:
            direction = "accelerating_up"
        elif norm_accel > 0.001:
            direction = "growing_up"
        elif norm_accel > -0.001:
            direction = "flat"
        elif norm_accel > -0.005:
            direction = "decelerating"
        else:
            direction = "sharp_reversal"

        # 判断强度
        abs_accel = abs(norm_accel)
        if abs_accel > 0.01:
            strength = "strong"
        elif abs_accel > 0.005:
            strength = "moderate"
        else:
            strength = "weak"

        # 置信度调整
        if is_buy:
            if direction == "accelerating_up":
                adjust = 0.04
            elif direction == "growing_up":
                adjust = 0.02
            elif direction == "flat":
                adjust = 0.0
            else:
                adjust = -0.03
        else:
            if direction == "sharp_reversal":
                adjust = 0.04
            elif direction == "decelerating":
                adjust = 0.02
            elif direction == "flat":
                adjust = 0.0
            else:
                adjust = -0.03

        result["acceleration"] = round(norm_accel, 5)
        result["momentum_direction"] = direction
        result["acceleration_strength"] = strength
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"加速度={norm_accel:.4f} 方向={direction} 强度={strength} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


# ── V78: 条件 244-247（买卖点周期位置+多信号一致性+波动率压缩突破+资金流向背离）────────────


def _calc_mmd_cycle_position_v78(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """买卖点周期位置评分（V78 条件244）。

    评估当前买卖点在完整波段中的相对位置：
    - 买入点在波段低位（近N日最低附近）→ 更高置信度
    - 卖出点在波段高位（近N日最高附近）→ 更高置信度
    - 中部位置 → 中性

    返回：position_score, cycle_position, distance_to_low, distance_to_high, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "position_score": 0.5,
        "cycle_position": "mid",
        "distance_to_low": 0.5,
        "distance_to_high": 0.5,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 30:
            result["msg"] = "数据不足"
            return result

        lookback = min(60, len(closes))
        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]
        current_price = closes[-1]

        period_high = max(recent_highs)
        period_low = min(recent_lows)
        price_range = period_high - period_low if period_high != period_low else 1.0

        # 当前位置（0=底部，1=顶部）
        position = (current_price - period_low) / price_range
        distance_to_low = position
        distance_to_high = 1.0 - position

        # 根据信号方向评分
        is_buy = "buy" in mmd.mmd_type.value
        if is_buy:
            if position < 0.2:
                position_score = 0.9
                cycle_pos = "bottom"
                adjust = 0.04
            elif position < 0.4:
                position_score = 0.7
                cycle_pos = "lower"
                adjust = 0.02
            elif position < 0.6:
                position_score = 0.5
                cycle_pos = "mid"
                adjust = 0.0
            elif position < 0.8:
                position_score = 0.3
                cycle_pos = "upper"
                adjust = -0.02
            else:
                position_score = 0.1
                cycle_pos = "top"
                adjust = -0.04
        else:  # sell
            if position > 0.8:
                position_score = 0.9
                cycle_pos = "top"
                adjust = 0.04
            elif position > 0.6:
                position_score = 0.7
                cycle_pos = "upper"
                adjust = 0.02
            elif position > 0.4:
                position_score = 0.5
                cycle_pos = "mid"
                adjust = 0.0
            elif position > 0.2:
                position_score = 0.3
                cycle_pos = "lower"
                adjust = -0.02
            else:
                position_score = 0.1
                cycle_pos = "bottom"
                adjust = -0.04

        result["position_score"] = position_score
        result["cycle_position"] = cycle_pos
        result["distance_to_low"] = round(distance_to_low, 3)
        result["distance_to_high"] = round(distance_to_high, 3)
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"周期位置={cycle_pos} 位置分={position_score:.0%} "
            f"距低={distance_to_low:.0%} 距高={distance_to_high:.0%} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_multi_signal_consensus_v78(
    mmds: list[MMD],
    current_mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """多信号时间窗口一致性（V78 条件245）。

    评估当前买卖点与其附近其他买卖点的方向一致性：
    - 附近信号方向一致 → 高共识度，增强置信度
    - 附近信号方向分歧 → 低共识度，降低置信度

    返回：consensus_score, nearby_buy_count, nearby_sell_count,
    consensus_level, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "consensus_score": 0.5,
        "nearby_buy_count": 0,
        "nearby_sell_count": 0,
        "consensus_level": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not mmds or len(mmds) < 2:
            result["msg"] = "信号不足"
            return result
        if len(closes) < 20:
            result["msg"] = "K线数据不足"
            return result

        # 找当前信号的索引
        try:
            curr_idx = mmds.index(current_mmd)
        except ValueError:
            result["msg"] = "信号未找到"
            return result

        # 在时间窗口内（最近20根K线）统计附近信号
        current_bar = current_mmd.bi.index if current_mmd.bi else len(closes)
        window = 20
        nearby_buys = 0
        nearby_sells = 0

        for i, other_mmd in enumerate(mmds):
            if i == curr_idx:
                continue
            other_bar = other_mmd.bi.index if other_mmd.bi else len(closes)
            if abs(other_bar - current_bar) <= window:
                if "buy" in other_mmd.mmd_type.value:
                    nearby_buys += 1
                elif "sell" in other_mmd.mmd_type.value:
                    nearby_sells += 1

        total_nearby = nearby_buys + nearby_sells
        result["nearby_buy_count"] = nearby_buys
        result["nearby_sell_count"] = nearby_sells

        is_buy = "buy" in current_mmd.mmd_type.value

        if total_nearby == 0:
            consensus_score = 0.5
            consensus_level = "isolated"
            adjust = 0.0
        elif is_buy:
            if nearby_buys >= 2 and nearby_sells == 0:
                consensus_score = 0.9
                consensus_level = "strong_consensus"
                adjust = 0.03
            elif nearby_buys >= 1 and nearby_sells <= 1:
                consensus_score = 0.7
                consensus_level = "moderate_consensus"
                adjust = 0.01
            elif nearby_sells > nearby_buys:
                consensus_score = 0.3
                consensus_level = "contradicted"
                adjust = -0.03
            else:
                consensus_score = 0.5
                consensus_level = "mixed"
                adjust = 0.0
        else:  # sell
            if nearby_sells >= 2 and nearby_buys == 0:
                consensus_score = 0.9
                consensus_level = "strong_consensus"
                adjust = 0.03
            elif nearby_sells >= 1 and nearby_buys <= 1:
                consensus_score = 0.7
                consensus_level = "moderate_consensus"
                adjust = 0.01
            elif nearby_buys > nearby_sells:
                consensus_score = 0.3
                consensus_level = "contradicted"
                adjust = -0.03
            else:
                consensus_score = 0.5
                consensus_level = "mixed"
                adjust = 0.0

        result["consensus_score"] = consensus_score
        result["consensus_level"] = consensus_level
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"共识度={consensus_level} 评分={consensus_score:.0%} "
            f"近买={nearby_buys} 近卖={nearby_sells} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_volatility_compression_breakout_v78(
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """波动率压缩突破预测（V78 条件246）。

    基于布林带宽度和ATR识别波动率压缩状态，预测突破方向：
    - 波动率压缩（低带宽）→ 即将突破，方向由价格位置判断
    - 波动率扩张 → 趋势延续或反转

    返回：compression_score, boll_width_percentile, breakout_direction, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "compression_score": 0.5,
        "boll_width_percentile": 0.5,
        "breakout_direction": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 50:
            result["msg"] = "数据不足"
            return result

        # 计算布林带宽度历史序列
        window = 50
        widths = []
        for i in range(window, len(closes)):
            period_closes = closes[i - window : i]
            ma = sum(period_closes) / window
            std = (sum((x - ma) ** 2 for x in period_closes) / window) ** 0.5
            width = 4 * std  # 2*2*std = 4*std (上下轨距离)
            widths.append(width)

        if not widths:
            result["msg"] = "宽度计算失败"
            return result

        current_width = widths[-1]
        sorted_widths = sorted(widths)
        percentile = sum(1 for w in sorted_widths if w <= current_width) / len(sorted_widths)

        # 判断压缩状态（下四分位为压缩）
        is_compressed = percentile < 0.25
        is_expanding = percentile > 0.75

        # 判断突破方向（价格在布林带中的位置）
        recent_closes = closes[-window:]
        ma = sum(recent_closes) / window
        std = (sum((x - ma) ** 2 for x in recent_closes) / window) ** 0.5
        upper = ma + 2 * std
        lower = ma - 2 * std
        current_price = closes[-1]
        percent_b = (current_price - lower) / (upper - lower) if upper != lower else 0.5

        if is_compressed:
            if percent_b > 0.8:
                direction = "up"
                adjust = 0.03
            elif percent_b < 0.2:
                direction = "down"
                adjust = 0.03
            else:
                direction = "neutral"
                adjust = 0.0
            compression_score = 0.8
        elif is_expanding:
            if percent_b > 0.9:
                direction = "up_continuing"
                adjust = 0.02
            elif percent_b < 0.1:
                direction = "down_continuing"
                adjust = 0.02
            else:
                direction = "neutral"
                adjust = 0.0
            compression_score = 0.3
        else:
            direction = "normal"
            adjust = 0.0
            compression_score = 0.5

        result["compression_score"] = compression_score
        result["boll_width_percentile"] = round(percentile, 3)
        result["breakout_direction"] = direction
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"压缩分={compression_score:.0%} 带宽百分位={percentile:.0%} "
            f"突破方向={direction} percent_b={percent_b:.2f} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_fund_flow_divergence_v78(
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """资金流向与价格背离检测（V78 条件247）。

    通过成交量加权价格变化检测资金流向与价格的背离：
    - 价格上涨但成交量萎缩 → 资金流出，看跌背离
    - 价格下跌但成交量放大 → 资金流入，看涨背离
    - 量价齐升/齐跌 → 方向确认

    返回：divergence_type, money_flow_score, volume_price_correlation, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "divergence_type": "none",
        "money_flow_score": 0.5,
        "volume_price_correlation": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 30 or len(volumes) < 30:
            result["msg"] = "数据不足"
            return result

        lookback = min(20, len(closes))
        recent_closes = closes[-lookback:]
        recent_vols = volumes[-lookback:]

        # 计算价格变化和成交量变化
        price_changes = [
            recent_closes[i] - recent_closes[i - 1] for i in range(1, len(recent_closes))
        ]
        vol_changes = [recent_vols[i] - recent_vols[i - 1] for i in range(1, len(recent_vols))]

        if not price_changes or not vol_changes:
            result["msg"] = "变化计算失败"
            return result

        # 计算量价相关性
        n = len(price_changes)
        mean_pc = sum(price_changes) / n
        mean_vc = sum(vol_changes) / n
        cov = sum((price_changes[i] - mean_pc) * (vol_changes[i] - mean_vc) for i in range(n)) / n
        std_pc = (sum((x - mean_pc) ** 2 for x in price_changes) / n) ** 0.5
        std_vc = (sum((x - mean_vc) ** 2 for x in vol_changes) / n) ** 0.5

        if std_pc > 0 and std_vc > 0:
            correlation = cov / (std_pc * std_vc)
        else:
            correlation = 0.0

        # 判断整体趋势方向
        total_price_change = recent_closes[-1] - recent_closes[0]
        total_vol_change = recent_vols[-1] - recent_vols[0]
        price_trending_up = total_price_change > 0
        vol_trending_up = total_vol_change > 0

        # 检测背离
        if price_trending_up and not vol_trending_up and correlation < -0.3:
            divergence_type = "bearish_divergence"  # 价格上涨但量能萎缩
            money_flow_score = 0.3
            adjust = -0.03
        elif not price_trending_up and vol_trending_up and correlation < -0.3:
            divergence_type = "bullish_divergence"  # 价格下跌但量能放大
            money_flow_score = 0.7
            adjust = 0.03
        elif price_trending_up and vol_trending_up and correlation > 0.3:
            divergence_type = "confirmed_up"  # 量价齐升
            money_flow_score = 0.8
            adjust = 0.02
        elif not price_trending_up and not vol_trending_up and correlation > 0.3:
            divergence_type = "confirmed_down"  # 量价齐跌
            money_flow_score = 0.2
            adjust = -0.02
        else:
            divergence_type = "neutral"
            money_flow_score = 0.5
            adjust = 0.0

        result["divergence_type"] = divergence_type
        result["money_flow_score"] = money_flow_score
        result["volume_price_correlation"] = round(correlation, 3)
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"背离类型={divergence_type} 资金分={money_flow_score:.0%} "
            f"量价相关={correlation:.2f} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


# ── V79: 条件 248-251（分型稳定性+距离安全+多级别一致性+动能持续性）────────────


def _calc_fractal_stability_validation_v79(
    mmd: MMD,
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """分型稳定性验证（V79 条件248）。

    检验顶底分型是否被后续K线破坏，确认信号的可靠性：
    - 买入信号：检查最近顶分型是否被后续高点突破（破坏）
    - 卖出信号：检查最近底分型是否被后续低点跌破（破坏）
    - 分型稳定 → 加分，分型被破坏 → 减分

    返回：stability_score, fractal_status, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "stability_score": 0.5,
        "fractal_status": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(highs) < 10 or len(lows) < 10:
            result["msg"] = "数据不足"
            return result

        lookback = min(20, len(highs))
        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]
        current_high = recent_highs[-1]
        current_low = recent_lows[-1]

        is_buy = "buy" in mmd.mmd_type.value

        if is_buy:
            # 买入信号：检查顶分型是否被后续高点突破（破坏）
            # 如果当前价格附近有更高的新高点，说明顶分型不稳定
            max_recent_high = max(recent_highs[:-1]) if len(recent_highs) > 1 else current_high
            price_new_high = current_high > max_recent_high * 1.02  # 新高超过2%

            if not price_new_high:
                stability = 0.9
                status = "stable"
                adjust = 0.03
            elif current_high > max_recent_high * 1.05:
                stability = 0.3
                status = "broken"
                adjust = -0.04
            else:
                stability = 0.6
                status = "weak"
                adjust = -0.01
        else:
            # 卖出信号：检查底分型是否被后续低点跌破（破坏）
            min_recent_low = min(recent_lows[:-1]) if len(recent_lows) > 1 else current_low
            price_new_low = current_low < min_recent_low * 0.98  # 新低超过2%

            if not price_new_low:
                stability = 0.9
                status = "stable"
                adjust = 0.03
            elif current_low < min_recent_low * 0.95:
                stability = 0.3
                status = "broken"
                adjust = -0.04
            else:
                stability = 0.6
                status = "weak"
                adjust = -0.01

        result["stability_score"] = stability
        result["fractal_status"] = status
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = f"分型状态={status} 稳定分={stability:.0%} 调整{adjust:+.0%}"
        return result
    except Exception:
        return result


def _calc_mmd_distance_safety_v79(
    mmds: list[MMD],
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """买卖点距离安全阈值（V79 条件249）。

    评估当前买卖点与最近同向买卖点的距离，避免追高/杀跌：
    - 距离过近（<5根K线）→ 高风险，减分
    - 距离适中（5-20根K线）→ 正常
    - 距离充足（>20根K线）→ 安全，加分

    返回：distance_score, bars_to_nearest, safety_level, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "distance_score": 0.5,
        "bars_to_nearest": 0,
        "safety_level": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmds is None or len(mmds) < 2 or not closes:
            result["msg"] = "数据不足"
            return result

        # 找最近同向买卖点的距离（以K线根数计）
        is_buy = "buy" in mmd.mmd_type.value
        same_type_prefix = "BUY" if is_buy else "SELL"

        nearest_dist = None
        for prev_mmd in reversed(mmds[:-1]):
            prev_is_same = prev_mmd.mmd_type.value.startswith(same_type_prefix)
            if prev_is_same and prev_mmd.bi is not None and mmd.bi is not None:
                # 用bi.index估算距离
                dist = abs(mmd.bi.index - prev_mmd.bi.index)
                if nearest_dist is None or dist < nearest_dist:
                    nearest_dist = dist

        if nearest_dist is None:
            nearest_dist = 99  # 没有最近的同向信号，视为安全
            safety = "isolated"
            score = 0.7
            adjust = 0.02
        elif nearest_dist < 5:
            safety = "too_close"
            score = 0.2
            adjust = -0.04
        elif nearest_dist < 10:
            safety = "close"
            score = 0.4
            adjust = -0.02
        elif nearest_dist < 20:
            safety = "moderate"
            score = 0.6
            adjust = 0.0
        else:
            safety = "safe"
            score = 0.85
            adjust = 0.03

        result["distance_score"] = score
        result["bars_to_nearest"] = nearest_dist
        result["safety_level"] = safety
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"最近同向={nearest_dist}根K线 安全={safety} 距离分={score:.0%} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_multi_level_structure_consistency_v79(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """多级别结构一致性评分（V79 条件250）。

    评估当前买卖点在短周期和长周期趋势中的一致性强弱：
    - 短期（5日）趋势与信号方向一致 → +2%
    - 中期（20日）趋势与信号方向一致 → +2%
    - 长期（60日）趋势与信号方向一致 → +2%
    - 全一致 → +6%，部分一致 → 加分，矛盾 → 减分

    返回：consistency_score, short_align, mid_align, long_align, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "consistency_score": 0.5,
        "short_align": False,
        "mid_align": False,
        "long_align": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 10:
            result["msg"] = "数据不足"
            return result

        is_buy = "buy" in mmd.mmd_type.value

        # 短周期（5日）趋势
        short_ma5 = sum(closes[-5:]) / 5
        short_trend_up = closes[-1] > short_ma5

        # 中期（20日）趋势
        mid_ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else short_ma5
        mid_trend_up = closes[-1] > mid_ma20

        # 长期（60日）趋势
        long_ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else mid_ma20
        long_trend_up = closes[-1] > long_ma60

        short_align = (is_buy and short_trend_up) or (not is_buy and not short_trend_up)
        mid_align = (is_buy and mid_trend_up) or (not is_buy and not mid_trend_up)
        long_align = (is_buy and long_trend_up) or (not is_buy and not long_trend_up)

        align_count = sum([short_align, mid_align, long_align])

        if align_count == 3:
            consistency = 0.95
            adjust = 0.06
            level = "full_consensus"
        elif align_count == 2:
            consistency = 0.7
            adjust = 0.03
            level = "partial_consensus"
        elif align_count == 1:
            consistency = 0.4
            adjust = -0.02
            level = "conflicted"
        else:
            consistency = 0.2
            adjust = -0.04
            level = "fully_conflicted"

        result["consistency_score"] = consistency
        result["short_align"] = short_align
        result["mid_align"] = mid_align
        result["long_align"] = long_align
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"多级别一致={level} 短={'✓' if short_align else '✗'} "
            f"中={'✓' if mid_align else '✗'} 长={'✓' if long_align else '✗'} "
            f"一致分={consistency:.0%} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_price_momentum_continuity_v79(
    mmd: MMD,
    closes: list[float],
    volumes: list[float] | None,
) -> dict[str, Any]:
    """价格动能持续性评分（V79 条件251）。

    评估当前买卖点对应的价格动能是否在持续：
    - 计算近N日价格加速度（二阶导）
    - 结合成交量变化判断动能衰减/增强
    - 动能持续 → 加分，动能衰竭 → 减分

    返回：momentum_score, acceleration, vol_trend, momentum_level, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "momentum_score": 0.5,
        "acceleration": 0.0,
        "vol_trend": "neutral",
        "momentum_level": "neutral",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 15:
            result["msg"] = "数据不足"
            return result

        lookback = min(20, len(closes))
        recent = closes[-lookback:]
        is_buy = "buy" in mmd.mmd_type.value

        # 计算价格加速度（二阶差分）
        if len(recent) >= 3:
            first_deriv = [recent[i] - recent[i - 1] for i in range(1, len(recent))]
            second_deriv = [first_deriv[i] - first_deriv[i - 1] for i in range(1, len(first_deriv))]
            avg_acceleration = sum(second_deriv) / len(second_deriv) if second_deriv else 0.0
        else:
            avg_acceleration = 0.0

        # 价格动量（一阶导的平均）
        price_momentum = sum(first_deriv[-5:]) / min(5, len(first_deriv)) if first_deriv else 0.0

        # 成交量趋势
        if volumes and len(volumes) >= lookback:
            vol_recent = volumes[-5:]
            vol_prev = volumes[-10:-5] if len(volumes) >= 10 else vol_recent
            avg_vol_recent = sum(vol_recent) / len(vol_recent)
            avg_vol_prev = sum(vol_prev) / len(vol_prev) if vol_prev else avg_vol_recent
            vol_trend = (
                "up"
                if avg_vol_recent > avg_vol_prev * 1.1
                else ("down" if avg_vol_recent < avg_vol_prev * 0.9 else "neutral")
            )
        else:
            vol_trend = "neutral"

        # 综合评估动能持续性
        if is_buy:
            momentum_positive = price_momentum > 0
            accel_positive = avg_acceleration > 0
            vol_support = vol_trend in ["up", "neutral"]
        else:
            momentum_positive = price_momentum < 0
            accel_positive = avg_acceleration < 0
            vol_support = vol_trend in ["down", "neutral"]

        positive_factors = sum([momentum_positive, accel_positive, vol_support])

        if positive_factors == 3:
            momentum_level = "strong"
            momentum_score = 0.9
            adjust = 0.04
        elif positive_factors == 2:
            momentum_level = "moderate"
            momentum_score = 0.65
            adjust = 0.02
        elif positive_factors == 1:
            momentum_level = "weak"
            momentum_score = 0.4
            adjust = -0.02
        else:
            momentum_level = "declining"
            momentum_score = 0.2
            adjust = -0.04

        result["momentum_score"] = momentum_score
        result["acceleration"] = round(avg_acceleration, 4)
        result["vol_trend"] = vol_trend
        result["momentum_level"] = momentum_level
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"动能级={momentum_level} 加速={avg_acceleration:.4f} "
            f"量能={'↑' if vol_trend == 'up' else '↓' if vol_trend == 'down' else '→'} "
            f"动量分={momentum_score:.0%} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


# ── V80: 条件 252-255（中枢距离+量能配合+均线排列+盈亏比）────────────────────


def _calc_mmd_zhongshu_distance_v80(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """买卖点与中枢距离验证（V80 条件252）。

    评估当前买卖点与最近完成中枢的距离关系：
    - 买入信号：在中枢上方0-3%区间 → 中枢支撑有效，加分；过远（>10%）→ 缺乏结构支撑，减分
    - 卖出信号：在中枢下方0-3%区间 → 中枢压制有效，加分；过远（>10%）→ 缺乏结构压制，减分

    返回：distance_score, nearest_zs_dist_pct, zs_position, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "distance_score": 0.5,
        "nearest_zs_dist_pct": 0.0,
        "zs_position": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 20 or mmd.zs is None:
            result["msg"] = "数据不足或无中枢"
            return result

        current_price = closes[-1]
        zs = mmd.zs
        zg = getattr(zs, "zg", 0.0)
        zd = getattr(zs, "zd", 0.0)
        if zg <= 0 or zd <= 0:
            result["msg"] = "中枢数据无效"
            return result

        zs_center = (zg + zd) / 2
        dist_pct = (current_price - zs_center) / max(zs_center, 1e-10) * 100
        result["nearest_zs_dist_pct"] = round(dist_pct, 2)

        is_buy = "buy" in mmd.mmd_type.value

        if is_buy:
            if 0 < dist_pct <= 5:
                distance_score, zs_pos, adjust = 0.9, "just_above", 0.04
            elif 5 < dist_pct <= 10:
                distance_score, zs_pos, adjust = 0.6, "above", 0.01
            elif dist_pct > 10:
                distance_score, zs_pos, adjust = 0.3, "far_above", -0.03
            elif -3 < dist_pct <= 0:
                distance_score, zs_pos, adjust = 0.7, "inside", 0.02
            else:
                distance_score, zs_pos, adjust = 0.2, "below", -0.04
        else:
            if -5 <= dist_pct < 0:
                distance_score, zs_pos, adjust = 0.9, "just_below", 0.04
            elif -10 <= dist_pct < -5:
                distance_score, zs_pos, adjust = 0.6, "below", 0.01
            elif dist_pct < -10:
                distance_score, zs_pos, adjust = 0.3, "far_below", -0.03
            elif 0 <= dist_pct < 3:
                distance_score, zs_pos, adjust = 0.7, "inside", 0.02
            else:
                distance_score, zs_pos, adjust = 0.2, "above", -0.04

        result["distance_score"] = distance_score
        result["zs_position"] = zs_pos
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"中枢距离={dist_pct:+.1f}% 位置={zs_pos} 距离分={distance_score:.0%} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_volume_confirmation_v80(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """量能配合度评分（V80 条件253）。

    评估近期成交量与价格趋势的配合程度：
    - 上涨+放量 → 量价齐升，配合良好，加分
    - 下跌+缩量 → 抛压减轻，配合良好，加分
    - 上涨+缩量 → 量价背离，配合不良，减分
    - 下跌+放量 → 恐慌抛售，配合不良，减分

    返回：confirmation_score, vol_ratio, volume_trend, price_trend, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "confirmation_score": 0.5,
        "vol_ratio": 1.0,
        "volume_trend": "neutral",
        "price_trend": "neutral",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 10 or not volumes or len(volumes) < 10:
            result["msg"] = "数据不足"
            return result

        lookback = min(20, len(closes))
        recent_closes = closes[-lookback:]
        recent_vols = volumes[-lookback:]

        if len(recent_closes) >= 10:
            price_recent = sum(recent_closes[-5:]) / 5
            price_prev = sum(recent_closes[-10:-5]) / 5
        else:
            price_recent = sum(recent_closes) / len(recent_closes)
            price_prev = price_recent
        price_trend = (
            "up"
            if price_recent > price_prev * 1.01
            else ("down" if price_recent < price_prev * 0.99 else "flat")
        )

        if len(recent_vols) >= 10:
            vol_recent = sum(recent_vols[-5:]) / 5
            vol_prev = sum(recent_vols[-10:-5]) / 5
        else:
            vol_recent = sum(recent_vols) / len(recent_vols)
            vol_prev = vol_recent
        vol_ratio = vol_recent / max(vol_prev, 1e-10)
        vol_trend = "up" if vol_ratio > 1.1 else ("down" if vol_ratio < 0.9 else "flat")

        result["vol_ratio"] = round(vol_ratio, 2)
        result["volume_trend"] = vol_trend
        result["price_trend"] = price_trend

        is_buy = "buy" in mmd.mmd_type.value

        if price_trend == "up" and vol_trend in ["up", "flat"]:
            confirmation = 0.85 if vol_trend == "up" else 0.65
            adjust = 0.03 if vol_trend == "up" else 0.01
        elif price_trend == "down" and vol_trend in ["down", "flat"]:
            confirmation = 0.85 if vol_trend == "down" else 0.65
            adjust = 0.03 if vol_trend == "down" else 0.01
        elif price_trend == "up" and vol_trend == "down":
            confirmation, adjust = 0.3, -0.03
        elif price_trend == "down" and vol_trend == "up":
            confirmation, adjust = 0.25, -0.03
        else:
            confirmation, adjust = 0.5, 0.0

        if is_buy and price_trend == "up" and confirmation >= 0.65:
            adjust += 0.01
        elif not is_buy and price_trend == "down" and confirmation >= 0.65:
            adjust += 0.01

        result["confirmation_score"] = confirmation
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"量比={vol_ratio:.2f} "
            f"价{'↑' if price_trend == 'up' else '↓' if price_trend == 'down' else '→'} "
            f"量{'↑' if vol_trend == 'up' else '↓' if vol_trend == 'down' else '→'} "
            f"配合分={confirmation:.0%} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_ma_alignment_strength_v80(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """均线排列强度确认（V80 条件254）。

    评估MA5/MA10/MA20/MA60的多空排列状态及价格相对位置：
    - 多头排列且价格在上方 → 强趋势，加分
    - 空头排列且价格在下方 → 强趋势，加分
    - 排列混乱 → 震荡市，中性

    返回：alignment_score, ma_alignment, price_position, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "alignment_score": 0.5,
        "ma_alignment": "unknown",
        "price_position": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 60:
            result["msg"] = "数据不足（需≥60根）"
            return result

        ma5 = MA(closes, 5)[-1]
        ma10 = MA(closes, 10)[-1]
        ma20 = MA(closes, 20)[-1]
        ma60 = MA(closes, 60)[-1]
        current = closes[-1]

        eps = 1e-10
        if ma5 > ma10 + eps and ma10 > ma20 + eps and ma20 > ma60 + eps:
            alignment = "bullish"
        elif ma5 < ma10 - eps and ma10 < ma20 - eps and ma20 < ma60 - eps:
            alignment = "bearish"
        else:
            alignment = "mixed"
        result["ma_alignment"] = alignment

        if current > ma5 > ma10 > ma20:
            price_pos = "above_all"
        elif current < ma5 < ma10 < ma20:
            price_pos = "below_all"
        elif current > ma20:
            price_pos = "above_mid"
        elif current < ma20:
            price_pos = "below_mid"
        else:
            price_pos = "near_ma20"
        result["price_position"] = price_pos

        is_buy = "buy" in mmd.mmd_type.value

        if alignment == "bullish" and price_pos in ["above_all", "above_mid"]:
            alignment_score, adjust = 0.9, 0.05
        elif alignment == "bearish" and price_pos in ["below_all", "below_mid"]:
            alignment_score, adjust = 0.9, 0.05
        elif alignment == "bullish":
            alignment_score, adjust = 0.6, 0.02
        elif alignment == "bearish":
            alignment_score, adjust = 0.6, 0.02
        elif alignment == "mixed":
            alignment_score, adjust = 0.3, -0.02
        else:
            alignment_score, adjust = 0.5, 0.0

        if is_buy and alignment == "bullish" and price_pos in ["above_all", "above_mid"]:
            adjust += 0.01
        elif not is_buy and alignment == "bearish" and price_pos in ["below_all", "below_mid"]:
            adjust += 0.01

        result["alignment_score"] = alignment_score
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"排列={alignment} 价格={price_pos} 排列分={alignment_score:.0%} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_dynamic_risk_reward_v80(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """盈亏比动态评估（V80 条件255）。

    基于近期波动区间动态评估止损止盈距离和盈亏比：
    - 使用近期高低点计算动态止损位
    - 评估风险（止损距离）与潜在收益（目标距离）的比值
    - 盈亏比≥2:1 → 加分；1:1~2:1 → 中性；<1:1 → 减分

    返回：rr_ratio, stop_loss_pct, take_profit_pct, risk_level, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "rr_ratio": 1.0,
        "stop_loss_pct": 0.0,
        "take_profit_pct": 0.0,
        "risk_level": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 20 or not highs or not lows:
            result["msg"] = "数据不足"
            return result

        lookback = min(20, len(closes))
        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]
        current_price = closes[-1]

        period_high = max(recent_highs)
        period_low = min(recent_lows)
        period_range = period_high - period_low
        if period_range <= 0:
            period_range = current_price * 0.02

        is_buy = "buy" in mmd.mmd_type.value

        if is_buy:
            stop_loss = period_low * 0.99
            take_profit = period_high * 1.03
            risk = (current_price - stop_loss) / current_price * 100
            reward = (take_profit - current_price) / current_price * 100
        else:
            stop_loss = period_high * 1.01
            take_profit = period_low * 0.97
            risk = (stop_loss - current_price) / current_price * 100
            reward = (current_price - take_profit) / current_price * 100

        risk = max(risk, 0.5)
        rr_ratio = reward / risk if risk > 0 else 1.0

        result["rr_ratio"] = round(rr_ratio, 2)
        result["stop_loss_pct"] = round(risk, 2)
        result["take_profit_pct"] = round(reward, 2)

        if rr_ratio >= 3.0:
            risk_level, adjust = "excellent", 0.04
        elif rr_ratio >= 2.0:
            risk_level, adjust = "good", 0.02
        elif rr_ratio >= 1.5:
            risk_level, adjust = "moderate", 0.0
        elif rr_ratio >= 1.0:
            risk_level, adjust = "poor", -0.02
        else:
            risk_level, adjust = "dangerous", -0.04

        result["risk_level"] = risk_level
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"盈亏比={rr_ratio:.1f}:1 风险{risk:.1f}% 收益{reward:.1f}% "
            f"风险级={risk_level} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


# ── V81 条件 256-259 实现 ──────────────────────────────────────────────


def _calc_volatility_regime_transition_v81(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """波动率状态转换检测（V81 条件256）。

    基于近期 ATR/价格比率划分波动率环境：
    - compressed: 低波动（<1.2%）→ 蓄势，突破信号加分
    - normal: 正常波动（1.2%-3%）
    - elevated: 波动偏高（3%-5%）
    - expanding: 波动放大（>5%）→ 风险加大，信号减分

    买入/卖出在 compressed 与 expanding 两个极端环境下的调整方向不同。
    """
    result: dict[str, Any] = {
        "regime": "unknown",
        "volatility_pct": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 30 or len(highs) < 30 or len(lows) < 30:
            result["msg"] = "数据不足"
            return result

        vol = _calc_atr_volatility(closes[-60:])
        vol_pct = vol * 100.0
        result["volatility_pct"] = round(vol_pct, 2)

        is_buy = "buy" in mmd.mmd_type.value

        if vol_pct < 1.2:
            regime = "compressed"
            adjust = 0.03 if is_buy else 0.02  # 压缩蓄势，买点加分更多
        elif vol_pct < 3.0:
            regime = "normal"
            adjust = 0.0
        elif vol_pct < 5.0:
            regime = "elevated"
            adjust = -0.01
        else:
            regime = "expanding"
            adjust = -0.03 if is_buy else -0.02  # 高波动风险，卖点略宽容

        result["regime"] = regime
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = f"波动率环境={regime} 波动率{vol_pct:.2f}% 调整{adjust:+.0%}"
        return result
    except Exception:
        return result


def _calc_support_resistance_strength_v81(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """关键支撑阻力强度验证（V81 条件257）。

    在近端价格区间内寻找反复验证的支撑/阻力位（触达次数越多越强），
    买入信号关注下方支撑强度，卖出信号关注上方阻力强度：
    - strong: 近端强支撑/阻力 → 加分
    - weak: 近端弱支撑/阻力 → 减分
    - moderate: 中等
    - distant: 支撑/阻力较远 → 中性
    """
    result: dict[str, Any] = {
        "strength_level": "unknown",
        "nearest_sr_dist_pct": 0.0,
        "sr_count": 0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 20 or not highs or not lows:
            result["msg"] = "数据不足"
            return result

        lookback = min(60, len(closes))
        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]
        current_price = closes[-1]
        is_buy = "buy" in mmd.mmd_type.value

        # 找到近期局部极值点作为候选支撑/阻力
        touch_counts: dict[float, int] = {}
        for i in range(1, len(recent_lows) - 1):
            # 局部低点（支撑候选）
            if recent_lows[i] < recent_lows[i - 1] and recent_lows[i] < recent_lows[i + 1]:
                level = round(recent_lows[i], 2)
                touch_counts[level] = touch_counts.get(level, 0) + 1
            # 局部高点（阻力候选）
            if recent_highs[i] > recent_highs[i - 1] and recent_highs[i] > recent_highs[i + 1]:
                level = round(recent_highs[i], 2)
                touch_counts[level] = touch_counts.get(level, 0) + 1

        if not touch_counts:
            result["strength_level"] = "distant"
            result["confidence_adjust"] = 0.0
            result["msg"] = "近端无显著支撑/阻力位"
            return result

        # 依据买卖方向选择关注的极值区（下方支撑 / 上方阻力）
        if is_buy:
            candidates = [
                (level, cnt) for level, cnt in touch_counts.items() if level <= current_price
            ]
            # 距离最近的支撑
            nearest = min(candidates, key=lambda x: current_price - x[0]) if candidates else None
        else:
            candidates = [
                (level, cnt) for level, cnt in touch_counts.items() if level >= current_price
            ]
            nearest = min(candidates, key=lambda x: x[0] - current_price) if candidates else None

        if nearest is None:
            result["strength_level"] = "distant"
            result["confidence_adjust"] = 0.0
            result["msg"] = "买卖方向对应无近端支撑/阻力位"
            return result

        level, touch = nearest
        dist_pct = abs(current_price - level) / current_price * 100.0 if current_price > 0 else 0.0
        result["nearest_sr_dist_pct"] = round(dist_pct, 2)
        result["sr_count"] = touch

        # 距离太远视为 distant
        if dist_pct > 12:
            result["strength_level"] = "distant"
            result["confidence_adjust"] = 0.0
            result["msg"] = f"最近支撑/阻力距{dist_pct:.1f}% 较远"
            return result

        if touch >= 3 and dist_pct < 5:
            strength, adjust = "strong", 0.03
        elif touch >= 2 and dist_pct < 8:
            strength, adjust = "moderate", 0.01
        elif touch == 1 and dist_pct < 5:
            strength, adjust = "weak", -0.01
        else:
            strength, adjust = "distant", 0.0

        result["strength_level"] = strength
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"支撑/阻力={level:.2f} 触达{touch}次 距离{dist_pct:.1f}% "
            f"强度={strength} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_volume_price_energy_distribution_v81(
    mmd: MMD,
    closes: list[float],
    volumes: list[float] | None,
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """量价能量分布验证（V81 条件258）。

    分析近期量能集中区与价格位置的关系：
    - 买入信号：价格处于低量能区（抛压衰竭）→ 加分
    - 卖出信号：价格处于高量能区（接盘充分）→ 加分
    - 量价背离（价格新高但量萎缩）→ 减分
    """
    result: dict[str, Any] = {
        "energy_zone": "unknown",
        "energy_score": 0.5,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 30 or volumes is None or len(volumes) < 30 or not highs or not lows:
            result["msg"] = "数据不足"
            return result

        lookback = min(60, len(closes))
        recent_closes = closes[-lookback:]
        recent_vols = volumes[-lookback:]

        price_min = min(recent_closes)
        price_max = max(recent_closes)
        price_range = price_max - price_min
        if price_range <= 0:
            result["energy_zone"] = "mid"
            result["msg"] = "价格区间过窄"
            return result

        current_price = recent_closes[-1]
        pos = (current_price - price_min) / price_range  # 0~1 价格位置

        # 量能分区：0=低区, 1=高区（按价格位置切两半统计均量）
        low_zone = [
            v for p, v in zip(recent_closes, recent_vols) if p <= price_min + price_range * 0.4
        ]
        high_zone = [
            v for p, v in zip(recent_closes, recent_vols) if p >= price_min + price_range * 0.6
        ]
        avg_vol = sum(recent_vols) / max(1, len(recent_vols))
        low_avg = sum(low_zone) / max(1, len(low_zone))
        high_avg = sum(high_zone) / max(1, len(high_zone))

        is_buy = "buy" in mmd.mmd_type.value

        if is_buy:
            if pos < 0.35:
                # 低位：若低区量能正常而当前无放量，抛压衰竭
                energy_zone = "low"
                score = 0.8
                adjust = 0.03 if low_avg <= avg_vol else 0.01
            elif pos < 0.65:
                energy_zone = "mid"
                score = 0.6
                adjust = 0.0
            else:
                # 高位买入：量价背离风险（放量追高）
                energy_zone = "high"
                score = 0.35
                adjust = -0.03 if recent_vols[-1] > avg_vol * 1.3 else -0.01
        else:
            if pos > 0.65:
                energy_zone = "high"
                score = 0.8
                adjust = 0.03 if high_avg >= avg_vol else 0.01
            elif pos > 0.35:
                energy_zone = "mid"
                score = 0.6
                adjust = 0.0
            else:
                energy_zone = "low"
                score = 0.35
                adjust = -0.03 if recent_vols[-1] > avg_vol * 1.3 else -0.01

        result["energy_zone"] = energy_zone
        result["energy_score"] = round(score, 2)
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = f"能量区={energy_zone} 分数={score:.2f} 位置={pos:.0%} 调整{adjust:+.0%}"
        return result
    except Exception:
        return result


def _calc_signal_execution_window_v81(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float] | None,
) -> dict[str, Any]:
    """信号执行窗口评估（V81 条件259）。

    综合波动率与流动性评估当前是否适合入场执行：
    - 波动率分：低波动作它的窗口（避免追高杀跌）
    - 流动性分：近期量能充足 → 执行滑移小
    - 综合 window_quality：favorable / acceptable / caution / unfavorable
    """
    result: dict[str, Any] = {
        "window_quality": "unknown",
        "volatility_score": 0.5,
        "liquidity_score": 0.5,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 20 or not highs or not lows:
            result["msg"] = "数据不足"
            return result

        vol = _calc_atr_volatility(closes[-40:])
        vol_pct = vol * 100.0

        # 波动率分：中枢波动 (1.5%~4%) 最优
        if vol_pct < 1.0:
            vol_score = 0.4  # 过于死寂
        elif vol_pct < 1.5:
            vol_score = 0.7
        elif vol_pct < 4.0:
            vol_score = 0.9
        elif vol_pct < 6.0:
            vol_score = 0.6
        else:
            vol_score = 0.3

        # 流动性分：近期量能相对平稳充足
        liq_score = 0.5
        if volumes is not None and len(volumes) >= 20:
            recent_vols = volumes[-20:]
            avg = sum(recent_vols) / len(recent_vols)
            if avg > 0:
                last15 = recent_vols[-15:]
                liq_ratio = sum(last15) / len(last15) / avg
                if liq_ratio > 0.8:
                    liq_score = 0.9
                elif liq_ratio > 0.5:
                    liq_score = 0.7
                else:
                    liq_score = 0.4

        result["volatility_score"] = round(vol_score, 2)
        result["liquidity_score"] = round(liq_score, 2)

        combined = vol_score * 0.6 + liq_score * 0.4
        if combined >= 0.8:
            quality, adjust = "favorable", 0.03
        elif combined >= 0.6:
            quality, adjust = "acceptable", 0.01
        elif combined >= 0.4:
            quality, adjust = "caution", -0.01
        else:
            quality, adjust = "unfavorable", -0.04

        result["window_quality"] = quality
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"执行窗口={quality} 波动分={vol_score:.2f} 流动性分={liq_score:.2f} "
            f"波动率{vol_pct:.2f}% 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


# ── V82 条件 260-263 实现 ──────────────────────────────────────────────


def _calc_mmd_age_decay_v82(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """买卖点时间衰减验证（V82 条件260）。

    计算从信号触发点至今的 K 线数量，评估信号新鲜度：
    - fresh: <60 根 → 新鲜，加分
    - moderate: 60-120 根 → 中性
    - aging: 120-200 根 → 减分
    - old: 200-300 根 → 明显减分
    - stale: >300 根 → 信号失效，大幅减分
    """
    result: dict[str, Any] = {
        "age_bars": 0,
        "age_label": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not closes or len(closes) < 5 or mmd.bi is None:
            result["msg"] = "数据不足"
            return result

        bi_end_idx = mmd.bi.end.k.k_index
        age_bars = max(0, len(closes) - 1 - bi_end_idx)
        result["age_bars"] = age_bars

        is_buy = "buy" in mmd.mmd_type.value
        # 买入信号随时间推移价值衰减更快（市场结构可能已变化）
        if is_buy:
            if age_bars < 30:
                label, adjust = "fresh", 0.03
            elif age_bars < 60:
                label, adjust = "fresh", 0.01
            elif age_bars < 120:
                label, adjust = "moderate", 0.0
            elif age_bars < 200:
                label, adjust = "aging", -0.02
            elif age_bars < 300:
                label, adjust = "old", -0.05
            else:
                label, adjust = "stale", -0.08
        else:
            if age_bars < 60:
                label, adjust = "fresh", 0.02
            elif age_bars < 120:
                label, adjust = "moderate", 0.0
            elif age_bars < 200:
                label, adjust = "aging", -0.02
            elif age_bars < 300:
                label, adjust = "old", -0.04
            else:
                label, adjust = "stale", -0.07

        result["age_label"] = label
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = f"信号距今{age_bars}根K线 新鲜度={label} 调整{adjust:+.0%}"
        return result
    except Exception:
        result["msg"] = "数据不足"
        return result


def _calc_breakout_retest_confirm_v82(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """中枢突破回踩确认（V82 条件261）。

    检测信号触发后是否出现"突破 → 回踩 → 确认"的完整结构：
    - 突破后价格回踩至突破位附近（38.2%-61.8%回撤）再回升 → strong
    - 突破后横盘消化 → moderate
    - 突破后直接单边（无回踩）→ weak
    - 突破后跌破突破位（失败）→ broken
    """
    result: dict[str, Any] = {
        "retest_detected": False,
        "retest_quality": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 20 or not highs or not lows or mmd.bi is None:
            result["msg"] = "数据不足"
            result["retest_quality"] = "unknown"
            return result

        bi_end_idx = mmd.bi.end.k.k_index
        # 信号触发后观察窗（最多20根）
        window_start = bi_end_idx + 1
        window_end = min(len(closes), window_start + 20)
        if window_start >= window_end:
            result["retest_quality"] = "unknown"
            result["msg"] = "触发点位于末端，无后续确认"
            return result

        # 突破极值（1买取低点，1卖取高点）
        is_buy = "buy" in mmd.mmd_type.value
        extreme = lows[bi_end_idx] if is_buy else highs[bi_end_idx]

        window_highs = highs[window_start:window_end]
        window_lows = lows[window_start:window_end]
        max_after = max(window_highs)
        min_after = min(window_lows)

        if is_buy:
            # 突破后最高点相对于极值的抬升幅度
            breakout_span = (max_after - extreme) / extreme if extreme > 0 else 0.0
            # 找到回踩低点（极值之后的最低点）
            retest_low = min_after
            pullback_pct = (
                (max_after - retest_low) / (max_after - extreme)
                if (max_after - extreme) > 0
                else 0.0
            )
        else:
            breakout_span = (extreme - min_after) / extreme if extreme > 0 else 0.0
            retest_high = max_after
            pullback_pct = (
                (retest_high - min_after) / (extreme - min_after)
                if (extreme - min_after) > 0
                else 0.0
            )

        # 突破幅度过小视为未突破
        if breakout_span < 0.01:
            result["retest_quality"] = "weak"
            result["msg"] = "突破幅度过小，无有效确认"
            return result

        # 回撤幅度 0.382-0.618 为理想回踩
        if 0.38 <= pullback_pct <= 0.65:
            quality, adjust = "strong", 0.04
            retest = True
        elif 0.2 <= pullback_pct < 0.38:
            quality, adjust = "moderate", 0.02
            retest = True
        elif pullback_pct < 0.2:
            quality, adjust = "weak", 0.0
            retest = True
        elif pullback_pct > 0.9:
            quality, adjust = "broken", -0.05
            retest = False
        else:
            quality, adjust = "moderate", 0.01
            retest = True

        result["retest_detected"] = retest
        result["retest_quality"] = quality
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"突破幅度{breakout_span:.1%} 回撤{pullback_pct:.1%} 回踩={quality} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        result["msg"] = "数据不足"
        result["retest_quality"] = "unknown"
        return result


def _calc_macd_multi_tf_resonance_v82(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """多级别MACD共振验证（V82 条件262）。

    用同一收盘价序列的短/中/长周期 MACD 模拟多级别视角：
    - short MACD(6,13,5)：短期加速度
    - mid MACD(12,26,9)：中期趋势
    - long MACD(24,52,18)：长期方向
    三周期同向 → 强共振；冲突 → 中性/减分。
    """
    result: dict[str, Any] = {
        "resonance": "none",
        "short_acceleration": 0.0,
        "mid_trend": 0.0,
        "long_trend": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 60:
            result["resonance"] = "none"
            result["msg"] = "数据不足"
            return result

        from easy_tdx.chanlun.macd import calc_macd

        macd_short = calc_macd(closes, 6, 13, 5)
        macd_mid = calc_macd(closes, 12, 26, 9)

        dif_s = macd_short["dif"]
        dif_m = macd_mid["dif"]

        # 用带类型的局部变量承载指标，避免 dict[str, object] 的 mypy strict 报错
        short_acc: float = 0.0
        mid_trend: float = 0.0
        long_trend: float = 0.0

        # 短期加速度：DIF 斜率（近5根）
        if len(dif_s) >= 6:
            short_acc = float(
                sum(1 for i in range(-4, 0) if dif_s[i] > dif_s[i - 1])
                - sum(1 for i in range(-4, 0) if dif_s[i] < dif_s[i - 1])
            )
        # 中期趋势：DIF 符号与斜率
        if len(dif_m) >= 6:
            mid_trend = float((1 if dif_m[-1] > 0 else 0) + (1 if dif_m[-1] > dif_m[-2] else 0))
        # 长期趋势：用更慢的 EMA 差
        long_slow = sum(closes[-50:]) / 50 if len(closes) >= 50 else sum(closes) / len(closes)
        long_fast = sum(closes[-10:]) / 10 if len(closes) >= 10 else sum(closes) / len(closes)
        long_trend = float(1 if long_fast > long_slow else 0)

        result["short_acceleration"] = short_acc
        result["mid_trend"] = mid_trend
        result["long_trend"] = long_trend

        is_buy = "buy" in mmd.mmd_type.value
        score = short_acc + mid_trend + long_trend

        if is_buy:
            if score >= 3:
                resonance, adjust = "bullish", 0.04
            elif score >= 1.5:
                resonance, adjust = "mostly_bullish", 0.02
            elif score <= -1.5:
                resonance, adjust = "bearish", -0.04
            else:
                resonance, adjust = "mixed", 0.0
        else:
            if score <= -1.5:
                resonance, adjust = "bearish", 0.04
            elif score <= 0:
                resonance, adjust = "mostly_bearish", 0.02
            elif score >= 2.5:
                resonance, adjust = "bullish", -0.04
            else:
                resonance, adjust = "mixed", 0.0

        result["resonance"] = resonance
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"多周期共振={resonance} 短加={result['short_acceleration']} "
            f"中={result['mid_trend']} 长={result['long_trend']} 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        result["msg"] = "数据不足"
        result["resonance"] = "none"
        return result


def _calc_volatility_compression_breakout_v82(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """波动率压缩突破确认（V82 条件263）。

    基于近期价格区间宽度检测波动率压缩状态，并评估突破力度：
    - extreme: 区间收窄至 3% 以内 → 蓄势充分，突破信号加分
    - high: 区间 3%-6% → 较充分
    - moderate: 6%-10% → 中性
    - low: >10% → 无压缩，信号减分
    """
    result: dict[str, Any] = {
        "compression_level": "none",
        "compression_pct": 0.0,
        "breakout_strength": 0.0,
        "volume_confirm": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 20 or not highs or not lows:
            result["msg"] = "数据不足"
            result["compression_level"] = "unknown"
            return result

        lookback = min(30, len(closes))
        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]
        current_price = closes[-1]
        if current_price <= 0:
            result["compression_level"] = "unknown"
            return result

        range_pct = (max(recent_highs) - min(recent_lows)) / current_price * 100.0
        result["compression_pct"] = round(range_pct, 2)

        # 近5根突破力度
        last5_high = max(highs[-5:]) if len(highs) >= 5 else current_price
        last5_low = min(lows[-5:]) if len(lows) >= 5 else current_price
        move_pct = (last5_high - last5_low) / current_price * 100.0
        result["breakout_strength"] = round(move_pct, 2)

        if range_pct < 3.0:
            compression = "extreme"
        elif range_pct < 6.0:
            compression = "high"
        elif range_pct < 10.0:
            compression = "moderate"
        else:
            compression = "low"

        result["compression_level"] = compression

        # 突破力度配合压缩程度评估
        if compression == "extreme":
            adjust = 0.04 if move_pct > 1.5 else 0.02
        elif compression == "high":
            adjust = 0.02 if move_pct > 2.0 else 0.0
        elif compression == "moderate":
            adjust = 0.0
        else:
            adjust = -0.02

        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"压缩度={compression} 区间宽{range_pct:.1f}% 近端波动{move_pct:.1f}% 调整{adjust:+.0%}"
        )
        return result
    except Exception:
        result["msg"] = "数据不足"
        result["compression_level"] = "unknown"
        return result
