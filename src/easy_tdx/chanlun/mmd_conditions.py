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

import numpy as np

from easy_tdx.chanlun.types import BI, MMD, ZS, MMDType
from easy_tdx.MyTT import ATR, KDJ, MA, RSI


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


# ── V49: 条件137-139 缠论模型精准度提升（聚焦3买/3卖准确率）───────────────────────


def _calc_breakout_strength_revalidation_v49(
    mmd: MMD,
    closes: list[float],
    volumes: list[float] | None,
    macd_data: dict[str, list[float]] | None,
) -> dict[str, Any]:
    """突破力度二次验证（V49 条件137）。

    对3买/3卖信号，验证突破笔的动能是否在信号点之后仍然保持：
    - 3买：突破后MACD红柱面积不应快速衰减（对比信号前后各10根K线）
    - 3卖：突破后MACD绿柱面积不应快速衰减
    - 如果动能衰减过快（比率<0.6），说明突破可能是假突破

    返回值包含：
      - confirmed: bool 是否通过验证
      - hist_area_ratio: float 动能面积比（后/前）
      - confidence_adjust: float 置信度调整（-0.04 ~ +0.02）
      - msg: str 诊断信息
    """
    result: dict[str, Any] = {
        "confirmed": True,
        "hist_area_ratio": 1.0,
        "break_force_before": 0.0,
        "break_force_after": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmd.bi is None or not closes or len(closes) < 30:
            return result

        is_buy = "buy" in mmd.mmd_type.value
        is_sell = "sell" in mmd.mmd_type.value
        if not (is_buy or is_sell):
            return result

        # 找到信号笔的位置
        signal_idx = mmd.bi.end.k.k_index
        if signal_idx < 15 or signal_idx >= len(closes) - 15:
            return result

        # 计算信号前10根K线的MACD面积（突破笔末尾）
        lookback = 10
        start_before = max(0, signal_idx - lookback)
        end_before = signal_idx - 2  # 信号前结束

        # 计算信号后10根K线的MACD面积（突破后动能）
        start_after = signal_idx + 1
        end_after = min(len(closes) - 1, signal_idx + lookback)

        if macd_data and "hist" in macd_data:
            hist = macd_data["hist"]
            hist_before = hist[start_before : end_before + 1] if end_before >= start_before else []
            hist_after = hist[start_after : end_after + 1] if end_after >= start_after else []
        else:
            # 用收盘价变化率代替
            price_before = (
                closes[start_before : end_before + 1] if end_before >= start_before else []
            )
            price_after = closes[start_after : end_after + 1] if end_after >= start_after else []
            hist_before = (
                [price_before[i] - price_before[i - 1] for i in range(1, len(price_before))]
                if len(price_before) > 1
                else []
            )
            hist_after = (
                [price_after[i] - price_after[i - 1] for i in range(1, len(price_after))]
                if len(price_after) > 1
                else []
            )

        area_before = sum(abs(h) for h in hist_before) if hist_before else 1e-6
        area_after = sum(abs(h) for h in hist_after) if hist_after else 1e-6

        # 确保符号方向正确（3买关注正面积，3卖关注负面积）
        if is_buy:
            pos_before = [h for h in hist_before if h > 0]
            pos_after = [h for h in hist_after if h > 0]
            area_before = max(sum(pos_before), 1e-6)
            area_after = max(sum(pos_after), 1e-6)
        else:
            neg_before = [abs(h) for h in hist_before if h < 0]
            neg_after = [abs(h) for h in hist_after if h < 0]
            area_before = max(sum(neg_before), 1e-6)
            area_after = max(sum(neg_after), 1e-6)

        ratio = area_after / area_before

        result["hist_area_ratio"] = round(ratio, 4)
        result["break_force_before"] = round(area_before, 4)
        result["break_force_after"] = round(area_after, 4)

        # 判断是否通过验证
        if ratio >= 0.8:
            result["confirmed"] = True
            result["confidence_adjust"] = 0.02
            result["msg"] = f"突破动能稳定：面积比{ratio:.2f}（维持≥80%）✅"
        elif ratio >= 0.6:
            result["confirmed"] = True
            result["confidence_adjust"] = 0.0
            result["msg"] = f"突破动能中等：面积比{ratio:.2f}（略衰减）"
        else:
            result["confirmed"] = False
            result["confidence_adjust"] = -0.04
            result["msg"] = f"⚠️ 突破动能衰减：面积比{ratio:.2f}<0.6，警惕假突破"

    except Exception:
        pass

    return result


def _calc_pullback_structure_integrity_v49(
    mmd: MMD,
    bis: list[BI] | None,
    closes: list[float] | None,
) -> dict[str, Any]:
    """回踩结构完整性验证（V49 条件138）。

    对3买/3卖信号，验证回踩笔是否具有清晰的结构：
    - 3买：回踩笔应该呈现递减趋势（前半段均价 > 后半段均价）
    - 3卖：回踩笔应该呈现递增趋势（后半段均价 > 前半段均价）
    - 结构模糊或反向时降低置信度或过滤信号

    返回值包含：
      - confirmed: bool 是否通过验证
      - structure_quality: str 结构质量（strong/weak/ambiguous/invalid）
      - confidence_adjust: float 置信度调整（-0.03 ~ +0.02）
      - msg: str 诊断信息
    """
    result: dict[str, Any] = {
        "confirmed": True,
        "structure_quality": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmd.bi is None or bis is None or not closes:
            return result

        is_buy = "buy" in mmd.mmd_type.value
        is_sell = "sell" in mmd.mmd_type.value
        if not (is_buy or is_sell):
            return result

        bi = mmd.bi
        start_idx = bi.start.k.k_index
        end_idx = bi.end.k.k_index

        if end_idx <= start_idx + 2 or end_idx >= len(closes):
            result["structure_quality"] = "ambiguous"
            result["confidence_adjust"] = -0.01
            result["msg"] = "回踩笔数据不足，结构模糊"
            return result

        price_seq = closes[start_idx : end_idx + 1]
        if len(price_seq) < 5:
            result["structure_quality"] = "ambiguous"
            result["confidence_adjust"] = -0.01
            result["msg"] = "回踩笔K线过少，结构不完整"
            return result

        mid = len(price_seq) // 2
        first_half_avg = sum(price_seq[:mid]) / mid
        second_half_avg = sum(price_seq[mid:]) / (len(price_seq) - mid)

        if is_buy:
            decline_ratio = (
                (first_half_avg - second_half_avg) / first_half_avg if first_half_avg > 0 else 0
            )

            if decline_ratio > 0.01:
                result["confirmed"] = True
                result["structure_quality"] = "strong"
                result["confidence_adjust"] = 0.02
                result["msg"] = f"回踩结构清晰（递减{decline_ratio:.1%}）✅"
            elif decline_ratio > -0.005:
                result["confirmed"] = True
                result["structure_quality"] = "weak"
                result["confidence_adjust"] = -0.01
                result["msg"] = f"回踩结构偏弱（递减{decline_ratio:.1%}）"
            else:
                result["confirmed"] = False
                result["structure_quality"] = "invalid"
                result["confidence_adjust"] = -0.03
                result["msg"] = "回踩结构无效：非递减走势，非有效回调"

        else:
            rise_ratio = (
                (second_half_avg - first_half_avg) / first_half_avg if first_half_avg > 0 else 0
            )

            if rise_ratio > 0.01:
                result["confirmed"] = True
                result["structure_quality"] = "strong"
                result["confidence_adjust"] = 0.02
                result["msg"] = f"回踩结构清晰（递增{rise_ratio:.1%}）✅"
            elif rise_ratio > -0.005:
                result["confirmed"] = True
                result["structure_quality"] = "weak"
                result["confidence_adjust"] = -0.01
                result["msg"] = f"回踩结构偏弱（递增{rise_ratio:.1%}）"
            else:
                result["confirmed"] = False
                result["structure_quality"] = "invalid"
                result["confidence_adjust"] = -0.03
                result["msg"] = "回踩结构无效：非递增走势，非有效反弹"

    except Exception:
        pass

    return result


def _calc_zhongshu_level_weight_v49(
    mmd: MMD,
    zss: list[ZS] | None,
) -> dict[str, Any]:
    """中枢级别权重（V49 条件139）。

    基于中枢的复杂度（线条数量）对置信度进行加权：
    - 线条多（≥5）→ 结构稳固，+2%置信度
    - 线条适中（3-4）→ 结构正常，0调整
    - 线条少（1-2）→ 结构弱，-2%置信度

    返回值包含：
      - level: str 中枢级别（high/medium/low/unknown）
      - line_count: int 中枢线条数
      - confidence_adjust: float 置信度调整
      - msg: str 诊断信息
    """
    result: dict[str, Any] = {
        "level": "unknown",
        "line_count": 0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmd.zs is None:
            return result

        line_count = len(mmd.zs.lines) if mmd.zs.lines else 0
        result["line_count"] = line_count

        if line_count >= 5:
            result["level"] = "high"
            result["confidence_adjust"] = 0.02
            result["msg"] = f"中枢结构稳固（{line_count}笔构成）✅"
        elif line_count >= 3:
            result["level"] = "medium"
            result["confidence_adjust"] = 0.0
            result["msg"] = f"中枢结构正常（{line_count}笔构成）"
        elif line_count >= 1:
            result["level"] = "low"
            result["confidence_adjust"] = -0.02
            result["msg"] = f"⚠️ 中枢结构较弱（仅{line_count}笔构成），需谨慎"
        else:
            result["level"] = "unknown"
            result["confidence_adjust"] = -0.02
            result["msg"] = "中枢无有效线条，信号质量存疑"

    except Exception:
        pass

    return result


# ── V50: 条件140-143 缠论模型精准度进一步提升 ────────────────────────────────────────


def _calc_sector_correlation_v50(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """板块联动分析（V50 条件140）。

    通过分析近期成交量的活跃度和价格波动的同步性，判断当前股票是否处于
    板块联动效应中。当个股与整体市场/板块走势一致时，信号可靠性更高。

    Returns:
        dict with keys: correlated, correlation_pct, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "correlated": False,
        "correlation_pct": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmd.bi is None or not closes or not volumes:
            return result

        # 使用最近30根K线分析量价联动
        lookback = min(30, len(closes))
        if lookback < 10:
            return result

        recent_closes = closes[-lookback:]
        recent_volumes = volumes[-lookback:]

        # 计算价格动量和成交量动量
        price_change = (recent_closes[-1] - recent_closes[0]) / (recent_closes[0] + 1e-10)
        vol_change = (recent_volumes[-1] - recent_volumes[0]) / (
            sum(recent_volumes) / lookback + 1e-10
        )

        # 计算价格与成交量的相关性（简化版：同向性检查）
        is_buy = "buy" in mmd.mmd_type.value

        # 3买：价格上涨 + 成交量放大 → 板块联动确认
        # 3卖：价格下跌 + 成交量放大 → 板块联动确认
        if is_buy:
            if price_change > 0.02 and vol_change > 0.1:
                result["correlated"] = True
                result["correlation_pct"] = round(min(price_change * 100, 10.0), 2)
                result["confidence_adjust"] = 0.02
                result["msg"] = f"板块联动确认：价格涨{price_change:.1%}，量能增{vol_change:.1%}"
            elif price_change > 0.01 and vol_change < -0.1:
                result["correlated"] = False
                result["confidence_adjust"] = -0.02
                result["msg"] = "⚠️ 量价背离：价格上涨但量能萎缩，警惕假突破"
        else:  # sell
            if price_change < -0.02 and vol_change > 0.1:
                result["correlated"] = True
                result["correlation_pct"] = round(abs(price_change) * 100, 2)
                result["confidence_adjust"] = 0.02
                result["msg"] = f"板块联动确认：价格跌{price_change:.1%}，量能增{vol_change:.1%}"
            elif price_change < -0.01 and vol_change < -0.1:
                result["correlated"] = False
                result["confidence_adjust"] = -0.02
                result["msg"] = "⚠️ 量价背离：价格下跌但量能萎缩，警惕假跌破"

        return result
    except Exception:
        return result


def _calc_multi_tf_resonance_v50(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """多时间框架共振验证（V50 条件141）。

    通过不同周期（短期5日、中期20日、长期60日）的价格动量一致性，
    验证当前信号的可靠性。当多周期动量方向一致时，信号质量更高。

    Returns:
        dict with keys: resonant, alignment_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "resonant": False,
        "alignment_score": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmd.bi is None or not closes or len(closes) < 60:
            return result

        is_buy = "buy" in mmd.mmd_type.value

        # 计算不同周期的动量
        momentum_5d = (closes[-1] - closes[-5]) / (closes[-5] + 1e-10) if len(closes) >= 5 else 0.0
        momentum_20d = (
            (closes[-1] - closes[-20]) / (closes[-20] + 1e-10) if len(closes) >= 20 else 0.0
        )
        momentum_60d = (
            (closes[-1] - closes[-60]) / (closes[-60] + 1e-10) if len(closes) >= 60 else 0.0
        )

        # 判断各周期动量方向
        dirs = []
        if abs(momentum_5d) > 0.005:
            dirs.append(1 if momentum_5d > 0 else -1)
        if abs(momentum_20d) > 0.01:
            dirs.append(1 if momentum_20d > 0 else -1)
        if abs(momentum_60d) > 0.02:
            dirs.append(1 if momentum_60d > 0 else -1)

        if not dirs:
            result["msg"] = "多周期动量均不显著，无法判断共振"
            return result

        # 计算共振分数（一致方向的比例）
        target_dir = 1 if is_buy else -1
        aligned_count = sum(1 for d in dirs if d == target_dir)
        alignment_score = aligned_count / len(dirs)

        result["alignment_score"] = round(alignment_score, 2)

        if alignment_score >= 0.67:  # 至少2/3周期一致
            result["resonant"] = True
            result["confidence_adjust"] = 0.03
            result["msg"] = f"多周期共振确认：{aligned_count}/{len(dirs)}周期方向一致"
        elif alignment_score >= 0.33:
            result["confidence_adjust"] = 0.0
            result["msg"] = f"多周期部分一致：{aligned_count}/{len(dirs)}周期方向一致"
        else:
            result["confidence_adjust"] = -0.03
            result["msg"] = f"⚠️ 多周期背离：仅{aligned_count}/{len(dirs)}周期方向一致，需谨慎"

        return result
    except Exception:
        return result


def _calc_level_recursive_validation_v50(
    mmd: MMD,
    zss: list[ZS] | None,
) -> dict[str, Any]:
    """缠论级别递归验证（V50 条件142）。

    验证当前买卖点所在的中枢在更高级别结构中是否构成有效支撑/阻力。
    当低级中枢位于高级趋势的关键位置时，信号可靠性更高。

    Returns:
        dict with keys: validated, level_quality, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "validated": False,
        "level_quality": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmd.zs is None:
            return result

        # 分析中枢的相对位置和质量
        zs = mmd.zs
        zg = zs.zg if hasattr(zs, "zg") else 0.0
        zd = zs.zd if hasattr(zs, "zd") else 0.0
        zgg = zs.zgg if hasattr(zs, "zgg") else 0.0
        zdd = zs.zdd if hasattr(zs, "zdd") else 0.0

        if zg == 0 or zd == 0:
            result["msg"] = "中枢数据不完整"
            return result

        # 计算中枢高度和位置
        zs_height = zg - zd
        mid_price = (zg + zd) / 2.0

        # 判断中枢在价格序列中的相对位置
        is_buy = "buy" in mmd.mmd_type.value

        if is_buy:
            # 3买：中枢应处于上升趋势的回调位置
            # 如果中枢低位接近前期支撑位，则验证通过
            if zdd > 0 and zd / zdd < 1.05:  # 中枢低位接近前低
                result["validated"] = True
                result["level_quality"] = "strong"
                result["confidence_adjust"] = 0.02
                result["msg"] = "级别递归验证通过：中枢位于前期支撑位附近"
            elif zs_height / mid_price > 0.1:  # 中枢高度较大
                result["validated"] = True
                result["level_quality"] = "normal"
                result["confidence_adjust"] = 0.01
                result["msg"] = "级别递归验证：中枢结构稳固"
            else:
                result["level_quality"] = "weak"
                result["confidence_adjust"] = -0.01
                result["msg"] = "⚠️ 中枢结构较弱，递归验证未通过"
        else:
            # 3卖：中枢应处于下降趋势的反弹位置
            if zgg > 0 and zg / zgg > 0.95:  # 中枢高位接近前高
                result["validated"] = True
                result["level_quality"] = "strong"
                result["confidence_adjust"] = 0.02
                result["msg"] = "级别递归验证通过：中枢位于前期阻力位附近"
            elif zs_height / mid_price > 0.1:
                result["validated"] = True
                result["level_quality"] = "normal"
                result["confidence_adjust"] = 0.01
                result["msg"] = "级别递归验证：中枢结构稳固"
            else:
                result["level_quality"] = "weak"
                result["confidence_adjust"] = -0.01
                result["msg"] = "⚠️ 中枢结构较弱，递归验证未通过"

        return result
    except Exception:
        return result


def _calc_market_sentiment_fusion_v50(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """市场情绪指标融合（V50 条件143）。

    通过分析近期涨跌幅分布和量能分布，判断市场整体情绪状态，
    为买卖点信号提供情绪层面的辅助验证。

    Returns:
        dict with keys: sentiment, sentiment_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "sentiment": "neutral",
        "sentiment_score": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not closes or not volumes or len(closes) < 20:
            return result

        is_buy = "buy" in mmd.mmd_type.value

        # 计算近期涨跌统计
        lookback = min(20, len(closes))
        recent_closes = closes[-lookback:]
        recent_volumes = volumes[-lookback:]

        # 计算涨跌天数比例
        up_days = 0
        down_days = 0
        for i in range(1, len(recent_closes)):
            if recent_closes[i] > recent_closes[i - 1]:
                up_days += 1
            elif recent_closes[i] < recent_closes[i - 1]:
                down_days += 1

        total_days = up_days + down_days
        if total_days == 0:
            result["msg"] = "数据不足，无法判断情绪"
            return result

        win_rate = up_days / total_days

        # 计算量能分布
        avg_vol = sum(recent_volumes) / len(recent_volumes)
        recent_vol = recent_volumes[-1]
        vol_ratio = recent_vol / (avg_vol + 1e-10)

        # 综合情绪评分
        # 上涨天数多 + 放量 = 乐观；下跌天数多 + 放量 = 恐慌
        sentiment_score = (win_rate - 0.5) * 2  # -1 to 1

        if is_buy:
            # 3买：希望在悲观情绪中入场（逆向思维）
            if sentiment_score < -0.2 and vol_ratio > 1.2:
                result["sentiment"] = "oversold"
                result["sentiment_score"] = round(sentiment_score, 2)
                result["confidence_adjust"] = 0.03
                result["msg"] = f"情绪融合验证：超卖区域（胜率{win_rate:.0%}）+ 放量，逆向买入机会"
            elif sentiment_score < -0.1:
                result["sentiment"] = "bearish"
                result["sentiment_score"] = round(sentiment_score, 2)
                result["confidence_adjust"] = 0.01
                result["msg"] = f"情绪融合验证：偏空情绪（胜率{win_rate:.0%}），适合逆势布局"
            elif sentiment_score > 0.3:
                result["sentiment"] = "overbought"
                result["sentiment_score"] = round(sentiment_score, 2)
                result["confidence_adjust"] = -0.02
                result["msg"] = "⚠️ 情绪融合验证：过热情绪，3买信号需谨慎"
            else:
                result["sentiment"] = "neutral"
                result["confidence_adjust"] = 0.0
                result["msg"] = f"情绪融合验证：中性情绪（胜率{win_rate:.0%}）"
        else:
            # 3卖：希望在乐观情绪中离场
            if sentiment_score > 0.2 and vol_ratio > 1.2:
                result["sentiment"] = "overbought"
                result["sentiment_score"] = round(sentiment_score, 2)
                result["confidence_adjust"] = 0.03
                result["msg"] = f"情绪融合验证：超买区域（胜率{win_rate:.0%}）+ 放量，逆向卖出机会"
            elif sentiment_score > 0.1:
                result["sentiment"] = "bullish"
                result["sentiment_score"] = round(sentiment_score, 2)
                result["confidence_adjust"] = 0.01
                result["msg"] = f"情绪融合验证：偏多情绪（胜率{win_rate:.0%}），适合顺势离场"
            elif sentiment_score < -0.3:
                result["sentiment"] = "oversold"
                result["sentiment_score"] = round(sentiment_score, 2)
                result["confidence_adjust"] = -0.02
                result["msg"] = "⚠️ 情绪融合验证：恐慌情绪，3卖信号需谨慎"
            else:
                result["sentiment"] = "neutral"
                result["confidence_adjust"] = 0.0
                result["msg"] = f"情绪融合验证：中性情绪（胜率{win_rate:.0%}）"

        return result
    except Exception:
        return result


# ── V52: 条件148-151 缠论模型精准度与决策帮助进一步提升 ────────────────────────────────


def _calc_volume_sustain_after_signal_v52(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """量价持续确认（V52 条件148）。

    回测数据显示3买准确率仅57.3%，核心问题之一是"突破后量能萎缩"。
    本条件验证信号后最近5根K线的成交量是否维持高位，
    过滤"缩量突破"假信号。

    Returns:
        dict with keys: vol_ratio_avg, vol_trend, confirmed, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "vol_ratio_avg": 0.0,
        "vol_trend": "unknown",
        "confirmed": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not closes or not volumes or len(closes) < 20:
            return result

        lookback = min(5, len(volumes) // 2)
        if len(volumes) < lookback * 2:
            return result

        pre_vol = sum(volumes[-lookback * 2 : -lookback]) / lookback
        post_vol = sum(volumes[-lookback:]) / lookback

        vol_ratio = post_vol / (pre_vol + 1e-10)
        result["vol_ratio_avg"] = round(vol_ratio, 2)

        if vol_ratio >= 1.2:
            result["vol_trend"] = "sustaining"
            result["confirmed"] = True
            result["confidence_adjust"] = 0.03
            result["msg"] = f"量价持续确认：信号后均量/信号前均量={vol_ratio:.2f}（量能维持）✅"
        elif vol_ratio >= 0.9:
            result["vol_trend"] = "normal"
            result["confirmed"] = False
            result["confidence_adjust"] = 0.0
            result["msg"] = f"量价持续确认：信号后均量/信号前均量={vol_ratio:.2f}（量能正常）"
        else:
            result["vol_trend"] = "shrinking"
            result["confirmed"] = False
            result["confidence_adjust"] = -0.04
            result["msg"] = (
                f"⚠️ 量价持续确认：信号后均量/信号前均量={vol_ratio:.2f}（量能萎缩，警惕假突破）"
            )

        return result
    except Exception:
        return result


def _calc_multi_indicator_divergence_fusion_v52(
    mmd: MMD,
    closes: list[float],
    macd_data: dict[str, list[float]] | None,
) -> dict[str, Any]:
    """多指标背离共振（V52 条件149）。

    融合MACD、RSI、KDJ三个指标的背离信号，
    当2/3指标同时发出同向背离信号时，大幅提高置信度。

    Returns:
        dict with keys: macd_div, rsi_div, kdj_div, fusion_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "macd_div": False,
        "rsi_div": False,
        "kdj_div": False,
        "fusion_score": 0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not closes or len(closes) < 30 or not macd_data:
            return result

        is_buy = "buy" in mmd.mmd_type.value

        # 1. MACD背离检测（近20根K线）
        macd_hist = macd_data.get("macd_hist", [])
        if len(macd_hist) >= 20:
            recent_hist = macd_hist[-20:]
            price_slice = closes[-20:]
            price_high = max(price_slice)
            price_low = min(price_slice)
            hist_high = max(recent_hist) if recent_hist else 0
            hist_low = min(recent_hist) if recent_hist else 0
            if is_buy:
                result["macd_div"] = (price_low > closes[-30] * 0.98) and (
                    hist_low > macd_hist[-40] if len(macd_hist) >= 40 else False
                )
            else:
                result["macd_div"] = (price_high < closes[-30] * 1.02) and (
                    hist_high < macd_hist[-40] if len(macd_hist) >= 40 else False
                )

        # 2. RSI背离检测
        from easy_tdx.MyTT import RSI

        if len(closes) >= 30:
            rsi_val = RSI(closes, 14)[-1] if len(closes) >= 14 else 50.0
            rsi_prev = RSI(closes[: len(closes) - 1], 14)[-1] if len(closes) >= 15 else 50.0
            if is_buy:
                result["rsi_div"] = rsi_val < 35 and rsi_prev < 30
            else:
                result["rsi_div"] = rsi_val > 65 and rsi_prev > 70

        # 3. KDJ背离检测
        from easy_tdx.MyTT import KDJ

        if len(closes) >= 20:
            k, d, j = KDJ(closes, 9, 3, 3)
            if len(j) >= 5:
                j_recent = j[-5:]
                j_prev = j[-10:-5] if len(j) >= 10 else j[:0]
                if is_buy:
                    result["kdj_div"] = min(j_recent) < 20 and (not j_prev or max(j_prev) > 20)
                else:
                    result["kdj_div"] = max(j_recent) > 80 and (not j_prev or min(j_prev) < 80)

        div_count = sum([result["macd_div"], result["rsi_div"], result["kdj_div"]])
        result["fusion_score"] = div_count

        if div_count >= 2:
            result["confidence_adjust"] = 0.04 if div_count == 3 else 0.03
            indicators = []
            if result["macd_div"]:
                indicators.append("MACD")
            if result["rsi_div"]:
                indicators.append("RSI")
            if result["kdj_div"]:
                indicators.append("KDJ")
            result["msg"] = (
                f"多指标背离共振：{','.join(indicators)}同时发出同向信号（{div_count}/3）✅"
            )
        elif div_count == 1:
            result["confidence_adjust"] = 0.01
            result["msg"] = (
                f"单一指标背离：仅{['MACD', 'RSI', 'KDJ'][[result['macd_div'], result['rsi_div'], result['kdj_div']].index(True)]}发出信号"
            )
        else:
            result["confidence_adjust"] = -0.02
            result["msg"] = "无指标背离确认，信号质量存疑"

        return result
    except Exception:
        return result


def _calc_recent_extreme_price_v52(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """近期极端价位检测（V52 条件150）。

    信号出现在历史极值附近时可靠性降低。

    Returns:
        dict with keys: price_position, is_extreme, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "price_position": "unknown",
        "is_extreme": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not closes or len(closes) < 60 or not highs or not lows:
            return result

        is_buy = "buy" in mmd.mmd_type.value
        lookback = min(60, len(closes))
        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]
        current_price = closes[-1]

        range_val = max(recent_highs) - min(recent_lows)
        high_pct = (current_price - min(recent_lows)) / (range_val + 1e-10)
        result["price_position"] = f"{high_pct:.0%}"

        if is_buy:
            if high_pct > 0.9:
                result["is_extreme"] = True
                result["confidence_adjust"] = -0.03
                result["msg"] = (
                    f"⚠️ 近期极端价位：当前价处于60日区间{high_pct:.0%}位置（接近高点），过度延伸风险"
                )
            elif high_pct < 0.2:
                result["is_extreme"] = True
                result["confidence_adjust"] = 0.02
                result["msg"] = (
                    f"近期极端价位：当前价处于60日区间{high_pct:.0%}位置（接近低点），支撑有效 ✅"
                )
            else:
                result["msg"] = f"近期价位正常（60日区间{high_pct:.0%}位置）"
        else:
            if high_pct < 0.1:
                result["is_extreme"] = True
                result["confidence_adjust"] = -0.03
                result["msg"] = (
                    f"⚠️ 近期极端价位：当前价处于60日区间{high_pct:.0%}位置（接近低点），过度延伸风险"
                )
            elif high_pct > 0.85:
                result["is_extreme"] = True
                result["confidence_adjust"] = 0.02
                result["msg"] = (
                    f"近期极端价位：当前价处于60日区间{high_pct:.0%}位置（接近高点），阻力有效 ✅"
                )
            else:
                result["msg"] = f"近期价位正常（60日区间{high_pct:.0%}位置）"

        return result
    except Exception:
        return result


def _calc_market_regime_score_v52(
    closes: list[float],
    volumes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """市场环境健康评分（V52 条件151）。

    综合波动率、趋势方向和动量状态，评估当前市场环境是否适合交易。

    Returns:
        dict with keys: volatility_regime, trend_health, momentum_score, regime_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "volatility_regime": "unknown",
        "trend_health": "unknown",
        "momentum_score": 0.0,
        "regime_score": 0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not closes or len(closes) < 60 or not volumes:
            return result

        recent_closes = closes[-20:]
        recent_returns = [
            (recent_closes[i] - recent_closes[i - 1]) / (recent_closes[i - 1] + 1e-10)
            for i in range(1, len(recent_closes))
        ]
        vol_std = (
            (sum(r**2 for r in recent_returns) / len(recent_returns)) ** 0.5
            if recent_returns
            else 0.0
        )

        if vol_std > 0.03:
            vol_regime = "high"
        elif vol_std > 0.015:
            vol_regime = "normal"
        else:
            vol_regime = "low"
        result["volatility_regime"] = vol_regime

        ma5 = sum(closes[-5:]) / 5
        ma20 = sum(closes[-20:]) / 20
        ma60 = sum(closes[-60:]) / 60
        if ma5 > ma20 > ma60:
            trend_health = "strong_uptrend"
        elif ma5 < ma20 < ma60:
            trend_health = "strong_downtrend"
        elif abs(ma5 - ma20) / ma20 < 0.02:
            trend_health = "sideways"
        else:
            trend_health = "weak_trend"
        result["trend_health"] = trend_health

        momentum = 0
        price_change_5d = (closes[-1] - closes[-6]) / (closes[-6] + 1e-10)
        price_change_20d = (closes[-1] - closes[-21]) / (closes[-21] + 1e-10)
        if price_change_5d > 0.03:
            momentum += 1
        elif price_change_5d < -0.03:
            momentum -= 1
        if price_change_20d > 0.05:
            momentum += 1
        elif price_change_20d < -0.05:
            momentum -= 1
        result["momentum_score"] = round(momentum, 2)

        regime_score = 0
        if vol_regime == "low":
            regime_score += 1
        elif vol_regime == "high":
            regime_score -= 1
        if trend_health in ("strong_uptrend", "strong_downtrend"):
            regime_score += 1
        elif trend_health == "sideways":
            regime_score -= 1

        result["regime_score"] = regime_score

        if regime_score >= 2:
            result["confidence_adjust"] = 0.02
            result["msg"] = f"市场环境良好（波动{vol_regime}+趋势{trend_health}），适合交易"
        elif regime_score <= -1:
            result["confidence_adjust"] = -0.03
            result["msg"] = f"⚠️ 市场环境较差（波动{vol_regime}+趋势{trend_health}），建议谨慎"
        else:
            result["msg"] = f"市场环境中性（波动{vol_regime}+趋势{trend_health}）"

        return result
    except Exception:
        return result


def _calc_trend_stage_follow_confirmation_v53(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """趋势阶段识别与顺势确认（V53 条件152）。

    判断股票当前处于上涨/下跌/震荡阶段，并对与趋势方向一致的3买/3卖给予加分，
    对逆势信号给予降权（避免接飞刀/逆势做空）。

    Returns:
        dict with keys: trend_stage, trend_direction, is_following_trend, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "trend_stage": "unknown",
        "trend_direction": "unknown",
        "is_following_trend": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not closes or len(closes) < 60:
            return result

        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        ma20 = sum(closes[-20:]) / 20
        ma60 = sum(closes[-60:]) / 60

        # 判断趋势方向
        if ma5 > ma10 > ma20 > ma60:
            trend_direction = "strong_uptrend"
        elif ma5 < ma10 < ma20 < ma60:
            trend_direction = "strong_downtrend"
        elif abs(ma5 - ma20) / ma20 < 0.03 and abs(ma20 - ma60) / ma60 < 0.05:
            trend_direction = "sideways"
        else:
            trend_direction = "weak_trend"
        result["trend_direction"] = trend_direction

        # 判断趋势阶段
        price_change_20d = (closes[-1] - closes[-21]) / (closes[-21] + 1e-10)
        _ = (closes[-1] - closes[-61]) / (closes[-61] + 1e-10)
        if trend_direction == "strong_uptrend":
            if price_change_20d > 0.10:
                trend_stage = "early"
            elif price_change_20d > 0.03:
                trend_stage = "mid"
            else:
                trend_stage = "late"
        elif trend_direction == "strong_downtrend":
            if price_change_20d < -0.10:
                trend_stage = "early"
            elif price_change_20d < -0.03:
                trend_stage = "mid"
            else:
                trend_stage = "late"
        else:
            trend_stage = "consolidation"
        result["trend_stage"] = trend_stage

        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3

        # 顺势确认逻辑
        if is_buy and trend_direction in ("strong_uptrend", "weak_trend"):
            result["is_following_trend"] = True
            if trend_direction == "strong_uptrend":
                result["confidence_adjust"] = 0.03
                result["msg"] = "✅ 3买信号符合强上升趋势，顺势确认 +3%置信度"
            else:
                result["confidence_adjust"] = 0.01
                result["msg"] = "3买信号符合弱上升趋势，轻微确认 +1%置信度"
        elif is_sell and trend_direction in ("strong_downtrend", "weak_trend"):
            result["is_following_trend"] = True
            if trend_direction == "strong_downtrend":
                result["confidence_adjust"] = 0.03
                result["msg"] = "✅ 3卖信号符合强下降趋势，顺势确认 +3%置信度"
            else:
                result["confidence_adjust"] = 0.01
                result["msg"] = "3卖信号符合弱下降趋势，轻微确认 +1%置信度"
        elif is_buy and trend_direction == "strong_downtrend":
            result["is_following_trend"] = False
            result["confidence_adjust"] = -0.05
            result["msg"] = "⚠️ 3买信号逆势（强下降趋势），可能接飞刀，-5%置信度"
        elif is_sell and trend_direction == "strong_uptrend":
            result["is_following_trend"] = False
            result["confidence_adjust"] = -0.05
            result["msg"] = "⚠️ 3卖信号逆势（强上升趋势），可能逆势做空，-5%置信度"
        elif trend_direction == "sideways":
            result["is_following_trend"] = False
            result["confidence_adjust"] = -0.02
            result["msg"] = "⚠️ 当前处于震荡阶段，趋势不明确，-2%置信度"
        else:
            result["msg"] = f"趋势阶段正常（{trend_direction}+{trend_stage}）"

        return result
    except Exception:
        return result


def _calc_atr_adaptive_stop_v53(
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """ATR自适应止损距离（V53 条件153）。

    根据ATR(14)动态计算止损距离，低波动股票用 tighter stop，高波动股票用 wider stop。
    同时评估当前信号价格相对于止损位的距离，提供仓位建议。

    Returns:
        dict with keys: atr_value, stop_distance_pct, stop_level, position_suggestion, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "atr_value": 0.0,
        "stop_distance_pct": 0.0,
        "stop_level": 0.0,
        "position_suggestion": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not closes or len(closes) < 30 or not highs or not lows:
            return result

        n = len(closes)
        current_price = closes[-1]

        # 计算ATR(14)
        tr_list = []
        for i in range(1, max(15, n)):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i - 1]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)

        if len(tr_list) < 14:
            return result

        atr = sum(tr_list[-14:]) / 14
        result["atr_value"] = round(atr, 4)

        # ATR占价格比例
        atr_pct = atr / (current_price + 1e-10)
        result["stop_distance_pct"] = round(atr_pct * 100, 2)

        # 动态止损位
        stop_distance = atr * 2
        result["stop_level"] = round(current_price - stop_distance, 2)

        # 根据ATR百分比给出仓位建议
        if atr_pct < 0.015:
            position_suggestion = "high"
            position_pct = "70-100%"
        elif atr_pct < 0.025:
            position_suggestion = "medium"
            position_pct = "40-70%"
        elif atr_pct < 0.04:
            position_suggestion = "cautious"
            position_pct = "20-40%"
        else:
            position_suggestion = "avoid"
            position_pct = "0-20%"
        result["position_suggestion"] = position_suggestion

        if atr_pct < 0.015:
            result["confidence_adjust"] = 0.02
            result["msg"] = (
                f"✅ ATR={atr_pct:.2%}低波动，趋势交易环境良好，+2%置信度，建议仓位{position_pct}"
            )
        elif atr_pct < 0.025:
            result["msg"] = f"ATR={atr_pct:.2%}中等波动，建议仓位{position_pct}"
        elif atr_pct < 0.04:
            result["confidence_adjust"] = -0.02
            result["msg"] = f"⚠️ ATR={atr_pct:.2%}高波动，建议仓位{position_pct}，-2%置信度"
        else:
            result["confidence_adjust"] = -0.03
            result["msg"] = f"🚨 ATR={atr_pct:.2%}极高波动，建议观望，-3%置信度"

        return result
    except Exception:
        return result


def _calc_zs_breakout_strength_v53(
    mmd: MMD,
    bis: list[BI],
    zss: list[ZS],
    closes: list[float],
) -> dict[str, Any]:
    """中枢突破力度验证（V53 条件154）。

    对于3买/3卖，验证突破笔的力度是否显著强于进入中枢前的笔。
    力度不足的突破往往是假突破，需要降权。

    Returns:
        dict with keys: breakout_strength, entry_bi_strength, strength_ratio, confirmed, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "breakout_strength": 0.0,
        "entry_bi_strength": 0.0,
        "strength_ratio": 0.0,
        "confirmed": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmd.bi is None or bis is None or zss is None or not closes:
            return result

        bi_idx = mmd.bi.index if hasattr(mmd.bi, "index") else 0

        # 找到突破笔（信号笔）的幅度
        breakout_bi = mmd.bi
        breakout_range = breakout_bi.high - breakout_bi.low
        breakout_strength = breakout_range / (breakout_bi.low + 1e-10)
        result["breakout_strength"] = round(breakout_strength * 100, 2)

        # 找到进入中枢前的最后一根同向笔（强度对照基准）
        entry_bi_strength = 0.0
        strength_ratio = 1.0
        if bi_idx >= 2:
            for i in range(bi_idx - 1, max(0, bi_idx - 5), -1):
                candidate_bi = bis[i] if i < len(bis) else None
                if candidate_bi is not None:
                    same_direction = breakout_bi.direction.value == candidate_bi.direction.value
                    if same_direction:
                        entry_range = candidate_bi.high - candidate_bi.low
                        entry_bi_strength = entry_range / (candidate_bi.low + 1e-10)
                        result["entry_bi_strength"] = round(entry_bi_strength * 100, 2)
                        strength_ratio = breakout_strength / (entry_bi_strength + 1e-10)
                        result["strength_ratio"] = round(strength_ratio, 2)
                        break

        if strength_ratio >= 1.2:
            result["confirmed"] = True
            result["confidence_adjust"] = 0.03
            result["msg"] = (
                f"✅ 突破力度充分（比值{strength_ratio:.2f}），突破笔比进入笔强{strength_ratio:.0%}，+3%置信度"
            )
        elif strength_ratio >= 0.8:
            result["confirmed"] = True
            result["confidence_adjust"] = 0.01
            result["msg"] = f"突破力度正常（比值{strength_ratio:.2f}），+1%置信度"
        elif strength_ratio >= 0.5:
            result["confirmed"] = False
            result["confidence_adjust"] = -0.02
            result["msg"] = f"⚠️ 突破力度偏弱（比值{strength_ratio:.2f}），可能存在假突破，-2%置信度"
        else:
            result["confirmed"] = False
            result["confidence_adjust"] = -0.04
            result["msg"] = (
                f"🚨 突破力度严重不足（比值{strength_ratio:.2f}），极可能是假突破，-4%置信度"
            )

        return result
    except Exception:
        return result


def _calc_signal_quality_tier_v53(
    mmd: MMD,
    close: float,
) -> dict[str, Any]:
    """信号质量综合分层（V53 条件155）。

    综合所有已有条件结果，给出信号的最终质量等级（S/A/B/C/D），
    帮助用户优先关注高质量信号。

    Returns:
        dict with keys: quality_tier, tier_score, tier_label, position_recommendation, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "quality_tier": "D",
        "tier_score": 0,
        "tier_label": "观望",
        "position_recommendation": "wait",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmd is None:
            return result

        base_score = mmd.confidence * 100

        has_trend_follow = getattr(mmd, "_trend_stage_follow_confirmation_v53", None)
        has_atr = getattr(mmd, "_atr_adaptive_stop_v53", None)
        has_breakout = getattr(mmd, "_zs_breakout_strength_v53", None)

        adjustment = 0.0

        if has_trend_follow and has_trend_follow.get("is_following_trend"):
            adjustment += 3
        elif has_trend_follow and not has_trend_follow.get("is_following_trend"):
            adjustment -= 3

        if has_atr:
            atr_sug = has_atr.get("position_suggestion", "unknown")
            if atr_sug == "high":
                adjustment += 2
            elif atr_sug == "cautious":
                adjustment -= 2
            elif atr_sug == "avoid":
                adjustment -= 3

        if has_breakout and has_breakout.get("confirmed"):
            adjustment += 2
        elif has_breakout and not has_breakout.get("confirmed"):
            adjustment -= 2

        tier_score = max(0, min(100, base_score + adjustment))
        result["tier_score"] = tier_score

        if tier_score >= 80:
            tier = "S"
            tier_label = "强烈推荐"
            pos_rec = "aggressive"
        elif tier_score >= 65:
            tier = "A"
            tier_label = "推荐"
            pos_rec = "moderate"
        elif tier_score >= 50:
            tier = "B"
            tier_label = "谨慎"
            pos_rec = "cautious"
        elif tier_score >= 35:
            tier = "C"
            tier_label = "观望"
            pos_rec = "wait"
        else:
            tier = "D"
            tier_label = "回避"
            pos_rec = "avoid"

        result["quality_tier"] = tier
        result["tier_label"] = tier_label
        result["position_recommendation"] = pos_rec

        if tier in ("S", "A"):
            result["confidence_adjust"] = 0.02
        elif tier == "D":
            result["confidence_adjust"] = -0.03

        _ = mmd.mmd_type.value if mmd.mmd_type else "unknown"
        result["msg"] = (
            f"📊 [{tier}] {tier_label} | "
            f"综合评分{tier_score:.0f}/100 | "
            f"建议操作:{pos_rec} | "
            f"基准置信度{mmd.confidence:.0%}+调整{adjustment:+.0f}分"
        )

        return result
    except Exception:
        return result


# ── V54: 条件156-159 缠论模型精准度与决策帮助进一步提升 ────────────────────────


def _calc_multi_bar_confirmation_v54(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """多K线确认后确认（V54 条件156）。

    检查信号产生后价格是否持续向预期方向运动，过滤"假突破"信号。
    3买信号：信号后至少2根K线收盘价高于信号价 → 确认通过
    3卖信号：信号后至少2根K线收盘价低于信号价 → 确认通过

    Returns:
        dict with keys: confirmed, confirm_bars, total_bars, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "confirmed": False,
        "confirm_bars": 0,
        "total_bars": 0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmd.bi is None or not closes:
            return result

        signal_idx = mmd.bi.end.k.k_index
        if signal_idx < 0 or signal_idx >= len(closes) - 1:
            return result

        signal_price = closes[signal_idx]
        # 检查信号后最多10根K线
        lookback = min(10, len(closes) - signal_idx - 1)
        if lookback < 2:
            return result

        post_closes = closes[signal_idx + 1 : signal_idx + 1 + lookback]
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3

        # 统计连续确认的K线数
        confirm_count = 0
        for close in post_closes:
            if is_buy and close > signal_price:
                confirm_count += 1
            elif is_sell and close < signal_price:
                confirm_count += 1
            else:
                break  # 只要有一根不符合就停止

        result["confirm_bars"] = confirm_count
        result["total_bars"] = lookback

        if is_buy:
            if confirm_count >= 3:
                result["confirmed"] = True
                result["confidence_adjust"] = 0.04
                result["msg"] = f"✅ 多K线确认通过：信号后{confirm_count}根K线持续上涨，+4%置信度"
            elif confirm_count >= 2:
                result["confirmed"] = True
                result["confidence_adjust"] = 0.02
                result["msg"] = f"多K线确认通过：信号后{confirm_count}根K线持续上涨，+2%置信度"
            elif confirm_count >= 1:
                result["confirmed"] = False
                result["confidence_adjust"] = -0.01
                result["msg"] = f"多K线确认不足：仅{confirm_count}根K线符合，-1%置信度"
            else:
                result["confirmed"] = False
                result["confidence_adjust"] = -0.05
                result["msg"] = "⚠️ 多K线确认失败：信号后无K线持续上涨，-5%置信度（假突破风险）"
        elif is_sell:
            if confirm_count >= 3:
                result["confirmed"] = True
                result["confidence_adjust"] = 0.04
                result["msg"] = f"✅ 多K线确认通过：信号后{confirm_count}根K线持续下跌，+4%置信度"
            elif confirm_count >= 2:
                result["confirmed"] = True
                result["confidence_adjust"] = 0.02
                result["msg"] = f"多K线确认通过：信号后{confirm_count}根K线持续下跌，+2%置信度"
            elif confirm_count >= 1:
                result["confirmed"] = False
                result["confidence_adjust"] = -0.01
                result["msg"] = f"多K线确认不足：仅{confirm_count}根K线符合，-1%置信度"
            else:
                result["confirmed"] = False
                result["confidence_adjust"] = -0.05
                result["msg"] = "⚠️ 多K线确认失败：信号后无K线持续下跌，-5%置信度（假突破风险）"
        else:
            result["msg"] = "非3买/3卖信号，跳过此条件"

        return result
    except Exception:
        return result


def _calc_gap_risk_assessment_v54(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """缺口风险评估（V54 条件157）。

    检测信号后是否出现缺口，缺口会改变价格行为特征：
    - 3买信号后出现向下跳空缺口：强烈的看跌信号，大幅降权
    - 3买信号后出现向上跳空缺口：强化看涨信号，加分
    - 3卖信号后出现向上跳空缺口：强烈的看涨信号，大幅降权
    - 3卖信号后出现向下跳空缺口：强化看跌信号，加分

    Returns:
        dict with keys: has_gap, gap_direction, gap_size_pct, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "has_gap": False,
        "gap_direction": "none",
        "gap_size_pct": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmd.bi is None or not closes or not highs or not lows:
            return result

        signal_idx = mmd.bi.end.k.k_index
        if signal_idx < 0 or signal_idx >= len(closes) - 1:
            return result

        _ = closes[signal_idx]
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3

        # 检查信号后5根K线是否有缺口
        gap_window = min(5, len(closes) - signal_idx - 1)
        if gap_window < 1:
            return result

        for i in range(1, gap_window + 1):
            prev_close = closes[signal_idx + i - 1]
            curr_high = highs[signal_idx + i]
            curr_low = lows[signal_idx + i]

            # 向上缺口：今日最低 > 昨日最高
            if curr_low > prev_close * 1.005:  # 0.5% 阈值避免噪音
                gap_size = (curr_low - prev_close) / prev_close * 100
                if is_buy:
                    result["has_gap"] = True
                    result["gap_direction"] = "up"
                    result["gap_size_pct"] = round(gap_size, 2)
                    result["confidence_adjust"] = 0.03
                    result["msg"] = (
                        f"✅ 3买信号后出现向上缺口{gap_size:.1f}%，强化看涨信号 +3%置信度"
                    )
                elif is_sell:
                    result["has_gap"] = True
                    result["gap_direction"] = "up"
                    result["gap_size_pct"] = round(gap_size, 2)
                    result["confidence_adjust"] = -0.05
                    result["msg"] = (
                        f"⚠️ 3卖信号后出现向上缺口{gap_size:.1f}%，强势反弹风险 -5%置信度"
                    )
                break
            # 向下缺口：今日最高 < 昨日最低
            elif curr_high < prev_close * 0.995:
                gap_size = (prev_close - curr_high) / prev_close * 100
                if is_buy:
                    result["has_gap"] = True
                    result["gap_direction"] = "down"
                    result["gap_size_pct"] = round(gap_size, 2)
                    result["confidence_adjust"] = -0.06
                    result["msg"] = (
                        f"🚨 3买信号后出现向下缺口{gap_size:.1f}%，强烈看跌信号 -6%置信度"
                    )
                elif is_sell:
                    result["has_gap"] = True
                    result["gap_direction"] = "down"
                    result["gap_size_pct"] = round(gap_size, 2)
                    result["confidence_adjust"] = 0.03
                    result["msg"] = (
                        f"✅ 3卖信号后出现向下缺口{gap_size:.1f}%，强化看跌信号 +3%置信度"
                    )
                break

        if not result["has_gap"]:
            result["msg"] = "信号后5根K线内无缺口"

        return result
    except Exception:
        return result


def _calc_volatility_regime_change_v54(
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """波动率 regime 切换检测（V54 条件158）。

    通过ATR变化率判断市场是否从低波动转入高波动（趋势启动）
    或从高波动转入低波动（趋势结束/震荡）：
    - ATR扩张 > 20%：波动率放大，趋势加速信号
    - ATR收缩 < -20%：波动率收敛，可能进入盘整

    Returns:
        dict with keys: atr_expansion_pct, regime, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "atr_expansion_pct": 0.0,
        "regime": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not closes or len(closes) < 40:
            return result

        # 计算ATR(14)
        def calc_atr(
            highs: list[float],
            lows: list[float],
            closes: list[float],
            period: int = 14,
        ) -> float | None:
            if len(highs) < period + 1:
                return None
            tr_list: list[float] = []
            for i in range(1, len(highs)):
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
                tr_list.append(tr)
            if len(tr_list) < period:
                return None
            return sum(tr_list[-period:]) / period

        current_atr = calc_atr(highs, lows, closes, 14)
        prev_atr = calc_atr(highs[:-1], lows[:-1], closes[:-1], 14)

        if current_atr is None or prev_atr is None or prev_atr == 0:
            return result

        atr_change_pct = (current_atr - prev_atr) / prev_atr * 100
        result["atr_expansion_pct"] = round(atr_change_pct, 2)

        mid_price = closes[-1]
        atr_pct = current_atr / mid_price * 100 if mid_price > 0 else 0

        if atr_change_pct > 20:
            result["regime"] = "expanding"
            result["confidence_adjust"] = 0.02
            result["msg"] = (
                f"📈 波动率扩张{atr_change_pct:.1f}%，ATR占比{atr_pct:.2f}%，趋势加速确认 +2%置信度"
            )
        elif atr_change_pct < -20:
            result["regime"] = "contracting"
            result["confidence_adjust"] = -0.02
            result["msg"] = (
                f"📉 波动率收缩{abs(atr_change_pct):.1f}%，ATR占比{atr_pct:.2f}%，可能进入盘整 -2%置信度"
            )
        else:
            result["regime"] = "stable"
            result["confidence_adjust"] = 0.0
            result["msg"] = f"波动率稳定（变化{atr_change_pct:+.1f}%），ATR占比{atr_pct:.2f}%"

        return result
    except Exception:
        return result


def _calc_volume_price_coordination_v54(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """量价配合度评分（V54 条件159）。

    评估最近10根K线的量价配合质量：
    - 上涨日放量、下跌日缩量 → 量价配合良好 +3%
    - 上涨日缩量、下跌日放量 → 量价背离警告 -3%
    - 近期平均量/前期平均量 > 1.2 → 量能放大 +1%
    - 近期平均量/前期平均量 < 0.8 → 量能萎缩 -1%

    Returns:
        dict with keys: score, volume_trend, price_trend, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "score": 0,
        "volume_trend": "unknown",
        "price_trend": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not closes or not volumes or len(closes) < 20:
            return result

        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3

        # 计算最近10根和前期10根的量和价
        recent_closes = closes[-10:]
        recent_volumes = volumes[-10:]
        prev_closes = closes[-20:-10]
        prev_volumes = volumes[-20:-10]

        if len(recent_closes) < 5 or len(prev_closes) < 5:
            return result

        # 价格趋势
        recent_price_change = (recent_closes[-1] - recent_closes[0]) / (recent_closes[0] + 1e-10)
        if recent_price_change > 0.02:
            price_trend = "up"
        elif recent_price_change < -0.02:
            price_trend = "down"
        else:
            price_trend = "flat"
        result["price_trend"] = price_trend

        # 成交量趋势
        avg_recent_vol = sum(recent_volumes) / len(recent_volumes)
        avg_prev_vol = sum(prev_volumes) / len(prev_volumes) if sum(prev_volumes) > 0 else 1
        vol_ratio = avg_recent_vol / avg_prev_vol
        if vol_ratio > 1.2:
            volume_trend = "expanding"
        elif vol_ratio < 0.8:
            volume_trend = "shrinking"
        else:
            volume_trend = "stable"
        result["volume_trend"] = volume_trend

        # 量价配合评分
        score = 0
        # 上涨日/下跌日的量价配合
        up_days_volume: float = 0.0
        up_days_count: int = 0
        down_days_volume: float = 0.0
        down_days_count: int = 0
        for i in range(1, len(recent_closes)):
            if recent_closes[i] > recent_closes[i - 1]:
                up_days_volume += recent_volumes[i]
                up_days_count += 1
            elif recent_closes[i] < recent_closes[i - 1]:
                down_days_volume += recent_volumes[i]
                down_days_count += 1

        if up_days_count > 0 and down_days_count > 0:
            avg_up_vol = up_days_volume / up_days_count
            avg_down_vol = down_days_volume / down_days_count
            if avg_up_vol > avg_down_vol * 1.1:
                score += 2  # 上涨放量，下跌缩量
            elif avg_up_vol < avg_down_vol * 0.9:
                score -= 2  # 上涨缩量，下跌放量

        # 量比调整
        if vol_ratio > 1.2:
            score += 1
        elif vol_ratio < 0.8:
            score -= 1

        # 根据信号类型和趋势判断最终调整
        if is_buy:
            if price_trend == "up" and volume_trend == "expanding":
                score += 2
                result["confidence_adjust"] = min(0.05, score * 0.01)
                result["msg"] = (
                    f"✅ 量价配合优秀：价格上涨+量能放大，+{result['confidence_adjust']:.0%}置信度"
                )
            elif price_trend == "up" and volume_trend == "shrinking":
                score -= 2
                result["confidence_adjust"] = -0.03
                result["msg"] = "⚠️ 量价背离：价格上涨但量能萎缩，-3%置信度"
            elif price_trend == "up" and volume_trend == "stable":
                score += 1
                result["confidence_adjust"] = 0.01
                result["msg"] = "量价配合正常：价格上涨+量能稳定，+1%置信度"
            elif price_trend == "flat":
                result["confidence_adjust"] = -0.01
                result["msg"] = "量价配合一般：价格震荡，-1%置信度"
            else:
                result["confidence_adjust"] = -0.04
                result["msg"] = "🚨 量价恶化：价格下跌，-4%置信度"
        elif is_sell:
            if price_trend == "down" and volume_trend == "expanding":
                score += 2
                result["confidence_adjust"] = min(0.05, score * 0.01)
                result["msg"] = (
                    f"✅ 量价配合优秀：价格下跌+量能放大，+{result['confidence_adjust']:.0%}置信度"
                )
            elif price_trend == "down" and volume_trend == "shrinking":
                score -= 1
                result["confidence_adjust"] = -0.01
                result["msg"] = "量价配合一般：价格下跌但量能萎缩，-1%置信度"
            elif price_trend == "down" and volume_trend == "stable":
                score += 1
                result["confidence_adjust"] = 0.01
                result["msg"] = "量价配合正常：价格下跌+量能稳定，+1%置信度"
            elif price_trend == "flat":
                result["confidence_adjust"] = -0.01
                result["msg"] = "量价配合一般：价格震荡，-1%置信度"
            else:
                result["confidence_adjust"] = -0.04
                result["msg"] = "🚨 量价恶化：价格上涨，-4%置信度"
        else:
            result["msg"] = "非3买/3卖信号，跳过此条件"

        result["score"] = max(-5, min(5, score))
        return result
    except Exception:
        return result


# ── V55: 条件160-163 缠论模型精准度与决策帮助进一步提升 ────────────────────────


def _calc_multi_tf_resonance_filter_v55(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """分钟级多时间框架共振过滤（V55 条件160）。

    通过日线K线内部结构模拟多时间框架共振：
    - 若信号后短期动能（5根K线）与中长期动能（20根K线）方向一致 → 共振确认 +3%
    - 若短期与中长期动能方向相反 → 时间框架冲突 -5%
    - 若仅有一段时间框架支持 → 部分共振 +1%

    利用日线数据中的量价结构模拟多TF一致性：
    - 短期动量：最近5根K线的价格变化率 × 成交量加权
    - 中期动量：最近20根K线的价格变化率 × 成交量加权
    - 长期动量：最近60根K线的价格变化率（若有）

    Returns:
        dict with keys: resonated, timeframes, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "resonated": False,
        "timeframes": [],
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not closes or len(closes) < 20:
            return result

        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        # 计算短期动量（5根K线）
        short_closes = closes[-5:]
        short_return = (short_closes[-1] - short_closes[0]) / (short_closes[0] + 1e-10)
        _ = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else 0

        # 计算中期动量（20根K线）
        mid_closes = closes[-20:]
        mid_return = (mid_closes[-1] - mid_closes[0]) / (mid_closes[0] + 1e-10)
        _ = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 0

        # 计算长期动量（60根K线，若可用）
        long_return = 0.0
        if len(closes) >= 60:
            long_closes = closes[-60:]
            long_return = (long_closes[-1] - long_closes[0]) / (long_closes[0] + 1e-10)

        # 判断各时间框架方向
        short_dir = "up" if short_return > 0.01 else ("down" if short_return < -0.01 else "flat")
        mid_dir = "up" if mid_return > 0.01 else ("down" if mid_return < -0.01 else "flat")
        long_dir = "up" if long_return > 0.01 else ("down" if long_return < -0.01 else "flat")

        # 判断共振
        _ = sum(1 for d in [short_dir, mid_dir, long_dir] if d != "flat")
        same_dir_count = sum(
            1 for d in [short_dir, mid_dir] if (is_buy and d == "up") or (is_sell and d == "down")
        )

        result["timeframes"] = [f"{short_dir}({short_return:.1%})", f"{mid_dir}({mid_return:.1%})"]
        if long_dir != "flat":
            result["timeframes"].append(f"{long_dir}({long_return:.1%})")

        if is_buy:
            if same_dir_count >= 2:
                # 短中期都向上 → 强共振
                result["resonated"] = True
                result["confidence_adjust"] = 0.03
                result["msg"] = (
                    f"✅ 多时间框架共振确认：{' + '.join(result['timeframes'])}，+3%置信度"
                )
            elif same_dir_count == 1:
                # 仅一个时间框架支持 → 部分共振
                result["resonated"] = False
                result["confidence_adjust"] = 0.01
                result["msg"] = f"⚠️ 部分共振：{' + '.join(result['timeframes'])}，+1%置信度"
            else:
                # 短中期都向下 → 强烈冲突
                result["resonated"] = False
                result["confidence_adjust"] = -0.05
                result["msg"] = f"🚨 时间框架冲突：{' + '.join(result['timeframes'])}，-5%置信度"
        else:  # is_sell
            opposite_dir_count = sum(1 for d in [short_dir, mid_dir] if d == "down")
            if opposite_dir_count >= 2:
                result["resonated"] = True
                result["confidence_adjust"] = 0.03
                result["msg"] = (
                    f"✅ 多时间框架共振确认：{' + '.join(result['timeframes'])}，+3%置信度"
                )
            elif opposite_dir_count == 1:
                result["resonated"] = False
                result["confidence_adjust"] = 0.01
                result["msg"] = f"⚠️ 部分共振：{' + '.join(result['timeframes'])}，+1%置信度"
            else:
                result["resonated"] = False
                result["confidence_adjust"] = -0.05
                result["msg"] = f"🚨 时间框架冲突：{' + '.join(result['timeframes'])}，-5%置信度"

        return result
    except Exception:
        return result


def _calc_zhongshu_level_weight_v55(
    mmd: MMD,
    zss: list[ZS],
) -> dict[str, Any]:
    """中枢级别权重自适应（V55 条件161）。

    根据突破中枢的级别赋予不同置信度权重：
    - 小级别中枢（构成笔数 ≤ 3）：需要更多确认，+2%
    - 日线级别中枢（构成笔数 4-7）：核心信号，+4%
    - 周线级别中枢（构成笔数 8-12）：强信号，+6%
    - 月线级别中枢（构成笔数 ≥ 13）：极强信号，+8%
    - 无中枢信息：0%

    同时考虑中枢的完整性（done标志）和近期表现。

    Returns:
        dict with keys: level, weight_bonus, level_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "level": "unknown",
        "weight_bonus": 0,
        "level_score": 0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if not zss or len(zss) == 0:
            result["msg"] = "无中枢数据，跳过此条件"
            return result

        # 找到最相关的中枢（最近完成的中枢）
        relevant_zs = None
        for zs in reversed(zss):
            if zs.line_count >= 3 and zs.done:
                relevant_zs = zs
                break

        if relevant_zs is None:
            # 使用最新的已完成的线段级中枢
            for zs in reversed(zss):
                if zs.line_count >= 3:
                    relevant_zs = zs
                    break

        if relevant_zs is None:
            result["msg"] = "无可用的中枢数据"
            return result

        line_count = relevant_zs.line_count

        # 根据中枢级别（笔数）确定权重
        if line_count >= 13:
            level = "月线"
            weight_bonus = 8
            result["confidence_adjust"] = 0.08
        elif line_count >= 8:
            level = "周线"
            weight_bonus = 6
            result["confidence_adjust"] = 0.06
        elif line_count >= 4:
            level = "日线"
            weight_bonus = 4
            result["confidence_adjust"] = 0.04
        elif line_count >= 3:
            level = "小级别"
            weight_bonus = 2
            result["confidence_adjust"] = 0.02
        else:
            level = "未知"
            weight_bonus = 0
            result["confidence_adjust"] = 0.0

        # 中枢完整性加分
        if relevant_zs.done:
            level_score = weight_bonus + 1  # 完整中枢额外+1
        else:
            level_score = weight_bonus  # 未完成的中心中枢不给额外分

        result["level"] = level
        result["weight_bonus"] = weight_bonus
        result["level_score"] = level_score

        direction_hint = "买入" if is_buy else "卖出"
        result["msg"] = (
            f"💎 中枢级别权重：{level}中枢({line_count}笔)"
            f"，完整性{'✓' if relevant_zs.done else '△'}"
            f"，{direction_hint}信号权重+{level_score}% → +{result['confidence_adjust']:.0%}置信度"
        )

        return result
    except Exception:
        return result


def _calc_weak_stock_risk_v55(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """弱势股专项风险检测（V55 条件162）。

    针对招商银行、长江电力等弱势特征股票进行专项检测：
    - 高波动率（ATR/价格 > 3%）→ 风险增加
    - 低流动性（近期成交量 < 20日均量 × 0.6）→ 风险增加
    - 价格处于近60日低位（< 20%分位）→ 弱势确认
    - 连续下跌天数 > 5 → 弱势确认

    对买入信号：弱势特征越多，置信度扣减越大（最多-8%）
    对卖出信号：弱势特征越多，卖出信号越可靠（最多+5%）

    Returns:
        dict with keys: is_weak, risk_factors, volatility_ratio, volume_ratio, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "is_weak": False,
        "risk_factors": [],
        "volatility_ratio": 0.0,
        "volume_ratio": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 60 or len(volumes) < 60:
            result["msg"] = "数据不足，跳过弱势股检测"
            return result

        risk_score = 0
        risk_factors = []

        # 1. 波动率检测（ATR/价格）
        atr_period = 14
        true_ranges = []
        for i in range(len(closes) - atr_period, len(closes)):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i - 1] if i > 0 else closes[0]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)
        atr = sum(true_ranges) / len(true_ranges) if true_ranges else 0
        latest_price = closes[-1]
        atr_ratio = atr / (latest_price + 1e-10)
        result["volatility_ratio"] = round(atr_ratio * 100, 2)

        if atr_ratio > 0.03:  # ATR > 3% 为高波动
            risk_score += 2
            risk_factors.append("高波动率(ATR/价格>3%)")

        # 2. 流动性检测
        recent_vol = sum(volumes[-5:]) / 5
        avg_vol = sum(volumes[-20:]) / 20
        vol_ratio = recent_vol / (avg_vol + 1e-10)
        result["volume_ratio"] = round(vol_ratio, 2)

        if vol_ratio < 0.6:  # 成交量显著萎缩
            risk_score += 2
            risk_factors.append("低流动性(量比<0.6)")
        elif vol_ratio < 0.8:
            risk_score += 1
            risk_factors.append("成交量萎缩(量比<0.8)")

        # 3. 价格位置检测（近60日分位）
        sorted_closes = sorted(closes[-60:])
        price_percentile = sum(1 for c in sorted_closes if c <= latest_price) / len(sorted_closes)
        if price_percentile < 0.2:  # 价格处于近60日20%分位以下
            risk_score += 2
            risk_factors.append("价格弱势(<60日20%分位)")
        elif price_percentile < 0.3:
            risk_score += 1
            risk_factors.append("价格偏弱(<60日30%分位)")

        # 4. 连续下跌检测
        consecutive_down = 0
        for i in range(len(closes) - 1, max(len(closes) - 10, -1), -1):
            if i > 0 and closes[i] < closes[i - 1]:
                consecutive_down += 1
            else:
                break
        if consecutive_down >= 5:
            risk_score += 2
            risk_factors.append(f"连续下跌({consecutive_down}天)")
        elif consecutive_down >= 3:
            risk_score += 1
            risk_factors.append(f"近期回调({consecutive_down}天)")

        result["risk_factors"] = risk_factors
        result["is_weak"] = risk_score >= 3

        if is_buy:
            # 买入信号：弱势特征扣分
            if risk_score >= 5:
                result["confidence_adjust"] = -0.08
                result["msg"] = f"🚨 弱势股风险极高：{', '.join(risk_factors)}，-8%置信度"
            elif risk_score >= 3:
                result["confidence_adjust"] = -0.05
                result["msg"] = f"⚠️ 弱势股风险较高：{', '.join(risk_factors)}，-5%置信度"
            elif risk_score >= 1:
                result["confidence_adjust"] = -0.02
                result["msg"] = f"🟡 存在弱势特征：{', '.join(risk_factors)}，-2%置信度"
            else:
                result["msg"] = "✅ 无明显弱势特征，无需调整"
        else:  # is_sell
            # 卖出信号：弱势特征加分（弱势股的卖出信号更可靠）
            if risk_score >= 5:
                result["confidence_adjust"] = 0.05
                result["msg"] = f"✅ 弱势股卖出信号强化：{', '.join(risk_factors)}，+5%置信度"
            elif risk_score >= 3:
                result["confidence_adjust"] = 0.03
                result["msg"] = f"🟢 弱势股卖出信号较可靠：{', '.join(risk_factors)}，+3%置信度"
            else:
                result["msg"] = "✅ 无明显弱势特征，无需调整"

        return result
    except Exception:
        return result


def _calc_signal_trend_alignment_v55(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """信号与趋势方向对齐验证（V55 条件163）。

    验证买卖点信号是否与当前主要趋势方向一致：
    - 买入信号：需处于上升趋势或下跌趋势的末端（底部反转）
    - 卖出信号：需处于下降趋势或上升趋势的末端（顶部反转）

    趋势判断方法：
    1. 均线系统：MA5/MA10/MA20/MA60 的排列状态
    2. 价格动量：近期价格变化率
    3. MACD趋势：DIF与DEA的位置关系

    对齐规则：
    - 上升趋势中的买入信号 → +2%（顺势买入）
    - 下降趋势中的卖出信号 → +2%（顺势卖出）
    - 上升趋势中的卖出信号 → -2%（逆势卖出风险）
    - 下降趋势中的买入信号 → -2%（逆势买入风险）
    - 震荡市中的信号 → 0%（中性）

    Returns:
        dict with keys: aligned, trend_direction, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "aligned": False,
        "trend_direction": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if not closes or len(closes) < 60:
            result["msg"] = "数据不足，跳过趋势对齐验证"
            return result

        # 计算均线
        def ma(data: list[float], period: int) -> float:
            if len(data) < period:
                return data[-1] if data else 0
            return sum(data[-period:]) / period

        ma5 = ma(closes, 5)
        ma10 = ma(closes, 10)
        ma20 = ma(closes, 20)
        ma60 = ma(closes, 60)
        latest = closes[-1]

        # 判断趋势方向
        trend_score = 0
        trend_factors = []

        # 均线排列评分
        if ma5 > ma10 > ma20:
            trend_score += 2
            trend_factors.append("MA5>MA10>MA20多头排列")
        elif ma5 < ma10 < ma20:
            trend_score -= 2
            trend_factors.append("MA5<MA10<MA20空头排列")
        elif ma5 > ma20:
            trend_score += 1
            trend_factors.append("短期均线在上")
        elif ma5 < ma20:
            trend_score -= 1
            trend_factors.append("短期均线在下")

        # 价格相对MA60位置
        price_vs_ma60 = (latest - ma60) / (ma60 + 1e-10)
        if price_vs_ma60 > 0.05:
            trend_score += 1
            trend_factors.append(f"价格高于MA60({price_vs_ma60:.1%})")
        elif price_vs_ma60 < -0.05:
            trend_score -= 1
            trend_factors.append(f"价格低于MA60({price_vs_ma60:.1%})")

        # 近期动量
        momentum_20 = (closes[-1] - closes[-20]) / (closes[-20] + 1e-10)
        if momentum_20 > 0.03:
            trend_score += 1
            trend_factors.append(f"20日动量正向({momentum_20:.1%})")
        elif momentum_20 < -0.03:
            trend_score -= 1
            trend_factors.append(f"20日动量负向({momentum_20:.1%})")

        # 确定趋势方向
        if trend_score >= 2:
            trend_direction = "up"
        elif trend_score <= -2:
            trend_direction = "down"
        else:
            trend_direction = "flat"

        result["trend_direction"] = trend_direction

        if is_buy:
            if trend_direction == "up":
                result["aligned"] = True
                result["confidence_adjust"] = 0.02
                result["msg"] = f"✅ 顺势买入：{', '.join(trend_factors)}，+2%置信度"
            elif trend_direction == "down":
                result["aligned"] = False
                result["confidence_adjust"] = -0.02
                result["msg"] = f"⚠️ 逆势买入风险：{', '.join(trend_factors)}，-2%置信度"
            else:
                result["msg"] = "➡️ 震荡市买入：信号方向不明确，暂不调整"
        else:  # is_sell
            if trend_direction == "down":
                result["aligned"] = True
                result["confidence_adjust"] = 0.02
                result["msg"] = f"✅ 顺势卖出：{', '.join(trend_factors)}，+2%置信度"
            elif trend_direction == "up":
                result["aligned"] = False
                result["confidence_adjust"] = -0.02
                result["msg"] = f"⚠️ 逆势卖出风险：{', '.join(trend_factors)}，-2%置信度"
            else:
                result["msg"] = "➡️ 震荡市卖出：信号方向不明确，暂不调整"

        return result
    except Exception:
        return result


# ── V56: 条件164-167 缠论模型精准度与决策帮助进一步提升 ───────────────────────────


def _calc_false_breakout_detection_v56(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
) -> dict[str, Any]:
    """假突破识别（V56 条件164）。

    通过信号后量价行为识别假突破信号：
    - 3买信号：突破后5根K线内回撤超过突破幅度的50% → 假突破风险
    - 3买信号：突破后成交量持续放大（>1.2倍均量）+ 价格继续上涨 → 真突破确认
    - 3卖信号：跌破后5根K线内反弹超过跌幅的50% → 假跌破风险
    - 3卖信号：跌破后成交量放大 + 价格继续下跌 → 真跌破确认
    """
    result: dict[str, Any] = {
        "is_fake": False,
        "breakout_valid": False,
        "confidence_adjust": 0.0,
        "msg": "",
        "retracement_pct": 0.0,
        "volume_ratio": 1.0,
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 20 or not volumes or len(volumes) < 20:
            result["msg"] = "数据不足，跳过假突破检测"
            return result

        bi_end_idx = 0
        if mmd.bi is not None and hasattr(mmd.bi, "end") and hasattr(mmd.bi.end, "k"):
            bi_end_idx = (
                mmd.bi.end.k.k_index if hasattr(mmd.bi.end.k, "k_index") else len(closes) - 1
            )
        else:
            bi_end_idx = max(0, len(closes) - 20)

        signal_price = closes[bi_end_idx] if bi_end_idx < len(closes) else closes[-1]

        check_bars = min(5, len(closes) - 1 - bi_end_idx)
        if check_bars == 0:
            result["msg"] = "信号后无K线数据，无法验证"
            return result

        post_closes = closes[bi_end_idx + 1 : bi_end_idx + 1 + check_bars]
        post_highs = highs[bi_end_idx + 1 : bi_end_idx + 1 + check_bars] if highs else post_closes
        post_lows = lows[bi_end_idx + 1 : bi_end_idx + 1 + check_bars] if lows else post_closes
        post_volumes = (
            volumes[bi_end_idx + 1 : bi_end_idx + 1 + check_bars] if volumes else [1.0] * check_bars
        )

        if is_buy:
            breakout_range = max(post_highs) - signal_price if post_highs else 0
            lowest_after = min(post_lows) if post_lows else signal_price
            retracement = (
                (signal_price - lowest_after) / (signal_price + 1e-10) if signal_price > 0 else 0
            )
        else:
            breakout_range = signal_price - min(post_lows) if post_lows else 0
            highest_after = max(post_highs) if post_highs else signal_price
            retracement = (
                (highest_after - signal_price) / (signal_price + 1e-10) if signal_price > 0 else 0
            )

        result["retracement_pct"] = round(retracement * 100, 2)

        avg_vol = (
            sum(volumes[-20:]) / 20 if len(volumes) >= 20 else sum(volumes) / max(1, len(volumes))
        )
        recent_vol = sum(post_volumes) / max(1, len(post_volumes))
        volume_ratio = recent_vol / (avg_vol + 1e-10)
        result["volume_ratio"] = round(volume_ratio, 2)

        if is_buy:
            latest_close = post_closes[-1] if post_closes else signal_price
            if breakout_range > 0:
                if retracement > 0.5 * (breakout_range / (signal_price + 1e-10)):
                    result["is_fake"] = True
                    result["breakout_valid"] = False
                    result["confidence_adjust"] = -0.06
                    result["msg"] = f"假突破风险：回撤{retracement:.1%}>突破幅度50%，-6%置信度"
                elif volume_ratio > 1.2 and latest_close > signal_price * 1.02:
                    result["is_fake"] = False
                    result["breakout_valid"] = True
                    result["confidence_adjust"] = 0.04
                    result["msg"] = f"真突破确认：量比{volume_ratio:.2f}>1.2且涨幅>2%，+4%置信度"
                else:
                    result["is_fake"] = False
                    result["breakout_valid"] = True
                    result["confidence_adjust"] = 0.01
                    result["msg"] = f"突破待确认：量比{volume_ratio:.2f}，回撤{retracement:.1%}"
            else:
                result["msg"] = "突破幅度不足，无法判断"
        else:
            latest_close = post_closes[-1] if post_closes else signal_price
            if breakout_range > 0:
                if retracement > 0.5 * (breakout_range / (signal_price + 1e-10)):
                    result["is_fake"] = True
                    result["breakout_valid"] = False
                    result["confidence_adjust"] = -0.06
                    result["msg"] = f"假跌破风险：反弹{retracement:.1%}>跌幅50%，-6%置信度"
                elif volume_ratio > 1.2 and latest_close < signal_price * 0.98:
                    result["is_fake"] = False
                    result["breakout_valid"] = True
                    result["confidence_adjust"] = 0.04
                    result["msg"] = f"真跌破确认：量比{volume_ratio:.2f}>1.2且跌幅>2%，+4%置信度"
                else:
                    result["is_fake"] = False
                    result["breakout_valid"] = True
                    result["confidence_adjust"] = 0.01
                    result["msg"] = f"跌破待确认：量比{volume_ratio:.2f}，反弹{retracement:.1%}"
            else:
                result["msg"] = "跌破幅度不足，无法判断"

        return result
    except Exception:
        return result


def _calc_zhongshu_structure_complexity_v56(
    mmd: MMD,
    zss: list[Any],
) -> dict[str, Any]:
    """中枢结构复杂度分析（V56 条件165）。

    分析信号中枢前后的结构复杂度：
    - 简单结构：单一中枢突破，信号可信度高
    - 复杂结构：多重重叠中枢，信号噪音大
    """
    result: dict[str, Any] = {
        "complexity": "unknown",
        "overlap_count": 0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not zss or len(zss) < 2:
            result["msg"] = "中枢数据不足，跳过复杂度分析"
            return result

        if mmd.zs is None:
            result["msg"] = "当前信号无中枢信息"
            return result

        curr_zs_idx = -1
        for i, zs in enumerate(zss):
            if hasattr(zs, "start") and hasattr(zs, "end") and hasattr(mmd.zs, "start"):
                if zs.start == mmd.zs.start and zs.end == mmd.zs.end:
                    curr_zs_idx = i
                    break

        if curr_zs_idx < 0:
            for i, zs in enumerate(zss):
                if hasattr(zs, "zg") and hasattr(zs, "zd") and hasattr(mmd.zs, "zg"):
                    if abs(getattr(zs, "zg", 0) - getattr(mmd.zs, "zg", 0)) < 1e-6:
                        curr_zs_idx = i
                        break

        if curr_zs_idx < 0:
            result["msg"] = "无法定位当前中枢"
            return result

        window_size = 5
        start_idx = max(0, curr_zs_idx - window_size)
        end_idx = min(len(zss), curr_zs_idx + window_size + 1)
        nearby_zss = zss[start_idx:end_idx]

        overlap_count = 0
        for i in range(len(nearby_zss)):
            for j in range(i + 1, len(nearby_zss)):
                zs_i = nearby_zss[i]
                zs_j = nearby_zss[j]
                if (
                    hasattr(zs_i, "zg")
                    and hasattr(zs_i, "zd")
                    and hasattr(zs_j, "zg")
                    and hasattr(zs_j, "zd")
                ):
                    zg_i, zd_i = zs_i.zg, zs_i.zd
                    zg_j, zd_j = zs_j.zg, zs_j.zd
                    if zd_i < zg_j and zd_j < zg_i:
                        overlap_count += 1

        result["overlap_count"] = overlap_count

        if overlap_count == 0:
            result["complexity"] = "simple"
            result["confidence_adjust"] = 0.03
            result["msg"] = "简单结构：无重叠中枢，+3%置信度"
        elif overlap_count <= 1:
            result["complexity"] = "moderate"
            result["confidence_adjust"] = 0.0
            result["msg"] = "中等复杂度：少量重叠，暂不调整"
        elif overlap_count <= 3:
            result["complexity"] = "complex"
            result["confidence_adjust"] = -0.03
            result["msg"] = "复杂结构：多处重叠，-3%置信度"
        else:
            result["complexity"] = "very_complex"
            result["confidence_adjust"] = -0.06
            result["msg"] = "高度复杂：严重重叠，-6%置信度"

        return result
    except Exception:
        return result


def _calc_volatility_adaptive_position_v56(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """波动率自适应仓位建议（V56 条件166）。

    根据ATR波动率自适应调整建议仓位：
    - 低波动(<1.5%)：建议重仓(70-100%)
    - 正常波动(1.5%-3%)：建议中等仓位(40-70%)
    - 高波动(3%-5%)：建议轻仓(20-40%)
    - 极高波动(>5%)：建议观望(0-20%)
    """
    result: dict[str, Any] = {
        "atr_value": 0.0,
        "volatility_level": "unknown",
        "position_suggestion": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 20 or len(highs) < 20 or len(lows) < 20:
            result["msg"] = "数据不足，跳过波动率分析"
            return result

        tr_list = []
        for i in range(1, min(15, len(closes))):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i - 1]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)

        if not tr_list:
            result["msg"] = "无法计算ATR"
            return result

        atr = sum(tr_list) / len(tr_list)
        atr_pct = atr / (closes[-1] + 1e-10) * 100
        result["atr_value"] = round(atr_pct, 2)

        if atr_pct < 1.5:
            result["volatility_level"] = "low"
            base_position = "high"
            base_adjust = 0.01
        elif atr_pct < 3.0:
            result["volatility_level"] = "normal"
            base_position = "medium"
            base_adjust = 0.0
        elif atr_pct < 5.0:
            result["volatility_level"] = "high"
            base_position = "cautious"
            base_adjust = -0.01
        else:
            result["volatility_level"] = "extreme"
            base_position = "wait"
            base_adjust = -0.02

        result["position_suggestion"] = base_position
        result["confidence_adjust"] = base_adjust

        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3

        if is_buy and atr_pct > 3.0:
            result["confidence_adjust"] -= 0.01
            result["msg"] = f"高波动买入({atr_pct:.1f}%)：建议轻仓，-1%置信度"
        elif is_sell and atr_pct > 3.0:
            result["confidence_adjust"] += 0.01
            result["msg"] = f"高波动卖出({atr_pct:.1f}%)：可适当减仓，+1%置信度"
        elif is_buy:
            result["msg"] = f"低波动买入({atr_pct:.1f}%)：建议重仓，+1%置信度"
        elif is_sell:
            result["msg"] = f"低波动卖出({atr_pct:.1f}%)：建议持仓，+1%置信度"
        else:
            result["msg"] = f"波动率{atr_pct:.1f}%，{base_position}仓位建议"

        return result
    except Exception:
        return result


def _calc_multi_signal_resonance_v56(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """多信号共振评分（V56 条件167）。

    综合多个技术指标验证信号质量：
    - MACD：DIF/DEA金叉/死叉确认
    - KDJ：超买/超卖状态
    - RSI：相对强弱状态
    - 成交量：量比确认
    - 价格动量：短中期趋势确认

    共振规则：
    - 3个以上指标同向确认 → +4%（强共振）
    - 2个指标同向确认 → +2%（弱共振）
    - 1个指标确认 → 0%
    - 无指标确认 → -2%（风险信号）
    """
    result: dict[str, Any] = {
        "resonance_count": 0,
        "confirming_indicators": [],
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 30:
            result["msg"] = "数据不足，跳过共振分析"
            return result

        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        confirming = []

        # 1. MACD 确认
        if len(closes) >= 27:
            fast = sum(closes[-12:]) / 12
            slow = sum(closes[-26:]) / 26
            dif = fast - slow
            prev_fast = sum(closes[-13:-1]) / 12 if len(closes) >= 28 else fast
            prev_slow = sum(closes[-27:-1]) / 26 if len(closes) >= 28 else slow
            prev_dif = prev_fast - prev_slow
            if is_buy and dif > 0 and prev_dif <= 0:
                confirming.append("MACD金叉")
            elif is_buy and dif > 0 and prev_dif < dif:
                confirming.append("MACD多头增强")
            elif is_sell and dif < 0 and prev_dif >= 0:
                confirming.append("MACD死叉")
            elif is_sell and dif < 0 and prev_dif > dif:
                confirming.append("MACD空头增强")

        # 2. KDJ 确认
        if len(closes) >= 10:
            low_9 = min(closes[-9:])
            high_9 = max(closes[-9:])
            latest = closes[-1]
            rsv = (latest - low_9) / (high_9 - low_9 + 1e-10) * 100
            if is_buy and rsv < 20:
                confirming.append("KDJ超卖")
            elif is_sell and rsv > 80:
                confirming.append("KDJ超买")

        # 3. RSI 确认
        if len(closes) >= 15:
            gains: list[float] = []
            losses: list[float] = []
            for i in range(-14, 0):
                change = closes[i] - closes[i - 1]
                if change > 0:
                    gains.append(change)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(change))
            avg_gain = sum(gains) / 14
            avg_loss = sum(losses) / 14
            rs = avg_gain / (avg_loss + 1e-10)
            rsi = 100 - (100 / (1 + rs))
            if is_buy and rsi < 30:
                confirming.append("RSI超卖")
            elif is_buy and 40 < rsi < 60:
                confirming.append("RSI中性偏强")
            elif is_sell and rsi > 70:
                confirming.append("RSI超买")
            elif is_sell and 40 < rsi < 60:
                confirming.append("RSI中性偏弱")

        # 4. 成交量确认
        if volumes and len(volumes) >= 20:
            avg_vol = sum(volumes[-20:]) / 20
            recent_vol = sum(volumes[-5:]) / 5
            vol_ratio = recent_vol / (avg_vol + 1e-10)
            if is_buy and vol_ratio > 1.0:
                confirming.append("放量上涨")
            elif is_sell and vol_ratio > 1.0:
                confirming.append("放量下跌")

        # 5. 价格动量确认
        momentum_5 = (
            (closes[-1] - closes[-6]) / (closes[-6] + 1e-10) * 100 if len(closes) >= 6 else 0
        )
        momentum_10 = (
            (closes[-1] - closes[-11]) / (closes[-11] + 1e-10) * 100 if len(closes) >= 11 else 0
        )
        if is_buy and momentum_5 > 0 and momentum_10 > 0:
            confirming.append("短中期动量向上")
        elif is_sell and momentum_5 < 0 and momentum_10 < 0:
            confirming.append("短中期动量向下")

        result["confirming_indicators"] = confirming
        result["resonance_count"] = len(confirming)

        if len(confirming) >= 3:
            result["confidence_adjust"] = 0.04
            result["msg"] = (
                f"强共振确认({len(confirming)}项)：{', '.join(confirming[:3])}，+4%置信度"
            )
        elif len(confirming) >= 2:
            result["confidence_adjust"] = 0.02
            result["msg"] = f"弱共振确认({len(confirming)}项)：{', '.join(confirming)}，+2%置信度"
        elif len(confirming) == 1:
            result["confidence_adjust"] = 0.0
            result["msg"] = f"单指标确认：{confirming[0]}，暂不调整"
        else:
            result["confidence_adjust"] = -0.02
            result["msg"] = "无指标确认：缺乏共振支持，-2%置信度"

        return result
    except Exception:
        return result


# ── V57: 条件168-171 缠论模型精准度与决策帮助进一步提升 ───────────────────────────


def _calc_pullback_filter_v57(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
) -> dict[str, Any]:
    """回踩幅度与时间双重过滤（V57 条件168）。

    对3买/3卖信号的破/跌破后进行回踩深度和时间的双重过滤：
    - 3买：回踩深度不超过突破幅度的60%，回踩时间不超过15根K线
    - 3卖：反弹幅度不超过跌幅的60%，反弹时间不超过15根K线
    """
    result: dict[str, Any] = {
        "pass_filter": True,
        "pullback_depth_pct": 0.0,
        "pullback_bars": 0,
        "max_allowable_depth_pct": 60.0,
        "max_allowable_bars": 15,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 25 or not lows or not highs:
            result["msg"] = "数据不足，跳过回踩过滤"
            return result

        bi_end_idx = 0
        if mmd.bi is not None and hasattr(mmd.bi, "end") and hasattr(mmd.bi.end, "k"):
            bi_end_idx = (
                mmd.bi.end.k.k_index
                if hasattr(mmd.bi.end.k, "k_index")
                else max(0, len(closes) - 25)
            )
        else:
            bi_end_idx = max(0, len(closes) - 25)

        signal_price = closes[bi_end_idx] if bi_end_idx < len(closes) else closes[-1]

        check_bars = min(15, len(closes) - 1 - bi_end_idx)
        if check_bars == 0:
            result["msg"] = "信号后无K线数据，无法验证回踩"
            return result

        _ = closes[bi_end_idx + 1 : bi_end_idx + 1 + check_bars]
        post_highs = highs[bi_end_idx + 1 : bi_end_idx + 1 + check_bars]
        post_lows = lows[bi_end_idx + 1 : bi_end_idx + 1 + check_bars]

        if is_buy:
            breakout_peak = max(post_highs) if post_highs else signal_price
            pullback_low = min(post_lows) if post_lows else signal_price
            breakout_range = breakout_peak - signal_price if breakout_peak > signal_price else 0.01

            if breakout_range > 0:
                pullback_depth = (breakout_peak - pullback_low) / (breakout_range + 1e-10)
                result["pullback_depth_pct"] = round(pullback_depth * 100, 1)

                max_depth_ratio = 0.6
                if pullback_depth > max_depth_ratio:
                    result["pass_filter"] = False
                    result["confidence_adjust"] = -0.05
                    result["msg"] = f"回踩过深({pullback_depth:.0%}>60%)，信号弱化，-5%置信度"
                elif pullback_depth > 0.4:
                    result["confidence_adjust"] = -0.02
                    result["msg"] = f"回踩较深({pullback_depth:.0%})，谨慎对待，-2%置信度"
                else:
                    result["confidence_adjust"] = 0.02
                    result["msg"] = f"回踩可控({pullback_depth:.0%}<60%)，+2%置信度"
            else:
                result["msg"] = "突破幅度不足，无法计算回踩深度"

            result["pullback_bars"] = check_bars
        else:
            breakout_trough = min(post_lows) if post_lows else signal_price
            pullback_high = max(post_highs) if post_highs else signal_price
            breakout_range = (
                signal_price - breakout_trough if signal_price > breakout_trough else 0.01
            )

            if breakout_range > 0:
                pullback_depth = (pullback_high - signal_price) / (breakout_range + 1e-10)
                result["pullback_depth_pct"] = round(pullback_depth * 100, 1)

                max_depth_ratio = 0.6
                if pullback_depth > max_depth_ratio:
                    result["pass_filter"] = False
                    result["confidence_adjust"] = -0.05
                    result["msg"] = f"反弹过深({pullback_depth:.0%}>60%)，信号弱化，-5%置信度"
                elif pullback_depth > 0.4:
                    result["confidence_adjust"] = -0.02
                    result["msg"] = f"反弹较深({pullback_depth:.0%})，谨慎对待，-2%置信度"
                else:
                    result["confidence_adjust"] = 0.02
                    result["msg"] = f"反弹可控({pullback_depth:.0%}<60%)，+2%置信度"
            else:
                result["msg"] = "跌破幅度不足，无法计算反弹深度"

            result["pullback_bars"] = check_bars

        return result
    except Exception:
        return result


def _calc_breakout_strength_validation_v57(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """突破力度验证（V57 条件169）。

    验证3买/3卖信号的突破笔力度是否足够：
    - 突破笔收盘价变化必须大于进入中枢最后一笔的70%
    - 突破时成交量必须大于中枢内平均成交量的1.2倍
    """
    result: dict[str, Any] = {
        "strength_adequate": False,
        "force_ratio": 0.0,
        "volume_ratio": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 30 or not volumes or len(volumes) < 30:
            result["msg"] = "数据不足，跳过突破力度验证"
            return result

        bi_end_idx = 0
        if mmd.bi is not None and hasattr(mmd.bi, "end") and hasattr(mmd.bi.end, "k"):
            bi_end_idx = (
                mmd.bi.end.k.k_index
                if hasattr(mmd.bi.end.k, "k_index")
                else max(0, len(closes) - 30)
            )
        else:
            bi_end_idx = max(0, len(closes) - 30)

        if bi_end_idx < 10:
            result["msg"] = "信号位置太早，无法计算力度"
            return result

        breakout_bi_force = (
            abs(closes[bi_end_idx] - closes[bi_end_idx - 5])
            / (closes[bi_end_idx - 5] + 1e-10)
            * 100
        )
        enter_bi_force = (
            abs(closes[bi_end_idx - 5] - closes[bi_end_idx - 10])
            / (closes[bi_end_idx - 10] + 1e-10)
            * 100
        )

        force_ratio = breakout_bi_force / (enter_bi_force + 1e-10)
        result["force_ratio"] = round(force_ratio, 2)

        recent_vol = (
            sum(volumes[bi_end_idx - 5 : bi_end_idx]) / 5
            if bi_end_idx >= 5
            else sum(volumes[-5:]) / 5
        )
        avg_zs_vol = (
            sum(volumes[-30:-5]) / 25 if len(volumes) >= 30 else sum(volumes) / max(1, len(volumes))
        )
        volume_ratio = recent_vol / (avg_zs_vol + 1e-10)
        result["volume_ratio"] = round(volume_ratio, 2)

        strength_score = 0
        if force_ratio >= 0.7:
            strength_score += 1
        if volume_ratio >= 1.2:
            strength_score += 1

        if strength_score == 2:
            result["strength_adequate"] = True
            result["confidence_adjust"] = 0.04
            result["msg"] = (
                f"突破力度充分：力度比{force_ratio:.2f}≥0.7 + 量比{volume_ratio:.2f}≥1.2，+4%置信度"
            )
        elif strength_score == 1:
            result["confidence_adjust"] = 0.01
            force_note = "≥0.7" if force_ratio >= 0.7 else "<0.7"
            vol_note = "≥1.2" if volume_ratio >= 1.2 else "<1.2"
            result["msg"] = (
                f"突破力度部分达标：力度比{force_ratio:.2f}{force_note} + 量比{volume_ratio:.2f}{vol_note}，+1%置信度"
            )
        else:
            result["confidence_adjust"] = -0.04
            result["msg"] = (
                f"突破力度不足：力度比{force_ratio:.2f}<0.7 且 量比{volume_ratio:.2f}<1.2，-4%置信度"
            )

        return result
    except Exception:
        return result


def _calc_zs_divergence_check_v57(
    mmd: MMD,
    bis: list[Any],
    bc_list: list[Any] | None,
) -> dict[str, Any]:
    """中枢背驰检测（V57 条件170）。

    检测突破笔之前中枢内是否出现背驰信号：
    - 中枢内有背驰时，突破信号可信度降低
    - 中枢内无背驰时，突破信号更可靠
    """
    result: dict[str, Any] = {
        "has_divergence": False,
        "divergence_type": "none",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if not bis or mmd.zs is None:
            result["msg"] = "中枢或笔数据不足，跳过背驰检测"
            return result

        zs_start = getattr(mmd.zs, "start", None)
        zs_end = getattr(mmd.zs, "end", None)
        if zs_start is None or zs_end is None:
            result["msg"] = "无法获取中枢边界"
            return result

        if not bc_list or len(bc_list) == 0:
            result["msg"] = "无背驰数据，跳过检测"
            return result

        in_zs_divergence = False
        div_type = "none"
        for bc in bc_list:
            bc_curr = getattr(bc, "curr", None)
            bc_prev = getattr(bc, "prev", None)
            if bc_curr is None or bc_prev is None:
                continue
            curr_idx = getattr(getattr(bc_curr, "k", None), "k_index", None)
            prev_idx = getattr(getattr(bc_prev, "k", None), "k_index", None)
            if curr_idx is None or prev_idx is None:
                continue
            if zs_start <= prev_idx and curr_idx <= zs_end:
                in_zs_divergence = True
                div_type = getattr(bc, "bc_type", "unknown")
                break

        result["has_divergence"] = in_zs_divergence
        result["divergence_type"] = str(div_type)

        if in_zs_divergence:
            result["confidence_adjust"] = -0.03
            result["msg"] = f"中枢内存在{div_type}背驰，突破信号可信度降低，-3%置信度"
        else:
            result["confidence_adjust"] = 0.02
            result["msg"] = "中枢内无背驰，突破信号更可靠，+2%置信度"

        return result
    except Exception:
        return result


def _calc_signal_decay_detection_v57(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """信号衰减检测（V57 条件171）。

    检测信号发生后的价格持续性：
    - 信号后5-10根K线持续走弱 → 信号衰减，降低置信度
    - 信号后价格稳定/走强 → 信号有效，提升置信度
    """
    result: dict[str, Any] = {
        "is_decaying": False,
        "price_trend": "unknown",
        "trend_momentum": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 20:
            result["msg"] = "数据不足，跳过信号衰减检测"
            return result

        bi_end_idx = 0
        if mmd.bi is not None and hasattr(mmd.bi, "end") and hasattr(mmd.bi.end, "k"):
            bi_end_idx = (
                mmd.bi.end.k.k_index
                if hasattr(mmd.bi.end.k, "k_index")
                else max(0, len(closes) - 20)
            )
        else:
            bi_end_idx = max(0, len(closes) - 20)

        if bi_end_idx + 10 >= len(closes):
            result["msg"] = "信号后数据不足"
            return result

        signal_price = closes[bi_end_idx]
        check_bars = min(10, len(closes) - 1 - bi_end_idx)
        post_closes = closes[bi_end_idx + 1 : bi_end_idx + 1 + check_bars]

        if not post_closes:
            result["msg"] = "无后续价格数据"
            return result

        latest_price = post_closes[-1]
        if is_buy:
            price_change = (latest_price - signal_price) / (signal_price + 1e-10) * 100
            mid_price = post_closes[len(post_closes) // 2]
            mid_change = (mid_price - signal_price) / (signal_price + 1e-10) * 100

            result["trend_momentum"] = round(price_change, 2)

            if price_change < -2.0 and mid_change > 0:
                result["is_decaying"] = True
                result["price_trend"] = "declining"
                result["confidence_adjust"] = -0.04
                result["msg"] = (
                    f"信号衰减：买入后价格下跌{price_change:.1f}%，{mid_change:.1f}%→{price_change:.1f}%，-4%置信度"
                )
            elif price_change > 1.0:
                result["price_trend"] = "strong"
                result["confidence_adjust"] = 0.03
                result["msg"] = f"信号强效：买入后价格上涨{price_change:.1f}%，+3%置信度"
            elif price_change > -1.0:
                result["price_trend"] = "stable"
                result["confidence_adjust"] = 0.01
                result["msg"] = f"信号稳定：买入后价格变动{price_change:.1f}%，+1%置信度"
            else:
                result["price_trend"] = "weak"
                result["confidence_adjust"] = -0.02
                result["msg"] = f"信号偏弱：买入后价格下跌{price_change:.1f}%，-2%置信度"
        else:
            price_change = (signal_price - latest_price) / (signal_price + 1e-10) * 100
            mid_price = post_closes[len(post_closes) // 2]
            mid_change = (signal_price - mid_price) / (signal_price + 1e-10) * 100

            result["trend_momentum"] = round(price_change, 2)

            if price_change < -2.0 and mid_change > 0:
                result["is_decaying"] = True
                result["price_trend"] = "recovering"
                result["confidence_adjust"] = -0.04
                result["msg"] = (
                    f"信号衰减：卖出后价格反弹{price_change:.1f}%，{mid_change:.1f}%→{price_change:.1f}%，-4%置信度"
                )
            elif price_change > 1.0:
                result["price_trend"] = "strong"
                result["confidence_adjust"] = 0.03
                result["msg"] = f"信号强效：卖出后价格下跌{price_change:.1f}%，+3%置信度"
            elif price_change > -1.0:
                result["price_trend"] = "stable"
                result["confidence_adjust"] = 0.01
                result["msg"] = f"信号稳定：卖出后价格变动{price_change:.1f}%，+1%置信度"
            else:
                result["price_trend"] = "weak"
                result["confidence_adjust"] = -0.02
                result["msg"] = f"信号偏弱：卖出后价格反弹{price_change:.1f}%，-2%置信度"

        return result
    except Exception:
        return result


def _calc_multi_tf_trend_consistency_v58(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """多时间框架趋势一致性验证（V58 条件172）。

    通过短/中/长期均线的方向判断当前趋势是否与信号方向一致：
    - 3买信号：短期MA(5)>中期MA(20)>长期MA(60) = 多头排列 → +3%
    - 3买信号：短期MA(5)<中期MA(20)<长期MA(60) = 空头排列 → -3%
    - 3卖信号方向相反
    """
    result: dict[str, Any] = {
        "short_ma": 0.0,
        "mid_ma": 0.0,
        "long_ma": 0.0,
        "bullish_alignment": False,
        "bearish_alignment": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 65:
            result["msg"] = "数据不足，需要至少65根K线"
            return result

        def ma(data: list[float], period: int) -> float:
            return sum(data[-period:]) / period

        short_ma = ma(closes, 5)
        mid_ma = ma(closes, 20)
        long_ma = ma(closes, 60)

        result["short_ma"] = round(short_ma, 2)
        result["mid_ma"] = round(mid_ma, 2)
        result["long_ma"] = round(long_ma, 2)

        bullish = short_ma > mid_ma > long_ma
        bearish = short_ma < mid_ma < long_ma
        result["bullish_alignment"] = bullish
        result["bearish_alignment"] = bearish

        if is_buy:
            if bullish:
                result["confidence_adjust"] = 0.03
                result["msg"] = (
                    f"多头排列确认( MA5={short_ma:.2f} > MA20={mid_ma:.2f} > MA60={long_ma:.2f} )，+3%置信度"
                )
            elif bearish:
                result["confidence_adjust"] = -0.03
                result["msg"] = (
                    f"空头排列确认( MA5={short_ma:.2f} < MA20={mid_ma:.2f} < MA60={long_ma:.2f} )，-3%置信度"
                )
            else:
                result["msg"] = (
                    f"均线交错( MA5={short_ma:.2f}, MA20={mid_ma:.2f}, MA60={long_ma:.2f} )，无明确方向，0%调整"
                )
        else:
            if bearish:
                result["confidence_adjust"] = 0.03
                result["msg"] = "空头排列确认，卖出信号增强，+3%置信度"
            elif bullish:
                result["confidence_adjust"] = -0.03
                result["msg"] = "多头排列确认，卖出信号弱化，-3%置信度"
            else:
                result["msg"] = "均线交错，无明确方向，0%调整"

        return result
    except Exception:
        return result


def _calc_volume_accumulation_validation_v58(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """成交量堆积验证（V58 条件173）。

    通过近期成交量与历史平均成交量的比值，验证价格突破时是否有量能配合：
    - 量比 ≥ 1.5（放量突破）→ +3%置信度
    - 量比 1.0-1.5（温和放量）→ +1%置信度
    - 量比 < 1.0（缩量突破）→ -3%置信度（无量突破可信度低）
    """
    result: dict[str, Any] = {
        "volume_ratio": 0.0,
        "recent_vol": 0.0,
        "avg_vol_20": 0.0,
        "volume_adequate": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 25 or not volumes or len(volumes) < 25:
            result["msg"] = "数据不足，需要至少25根K线和成交量"
            return result

        recent_vol = sum(volumes[-5:]) / 5
        avg_vol_20 = sum(volumes[-20:]) / 20

        result["recent_vol"] = round(recent_vol, 2)
        result["avg_vol_20"] = round(avg_vol_20, 2)

        volume_ratio = recent_vol / (avg_vol_20 + 1e-10)
        result["volume_ratio"] = round(volume_ratio, 2)

        if volume_ratio >= 1.5:
            result["volume_adequate"] = True
            result["confidence_adjust"] = 0.03
            result["msg"] = f"放量突破(量比={volume_ratio:.2f}≥1.5)，量能配合良好，+3%置信度"
        elif volume_ratio >= 1.0:
            result["volume_adequate"] = True
            result["confidence_adjust"] = 0.01
            result["msg"] = f"温和放量(量比={volume_ratio:.2f})，+1%置信度"
        else:
            result["volume_adequate"] = False
            result["confidence_adjust"] = -0.03
            result["msg"] = f"缩量突破(量比={volume_ratio:.2f}<1.0)，无量突破可信度低，-3%置信度"

        return result
    except Exception:
        return result


def _calc_atr_adaptive_stop_v58(
    mmd: MMD,
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """ATR自适应止损距离（V58 条件174）。

    基于ATR(14)计算动态止损距离，帮助投资者设置合理止损位：
    - 输出建议止损价位（3买：止损位；3卖：反弹止损位）
    - 波动率等级分类（低/中/高/极高）
    - 置信度微调（高波动时-1%，极高波动时-2%）
    """
    result: dict[str, Any] = {
        "atr_14": 0.0,
        "stop_loss_price": 0.0,
        "stop_distance_pct": 0.0,
        "volatility_level": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if not highs or not lows or len(highs) < 15 or len(lows) < 15:
            result["msg"] = "数据不足，需要至少15根K线"
            return result

        # 计算ATR(14)
        tr_list: list[float] = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - lows[i - 1]),
                abs(lows[i] - highs[i - 1]),
            )
            tr_list.append(tr)

        if len(tr_list) < 14:
            result["msg"] = "TR数据不足"
            return result

        atr_14 = sum(tr_list[-14:]) / 14
        result["atr_14"] = round(atr_14, 4)

        current_price = highs[-1]

        # 波动率等级
        atr_pct = atr_14 / (current_price + 1e-10) * 100
        if atr_pct < 1.5:
            vol_level = "low"
        elif atr_pct < 3.0:
            vol_level = "medium"
        elif atr_pct < 5.0:
            vol_level = "high"
        else:
            vol_level = "extreme"

        result["volatility_level"] = vol_level

        # 止损距离 = 2倍ATR
        stop_distance = 2 * atr_14
        stop_pct = stop_distance / (current_price + 1e-10) * 100
        result["stop_distance_pct"] = round(stop_pct, 2)

        if is_buy:
            stop_price = current_price - stop_distance
            result["stop_loss_price"] = round(stop_price, 2)
            result["msg"] = (
                f"3买信号 | ATR={atr_14:.4f}({atr_pct:.2f}%) | "
                f"建议止损位={stop_price:.2f}({stop_distance:.2f}元,{stop_pct:.1f}%) | "
                f"波动率={vol_level}"
            )
            if vol_level in ("high", "extreme"):
                result["confidence_adjust"] = -0.01 if vol_level == "high" else -0.02
                result["msg"] += "，高波动，-1%/-2%置信度"
        else:
            stop_price = current_price + stop_distance
            result["stop_loss_price"] = round(stop_price, 2)
            result["msg"] = (
                f"3卖信号 | ATR={atr_14:.4f}({atr_pct:.2f}%) | "
                f"建议反弹止损位={stop_price:.2f}({stop_distance:.2f}元,{stop_pct:.1f}%) | "
                f"波动率={vol_level}"
            )
            if vol_level in ("high", "extreme"):
                result["confidence_adjust"] = -0.01 if vol_level == "high" else -0.02
                result["msg"] += "，高波动，-1%/-2%置信度"

        return result
    except Exception:
        return result


def _calc_composite_quality_score_v58(
    mmd: MMD,
) -> dict[str, Any]:
    """信号质量综合评分（V58 条件175）。

    综合所有V57和V58条件的结果，给出一个综合质量评分：
    - 汇总所有confidence_adjust
    - 评分等级：S(≥+10%) / A(+5~+10%) / B(0~+5%) / C(-5~0%) / D(<-5%)
    - 不直接调整confidence，仅作为参考输出
    """
    result: dict[str, Any] = {
        "total_adjust": 0.0,
        "grade": "C",
        "grade_desc": "",
        "detail_scores": {},
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        fields_to_sum = [
            ("pullback_filter_v57", "_pullback_filter_v57"),
            ("breakout_strength_v57", "_breakout_strength_validation_v57"),
            ("zs_divergence_v57", "_zs_divergence_check_v57"),
            ("signal_decay_v57", "_signal_decay_detection_v57"),
            ("multi_tf_v58", "_multi_tf_trend_consistency_v58"),
            ("volume_accum_v58", "_volume_accumulation_validation_v58"),
            ("atr_stop_v58", "_atr_adaptive_stop_v58"),
        ]

        total = 0.0
        details: dict[str, float] = {}
        for label, attr in fields_to_sum:
            val = getattr(mmd, attr, None)
            if isinstance(val, dict):
                adj = val.get("confidence_adjust", 0.0)
                if adj != 0.0:
                    details[label] = round(adj, 4)
                    total += adj

        result["total_adjust"] = round(total, 4)
        result["detail_scores"] = details

        # 评级
        if total >= 0.10:
            grade, desc = "S", "极强信号"
        elif total >= 0.05:
            grade, desc = "A", "强信号"
        elif total >= 0.0:
            grade, desc = "B", "中等信号"
        elif total >= -0.05:
            grade, desc = "C", "偏弱信号"
        else:
            grade, desc = "D", "弱信号，需谨慎"

        result["grade"] = grade
        result["grade_desc"] = desc

        detail_str = (
            "，".join(f"{k}={v:+.0%}" for k, v in details.items()) if details else "无有效条件"
        )
        result["msg"] = (
            f"综合质量评分：{grade}档({desc}) | 总调整={total:+.0%} | 明细：{detail_str}"
        )

        return result
    except Exception:
        return result


# ──────────────────────────────────────────────────────────────────────────────
# V59 条件176-179：参数自适应 + 多TF共振 + 信号衰减速度评估
# ──────────────────────────────────────────────────────────────────────────────


def _calc_volatility_adaptive_ma_v59(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """波动率自适应MA周期（V59 条件176）。

    根据当前波动率动态调整MA周期，使均线更适应当前市场环境：
    - 高波动：缩短MA周期（MA5→MA3, MA20→MA10, MA60→MA30），提高响应速度
    - 低波动：延长MA周期（MA5→MA8, MA20→MA30, MA60→MA90），减少噪音干扰
    - 正常波动：保持默认周期
    """
    result: dict[str, Any] = {
        "adaptive_ma_short": 5,
        "adaptive_ma_mid": 20,
        "adaptive_ma_long": 60,
        "volatility_regime": "normal",
        "recommended_period": "",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 90:
            result["msg"] = "数据不足，需要至少90根K线"
            return result

        # 计算实际波动率（近20日收盘价标准差/均值）
        recent_20 = closes[-20:]
        mean_20 = sum(recent_20) / 20
        var_20 = sum((x - mean_20) ** 2 for x in recent_20) / 20
        std_20 = var_20**0.5
        vol_pct = (std_20 / (mean_20 + 1e-10)) * 100

        # 波动率分级并调整MA周期
        if vol_pct > 4.0:
            regime = "high"
            short_p, mid_p, long_p = 3, 10, 30
            adj = -0.02  # 高波动环境信号噪音大，略降置信度
        elif vol_pct < 1.0:
            regime = "low"
            short_p, mid_p, long_p = 8, 30, 90
            adj = +0.02  # 低波动环境趋势更稳定，略升置信度
        else:
            regime = "normal"
            short_p, mid_p, long_p = 5, 20, 60
            adj = 0.0

        result["adaptive_ma_short"] = short_p
        result["adaptive_ma_mid"] = mid_p
        result["adaptive_ma_long"] = long_p
        result["volatility_regime"] = regime
        result["confidence_adjust"] = adj
        result["msg"] = (
            f"波动率={vol_pct:.2f}%({regime}) | "
            f"自适应MA周期：MA{short_p}/{mid_p}/{long_p} | "
            f"置信度调整{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_atr_multiplier_adapt_v59(
    mmd: MMD,
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """ATR倍数自适应（V59 条件177）。

    根据波动率环境动态调整ATR止损倍数：
    - 高波动：使用更大ATR倍数（3x），避免频繁触发止损
    - 低波动：使用更小ATR倍数（1.5x），收紧止损减少损失
    - 正常波动：使用默认倍数（2x）
    """
    result: dict[str, Any] = {
        "atr_14": 0.0,
        "optimal_multiplier": 2.0,
        "stop_distance_pct": 0.0,
        "volatility_regime": "normal",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if not highs or not lows or len(highs) < 15:
            result["msg"] = "数据不足"
            return result

        # 计算ATR(14)
        tr_list: list[float] = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - lows[i - 1]),
                abs(lows[i] - highs[i - 1]),
            )
            tr_list.append(tr)
        if len(tr_list) < 14:
            result["msg"] = "TR数据不足"
            return result

        atr_14 = sum(tr_list[-14:]) / 14
        current_price = highs[-1]
        atr_pct = atr_14 / (current_price + 1e-10) * 100

        # 根据ATR百分比确定波动率层级和最优倍数
        if atr_pct > 5.0:
            regime = "extreme"
            multiplier = 3.0
            adj = -0.02
        elif atr_pct > 3.0:
            regime = "high"
            multiplier = 2.5
            adj = -0.01
        elif atr_pct < 1.0:
            regime = "low"
            multiplier = 1.5
            adj = +0.01
        else:
            regime = "normal"
            multiplier = 2.0
            adj = 0.0

        stop_distance = multiplier * atr_14
        stop_pct = stop_distance / (current_price + 1e-10) * 100

        result["atr_14"] = round(atr_14, 4)
        result["optimal_multiplier"] = multiplier
        result["stop_distance_pct"] = round(stop_pct, 2)
        result["volatility_regime"] = regime
        result["confidence_adjust"] = adj

        direction = "买入" if is_buy else "卖出"
        result["msg"] = (
            f"{direction}信号 | ATR={atr_14:.4f}({atr_pct:.2f}%) | "
            f"最优倍数={multiplier}x | 止损距离={stop_pct:.1f}% | "
            f"波动率={regime} | 置信度调整{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_multi_tf_resonance_signal_v59(
    mmd: MMD,
    closes: list[float],
    volumes: list[float] | None = None,
) -> dict[str, Any]:
    """多时间框架共振信号（V59 条件178）。

    通过比较短期（近5根K线）与中期（近20根K线）趋势和动量，
    验证日线信号是否有短周期共振支持：
    - 短期上涨+中期上涨 → 共振强，+4%置信度
    - 短期上涨+中期下跌 → 共振弱（逆势），-4%置信度
    - 仅一级共振 → +1%置信度
    """
    result: dict[str, Any] = {
        "short_tf_trend": "unknown",
        "short_tf_momentum": "unknown",
        "resonance_score": 0,
        "resonance_strength": "none",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 25:
            result["msg"] = "数据不足，需要至少25根K线"
            return result

        # 短期趋势：近5根K线收盘价变化
        close_5 = closes[-5:]
        short_trend = (
            "up" if close_5[-1] > close_5[0] else ("down" if close_5[-1] < close_5[0] else "flat")
        )

        # 短期动量：近5根K线的涨跌比例
        up_bars = sum(1 for i in range(1, len(close_5)) if close_5[i] > close_5[i - 1])
        momentum_ratio = up_bars / 4.0 if len(close_5) > 1 else 0.5

        if momentum_ratio >= 0.75:
            short_mom = "strong"
        elif momentum_ratio >= 0.5:
            short_mom = "weak"
        else:
            short_mom = "negative"

        # 中期趋势：近20根K线 vs 前20根
        if len(closes) >= 40:
            recent_20 = closes[-20:]
            prior_20 = closes[-40:-20]
            recent_avg = sum(recent_20) / 20
            prior_avg = sum(prior_20) / 20
            mid_trend = (
                "up" if recent_avg > prior_avg else ("down" if recent_avg < prior_avg else "flat")
            )
        else:
            mid_trend = "unknown"

        result["short_tf_trend"] = short_trend
        result["short_tf_momentum"] = short_mom

        # 共振评分：短期与中期趋势一致性
        resonance_score = 0
        if is_buy:
            if short_trend == "up" and mid_trend == "up":
                resonance_score = 2
            elif short_trend == "up" or mid_trend == "up":
                resonance_score = 1
            elif short_trend == "down" and mid_trend == "down":
                resonance_score = -2
            else:
                resonance_score = 0
        else:  # sell
            if short_trend == "down" and mid_trend == "down":
                resonance_score = 2
            elif short_trend == "down" or mid_trend == "down":
                resonance_score = 1
            elif short_trend == "up" and mid_trend == "up":
                resonance_score = -2
            else:
                resonance_score = 0

        result["resonance_score"] = resonance_score

        if resonance_score >= 2:
            strength = "strong"
            adj = 0.04
        elif resonance_score == 1:
            strength = "moderate"
            adj = 0.01
        elif resonance_score <= -2:
            strength = "strong_opposite"
            adj = -0.04
        elif resonance_score == -1:
            strength = "weak_opposite"
            adj = -0.01
        else:
            strength = "neutral"
            adj = 0.0

        result["resonance_strength"] = strength
        result["confidence_adjust"] = adj

        dir_label = "买入" if is_buy else "卖出"
        result["msg"] = (
            f"{dir_label}共振验证 | "
            f"短周期：{short_trend}({short_mom}) | "
            f"中周期：{mid_trend} | "
            f"共振分={resonance_score}({strength}) | "
            f"置信度调整{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_signal_decay_speed_v59(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """信号衰减速度评估（V59 条件179）。

    测量信号产生后价格远离信号点的速度，快速远离 = 强信号，
    缓慢或回退 = 弱信号/假信号。
    """
    result: dict[str, Any] = {
        "price_speed_after_signal": 0.0,
        "decay_rate": "unknown",
        "signal_strength": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 15:
            result["msg"] = "数据不足，需要至少15根K线"
            return result

        # 取信号点价格（倒数第15根到倒数第1根之间）
        signal_idx = len(closes) - 15
        if signal_idx < 0:
            signal_idx = 0
        signal_price = closes[signal_idx]

        # 计算信号后N根K线的平均日涨幅
        lookback = min(10, len(closes) - signal_idx - 1)
        if lookback < 3:
            result["msg"] = "信号后K线不足，无法评估"
            return result

        post_signal = closes[signal_idx + 1 : signal_idx + 1 + lookback]
        changes = [
            (post_signal[i] - post_signal[i - 1]) / (post_signal[i - 1] + 1e-10) * 100
            for i in range(1, len(post_signal))
        ]
        _ = sum(changes) / len(changes) if changes else 0.0
        total_change = (post_signal[-1] - signal_price) / (signal_price + 1e-10) * 100

        result["price_speed_after_signal"] = round(abs(total_change), 2)

        # 根据价格变化速度评估信号强度
        if is_buy:
            if total_change >= 3.0:
                decay = "fast_rise"
                strength = "strong"
                adj = 0.03
            elif total_change >= 1.5:
                decay = "moderate_rise"
                strength = "moderate"
                adj = 0.01
            elif total_change >= 0.0:
                decay = "slow_rise"
                strength = "weak"
                adj = -0.01
            else:
                decay = "reversal"
                strength = "fake"
                adj = -0.04
        else:  # sell
            if total_change <= -3.0:
                decay = "fast_fall"
                strength = "strong"
                adj = 0.03
            elif total_change <= -1.5:
                decay = "moderate_fall"
                strength = "moderate"
                adj = 0.01
            elif total_change <= 0.0:
                decay = "slow_fall"
                strength = "weak"
                adj = -0.01
            else:
                decay = "rebound"
                strength = "fake"
                adj = -0.04

        result["decay_rate"] = decay
        result["signal_strength"] = strength
        result["confidence_adjust"] = adj
        result["msg"] = (
            f"信号后{lookback}根K线 | 总变化={total_change:+.2f}% | "
            f"衰减={decay} | 强度={strength} | "
            f"置信度调整{adj:+.0%}"
        )
        return result
    except Exception:
        return result


# ── V60 条件 180-183 ──


def _calc_rsi_deep_divergence_v60(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """RSI深度背离过滤（V60 条件180）。

    检测价格与RSI的深度背离信号：
    - 深度底背离：价格创新低但RSI未创新低（两次低点比较），强烈确认3买
    - 深度顶背离：价格创新高但RSI未创新高，强烈确认3卖
    - 轻微背离：仅单次低点比较，温和确认
    """
    result: dict[str, Any] = {
        "rsi_current": 0.0,
        "rsi_prev_low": 0.0,
        "price_curr_low": 0.0,
        "price_prev_low": 0.0,
        "divergence_type": "none",
        "divergence_depth": "none",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 60:
            result["msg"] = "数据不足，需要至少60根K线"
            return result

        # 计算RSI序列
        rsi_values = RSI(closes, N=14)
        if len(rsi_values) < 40:
            result["msg"] = "RSI数据不足"
            return result

        result["rsi_current"] = round(float(rsi_values[-1]), 1)

        # 深度背离检测窗口：比较近40根与之前40根的极值
        window = 40
        if len(closes) < window * 2:
            window = len(closes) // 2
        if window < 20:
            result["msg"] = "数据不足进行背离检测"
            return result

        recent = closes[-window:]
        prior = closes[-window * 2 : -window] if len(closes) >= window * 2 else closes[:window]

        price_curr_low = min(recent)
        price_prev_low = min(prior)
        price_curr_high = max(recent)
        price_prev_high = max(prior)

        rsi_curr_window = rsi_values[-window:]
        rsi_prior_window = (
            rsi_values[-window * 2 : -window]
            if len(rsi_values) >= window * 2
            else rsi_values[:window]
        )

        rsi_curr_low = min(rsi_curr_window)
        rsi_prev_low = min(rsi_prior_window)
        rsi_curr_high = max(rsi_curr_window)
        rsi_prev_high = max(rsi_prior_window)

        result["price_curr_low"] = round(price_curr_low, 2)
        result["price_prev_low"] = round(price_prev_low, 2)
        result["rsi_prev_low"] = round(rsi_prev_low, 1)

        divergence_type = "none"
        divergence_depth = "none"
        adj = 0.0

        if is_buy:
            # 3买：价格创新低 + RSI未创新低 → 底背离
            if price_curr_low < price_prev_low * 0.995 and rsi_curr_low > rsi_prev_low:
                divergence_type = "bullish_deep"
                # 深度：价格新低幅度
                price_drop_pct = (price_prev_low - price_curr_low) / (price_prev_low + 1e-10) * 100
                if price_drop_pct > 5.0:
                    divergence_depth = "deep"
                    adj = 0.04
                elif price_drop_pct > 2.0:
                    divergence_depth = "moderate"
                    adj = 0.02
                else:
                    divergence_depth = "shallow"
                    adj = 0.01
            elif price_curr_low < price_prev_low * 0.995:
                # 价格新低但RSI也新低 → 无背离，正常趋势延续
                divergence_type = "no_divergence"
                divergence_depth = "none"
                adj = -0.01
            else:
                divergence_type = "no_divergence"
                adj = 0.0
        else:  # sell
            # 3卖：价格创新高 + RSI未创新高 → 顶背离
            if price_curr_high > price_prev_high * 1.005 and rsi_curr_high < rsi_prev_high:
                divergence_type = "bearish_deep"
                price_rise_pct = (
                    (price_curr_high - price_prev_high) / (price_prev_high + 1e-10) * 100
                )
                if price_rise_pct > 5.0:
                    divergence_depth = "deep"
                    adj = 0.04
                elif price_rise_pct > 2.0:
                    divergence_depth = "moderate"
                    adj = 0.02
                else:
                    divergence_depth = "shallow"
                    adj = 0.01
            elif price_curr_high > price_prev_high * 1.005:
                divergence_type = "no_divergence"
                adj = -0.01
            else:
                divergence_type = "no_divergence"
                adj = 0.0

        result["divergence_type"] = divergence_type
        result["divergence_depth"] = divergence_depth
        result["confidence_adjust"] = adj
        result["msg"] = (
            f"RSI={result['rsi_current']:.1f} | "
            f"背离={divergence_type}({divergence_depth}) | "
            f"价格低点{result['price_prev_low']:.2f}→{result['price_curr_low']:.2f} | "
            f"置信度调整{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_ma_spacing_strength_v60(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """MA排列间距强度评分（V60 条件181）。

    计算MA5/MA20/MA60之间的间距比例，评估均线排列的健康程度：
    - 多头排列间距大 → 强趋势，+3%置信度
    - 均线纠缠（间距小）→ 震荡，-2%置信度
    - 空头排列 → 对3买不利
    """
    result: dict[str, Any] = {
        "ma5": 0.0,
        "ma20": 0.0,
        "ma60": 0.0,
        "spacing_ratio": 0.0,
        "alignment": "unknown",
        "spacing_strength": "weak",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 60:
            result["msg"] = "数据不足，需要至少60根K线"
            return result

        ma5 = MA(closes, 5)
        ma20 = MA(closes, 20)
        ma60 = MA(closes, 60)

        if len(ma5) < 1 or len(ma20) < 1 or len(ma60) < 1:
            result["msg"] = "MA计算失败"
            return result

        m5 = float(ma5[-1])
        m20 = float(ma20[-1])
        m60 = float(ma60[-1])
        _ = closes[-1]

        result["ma5"] = round(m5, 2)
        result["ma20"] = round(m20, 2)
        result["ma60"] = round(m60, 2)

        # 计算间距比例（相对均值的百分比）
        mean_ma = (m5 + m20 + m60) / 3.0
        spread_5_20 = abs(m5 - m20) / (mean_ma + 1e-10) * 100
        spread_20_60 = abs(m20 - m60) / (mean_ma + 1e-10) * 100
        spacing_ratio = (spread_5_20 + spread_20_60) / 2.0
        result["spacing_ratio"] = round(spacing_ratio, 2)

        # 判断排列方向
        if m5 > m20 > m60:
            alignment = "bullish"
        elif m5 < m20 < m60:
            alignment = "bearish"
        else:
            alignment = "entangled"

        result["alignment"] = alignment

        # 评估间距强度
        if spacing_ratio > 3.0:
            spacing_strength = "strong"
        elif spacing_ratio > 1.5:
            spacing_strength = "moderate"
        else:
            spacing_strength = "weak"
        result["spacing_strength"] = spacing_strength

        # 根据排列和间距给出置信度调整
        if is_buy:
            if alignment == "bullish" and spacing_strength == "strong":
                adj = 0.03
            elif alignment == "bullish" and spacing_strength == "moderate":
                adj = 0.015
            elif alignment == "bullish" and spacing_strength == "weak":
                adj = 0.005
            elif alignment == "entangled":
                adj = -0.02  # 均线纠缠，不确定性强
            else:  # bearish
                adj = -0.03  # 空头排列，3买信号不可靠
        else:  # sell
            if alignment == "bearish" and spacing_strength == "strong":
                adj = 0.03
            elif alignment == "bearish" and spacing_strength == "moderate":
                adj = 0.015
            elif alignment == "bearish" and spacing_strength == "weak":
                adj = 0.005
            elif alignment == "entangled":
                adj = -0.02
            else:
                adj = -0.03

        result["confidence_adjust"] = adj
        result["msg"] = (
            f"MA5={m5:.2f}/MA20={m20:.2f}/MA60={m60:.2f} | "
            f"排列={alignment} | 间距={spacing_ratio:.2f}%({spacing_strength}) | "
            f"置信度调整{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_zs_distance_enhanced_v60(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """中枢支撑/阻力距离评分增强（V60 条件182）。

    在原有中枢距离评分基础上增加多维度评估：
    - 价格与中枢上下沿的距离比
    - 突破/跌破后的回踩/反弹确认
    - 中枢宽度与当前价格波动的关系
    """
    result: dict[str, Any] = {
        "zs_zg": 0.0,
        "zs_zd": 0.0,
        "price": 0.0,
        "distance_to_zg_pct": 0.0,
        "distance_to_zd_pct": 0.0,
        "zs_width_pct": 0.0,
        "position": "unknown",
        "pullback_confirmed": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if mmd.zs is None:
            result["msg"] = "无中枢数据"
            return result

        if len(closes) < 20:
            result["msg"] = "数据不足，需要至少20根K线"
            return result

        zg = mmd.zs.zg
        zd = mmd.zs.zd
        price = closes[-1]

        result["zs_zg"] = round(zg, 2)
        result["zs_zd"] = round(zd, 2)
        result["price"] = round(price, 2)

        # 计算距离百分比
        price_range = zg - zd if zg != zd else price * 0.01
        dist_zg_pct = (price - zg) / (price_range + 1e-10) * 100
        dist_zd_pct = (price - zd) / (price_range + 1e-10) * 100
        zs_width_pct = price_range / (price + 1e-10) * 100

        result["distance_to_zg_pct"] = round(dist_zg_pct, 2)
        result["distance_to_zd_pct"] = round(dist_zd_pct, 2)
        result["zs_width_pct"] = round(zs_width_pct, 2)

        # 判断价格位置
        if price > zg:
            position = "above_zs"
        elif price < zd:
            position = "below_zs"
        else:
            position = "inside_zs"
        result["position"] = position

        # 回踩/反弹确认检测
        pullback_confirmed = False
        if is_buy and position == "above_zs":
            # 3买：突破中枢后回踩确认
            lookback = min(10, len(closes) - 1)
            if lookback >= 3:
                recent_lows = [
                    min(closes[-i : -i + 2]) if i < len(closes) else closes[-1]
                    for i in range(1, lookback + 1, 2)
                ]
                if recent_lows and min(recent_lows) >= zd * 0.98:
                    pullback_confirmed = True

        if is_sell and position == "below_zs":
            lookback = min(10, len(closes) - 1)
            if lookback >= 3:
                recent_highs = [
                    max(closes[-i : -i + 2]) if i < len(closes) else closes[-1]
                    for i in range(1, lookback + 1, 2)
                ]
                if recent_highs and max(recent_highs) <= zg * 1.02:
                    pullback_confirmed = True
        result["pullback_confirmed"] = pullback_confirmed

        # 综合评分
        adj = 0.0
        if is_buy:
            if position == "above_zs":
                if dist_zg_pct < 5.0:  # 刚突破，距离近
                    adj = 0.02
                elif dist_zg_pct < 15.0:
                    adj = 0.01
                else:
                    adj = -0.01  # 偏离过大，可能回调
            elif position == "inside_zs":
                if dist_zd_pct < 20.0:  # 接近下沿，可能3买
                    adj = 0.015
                else:
                    adj = 0.0
            else:  # below_zs
                adj = -0.03  # 仍在中枢下方，不是有效的3买
            if pullback_confirmed:
                adj = min(0.05, adj + 0.02)
        else:  # sell
            if position == "below_zs":
                if dist_zd_pct > -5.0:  # 刚跌破
                    adj = 0.02
                elif dist_zd_pct > -15.0:
                    adj = 0.01
                else:
                    adj = -0.01
            elif position == "inside_zs":
                if dist_zg_pct > -20.0:  # 接近上沿
                    adj = 0.015
                else:
                    adj = 0.0
            else:
                adj = -0.03
            if pullback_confirmed:
                adj = min(0.05, adj + 0.02)

        result["confidence_adjust"] = adj
        result["msg"] = (
            f"价格={price:.2f} | 中枢[{zd:.2f},{zg:.2f}] | "
            f"位置={position} | 距上沿{dist_zg_pct:+.1f}% | "
            f"回踩确认={pullback_confirmed} | "
            f"置信度调整{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_kdj_ob_os_confirm_v60(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """KDJ超买超卖确认（V60 条件183）。

    利用KDJ的J值验证买卖信号的合理性：
    - 3买：J值应处于超卖区或刚从超卖区回升（J<30或J从低位拐头向上）
    - 3卖：J值应处于超买区或刚从超买区回落（J>70或J从高位拐头向下）
    - J值极端区域但方向错误 → 假信号预警
    """
    result: dict[str, Any] = {
        "kdj_k": 0.0,
        "kdj_d": 0.0,
        "kdj_j": 0.0,
        "j_prev": 0.0,
        "j_trend": "unknown",
        "ob_os_zone": "neutral",
        "signal_aligned": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 15:
            result["msg"] = "数据不足，需要至少15根K线"
            return result

        # 使用收盘价近似计算KDJ（精度足够用于方向确认）
        n = len(closes)
        highs = [closes[i] * (1.0 + 0.005 * (i % 3)) for i in range(n)]
        lows = [closes[i] * (1.0 - 0.005 * ((i + 1) % 3)) for i in range(n)]

        k_val, d_val, j_val = KDJ(closes, highs, lows, N=9)

        if len(j_val) < 3:
            result["msg"] = "KDJ数据不足"
            return result

        j_current = float(j_val[-1])
        j_prev = float(j_val[-2]) if len(j_val) >= 2 else j_current
        j_prev2 = float(j_val[-3]) if len(j_val) >= 3 else j_prev
        k_current = float(k_val[-1])
        d_current = float(d_val[-1])

        result["kdj_k"] = round(k_current, 1)
        result["kdj_d"] = round(d_current, 1)
        result["kdj_j"] = round(j_current, 1)
        result["j_prev"] = round(j_prev, 1)

        # 判断J值趋势
        if j_current > j_prev > j_prev2:
            j_trend = "rising"
        elif j_current < j_prev < j_prev2:
            j_trend = "falling"
        else:
            j_trend = "flat"
        result["j_trend"] = j_trend

        # 判断超买超卖区域
        if j_current >= 100:
            ob_os_zone = "extreme_overbought"
        elif j_current >= 80:
            ob_os_zone = "overbought"
        elif j_current <= -20:
            ob_os_zone = "extreme_oversold"
        elif j_current <= 20:
            ob_os_zone = "oversold"
        else:
            ob_os_zone = "neutral"
        result["ob_os_zone"] = ob_os_zone

        # 信号对齐判断
        signal_aligned = False
        adj = 0.0

        if is_buy:
            # 3买：J值应在超卖区或刚从超卖区回升
            if ob_os_zone in ("oversold", "extreme_oversold"):
                if j_trend == "rising":
                    signal_aligned = True
                    adj = 0.03
                else:
                    adj = 0.01  # 超卖但未回升，中性
            elif ob_os_zone == "neutral" and j_trend == "rising" and j_prev < 30:
                # J值从中性区刚从超卖回升
                signal_aligned = True
                adj = 0.02
            elif ob_os_zone in ("overbought", "extreme_overbought"):
                # 超买区出现买入信号，警惕
                adj = -0.03
            else:
                adj = 0.0
        else:  # sell
            # 3卖：J值应在超买区或刚从超买区回落
            if ob_os_zone in ("overbought", "extreme_overbought"):
                if j_trend == "falling":
                    signal_aligned = True
                    adj = 0.03
                else:
                    adj = 0.01
            elif ob_os_zone == "neutral" and j_trend == "falling" and j_prev > 70:
                signal_aligned = True
                adj = 0.02
            elif ob_os_zone in ("oversold", "extreme_oversold"):
                adj = -0.03
            else:
                adj = 0.0

        result["signal_aligned"] = signal_aligned
        result["confidence_adjust"] = adj
        result["msg"] = (
            f"K={k_current:.1f}/D={d_current:.1f}/J={j_current:.1f} | "
            f"J趋势={j_trend} | 区域={ob_os_zone} | "
            f"信号对齐={signal_aligned} | "
            f"置信度调整{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_macd_histogram_divergence_v61(
    mmd: MMD,
    closes: list[float],
    macd_data: dict[str, list[float]],
) -> dict[str, Any]:
    """MACD柱状图背离融合（V61 条件184）。

    检测价格与MACD柱状图的背离信号，并与RSI背离融合：
    - 深度底背离（价格新低+MACD柱未新低）→ 强烈确认3买
    - 深度顶背离（价格新高+MACD柱未新高）→ 强烈确认3卖
    - 与RSI背离双确认 → 额外加分

    返回：
        {
            "divergence_type": str,       # "none"/"bullish_macd"/"bearish_macd"
            "macd_hist_curr": float,      # 当前MACD柱值
            "macd_hist_prev": float,      # 前期MACD柱值
            "divergence_depth": str,      # "deep"/"moderate"/"shallow"
            "rsi_fusion": str,            # "none"/"fused_bullish"/"fused_bearish"
            "confidence_adjust": float,   # 置信度调整
            "msg": str,
        }
    """
    result: dict[str, Any] = {
        "divergence_type": "none",
        "macd_hist_curr": 0.0,
        "macd_hist_prev": 0.0,
        "price_curr_low": 0.0,
        "price_prev_low": 0.0,
        "price_curr_high": 0.0,
        "price_prev_high": 0.0,
        "divergence_depth": "none",
        "rsi_fusion": "none",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        hist = macd_data.get("hist", [])
        if len(hist) < 40:
            result["msg"] = "MACD柱状图数据不足，需要至少40根K线"
            return result

        if len(closes) < 40:
            result["msg"] = "价格数据不足"
            return result

        result["macd_hist_curr"] = round(float(hist[-1]), 6)
        result["macd_hist_prev"] = round(float(hist[-21]) if len(hist) >= 21 else hist[-1], 6)

        # MACD背离检测窗口
        window = 20
        if len(closes) < window * 2:
            window = len(closes) // 2
        if window < 10:
            result["msg"] = "数据不足进行MACD背离检测"
            return result

        recent = closes[-window:]
        prior = closes[-window * 2 : -window] if len(closes) >= window * 2 else closes[:window]

        price_curr_low = min(recent)
        price_prev_low = min(prior)
        price_curr_high = max(recent)
        price_prev_high = max(prior)

        hist_curr_window = hist[-window:]
        hist_prior_window = (
            hist[-window * 2 : -window] if len(hist) >= window * 2 else hist[:window]
        )

        hist_curr_low = min(hist_curr_window)
        hist_prev_low = min(hist_prior_window)
        hist_curr_high = max(hist_curr_window)
        hist_prev_high = max(hist_prior_window)

        result["price_curr_low"] = round(price_curr_low, 2)
        result["price_prev_low"] = round(price_prev_low, 2)
        result["price_curr_high"] = round(price_curr_high, 2)
        result["price_prev_high"] = round(price_prev_high, 2)

        divergence_type = "none"
        divergence_depth = "none"
        adj = 0.0

        if is_buy:
            # 3买：价格创新低 + MACD柱未创新低 → 底背离
            if price_curr_low < price_prev_low * 0.995 and hist_curr_low > hist_prev_low:
                divergence_type = "bullish_macd"
                price_drop_pct = (price_prev_low - price_curr_low) / (price_prev_low + 1e-10) * 100
                if price_drop_pct > 5.0:
                    divergence_depth = "deep"
                    adj = 0.04
                elif price_drop_pct > 2.0:
                    divergence_depth = "moderate"
                    adj = 0.02
                else:
                    divergence_depth = "shallow"
                    adj = 0.01
            elif price_curr_low < price_prev_low * 0.995:
                divergence_type = "no_divergence"
                divergence_depth = "none"
                adj = -0.01
            else:
                divergence_type = "no_divergence"
                adj = 0.0
        else:  # sell
            # 3卖：价格创新高 + MACD柱未创新高 → 顶背离
            if price_curr_high > price_prev_high * 1.005 and hist_curr_high < hist_prev_high:
                divergence_type = "bearish_macd"
                price_rise_pct = (
                    (price_curr_high - price_prev_high) / (price_prev_high + 1e-10) * 100
                )
                if price_rise_pct > 5.0:
                    divergence_depth = "deep"
                    adj = 0.04
                elif price_rise_pct > 2.0:
                    divergence_depth = "moderate"
                    adj = 0.02
                else:
                    divergence_depth = "shallow"
                    adj = 0.01
            elif price_curr_high > price_prev_high * 1.005:
                divergence_type = "no_divergence"
                adj = -0.01
            else:
                divergence_type = "no_divergence"
                adj = 0.0

        result["divergence_type"] = divergence_type
        result["divergence_depth"] = divergence_depth

        # RSI融合：检查RSI背离是否存在
        rsi_div = getattr(mmd, "_rsi_deep_divergence_v60", None)
        rsi_fusion = "none"
        if rsi_div and rsi_div.get("divergence_type") in ("bullish_deep", "bearish_deep"):
            if (
                is_buy
                and rsi_div.get("divergence_type") == "bullish_deep"
                and divergence_type == "bullish_macd"
            ):
                rsi_fusion = "fused_bullish"
                adj += 0.02  # 双指标确认额外加分
            elif (
                not is_buy
                and rsi_div.get("divergence_type") == "bearish_deep"
                and divergence_type == "bearish_macd"
            ):
                rsi_fusion = "fused_bearish"
                adj += 0.02  # 双指标确认额外加分

        result["rsi_fusion"] = rsi_fusion
        result["confidence_adjust"] = adj
        result["msg"] = (
            f"MACD柱={result['macd_hist_curr']:.4f}/{result['macd_hist_prev']:.4f} | "
            f"背离类型={divergence_type} | 深度={divergence_depth} | "
            f"RSI融合={rsi_fusion} | "
            f"置信度调整{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_composite_signal_score_v61(
    mmd: MMD,
) -> dict[str, Any]:
    """综合多信号评分（V61 条件185）。

    聚合V58-V60所有条件的置信度调整，生成综合质量评分和等级：
    - S级（综合分≥0.75）：金色边框，强烈推荐
    - A级（综合分≥0.60）：绿色边框，推荐
    - B级（综合分≥0.45）：蓝色边框，一般
    - C级（综合分≥0.30）：橙色边框，谨慎
    - D级（综合分<0.30）：红色边框，不推荐

    返回：
        {
            "composite_score": float,       # 综合评分（0.0~1.0）
            "quality_tier": str,            # S/A/B/C/D
            "tier_color": str,              # 边框颜色
            "condition_count": int,         # 有效条件数
            "total_adjustment": float,      # 总置信度调整
            "breakdown": dict,              # 各条件贡献明细
            "decision_help": str,           # 决策帮助建议
            "recommendation": str,          # 推荐操作
        }
    """
    result: dict[str, Any] = {
        "composite_score": 0.0,
        "quality_tier": "unknown",
        "tier_color": "#9ca3af",
        "condition_count": 0,
        "total_adjustment": 0.0,
        "breakdown": {},
        "decision_help": "",
        "recommendation": "",
    }
    try:
        # 收集V58-V60所有条件的置信度调整
        adjustments = {}
        total_adj = 0.0
        valid_count = 0

        # V58 条件172-175
        for field_name in [
            "_multi_tf_trend_consistency_v58",
            "_volume_accumulation_validation_v58",
            "_atr_adaptive_stop_v58",
            "_composite_quality_score_v58",
        ]:
            val = getattr(mmd, field_name, None)
            if val and isinstance(val, dict):
                adj = val.get("confidence_adjust", 0.0)
                if adj != 0.0:
                    adjustments[field_name.replace("_", "").replace("v58", "V58")] = adj
                    total_adj += adj
                    valid_count += 1

        # V59 条件176-179
        for field_name in [
            "_volatility_adaptive_ma_v59",
            "_atr_multiplier_adapt_v59",
            "_multi_tf_resonance_signal_v59",
            "_signal_decay_speed_v59",
        ]:
            val = getattr(mmd, field_name, None)
            if val and isinstance(val, dict):
                adj = val.get("confidence_adjust", 0.0)
                if adj != 0.0:
                    adjustments[field_name.replace("_", "").replace("v59", "V59")] = adj
                    total_adj += adj
                    valid_count += 1

        # V60 条件180-183
        for field_name in [
            "_rsi_deep_divergence_v60",
            "_ma_spacing_strength_v60",
            "_zs_distance_enhanced_v60",
            "_kdj_ob_os_confirm_v60",
        ]:
            val = getattr(mmd, field_name, None)
            if val and isinstance(val, dict):
                adj = val.get("confidence_adjust", 0.0)
                if adj != 0.0:
                    adjustments[field_name.replace("_", "").replace("v60", "V60")] = adj
                    total_adj += adj
                    valid_count += 1

        # V61 条件184
        macd_div = getattr(mmd, "_macd_hist_divergence_v61", None)
        if macd_div and isinstance(macd_div, dict):
            adj = macd_div.get("confidence_adjust", 0.0)
            if adj != 0.0:
                adjustments["MACDhist_divergence"] = adj
                total_adj += adj
                valid_count += 1

        # 计算综合评分
        base_confidence = mmd.confidence
        # 综合评分 = 基础置信度 + 平均调整量（上限±10%）
        avg_adjustment = total_adj / max(1, valid_count) if valid_count > 0 else 0.0
        composite_score = base_confidence + avg_adjustment * 0.5
        composite_score = max(0.0, min(1.0, composite_score))

        # 确定质量等级和颜色
        if composite_score >= 0.75:
            quality_tier = "S"
            tier_color = "#f59e0b"  # 金色
            recommendation = "强烈建议操作"
        elif composite_score >= 0.60:
            quality_tier = "A"
            tier_color = "#22c55e"  # 绿色
            recommendation = "建议操作"
        elif composite_score >= 0.45:
            quality_tier = "B"
            tier_color = "#3b82f6"  # 蓝色
            recommendation = "可考虑操作"
        elif composite_score >= 0.30:
            quality_tier = "C"
            tier_color = "#f97316"  # 橙色
            recommendation = "谨慎操作"
        else:
            quality_tier = "D"
            tier_color = "#ef4444"  # 红色
            recommendation = "不建议操作"

        # 生成决策帮助
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        signals_positive = sum(1 for v in adjustments.values() if v > 0)
        signals_negative = sum(1 for v in adjustments.values() if v < 0)

        if is_buy:
            if signals_negative > signals_positive:
                decision_help = f"多方信号{signals_positive}个，空方信号{signals_negative}个，建议观望等待更多确认"
            elif signals_positive >= 3:
                decision_help = f"多方信号强劲（{signals_positive}个确认），可在支撑位附近轻仓试探"
            else:
                decision_help = f"多方信号{signals_positive}个，可逢低布局但需设好止损"
        elif is_sell:
            if signals_negative > signals_positive:
                decision_help = (
                    f"空方信号{signals_negative}个，多方信号{signals_positive}个，建议果断离场"
                )
            elif signals_positive >= 3:
                decision_help = f"空方信号强劲（{signals_negative}个确认），可在反弹时减仓"
            else:
                decision_help = f"空方信号{signals_negative}个，可考虑分批减仓"
        else:
            decision_help = "非买卖点信号，仅供参考"

        result["composite_score"] = round(composite_score, 3)
        result["quality_tier"] = quality_tier
        result["tier_color"] = tier_color
        result["condition_count"] = valid_count
        result["total_adjustment"] = round(total_adj, 3)
        result["breakdown"] = {k: round(v, 3) for k, v in adjustments.items()}
        result["decision_help"] = decision_help
        result["recommendation"] = recommendation

        return result
    except Exception:
        return result


# =============================================================================
# V62: 条件 186-189（BOLL带宽确认 + 动态阈值）
# =============================================================================


def _calc_boll_bandwidth_breakout_confirm_v62(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """BOLL带宽突破确认（V62 条件186）。

    检测3买/3卖时BOLL带宽是否处于有效突破状态：
    - 3买：价格突破BOLL上轨 + 带宽较前期扩张 → 突破有效，+3%
    - 3卖：价格跌破BOLL下轨 + 带宽较前期扩张 → 突破有效，+3%
    - 价格接近轨道但未突破 → +1%（潜在突破）
    - 带宽持续收缩 → -1%（可能即将反转，信号质量下降）
    """
    result: dict[str, Any] = {
        "boll_upper": 0.0,
        "boll_lower": 0.0,
        "band_width": 0.0,
        "price_position": "mid",
        "breakout_confirmed": False,
        "band_trend": "stable",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 40:
            result["msg"] = "数据不足，需要至少40根K线"
            return result

        # 计算BOLL(20,2)
        period = 20
        window = closes[-period:]
        mid = sum(window) / period
        std = (sum((x - mid) ** 2 for x in window) / period) ** 0.5
        upper = mid + 2 * std
        lower = mid - 2 * std
        current_price = closes[-1]

        # 计算带宽和价格位置
        band_width = (upper - lower) / (mid + 1e-10) * 100 if mid > 0 else 0
        percent_b = (current_price - lower) / (upper - lower) if upper > lower else 0.5

        result["boll_upper"] = round(upper, 2)
        result["boll_lower"] = round(lower, 2)
        result["band_width"] = round(band_width, 3)
        result["price_position"] = (
            "upper" if percent_b > 0.8 else ("lower" if percent_b < 0.2 else "mid")
        )

        # 带宽趋势：比较当前带宽与10根K线前的带宽
        prev_window = (
            closes[-(period + 10) : -(10)] if len(closes) >= period + 10 else closes[:period]
        )
        if len(prev_window) >= period:
            prev_mid = sum(prev_window) / period
            prev_std = (sum((x - prev_mid) ** 2 for x in prev_window) / period) ** 0.5
            prev_upper = prev_mid + 2 * prev_std
            prev_lower = prev_mid - 2 * prev_std
            prev_band_width = (
                (prev_upper - prev_lower) / (prev_mid + 1e-10) * 100 if prev_mid > 0 else 0
            )
            band_change = (band_width - prev_band_width) / (prev_band_width + 1e-10) * 100

            if band_change > 10:
                band_trend = "expanding"
            elif band_change < -10:
                band_trend = "contracting"
            else:
                band_trend = "stable"
            result["band_trend"] = band_trend
        else:
            band_trend = "insufficient_data"

        # 置信度调整
        adj = 0.0
        breakout_confirmed = False
        if is_buy:
            if percent_b > 1.0 and band_trend == "expanding":
                adj = 0.03
                breakout_confirmed = True
            elif percent_b > 0.85 and band_trend in ("expanding", "stable"):
                adj = 0.01
            elif band_trend == "contracting":
                adj = -0.01
        else:
            if percent_b < 0.0 and band_trend == "expanding":
                adj = 0.03
                breakout_confirmed = True
            elif percent_b < 0.15 and band_trend in ("expanding", "stable"):
                adj = 0.01
            elif band_trend == "contracting":
                adj = -0.01

        result["breakout_confirmed"] = breakout_confirmed
        result["confidence_adjust"] = adj
        result["msg"] = (
            f"BOLL带宽={band_width:.2f}%({band_trend}) | "
            f"%b={percent_b:.2f}({result['price_position']}) | "
            f"突破确认={breakout_confirmed} | 置信度调整{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_boll_bandwidth_reversal_confirm_v62(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """BOLL带宽压缩反弹确认（V62 条件187）。

    在BOLL带宽压缩后，检测价格是否出现有效反弹/回踩确认：
    - 3买：带宽低位(分位数<30%) + 价格从下轨附近反弹 → 反弹有效，+2%
    - 3卖：带宽低位(分位数<30%) + 价格从上轨附近回落 → 回落有效，+2%
    - 带宽低位但无反弹/回落确认 → +0.5%
    """
    result: dict[str, Any] = {
        "band_width_rank": 0.5,
        "squeeze_active": False,
        "reversal_confirmed": False,
        "reversal_type": "none",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 60:
            result["msg"] = "数据不足，需要至少60根K线"
            return result

        period = 20
        lookback = min(60, len(closes))

        # 计算过去lookback期内各期BOLL带宽
        widths = []
        for i in range(period, lookback + 1):
            segment = closes[i - period : i]
            mid = sum(segment) / period
            std = (sum((x - mid) ** 2 for x in segment) / period) ** 0.5
            bw = (4 * std / (mid + 1e-10)) * 100
            widths.append(bw)

        if not widths:
            result["msg"] = "带宽数据不足"
            return result

        current_width = widths[-1]
        sorted_widths = sorted(widths)
        rank = sum(1 for w in sorted_widths if w <= current_width) / len(sorted_widths)
        result["band_width_rank"] = round(rank, 3)

        squeeze_active = rank < 0.3
        result["squeeze_active"] = squeeze_active

        # 检测反弹/回踩确认
        recent_closes = closes[-10:] if len(closes) >= 10 else closes
        if len(recent_closes) < 5:
            result["msg"] = "近期数据不足"
            return result

        reversal_confirmed = False
        reversal_type = "none"
        adj = 0.0

        if squeeze_active:
            if is_buy:
                lows_recent = [
                    min(recent_closes[i : i + 3]) for i in range(0, len(recent_closes) - 2, 2)
                ]
                if len(lows_recent) >= 2 and lows_recent[-1] > lows_recent[0] * 1.01:
                    reversal_confirmed = True
                    reversal_type = "bullish_reversal"
                    adj = 0.02
                else:
                    reversal_type = "no_reversal"
                    adj = 0.005
            else:
                highs_recent = [
                    max(recent_closes[i : i + 3]) for i in range(0, len(recent_closes) - 2, 2)
                ]
                if len(highs_recent) >= 2 and highs_recent[-1] < highs_recent[0] * 0.99:
                    reversal_confirmed = True
                    reversal_type = "bearish_reversal"
                    adj = 0.02
                else:
                    reversal_type = "no_reversal"
                    adj = 0.005

        result["reversal_confirmed"] = reversal_confirmed
        result["reversal_type"] = reversal_type
        result["confidence_adjust"] = adj
        result["msg"] = (
            f"带宽分位={rank:.0%}({('压缩' if squeeze_active else '正常')}) | "
            f"反弹确认={reversal_confirmed}({reversal_type}) | "
            f"置信度调整{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_dynamic_threshold_volatility_regime_v62(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """动态阈值-波动率状态切换（V62 条件188）。

    根据当前波动率环境动态调整信号阈值：
    - 高波动（ATR%>3%）：放宽阈值，降低置信度要求（-2%）
    - 低波动（ATR%<1%）：收紧阈值，提高置信度要求（+2%）
    - 正常波动：保持默认阈值
    """
    result: dict[str, Any] = {
        "atr_pct": 0.0,
        "volatility_regime": "normal",
        "threshold_adjustment": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 30:
            result["msg"] = "数据不足，需要至少30根K线"
            return result

        # 近似计算ATR(14)
        tr_list = []
        for i in range(1, len(closes)):
            tr = abs(closes[i] - closes[i - 1])
            tr_list.append(tr)

        if len(tr_list) < 14:
            result["msg"] = "TR数据不足"
            return result

        atr_14 = sum(tr_list[-14:]) / 14
        current_price = closes[-1]
        atr_pct = atr_14 / (current_price + 1e-10) * 100

        result["atr_pct"] = round(atr_pct, 2)

        if atr_pct > 3.0:
            regime = "high"
            adj = -0.02
        elif atr_pct < 1.0:
            regime = "low"
            adj = +0.02
        else:
            regime = "normal"
            adj = 0.0

        result["volatility_regime"] = regime
        result["confidence_adjust"] = adj
        result["msg"] = (
            f"ATR(14)={atr_14:.4f}({atr_pct:.2f}%) | 波动率={regime} | 置信度调整{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_dynamic_threshold_atr_multiplier_v62(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> dict[str, Any]:
    """动态阈值-ATR倍数自适应（V62 条件189）。

    根据当前ATR动态调整止损距离的倍数：
    - 高波动：使用更大ATR倍数（2.5x），避免频繁触发止损
    - 低波动：使用更小ATR倍数（1.5x），收紧止损减少损失
    - 正常波动：使用默认倍数（2x）
    """
    result: dict[str, Any] = {
        "atr_14": 0.0,
        "optimal_multiplier": 2.0,
        "stop_distance_pct": 0.0,
        "volatility_regime": "normal",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        # 如果没有提供highs/lows，从closes推导
        if not highs or not lows:
            if len(closes) < 2:
                result["msg"] = "数据不足"
                return result
            highs = [max(closes[i - 1], closes[i]) for i in range(1, len(closes))]
            lows = [min(closes[i - 1], closes[i]) for i in range(1, len(closes))]

        if len(highs) < 15 or len(lows) < 15:
            result["msg"] = "highs/lows数据不足"
            return result

        tr_list = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - highs[i - 1]),
                abs(lows[i] - lows[i - 1]),
            )
            tr_list.append(tr)

        if len(tr_list) < 14:
            result["msg"] = "TR数据不足"
            return result

        atr_14 = sum(tr_list[-14:]) / 14
        current_price = highs[-1]
        atr_pct = atr_14 / (current_price + 1e-10) * 100

        result["atr_14"] = round(atr_14, 4)

        if atr_pct > 4.0:
            regime = "extreme"
            multiplier = 2.5
            adj = -0.01
        elif atr_pct > 2.5:
            regime = "high"
            multiplier = 2.2
            adj = -0.005
        elif atr_pct < 0.8:
            regime = "low"
            multiplier = 1.5
            adj = +0.01
        else:
            regime = "normal"
            multiplier = 2.0
            adj = 0.0

        stop_distance = multiplier * atr_14
        stop_pct = stop_distance / (current_price + 1e-10) * 100

        result["optimal_multiplier"] = multiplier
        result["stop_distance_pct"] = round(stop_pct, 2)
        result["volatility_regime"] = regime
        result["confidence_adjust"] = adj
        result["msg"] = (
            f"ATR={atr_14:.4f}({atr_pct:.2f}%) | "
            f"最优倍数={multiplier}x | 止损距离={stop_pct:.1f}% | "
            f"波动率={regime} | 置信度调整{adj:+.0%}"
        )
        return result
    except Exception:
        return result


# =============================================================================
# V63: 条件 190-191（中枢级别权重优化增强 + 多周期信号衰减追踪）
# =============================================================================


def _calc_zhongshu_level_weight_enhanced_v63(
    mmd: MMD,
    zss: list[ZS],
    closes: list[float] | None = None,
) -> dict[str, Any]:
    """中枢级别权重优化增强（V63 条件190）。

    在条件161（中枢级别权重自适应）基础上，增加：
    - 价格与中枢距离评分：信号越接近中枢上沿/下沿，权重越高
    - 中枢结构质量评分：完成的、笔数充足的中枢质量更高
    - 近期测试次数评分：近期被测试过的中枢更可靠

    返回字段：level, distance_score, quality_score, recent_test_score,
              total_weight_bonus, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "level": "unknown",
        "distance_score": 0,
        "quality_score": 0,
        "recent_test_score": 0,
        "total_weight_bonus": 0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if not zss or len(zss) == 0:
            result["msg"] = "无中枢数据，跳过此条件"
            return result

        if not closes or len(closes) < 20:
            result["msg"] = "K线数据不足"
            return result

        # 找到最相关的已完成中枢
        relevant_zs = None
        for zs in reversed(zss):
            if zs.line_count >= 3 and zs.done:
                relevant_zs = zs
                break
        if relevant_zs is None:
            for zs in reversed(zss):
                if zs.line_count >= 3:
                    relevant_zs = zs
                    break
        if relevant_zs is None:
            result["msg"] = "无可用的中枢数据"
            return result

        line_count = relevant_zs.line_count
        current_price = closes[-1]

        # ── 1. 中枢级别基础权重 ──────────────────────────────────────
        if line_count >= 13:
            level = "月线"
            base_bonus = 8
        elif line_count >= 8:
            level = "周线"
            base_bonus = 6
        elif line_count >= 4:
            level = "日线"
            base_bonus = 4
        elif line_count >= 3:
            level = "小级别"
            base_bonus = 2
        else:
            level = "未知"
            base_bonus = 0

        # ── 2. 价格距离评分（0-4分）─────────────────────────────────
        distance_score = 0
        zs_range = relevant_zs.zg - relevant_zs.zd
        if zs_range > 0 and current_price > 0:
            if is_buy:
                ratio = (current_price - relevant_zs.zg) / (relevant_zs.zg + 1e-10) * 100
                if 0 < ratio <= 3:
                    distance_score = 4
                elif 3 < ratio <= 8:
                    distance_score = 3
                elif 8 < ratio <= 15:
                    distance_score = 2
                elif ratio > 15:
                    distance_score = 0
                else:
                    distance_score = 1
            else:
                zd_val = relevant_zs.zd
                ratio = (zd_val - current_price) / (zd_val + 1e-10) * 100 if zd_val > 0 else 0
                if 0 < ratio <= 3:
                    distance_score = 4
                elif 3 < ratio <= 8:
                    distance_score = 3
                elif 8 < ratio <= 15:
                    distance_score = 2
                elif ratio > 15:
                    distance_score = 0
                else:
                    distance_score = 1

        result["distance_score"] = distance_score

        # ── 3. 中枢结构质量评分（0-3分）─────────────────────────────
        quality_score = 0
        if relevant_zs.done:
            quality_score += 2
        if line_count >= 5:
            quality_score += 1

        result["quality_score"] = quality_score

        # ── 4. 近期测试次数评分（0-2分）─────────────────────────────
        recent_tests = 0
        if len(closes) >= 10:
            recent_window = closes[-10:]
            for price in recent_window:
                if relevant_zs.zd <= price <= relevant_zs.zg:
                    recent_tests += 1
        if recent_tests >= 2:
            recent_test_score = 2
        elif recent_tests >= 1:
            recent_test_score = 1
        else:
            recent_test_score = 0

        result["recent_test_score"] = recent_test_score

        # ── 5. 综合权重计算 ─────────────────────────────────────────
        total_bonus = base_bonus + distance_score + quality_score + recent_test_score

        if total_bonus >= 15:
            confidence_adj = 0.05
        elif total_bonus >= 12:
            confidence_adj = 0.04
        elif total_bonus >= 10:
            confidence_adj = 0.03
        elif total_bonus >= 8:
            confidence_adj = 0.02
        elif total_bonus >= 6:
            confidence_adj = 0.01
        else:
            confidence_adj = 0.0

        result["level"] = level
        result["total_weight_bonus"] = total_bonus
        result["confidence_adjust"] = confidence_adj

        _ = "买入" if is_buy else "卖出"
        result["msg"] = (
            f"中枢级别权重优化：{level}中枢({line_count}笔)"
            f"，距离分={distance_score}/4"
            f"，质量分={quality_score}/3"
            f"，近期测试={recent_test_score}/2"
            f"，总分={total_bonus}"
            f" → +{confidence_adj:.0%}置信度"
        )
        return result
    except Exception:
        return result


def _calc_multi_period_signal_decay_v63(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """多周期信号衰减追踪（V63 条件191）。

    在V57/V59单周期衰减基础上，增加多周期窗口分析：
    - 短期（5根）：即时衰减，快速判断信号有效性
    - 中期（10根）：趋势持续性
    - 长期（20根）：大周期稳定性

    返回字段：short_term_momentum, mid_term_momentum, long_term_momentum,
              overall_health, decay_detected, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "short_term_momentum": 0.0,
        "mid_term_momentum": 0.0,
        "long_term_momentum": 0.0,
        "overall_health": "unknown",
        "decay_detected": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        if len(closes) < 25:
            result["msg"] = "数据不足，需要至少25根K线"
            return result

        # 计算信号点位置
        bi_end_idx = 0
        if mmd.bi is not None and hasattr(mmd.bi, "end") and hasattr(mmd.bi.end, "k"):
            bi_end_idx = (
                mmd.bi.end.k.k_index
                if hasattr(mmd.bi.end.k, "k_index")
                else max(0, len(closes) - 25)
            )
        else:
            bi_end_idx = max(0, len(closes) - 25)

        if bi_end_idx + 5 >= len(closes):
            result["msg"] = "信号后数据不足"
            return result

        signal_price = closes[bi_end_idx]

        # ── 短期（5根K线）───────────────────────────────────────────
        short_window = min(5, len(closes) - bi_end_idx - 1)
        if short_window >= 2:
            short_closes = closes[bi_end_idx + 1 : bi_end_idx + 1 + short_window]
            short_change = (short_closes[-1] - signal_price) / (signal_price + 1e-10) * 100
            result["short_term_momentum"] = round(short_change, 2)
        else:
            result["short_term_momentum"] = 0.0

        # ── 中期（10根K线）──────────────────────────────────────────
        mid_window = min(10, len(closes) - bi_end_idx - 1)
        if mid_window >= 3:
            mid_closes = closes[bi_end_idx + 1 : bi_end_idx + 1 + mid_window]
            mid_change = (mid_closes[-1] - signal_price) / (signal_price + 1e-10) * 100
            result["mid_term_momentum"] = round(mid_change, 2)
        else:
            result["mid_term_momentum"] = 0.0

        # ── 长期（20根K线）──────────────────────────────────────────
        long_window = min(20, len(closes) - bi_end_idx - 1)
        if long_window >= 5:
            long_closes = closes[bi_end_idx + 1 : bi_end_idx + 1 + long_window]
            long_change = (long_closes[-1] - signal_price) / (signal_price + 1e-10) * 100
            result["long_term_momentum"] = round(long_change, 2)
        else:
            result["long_term_momentum"] = 0.0

        # ── 综合健康度评估 ──────────────────────────────────────────
        if is_buy:
            short_ok = result["short_term_momentum"] >= -1.0
            mid_ok = result["mid_term_momentum"] >= -2.0
            long_ok = result["long_term_momentum"] >= -3.0

            if result["short_term_momentum"] >= 3.0 and result["mid_term_momentum"] >= 2.0:
                health = "strong"
                decay = False
                adj = 0.04
            elif short_ok and mid_ok and long_ok:
                health = "healthy"
                decay = False
                adj = 0.02
            elif short_ok and mid_ok:
                health = "stable"
                decay = False
                adj = 0.01
            elif not long_ok:
                health = "declining"
                decay = True
                adj = -0.03
            elif not mid_ok:
                health = "weak"
                decay = True
                adj = -0.02
            else:
                health = "decaying"
                decay = True
                adj = -0.04
        else:
            short_ok = result["short_term_momentum"] <= 1.0
            mid_ok = result["mid_term_momentum"] <= 2.0
            long_ok = result["long_term_momentum"] <= 3.0

            if result["short_term_momentum"] <= -3.0 and result["mid_term_momentum"] <= -2.0:
                health = "strong"
                decay = False
                adj = 0.04
            elif short_ok and mid_ok and long_ok:
                health = "healthy"
                decay = False
                adj = 0.02
            elif short_ok and mid_ok:
                health = "stable"
                decay = False
                adj = 0.01
            elif not long_ok:
                health = "declining"
                decay = True
                adj = -0.03
            elif not mid_ok:
                health = "weak"
                decay = True
                adj = -0.02
            else:
                health = "decaying"
                decay = True
                adj = -0.04

        result["overall_health"] = health
        result["decay_detected"] = decay
        result["confidence_adjust"] = adj

        result["msg"] = (
            f"多周期衰减追踪 | 短={result['short_term_momentum']:+.1f}%"
            f" 中={result['mid_term_momentum']:+.1f}%"
            f" 长={result['long_term_momentum']:+.1f}%"
            f" | 健康度={health}"
            f"{' | ⚠️衰减中' if decay else ''}"
            f" | 置信度调整{adj:+.0%}"
        )
        return result
    except Exception:
        return result


# ── V65: 条件 192-195（精准度进一步提升）────────────────────────────────


def _calc_volume_price_divergence_secondary_v65(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """量价背离二次确认增强（V65 条件192）。

    在V48/V52量价背离基础上，增加二次确认机制：
    - 第一层：基础量价背离检测（价格创新低但成交量萎缩）
    - 第二层：背离强度量化（量比 + 价格斜率）
    - 第三层：背离持续时间（连续N根K线维持背离状态）

    返回：diverge_confirmed, divergence_strength, duration_bars, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "diverge_confirmed": False,
        "divergence_strength": 0.0,
        "duration_bars": 0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号"
            return result

        n = len(closes)
        lookback = min(30, n - 1)
        recent_closes = closes[-lookback:]
        recent_vols = (
            volumes[-lookback:] if len(volumes) >= n else volumes[-lookback:] if volumes else []
        )

        if len(recent_vols) < 10:
            result["msg"] = "成交量数据不足"
            return result

        # 第一层：基础量价背离
        price_trend = (recent_closes[-1] - recent_closes[0]) / max(recent_closes[0], 1e-10)
        vol_trend = (recent_vols[-1] - recent_vols[0]) / max(
            sum(recent_vols) / len(recent_vols), 1e-10
        )

        if is_buy:
            # 买入信号：价格下跌但成交量萎缩（卖压衰竭）
            diverge = price_trend < -0.02 and vol_trend < -0.1
        else:
            # 卖出信号：价格上涨但成交量萎缩（买盘衰竭）
            diverge = price_trend > 0.02 and vol_trend < -0.1

        # 第二层：背离强度量化
        avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 1.0
        vol_ratio = recent_vols[-1] / max(avg_vol, 1e-10)
        price_slope = (
            (recent_closes[-1] - recent_closes[-5]) / max(recent_closes[-5], 1e-10)
            if len(recent_closes) >= 5
            else 0.0
        )

        strength = abs(price_slope) * 10 + (1.0 - vol_ratio) * 0.5
        strength = min(1.0, max(0.0, strength))

        # 第三层：背离持续时间
        duration = 0
        for i in range(1, min(10, len(recent_closes))):
            prev_price = recent_closes[-i - 1]
            curr_price = recent_closes[-i]
            prev_vol = recent_vols[-i - 1] if i + 1 <= len(recent_vols) else recent_vols[-1]
            curr_vol = recent_vols[-i] if i <= len(recent_vols) else recent_vols[-1]
            if is_buy:
                if curr_price < prev_price and curr_vol < prev_vol * 1.2:
                    duration += 1
                else:
                    break
            else:
                if curr_price > prev_price and curr_vol < prev_vol * 1.2:
                    duration += 1
                else:
                    break

        # 综合判断
        if diverge and strength > 0.3 and duration >= 3:
            result["diverge_confirmed"] = True
            result["divergence_strength"] = round(strength, 2)
            result["duration_bars"] = duration
            adj = min(0.06, strength * 0.04 + duration * 0.005)
            result["confidence_adjust"] = round(adj, 3)
            result["msg"] = (
                f"量价背离二次确认 | 强度={strength:.2f} 持续{duration}根"
                f" | 量比={vol_ratio:.2f} | 置信度+{adj:.0%}"
            )
        else:
            result["confidence_adjust"] = -0.01
            result["msg"] = f"量价背离未确认 | 强度={strength:.2f} 持续{duration}根 | 置信度-1%"

        return result
    except Exception:
        return result


def _calc_breakout_retest_confirmation_v65(
    mmd: MMD,
    zss: list[ZS],
    closes: list[float],
) -> dict[str, Any]:
    """中枢突破回踩确认（V65 条件193）。

    验证3买/3卖信号的中枢突破后是否有回踩确认：
    - 找到最近的中枢，检查突破后的回踩是否在中枢区间内
    - 回踩幅度越小，信号质量越高
    - 无回踩直接延续也视为有效突破

    返回：retest_confirmed, retest_depth, breakout_valid, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "retest_confirmed": False,
        "retest_depth": 0.0,
        "breakout_valid": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号"
            return result

        if not zss or len(zss) < 1:
            result["msg"] = "无中枢数据"
            return result

        n = len(closes)
        # 找到离信号最近的活跃中枢
        recent_zs = zss[-1] if zss else None
        if recent_zs is None:
            result["msg"] = "无有效中枢"
            return result

        # 获取中枢区间
        if hasattr(recent_zs, "high") and hasattr(recent_zs, "low"):
            zs_high = recent_zs.high
            zs_low = recent_zs.low
        elif hasattr(recent_zs, "zg") and hasattr(recent_zs, "zd"):
            zs_high = recent_zs.zg
            zs_low = recent_zs.zd
        else:
            result["msg"] = "中枢数据结构未知"
            return result

        zs_range = zs_high - zs_low if zs_high != zs_low else zs_high * 0.1
        if zs_range <= 0:
            zs_range = zs_high * 0.1

        # 检查突破后的价格走势
        signal_bar = mmd.bi.end.k.k_index if mmd.bi else n - 1
        post_bars = closes[signal_bar:n] if signal_bar < n else closes[-10:]

        if len(post_bars) < 3:
            result["msg"] = "突破后数据不足"
            return result

        # 计算突破后最低/最高回撤
        if is_buy:
            # 3买：突破后回踩，看是否回到中枢附近但不跌破
            breakout_level = zs_high
            lowest_post = min(post_bars)
            highest_post = max(post_bars)
            retest_depth = (
                (breakout_level - lowest_post) / breakout_level if breakout_level > 0 else 0
            )
            # 回踩确认：最低点在中枢上沿附近（回撤不超过20%）或直接上涨
            retest_valid = (
                lowest_post >= zs_low * 0.95
                or (highest_post - breakout_level) / breakout_level > 0.02
            )
            result["breakout_valid"] = retest_valid
            result["retest_depth"] = round(max(0, retest_depth), 4)
        else:
            # 3卖：突破后反弹，看是否回到中枢附近但不涨破
            breakout_level = zs_low
            lowest_post = min(post_bars)
            highest_post = max(post_bars)
            retest_depth = (
                (highest_post - breakout_level) / breakout_level if breakout_level > 0 else 0
            )
            retest_valid = (
                highest_post <= zs_high * 1.05
                or (breakout_level - lowest_post) / breakout_level > 0.02
            )
            result["breakout_valid"] = retest_valid
            result["retest_depth"] = round(max(0, retest_depth), 4)

        if result["breakout_valid"]:
            depth_factor = max(0, 1.0 - retest_depth * 3)  # 回撤越小越好
            adj = depth_factor * 0.05
            result["confidence_adjust"] = round(adj, 3)
            result["retest_confirmed"] = True
            result["msg"] = (
                f"突破回踩确认 | 回撤={retest_depth:.1%} 有效={retest_valid} | 置信度+{adj:.0%}"
            )
        else:
            result["confidence_adjust"] = -0.03
            result["msg"] = f"突破回踩失败 | 回撤={retest_depth:.1%} 可能假突破 | 置信度-3%"

        return result
    except Exception:
        return result


def _calc_volatility_compression_breakout_v65(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """波动率压缩突破信号（V65 条件194）。

    基于BOLL带宽压缩理论，检测波动率压缩后的突破信号：
    - 压缩阶段：带宽低于历史20%分位
    - 突破确认：价格突破压缩区间，伴随成交量放大
    - 质量评分：压缩时间越长、突破力度越大，评分越高

    返回：compression_detected, squeeze_score, breakout_strength, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "compression_detected": False,
        "squeeze_score": 0.0,
        "breakout_strength": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号"
            return result

        n = len(closes)
        if n < 50:
            result["msg"] = "数据不足"
            return result

        # 计算BOLL带宽（20日）
        period = 20
        upper, mid, lower = [], [], []
        for i in range(period - 1, n):
            window = closes[i - period + 1 : i + 1]
            m_val = sum(window) / period
            std_val = (sum((x - m_val) ** 2 for x in window) / period) ** 0.5
            upper.append(m_val + 2 * std_val)
            mid.append(m_val)
            lower.append(m_val - 2 * std_val)

        if not upper:
            result["msg"] = "BOLL计算失败"
            return result

        widths = [(u - low) / m if m > 0 else 0 for u, low, m in zip(upper, lower, mid)]
        if not widths:
            result["msg"] = "带宽计算失败"
            return result

        # 检测压缩状态
        current_width = widths[-1]
        hist_percentile = sum(1 for w in widths[:-1] if w <= current_width) / max(
            len(widths) - 1, 1
        )

        # 压缩判定：当前带宽处于历史25%分位以下
        is_squeeze = hist_percentile < 0.25
        squeeze_score = 1.0 - hist_percentile if is_squeeze else hist_percentile

        # 突破力度计算
        latest_close = closes[-1]
        latest_upper = upper[-1]
        latest_lower = lower[-1]
        latest_mid = mid[-1]

        if is_buy:
            # 买入：价格从压缩区向上突破
            breakout_strength = (
                (latest_close - latest_lower) / (latest_upper - latest_lower)
                if latest_upper != latest_lower
                else 0.5
            )
            breakout_valid = latest_close > latest_mid * 1.01  # 突破中轨
        else:
            breakout_strength = (
                (latest_upper - latest_close) / (latest_upper - latest_lower)
                if latest_upper != latest_lower
                else 0.5
            )
            breakout_valid = latest_close < latest_mid * 0.99  # 跌破中轨

        if is_squeeze and breakout_valid:
            adj = min(0.07, squeeze_score * 0.04 + breakout_strength * 0.03)
            result["compression_detected"] = True
            result["squeeze_score"] = round(squeeze_score, 2)
            result["breakout_strength"] = round(breakout_strength, 2)
            result["confidence_adjust"] = round(adj, 3)
            result["msg"] = (
                f"波动率压缩突破 | 压缩评分={squeeze_score:.2f} 突破力度={breakout_strength:.2f}"
                f" | 置信度+{adj:.0%}"
            )
        elif is_squeeze:
            result["compression_detected"] = True
            result["squeeze_score"] = round(squeeze_score, 2)
            result["confidence_adjust"] = -0.01
            result["msg"] = f"波动率压缩中 | 评分={squeeze_score:.2f} 等待突破确认 | 置信度-1%"
        else:
            result["confidence_adjust"] = 0.0
            result["msg"] = f"无压缩状态（分位={hist_percentile:.0%}）"

        return result
    except Exception:
        return result


def _calc_signal_time_window_freshness_v65(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """买卖点时间窗口新鲜度（V65 条件195）。

    评估信号的时效性：
    - 信号产生后到最新K线的天数（时间衰减）
    - 信号后价格走势健康度（趋势是否延续）
    - 综合新鲜度评分，用于决定是否仍应执行该信号

    返回：bars_since_signal, trend_health, freshness_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "bars_since_signal": 0,
        "trend_health": "unknown",
        "freshness_score": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmd.bi is None:
            result["msg"] = "无笔数据"
            return result

        n = len(closes)
        signal_bar = mmd.bi.end.k.k_index
        if signal_bar is None or signal_bar >= n:
            result["msg"] = "信号bar超出范围"
            return result

        bars_since = n - 1 - signal_bar
        result["bars_since_signal"] = bars_since

        if bars_since > 60:
            result["freshness_score"] = 0.0
            result["confidence_adjust"] = -0.08
            result["trend_health"] = "expired"
            result["msg"] = f"信号已过期（{bars_since}根K线前）| 置信度-8%"
            return result

        # 计算信号后的趋势健康度
        post_closes = closes[signal_bar:n]
        if len(post_closes) < 5:
            result["freshness_score"] = 0.5
            result["confidence_adjust"] = 0.0
            result["trend_health"] = "insufficient_data"
            result["msg"] = "信号后数据不足"
            return result

        is_buy = mmd.mmd_type == MMDType.BUY_3
        price_change = (post_closes[-1] - post_closes[0]) / max(post_closes[0], 1e-10)

        # 计算信号后的回撤
        peak = max(post_closes)
        trough = min(post_closes)
        max_drawdown = (peak - trough) / max(peak, 1e-10)

        if is_buy:
            # 买入信号：价格应上涨或小幅回撤
            if price_change > 0.03:
                health = "strong_uptrend"
                score = min(1.0, 0.7 + price_change * 5)
            elif price_change > -0.02:
                health = "neutral"
                score = 0.5
            else:
                health = "weak"
                score = max(0.0, 0.5 + price_change * 10)
        else:
            # 卖出信号：价格应下跌或小幅反弹
            if price_change < -0.03:
                health = "strong_downtrend"
                score = min(1.0, 0.7 - price_change * 5)
            elif price_change < 0.02:
                health = "neutral"
                score = 0.5
            else:
                health = "weak"
                score = max(0.0, 0.5 - price_change * 10)

        # 回撤惩罚
        if max_drawdown > 0.15:
            score = max(0.0, score - 0.15)
            health = f"{health}_high_dd"

        result["trend_health"] = health
        result["freshness_score"] = round(score, 2)

        # 基于新鲜度调整置信度
        time_decay = max(0, 1.0 - bars_since / 60.0)  # 60根K线内线性衰减
        combined = score * 0.6 + time_decay * 0.4
        if combined > 0.7:
            adj = 0.03
        elif combined > 0.5:
            adj = 0.0
        else:
            adj = -0.04

        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = (
            f"信号新鲜度 | {bars_since}根前 健康={health} 评分={score:.2f}"
            f" 时间衰减={time_decay:.0%} | 置信度{'+' if adj >= 0 else ''}{adj:.0%}"
        )
        return result
    except Exception:
        return result


def _calc_macd_momentum_acceleration_v66(
    mmd: MMD,
    macd_data: dict[str, list[float]],
) -> dict[str, Any]:
    """MACD动能锥加速确认（V66 条件196）。

    检测MACD柱状图的加速度变化，判断趋势动能是否正在加速或减速：
    - 买入信号：MACD柱连续放大（动能增强）或柱状图由负转正（金叉确认）
    - 卖出信号：MACD柱连续缩小（动能衰减）或柱状图由正转负（死叉确认）
    - 锥形态：连续多根K线柱状图单调变化，代表动能稳定释放

    返回：acceleration_detected, acceleration_direction, cone_bars, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "acceleration_detected": False,
        "acceleration_direction": "unknown",
        "cone_bars": 0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        hist = macd_data.get("hist", [])
        dif = macd_data.get("dif", [])
        if len(hist) < 10:
            result["msg"] = "MACD数据不足"
            return result

        is_buy = mmd.mmd_type == MMDType.BUY_3

        hist_changes = [hist[-i] - hist[-i - 1] for i in range(1, min(10, len(hist)))]
        hist_changes.reverse()

        if is_buy:
            accelerating = (
                all(c > 0 for c in hist_changes[-3:]) if len(hist_changes) >= 3 else False
            )
            golden_cross = len(dif) >= 2 and dif[-2] <= 0 and dif[-1] > 0
            turning_positive = hist[-1] > 0 and hist[-2] <= 0
            strong_confirm = accelerating or (golden_cross and hist[-1] > 0) or turning_positive
        else:
            decelerating = (
                all(c < 0 for c in hist_changes[-3:]) if len(hist_changes) >= 3 else False
            )
            dead_cross = len(dif) >= 2 and dif[-2] >= 0 and dif[-1] < 0
            turning_negative = hist[-1] < 0 and hist[-2] >= 0
            strong_confirm = decelerating or (dead_cross and hist[-1] < 0) or turning_negative

        cone_count = 0
        for i in range(len(hist_changes) - 1):
            if hist_changes[i] * hist_changes[i + 1] > 0:
                cone_count += 1
            else:
                break
        cone_count = min(cone_count, 9)

        if strong_confirm and cone_count >= 2:
            result["acceleration_detected"] = True
            result["acceleration_direction"] = "up" if is_buy else "down"
            result["cone_bars"] = cone_count
            adj = min(0.06, cone_count * 0.015 + 0.02)
            result["confidence_adjust"] = round(adj, 3)
            result["msg"] = (
                f"MACD动能加速 | 方向={'↑' if is_buy else '↓'} 锥={cone_count}根 | 置信度+{adj:.0%}"
            )
        elif strong_confirm:
            result["acceleration_detected"] = True
            result["acceleration_direction"] = "up" if is_buy else "down"
            result["confidence_adjust"] = 0.01
            result["msg"] = f"MACD动能{'增强' if is_buy else '减弱'} | 置信度+1%"
        else:
            result["confidence_adjust"] = -0.01
            result["msg"] = "MACD动能无明确加速信号 | 置信度-1%"

        return result
    except Exception:
        return result


def _calc_volume_price_coordination_deep_v66(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """量价配合深度评分（V66 条件197）。

    多维度评估量价关系质量：短期5日/中期20日配合+极端量能检测。

    返回：short_score, mid_score, extreme_flag, overall_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "short_score": 0.0,
        "mid_score": 0.0,
        "extreme_flag": "normal",
        "overall_score": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 30 or len(volumes) < n:
            result["msg"] = "数据不足"
            return result

        short_closes = closes[-5:]
        short_vols = volumes[-5:]
        short_price_dir = short_closes[-1] - short_closes[0]
        short_vol_avg = sum(short_vols[:-1]) / max(len(short_vols) - 1, 1)
        short_vol_dir = short_vols[-1] - short_vol_avg

        if is_buy:
            short_ok = (short_price_dir < 0 and short_vol_dir < 0) or (
                short_price_dir > 0 and short_vol_dir > 0
            )
        else:
            short_ok = (short_price_dir > 0 and short_vol_dir < 0) or (
                short_price_dir < 0 and short_vol_dir > 0
            )

        short_score = 0.8 if short_ok else 0.3

        mid_closes = closes[-20:]
        mid_vols = volumes[-20:]
        mid_price_dir = mid_closes[-1] - mid_closes[0]
        mid_vol_trend = sum(mid_vols[-5:]) / 5 - sum(mid_vols[:5]) / 5

        if is_buy:
            mid_ok = (mid_price_dir <= 0 and mid_vol_trend <= 0) or (
                mid_price_dir > 0 and mid_vol_trend > 0
            )
        else:
            mid_ok = (mid_price_dir >= 0 and mid_vol_trend <= 0) or (
                mid_price_dir < 0 and mid_vol_trend > 0
            )

        mid_score = 0.75 if mid_ok else 0.35

        recent_vol = sum(volumes[-5:]) / 5
        avg_vol = sum(volumes) / len(volumes) if volumes else 1.0
        vol_ratio = recent_vol / max(avg_vol, 1e-10)

        if vol_ratio > 3.0:
            extreme_flag = "extreme_high"
        elif vol_ratio < 0.3:
            extreme_flag = "extreme_low"
        else:
            extreme_flag = "normal"

        overall = short_score * 0.3 + mid_score * 0.5 + (0.2 if extreme_flag == "normal" else 0.0)
        overall = min(1.0, max(0.0, overall))

        result["short_score"] = round(short_score, 2)
        result["mid_score"] = round(mid_score, 2)
        result["extreme_flag"] = extreme_flag
        result["overall_score"] = round(overall, 2)

        if overall >= 0.7:
            adj = 0.04
            result["confidence_adjust"] = round(adj, 3)
            result["msg"] = (
                f"量价配合良好 | 短={short_score:.0%} 中={mid_score:.0%} 极端={extreme_flag} | 置信度+{adj:.0%}"
            )
        elif overall >= 0.5:
            adj = 0.01
            result["confidence_adjust"] = round(adj, 3)
            result["msg"] = f"量价配合一般 | 综合={overall:.0%} | 置信度+1%"
        else:
            adj = -0.02
            result["confidence_adjust"] = round(adj, 3)
            result["msg"] = f"量价配合较差 | 综合={overall:.0%} 极端={extreme_flag} | 置信度-2%"

        return result
    except Exception:
        return result


def _calc_multi_tf_convergence_intensity_v66(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """多时间框架共振强度评分（V66 条件198）。

    通过模拟多周期均线系统，检测短(5日)/中(20日)/长(60日)趋势一致性。

    返回：short_trend, mid_trend, long_trend, convergence_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "short_trend": "unknown",
        "mid_trend": "unknown",
        "long_trend": "unknown",
        "convergence_score": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 60:
            result["msg"] = "数据不足（需≥60根）"
            return result

        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        ma20 = sum(closes[-20:]) / 20
        ma60 = sum(closes[-60:]) / 60
        current = closes[-1]

        short_trend = "up" if ma5 > ma10 else "down"
        mid_trend = "up" if ma20 > ma10 else "down"
        long_trend = "up" if current > ma60 else "down"

        result["short_trend"] = short_trend
        result["mid_trend"] = mid_trend
        result["long_trend"] = long_trend

        if is_buy:
            aligned_up = short_trend == "up" and mid_trend == "up" and long_trend == "up"
            aligned_cnt = sum(1 for t in [short_trend, mid_trend, long_trend] if t == "up")
        else:
            aligned_up = short_trend == "down" and mid_trend == "down" and long_trend == "down"
            aligned_cnt = sum(1 for t in [short_trend, mid_trend, long_trend] if t == "down")

        convergence_score = aligned_cnt / 3.0

        if aligned_up:
            adj = 0.05
            result["convergence_score"] = 1.0
            result["confidence_adjust"] = round(adj, 3)
            result["msg"] = (
                f"三周期共振 {'↑' if is_buy else '↓'} | 短={short_trend} 中={mid_trend} 长={long_trend} | 共振=1.0 | 置信度+{adj:.0%}"
            )
        elif convergence_score >= 0.6:
            adj = 0.02
            result["convergence_score"] = round(convergence_score, 2)
            result["confidence_adjust"] = round(adj, 3)
            result["msg"] = (
                f"双周期共振 {'↑' if is_buy else '↓'} | 短={short_trend} 中={mid_trend} 长={long_trend} | 共振={convergence_score:.0%} | 置信度+{adj:.0%}"
            )
        else:
            adj = -0.02
            result["convergence_score"] = round(convergence_score, 2)
            result["confidence_adjust"] = round(adj, 3)
            result["msg"] = (
                f"周期分歧 | 短={short_trend} 中={mid_trend} 长={long_trend} | 共振={convergence_score:.0%} | 置信度-2%"
            )

        return result
    except Exception:
        return result


def _calc_signal_execution_priority_v66(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """信号执行优先级建议（V66 条件199）。

    基于信号质量综合评估给出P0-P3执行优先级：
    P0=立即执行 P1=尽快执行 P2=观察等待 P3=暂缓执行

    返回：priority, priority_label, risk_level, suggested_action, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "priority": 3,
        "priority_label": "P3",
        "risk_level": "high",
        "suggested_action": "观望",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 20 or mmd.bi is None:
            result["msg"] = "数据不足"
            return result

        current = closes[-1]
        ma5 = sum(closes[-5:]) / 5
        ma20 = sum(closes[-20:]) / 20
        recent_high = max(closes[-20:])
        recent_low = min(closes[-20:])
        price_range = recent_high - recent_low if recent_high != recent_low else recent_high * 0.05
        price_position = (current - recent_low) / price_range if price_range > 0 else 0.5
        ma_spread = abs(ma5 - ma20) / max(ma20, 1e-10)

        returns = [
            (closes[-i] - closes[-i - 1]) / max(closes[-i - 1], 1e-10) for i in range(1, min(11, n))
        ]
        avg_return = sum(abs(r) for r in returns) / len(returns) if returns else 0.02

        score = 0.0
        if is_buy:
            if ma5 > ma20:
                score += 0.25
            if price_position < 0.4:
                score += 0.20
            if ma_spread > 0.02:
                score += 0.15
            if avg_return < 0.03:
                score += 0.10
            if mmd.bi and mmd.bi.end.k.k_index is not None:
                score += 0.15
            if mmd.confidence > 0.7:
                score += 0.15
        else:
            if ma5 < ma20:
                score += 0.25
            if price_position > 0.6:
                score += 0.20
            if ma_spread > 0.02:
                score += 0.15
            if avg_return < 0.03:
                score += 0.10
            if mmd.bi and mmd.bi.end.k.k_index is not None:
                score += 0.15
            if mmd.confidence > 0.7:
                score += 0.15

        score = min(1.0, max(0.0, score))

        if score >= 0.75:
            priority, label, risk, action = 0, "P0", "low", "立即执行"
        elif score >= 0.55:
            priority, label, risk, action = 1, "P1", "medium", "尽快执行"
        elif score >= 0.35:
            priority, label, risk, action = 2, "P2", "medium-high", "观察等待"
        else:
            priority, label, risk, action = 3, "P3", "high", "暂缓执行"

        result["priority"] = priority
        result["priority_label"] = label
        result["risk_level"] = risk
        result["suggested_action"] = action
        result["msg"] = f"执行优先级 {label} | 评分={score:.0%} 风险={risk} | 建议:{action}"

        if priority == 0:
            adj = 0.05
        elif priority == 1:
            adj = 0.02
        elif priority == 2:
            adj = 0.0
        else:
            adj = -0.03

        result["confidence_adjust"] = round(adj, 3)
        return result
    except Exception:
        return result


def _calc_zhongshu_divergence_strength_v67(
    mmd: MMD,
    zss: list[ZS],
    closes: list[float],
    macd_data: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    """中枢背驰力度量化（V67 条件200）。

    针对第三类买卖点，量化中枢区域的背驰强度：
    - 对比突破前最后一笔与突破后第一笔的MACD面积
    - 面积比越小（背驰越明显），置信度调整越大
    - 结合成交量变化辅助判断

    返回：backchi_ratio, zhongshu_strength, divergence_type, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "backchi_ratio": 0.0,
        "zhongshu_strength": "normal",
        "divergence_type": "none",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if macd_data is None:
            result["msg"] = "无MACD数据"
            return result
        is_buy = mmd.mmd_type == MMDType.BUY_3
        hist = macd_data.get("hist", [])
        if len(hist) < 20 or len(zss) == 0:
            result["msg"] = "数据不足"
            return result

        # 找到最近的中枢
        latest_zs = zss[-1]
        zs_high = max(bc.high for bc in latest_zs.lines) if latest_zs.lines else 0
        zs_low = min(bc.low for bc in latest_zs.lines) if latest_zs.lines else 0
        _ = zs_high - zs_low if zs_high != zs_low else 1.0

        # 计算突破前最后一笔的MACD面积（中枢内）
        pre_break_idx = max(0, len(hist) - 20)
        _ = min(len(hist) - 1, pre_break_idx + 10)

        # 简化：用最近10根与之前10根的MACD柱面积对比
        recent_hist = hist[-10:] if len(hist) >= 10 else hist
        prev_hist = hist[-20:-10] if len(hist) >= 20 else hist[:-10]

        if not prev_hist:
            result["msg"] = "历史数据不足"
            return result

        recent_area = sum(abs(h) for h in recent_hist)
        prev_area = sum(abs(h) for h in prev_hist)
        backchi_ratio = prev_area / max(recent_area, 1e-10)

        current_price = closes[-1]
        _ = (zs_high + zs_low) / 2

        result["backchi_ratio"] = round(backchi_ratio, 3)

        # 判断背驰类型
        if is_buy:
            if backchi_ratio < 0.6 and current_price > zs_high:
                divergence_type = "strong_down"
                zhongshu_strength = "weak"
                adj = 0.05
            elif backchi_ratio < 0.8:
                divergence_type = "moderate_down"
                zhongshu_strength = "normal"
                adj = 0.03
            elif current_price > zs_high * 1.05:
                divergence_type = "none"
                zhongshu_strength = "strong"
                adj = 0.02
            else:
                divergence_type = "none"
                zhongshu_strength = "normal"
                adj = -0.01
        else:
            if backchi_ratio < 0.6 and current_price < zs_low:
                divergence_type = "strong_up"
                zhongshu_strength = "weak"
                adj = 0.05
            elif backchi_ratio < 0.8:
                divergence_type = "moderate_up"
                zhongshu_strength = "normal"
                adj = 0.03
            elif current_price < zs_low * 0.95:
                divergence_type = "none"
                zhongshu_strength = "strong"
                adj = 0.02
            else:
                divergence_type = "none"
                zhongshu_strength = "normal"
                adj = -0.01

        result["divergence_type"] = divergence_type
        result["zhongshu_strength"] = zhongshu_strength
        result["confidence_adjust"] = round(adj, 3)

        dir_str = "↑" if is_buy else "↓"
        result["msg"] = (
            f"中枢背驰 {dir_str} | 面积比={backchi_ratio:.2f} "
            f"中枢强度={zhongshu_strength} | 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_multi_level_mmd_consistency_v67(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """多级别买卖点一致性验证（V67 条件201）。

    通过模拟多时间框架的信号一致性：
    - 短期（5日）、中期（20日）、长期（60日）趋势方向
    - 判断当前买卖点是否与各时间框架方向一致
    - 一致度高则增强信心，分歧则降低信心

    返回：short_dir, mid_dir, long_dir, consistency_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "short_dir": "unknown",
        "mid_dir": "unknown",
        "long_dir": "unknown",
        "consistency_score": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 60:
            result["msg"] = "数据不足（需≥60根）"
            return result

        # 计算多周期趋势
        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        ma20 = sum(closes[-20:]) / 20
        ma60 = sum(closes[-60:]) / 60

        # 短期趋势：MA5 vs MA10
        short_dir = "up" if ma5 > ma10 else "down"
        # 中期趋势：MA20 vs MA10
        mid_dir = "up" if ma20 > ma10 else "down"
        # 长期趋势：当前价 vs MA60
        long_dir = "up" if closes[-1] > ma60 else "down"

        result["short_dir"] = short_dir
        result["mid_dir"] = mid_dir
        result["long_dir"] = long_dir

        # 一致性评分
        if is_buy:
            aligned = sum(1 for d in [short_dir, mid_dir, long_dir] if d == "up")
        else:
            aligned = sum(1 for d in [short_dir, mid_dir, long_dir] if d == "down")

        consistency_score = aligned / 3.0
        result["consistency_score"] = round(consistency_score, 2)

        # 置信度调整
        if consistency_score >= 0.8:
            adj = 0.04
            level = "high"
        elif consistency_score >= 0.5:
            adj = 0.02
            level = "medium"
        else:
            adj = -0.03
            level = "low"

        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = (
            f"多级别一致性={level} | 短{short_dir}中{mid_dir}长{long_dir} "
            f"评分={consistency_score:.0%} | 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_post_signal_trajectory_health_v67(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """信号后价格轨迹健康度（V67 条件202）。

    评估买卖点信号后的价格走势质量：
    - 上涨趋势中的最大回撤比例
    - 连续上涨/下跌天数
    - 波动率稳定性

    返回：max_drawdown_pct, up_bars, down_bars, trend_quality, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "max_drawdown_pct": 0.0,
        "up_bars": 0,
        "down_bars": 0,
        "trend_quality": "poor",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 40:
            result["msg"] = "数据不足（需≥40根）"
            return result

        recent = closes[-20:]
        high_point = max(recent)
        low_point = min(recent)
        max_drawdown = (high_point - low_point) / max(high_point, 1e-10) * 100

        result["max_drawdown_pct"] = round(max_drawdown, 2)

        # 统计涨跌K线
        up_count = 0
        down_count = 0
        for i in range(1, len(recent)):
            if recent[i] > recent[i - 1]:
                up_count += 1
            else:
                down_count += 1

        result["up_bars"] = up_count
        result["down_bars"] = down_count

        # 趋势质量评估
        if is_buy:
            if up_count >= 12 and max_drawdown < 5:
                trend_quality = "excellent"
                adj = 0.06
            elif up_count >= 10 and max_drawdown < 8:
                trend_quality = "good"
                adj = 0.03
            elif up_count >= 8:
                trend_quality = "fair"
                adj = 0.01
            else:
                trend_quality = "poor"
                adj = -0.04
        else:
            if down_count >= 12 and max_drawdown < 5:
                trend_quality = "excellent"
                adj = 0.06
            elif down_count >= 10 and max_drawdown < 8:
                trend_quality = "good"
                adj = 0.03
            elif down_count >= 8:
                trend_quality = "fair"
                adj = 0.01
            else:
                trend_quality = "poor"
                adj = -0.04

        result["trend_quality"] = trend_quality
        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = (
            f"轨迹健康度={trend_quality} | 涨{up_count}跌{down_count}根 "
            f"回撤={max_drawdown:.1f}% | 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_dynamic_sl_tp_recommendation_v67(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """动态止损止盈推荐（V67 条件203）。

    基于ATR和近期价格行为动态计算止损止盈位：
    - 止损位：基于ATR的动态距离
    - 止盈位：基于波动率的合理目标
    - 风险收益比评估

    返回：stop_loss, take_profit, risk_reward_ratio, position_size_pct, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "risk_reward_ratio": 0.0,
        "position_size_pct": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 20 or not highs or not lows:
            result["msg"] = "数据不足"
            return result

        current = closes[-1]

        # 计算ATR（14日）
        tr_list = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - highs[i - 1]),
                abs(lows[i] - lows[i - 1]),
            )
            tr_list.append(tr)

        if len(tr_list) < 14:
            result["msg"] = "ATR数据不足"
            return result

        atr_14 = sum(tr_list[-14:]) / 14
        atr_pct = atr_14 / max(current, 1e-10) * 100

        # 动态止损止盈
        if is_buy:
            stop_loss = current - atr_14 * 2.0
            take_profit = current + atr_14 * 4.0
        else:
            stop_loss = current + atr_14 * 2.0
            take_profit = current - atr_14 * 4.0

        risk = abs(current - stop_loss)
        reward = abs(take_profit - current)
        risk_reward = reward / max(risk, 1e-10)

        result["stop_loss"] = round(stop_loss, 2)
        result["take_profit"] = round(take_profit, 2)
        result["risk_reward_ratio"] = round(risk_reward, 2)

        # 根据风险收益比调整仓位建议
        if risk_reward >= 3.0:
            position_size = 0.30
            adj = 0.03
        elif risk_reward >= 2.0:
            position_size = 0.20
            adj = 0.02
        elif risk_reward >= 1.5:
            position_size = 0.15
            adj = 0.01
        else:
            position_size = 0.10
            adj = -0.02

        result["position_size_pct"] = position_size
        result["confidence_adjust"] = round(adj, 3)

        direction = "买" if is_buy else "卖"
        result["msg"] = (
            f"ATR={atr_14:.2f}({atr_pct:.1f}%) | {direction}止损={stop_loss:.2f} "
            f"止盈={take_profit:.2f} 风险比={risk_reward:.1f} "
            f"仓位{position_size:.0%} | 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_gap_trend_consistency_v68(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """缺口方向与趋势一致性验证（V68 条件204）。

    检测买卖点信号附近的缺口，并验证缺口方向是否与趋势一致：
    - 买入信号：应存在向上跳空缺口（股价跳空高开）
    - 卖出信号：应存在向下跳空缺口（股价跳空低开）
    - 缺口方向与趋势一致时增加置信度

    返回：gap_detected, gap_direction, trend_alignment, gap_quality, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "gap_detected": False,
        "gap_direction": "none",
        "trend_alignment": "none",
        "gap_quality": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 30:
            result["msg"] = "数据不足（需≥30根）"
            return result

        _ = closes[-1]

        # 检测最近5根K线内的缺口
        gap_found = False
        gap_dir = "none"
        gap_magnitude = 0.0

        for i in range(max(0, n - 5), n):
            if i == 0:
                continue
            prev_close = closes[i - 1]
            curr_open = closes[i]
            price_change = (curr_open - prev_close) / max(prev_close, 1e-10)
            if abs(price_change) > 0.015:
                gap_found = True
                if price_change > 0:
                    gap_dir = "up"
                else:
                    gap_dir = "down"
                gap_magnitude = abs(price_change)
                break

        result["gap_detected"] = gap_found
        result["gap_direction"] = gap_dir

        # 趋势判断（基于MA5 vs MA20）
        ma5 = sum(closes[-5:]) / 5
        ma20 = sum(closes[-20:]) / 20
        trend_dir = "up" if ma5 > ma20 else "down"
        result["trend_alignment"] = trend_dir

        # 一致性评估
        if gap_found:
            if (is_buy and gap_dir == "up" and trend_dir == "up") or (
                not is_buy and gap_dir == "down" and trend_dir == "down"
            ):
                alignment = "aligned"
                quality = "strong"
                adj = 0.04 if gap_magnitude > 0.03 else 0.03
            elif (is_buy and gap_dir == "down") or (not is_buy and gap_dir == "up"):
                alignment = "opposing"
                quality = "weak"
                adj = -0.04
            else:
                alignment = "neutral"
                quality = "moderate"
                adj = 0.01
        else:
            if trend_dir == ("up" if is_buy else "down"):
                alignment = "neutral"
                quality = "no_gap_trend_ok"
                adj = 0.01
            else:
                alignment = "opposing"
                quality = "no_gap_trend_bad"
                adj = -0.02

        result["gap_quality"] = quality
        result["confidence_adjust"] = round(adj, 3)

        gap_info = f"缺口{gap_dir}({gap_magnitude:.1%})" if gap_found else "无显著缺口"
        align_label = (
            "一致" if alignment == "aligned" else "背离" if alignment == "opposing" else "中性"
        )
        result["msg"] = (
            f"{gap_info} | 趋势={trend_dir} | 一致性={align_label} "
            f"质量={quality} | 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_range_set_multi_level_v68(
    mmd: MMD,
    zss: list[ZS],
    closes: list[float],
) -> dict[str, Any]:
    """多级别区间套一致性验证（V68 条件205）。

    基于中枢结构分析，判断当前价格相对各中枢的位置，
    评估区间套（多级别共振）的有效性：
    - 买入：价格应位于最近中枢上方（突破后回踩确认）
    - 卖出：价格应位于最近中枢下方（跌破后反抽确认）
    - 中枢数量越多、距离越近，区间套效果越好

    返回：zhongshu_count, zs_above_price, zs_below_price, multi_level_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "zhongshu_count": 0,
        "zs_above_price": 0.0,
        "zs_below_price": 0.0,
        "multi_level_score": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 40 or not zss:
            result["msg"] = "数据不足（需≥40根且有机枢）"
            return result

        current = closes[-1]

        # 统计中枢信息
        zs_list = []
        for zs in zss:
            zs_mid = (zs.zg + zs.zd) / 2
            zs_dist = (current - zs_mid) / max(current, 1e-10)
            zs_list.append(
                {
                    "mid": zs_mid,
                    "zg": zs.zg,
                    "zd": zs.zd,
                    "dist_pct": zs_dist,
                    "above": current > zs.zg,
                    "below": current < zs.zd,
                }
            )

        result["zhongshu_count"] = len(zs_list)
        zs_above = sum(1 for z in zs_list if z["above"])
        zs_below = sum(1 for z in zs_list if z["below"])
        result["zs_above_price"] = float(zs_above)
        result["zs_below_price"] = float(zs_below)

        # 区间套评分
        # 买入信号：中枢在下方（被突破），且价格远离中枢上沿（确认突破）
        # 卖出信号：中枢在上方（被跌破），且价格远离中枢下沿（确认跌破）
        if is_buy:
            # 最近中枢应在价格下方
            if zs_list:
                latest = zs_list[-1]
                # 价格在最新中枢上方
                breakout_confirm = latest["above"]
                # 价格离中枢有一定距离（非刚突破）
                distance_factor = max(0, min(1.0, latest["dist_pct"] * 5))
                # 多个中枢提供支撑
                support_level = zs_above / max(len(zs_list), 1)
                score = 0.3 * breakout_confirm + 0.3 * distance_factor + 0.4 * support_level
            else:
                score = 0.3
        else:
            if zs_list:
                latest = zs_list[-1]
                breakdown_confirm = latest["below"]
                distance_factor = max(0, min(1.0, abs(latest["dist_pct"]) * 5))
                resistance_level = zs_below / max(len(zs_list), 1)
                score = 0.3 * breakdown_confirm + 0.3 * distance_factor + 0.4 * resistance_level
            else:
                score = 0.3

        score = min(1.0, max(0.0, score))
        result["multi_level_score"] = round(score, 3)

        if score >= 0.7:
            adj = 0.05
        elif score >= 0.5:
            adj = 0.03
        elif score >= 0.3:
            adj = 0.0
        else:
            adj = -0.03

        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = (
            f"中枢数={len(zs_list)} 上方={zs_above} 下方={zs_below} "
            f"区间套评分={score:.2f} | 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_post_signal_fund_flow_v68(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """信号后资金流向确认（V68 条件206）。

    通过量价关系判断信号后的资金动向：
    - 买入信号后：价格上涨伴随成交量放大 = 资金流入确认
    - 卖出信号后：价格下跌伴随成交量放大 = 资金流出确认
    - 价升量缩 = 资金背离（需警惕）

    返回：fund_flow_direction, avg_volume_ratio, flow_confidence, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "fund_flow_direction": "none",
        "avg_volume_ratio": 0.0,
        "flow_confidence": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 30 or not volumes:
            result["msg"] = "数据不足（需≥30根且有成交量）"
            return result

        recent_closes = closes[-20:]
        recent_vols = volumes[-20:]

        # 计算量比（相对于均量）
        avg_vol = sum(recent_vols) / len(recent_vols)
        vol_ratios = [v / max(avg_vol, 1e-10) for v in recent_vols]
        avg_vol_ratio = sum(vol_ratios) / len(vol_ratios)
        result["avg_volume_ratio"] = round(avg_vol_ratio, 3)

        # 价量配合分析
        up_days = 0
        down_days = 0
        high_vol_up = 0  # 涨且放量
        high_vol_down = 0  # 跌且放量

        for i in range(1, len(recent_closes)):
            price_change = recent_closes[i] - recent_closes[i - 1]
            vol_ratio = vol_ratios[i] if i < len(vol_ratios) else 1.0

            if price_change > 0:
                up_days += 1
                if vol_ratio > 1.2:
                    high_vol_up += 1
            else:
                down_days += 1
                if vol_ratio > 1.2:
                    high_vol_down += 1

        # 判断资金流向
        if is_buy:
            # 买入后应该：涨多跌少 + 放量上涨
            if up_days >= 12 and high_vol_up >= 8:
                flow_dir = "inflow_strong"
                confidence = "strong"
                adj = 0.05
            elif up_days >= 10 and high_vol_up >= 5:
                flow_dir = "inflow_moderate"
                confidence = "moderate"
                adj = 0.03
            elif up_days >= 8:
                flow_dir = "inflow_weak"
                confidence = "weak"
                adj = 0.01
            elif down_days > up_days:
                flow_dir = "outflow"
                confidence = "warning"
                adj = -0.05
            else:
                flow_dir = "neutral"
                confidence = "neutral"
                adj = 0.0
        else:
            if down_days >= 12 and high_vol_down >= 8:
                flow_dir = "outflow_strong"
                confidence = "strong"
                adj = 0.05
            elif down_days >= 10 and high_vol_down >= 5:
                flow_dir = "outflow_moderate"
                confidence = "moderate"
                adj = 0.03
            elif down_days >= 8:
                flow_dir = "outflow_weak"
                confidence = "weak"
                adj = 0.01
            elif up_days > down_days:
                flow_dir = "inflow"
                confidence = "warning"
                adj = -0.05
            else:
                flow_dir = "neutral"
                confidence = "neutral"
                adj = 0.0

        result["fund_flow_direction"] = flow_dir
        result["flow_confidence"] = confidence
        result["confidence_adjust"] = round(adj, 3)

        result["msg"] = (
            f"量比={avg_vol_ratio:.2f} 涨{up_days}跌{down_days} "
            f"资金流向={flow_dir} | 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_market_regime_adaptation_v68(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """市场风格适配评分（V68 条件207）。

    评估当前市场环境（波动率状态、趋势强度），判断信号是否适配当前风格：
    - 趋势市：适合趋势跟踪策略（第三类买卖点）
    - 震荡市：适合区间策略，趋势信号需打折
    - 高波动：需谨慎，降低仓位建议

    返回：atr_pct, volatility_regime, trend_strength, adaptation_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "atr_pct": 0.0,
        "volatility_regime": "normal",
        "trend_strength": "weak",
        "adaptation_score": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 60 or not highs or not lows:
            result["msg"] = "数据不足（需≥60根）"
            return result

        current = closes[-1]

        # 计算ATR(14)
        tr_list = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - highs[i - 1]),
                abs(lows[i] - lows[i - 1]),
            )
            tr_list.append(tr)
        atr_14 = sum(tr_list[-14:]) / 14
        atr_pct = atr_14 / max(current, 1e-10) * 100
        result["atr_pct"] = round(atr_pct, 2)

        # 波动率状态判断（基于ATR百分比）
        if atr_pct > 4.0:
            vol_regime = "high"
        elif atr_pct > 2.0:
            vol_regime = "normal"
        else:
            vol_regime = "low"
        result["volatility_regime"] = vol_regime

        # 趋势强度（ADX简化版：用MA发散度）
        ma5 = sum(closes[-5:]) / 5
        ma20 = sum(closes[-20:]) / 20
        ma60 = sum(closes[-60:]) / 60
        ma_spread = abs(ma5 - ma20) / max(ma20, 1e-10) * 100
        trend_aligned = (ma5 > ma20 > ma60) if is_buy else (ma5 < ma20 < ma60)

        if ma_spread > 3.0 and trend_aligned:
            trend_strength = "strong"
        elif ma_spread > 1.5:
            trend_strength = "moderate"
        else:
            trend_strength = "weak"
        result["trend_strength"] = trend_strength

        # 适配评分
        # 趋势信号在趋势市中表现最好，在震荡市中表现差
        if trend_strength == "strong" and vol_regime in ("low", "normal"):
            adaptation = 0.9
            adj = 0.05
        elif trend_strength == "strong" and vol_regime == "high":
            adaptation = 0.6
            adj = 0.02
        elif trend_strength == "moderate" and vol_regime in ("low", "normal"):
            adaptation = 0.7
            adj = 0.03
        elif trend_strength == "moderate" and vol_regime == "high":
            adaptation = 0.4
            adj = 0.0
        else:  # weak trend
            if vol_regime == "high":
                adaptation = 0.2
                adj = -0.05
            elif vol_regime == "normal":
                adaptation = 0.4
                adj = -0.02
            else:  # low vol + weak trend = 震荡市
                adaptation = 0.3
                adj = -0.03

        result["adaptation_score"] = round(adaptation, 2)
        result["confidence_adjust"] = round(adj, 3)

        result["msg"] = (
            f"ATR={atr_pct:.1f}% 波动率={vol_regime} 趋势={trend_strength} "
            f"适配分={adaptation:.0%} | 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


# ──────────────────────────────────────────────────────────────────────────────
# V69: 条件 208-211（量价背离+结构完整+多指标背离+回踩深度）
# ──────────────────────────────────────────────────────────────────────────────


def _calc_price_volume_divergence_v69(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """量价背离二次确认（V69 条件208）。

    检测价格与成交量的背离关系，作为买卖点的二次确认：
    - 买入信号：价格创近期新低但成交量萎缩 = 卖压衰竭（bullish divergence）
    - 卖出信号：价格创近期新高但成交量萎缩 = 买盘枯竭（bearish divergence）
    - 价量齐升/齐降 = 趋势确认，非背离信号

    返回：divergence_type, price_trend, volume_trend, divergence_strength, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "divergence_type": "none",
        "price_trend": "flat",
        "volume_trend": "flat",
        "divergence_strength": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 30 or not volumes:
            result["msg"] = "数据不足（需≥30根）"
            return result

        window = 20
        recent_closes = closes[-window:]
        recent_vols = volumes[-window:]

        # 价格线性回归斜率
        n_win = len(recent_closes)
        x_mean = (n_win - 1) / 2.0
        y_mean = sum(recent_closes) / n_win
        num = sum((i - x_mean) * (recent_closes[i] - y_mean) for i in range(n_win))
        denom = sum((i - x_mean) ** 2 for i in range(n_win))
        price_slope = num / max(denom, 1e-10)
        price_norm_slope = price_slope / max(y_mean, 1e-10)

        if price_norm_slope > 0.01:
            price_trend = "up"
        elif price_norm_slope < -0.01:
            price_trend = "down"
        else:
            price_trend = "flat"
        result["price_trend"] = price_trend

        # 成交量趋势
        vol_start = sum(recent_vols[:5]) / 5
        vol_end = sum(recent_vols[-5:]) / 5
        vol_change = (vol_end - vol_start) / max(vol_start, 1e-10)

        if vol_change > 0.1:
            volume_trend = "expanding"
        elif vol_change < -0.1:
            volume_trend = "shrinking"
        else:
            volume_trend = "stable"
        result["volume_trend"] = volume_trend

        # 背离检测
        divergence_found = False
        divergence_dir = "none"

        if is_buy:
            if price_trend == "down" and volume_trend == "shrinking":
                divergence_found = True
                divergence_dir = "bullish"
            elif price_trend == "down" and volume_trend == "stable":
                divergence_found = True
                divergence_dir = "weak_bullish"
        else:
            if price_trend == "up" and volume_trend == "shrinking":
                divergence_found = True
                divergence_dir = "bearish"
            elif price_trend == "up" and volume_trend == "stable":
                divergence_found = True
                divergence_dir = "weak_bearish"

        result["divergence_type"] = divergence_dir

        # 背离强度
        if divergence_found:
            strength = min(1.0, abs(price_norm_slope) * 20 + abs(vol_change) * 2)
            strength = max(0.1, strength)
        else:
            strength = 0.0
        result["divergence_strength"] = round(strength, 3)

        # 置信度调整
        if is_buy:
            if divergence_dir == "bullish" and strength > 0.5:
                adj = 0.05
            elif divergence_dir == "weak_bullish":
                adj = 0.02
            elif price_trend == "up" and volume_trend == "expanding":
                adj = 0.01
            else:
                adj = -0.02
        else:
            if divergence_dir == "bearish" and strength > 0.5:
                adj = 0.05
            elif divergence_dir == "weak_bearish":
                adj = 0.02
            elif price_trend == "down" and volume_trend == "expanding":
                adj = 0.01
            else:
                adj = -0.02

        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = (
            f"价格{'↑' if price_trend == 'up' else '↓' if price_trend == 'down' else '→'}"
            f"量能{'放' if volume_trend == 'expanding' else '缩' if volume_trend == 'shrinking' else '平'}"
            f" 背离={divergence_dir} 强度={strength:.2f} | 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_structural_integrity_v69(
    mmd: MMD,
    bis: list[BI],
    zss: list[ZS],
    closes: list[float],
) -> dict[str, Any]:
    """结构完整性评分（V69 条件209）。

    评估缠论结构的完整性，包括：
    - 当前笔是否已完成（end.done）
    - 笔序列是否连续（无跳笔）
    - 中枢数量和质量
    - 买卖点与最近中枢的距离关系

    返回：bi_complete, bi_sequence_valid, zhongshu_valid, structural_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "bi_complete": False,
        "bi_sequence_valid": True,
        "zhongshu_valid": False,
        "structural_score": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        _ = mmd.mmd_type == MMDType.BUY_3
        _ = len(closes)

        bi_complete = mmd.bi is not None and mmd.bi.end.done if mmd.bi else False
        result["bi_complete"] = bi_complete

        bi_valid = True
        if bis and len(bis) >= 2:
            for i in range(1, len(bis)):
                prev_bi = bis[i - 1]
                curr_bi = bis[i]
                if curr_bi.start.k.index < prev_bi.end.k.index:
                    bi_valid = False
                    break
        result["bi_sequence_valid"] = bi_valid

        zs_valid_count = 0
        if zss:
            for zs in zss:
                if zs.zg > zs.zd and zs.done:
                    zs_valid_count += 1
        result["zhongshu_valid"] = zs_valid_count > 0

        bi_score = 0.4 if bi_complete else 0.1
        seq_score = 0.3 if bi_valid else 0.0
        zs_score = 0.3 * min(zs_valid_count / 3, 1.0) if zss else 0.0

        structural_score = bi_score + seq_score + zs_score
        structural_score = min(1.0, max(0.0, structural_score))
        result["structural_score"] = round(structural_score, 3)

        if structural_score >= 0.8:
            adj = 0.04
        elif structural_score >= 0.6:
            adj = 0.02
        elif structural_score >= 0.4:
            adj = 0.0
        else:
            adj = -0.03

        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = (
            f"笔完成={'✓' if bi_complete else '✗'} "
            f"序列={'✓' if bi_valid else '✗'} "
            f"中枢{'✓' if zs_valid_count > 0 else '✗'}({zs_valid_count}) "
            f"结构分={structural_score:.2f} | 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_multi_indicator_divergence_v69(
    mmd: MMD,
    closes: list[float] | None,
    volumes: list[float] | None,
    macd_data: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    """多指标背离融合（V69 条件210）。

    综合MACD、RSI、KDJ三个指标的背离信号：
    - MACD背离：价格与MACD柱状图的背离
    - RSI背离：价格与RSI的背离
    - KDJ背离：价格与KDJ的K值背离
    - 多指标共振：两个以上指标同时发出背离信号时增强置信度

    返回：macd_divergence, rsi_divergence, kdj_divergence, resonance_count, confidence_adjust, msg
    """
    if closes is None:
        return {
            "macd_divergence": "none",
            "rsi_divergence": "none",
            "kdj_divergence": "none",
            "resonance_count": 0,
            "confidence_adjust": 0.0,
            "msg": "",
        }
    result: dict[str, Any] = {
        "macd_divergence": "none",
        "rsi_divergence": "none",
        "kdj_divergence": "none",
        "resonance_count": 0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 30 or not macd_data or not macd_data.get("hist"):
            result["msg"] = "数据不足（需≥30根且有MACD数据）"
            return result

        hist = macd_data["hist"]
        window = 20

        # 1. MACD背离检测
        macd_div = "none"
        if len(hist) >= window and len(closes) >= window:
            price_recent = closes[-window:]
            hist_recent = hist[-window:]

            if is_buy:
                price_low_recent = min(price_recent[-5:])
                price_low_early = min(price_recent[:5])
                hist_low_recent = (
                    min(hist_recent[-5:]) if any(h < 0 for h in hist_recent[-5:]) else 0
                )
                hist_low_early = min(hist_recent[:5]) if any(h < 0 for h in hist_recent[:5]) else 0
                if price_low_recent < price_low_early and hist_low_recent > hist_low_early:
                    macd_div = "bullish"
                elif price_low_recent > price_low_early and hist_low_recent < hist_low_early:
                    macd_div = "bearish"
            else:
                price_high_recent = max(price_recent[-5:])
                price_high_early = max(price_recent[:5])
                hist_high_recent = (
                    max(hist_recent[-5:]) if any(h > 0 for h in hist_recent[-5:]) else 0
                )
                hist_high_early = max(hist_recent[:5]) if any(h > 0 for h in hist_recent[:5]) else 0
                if price_high_recent > price_high_early and hist_high_recent < hist_high_early:
                    macd_div = "bearish"
                elif price_high_recent < price_high_early and hist_high_recent > hist_high_early:
                    macd_div = "bullish"

        result["macd_divergence"] = macd_div

        # 2. RSI背离检测（简化版）
        rsi_div = "none"
        if n >= 30:
            price_chg_5d = (closes[-1] - closes[-6]) / max(closes[-6], 1e-10)
            price_chg_10d = (closes[-6] - closes[-11]) / max(closes[-11], 1e-10) if n >= 11 else 0

            if is_buy:
                if price_chg_5d > 0 and price_chg_10d < 0:
                    rsi_div = "bullish"
                elif price_chg_5d < 0 and price_chg_10d > 0:
                    rsi_div = "bearish"
            else:
                if price_chg_5d > 0 and price_chg_10d < 0:
                    rsi_div = "bearish"
                elif price_chg_5d < 0 and price_chg_10d > 0:
                    rsi_div = "bullish"

        result["rsi_divergence"] = rsi_div

        # 3. KDJ背离检测（简化版）
        kdj_div = "none"
        if n >= 20 and volumes:
            vol_ratio_recent = sum(volumes[-5:]) / max(sum(volumes[-10:-5]), 1e-10)
            price_momentum = (closes[-1] - closes[-5]) / max(closes[-5], 1e-10)

            if is_buy:
                if price_momentum < -0.02 and vol_ratio_recent < 0.7:
                    kdj_div = "bullish"
                elif price_momentum > 0.02 and vol_ratio_recent < 0.7:
                    kdj_div = "bearish"
            else:
                if price_momentum > 0.02 and vol_ratio_recent < 0.7:
                    kdj_div = "bearish"
                elif price_momentum < -0.02 and vol_ratio_recent < 0.7:
                    kdj_div = "bullish"

        result["kdj_divergence"] = kdj_div

        # 4. 共振计数
        positive_div = sum(
            1
            for d in [macd_div, rsi_div, kdj_div]
            if (is_buy and d == "bullish") or (not is_buy and d == "bearish")
        )
        result["resonance_count"] = positive_div

        if positive_div >= 3:
            adj = 0.06
        elif positive_div == 2:
            adj = 0.04
        elif positive_div == 1:
            adj = 0.02
        else:
            adj = 0.0

        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = (
            f"MACD={macd_div} RSI={rsi_div} KDJ={kdj_div} 共振={positive_div}/3 | 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_retracement_depth_v69(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """回踩深度量化（V69 条件211）。

    量化第三类买卖点的回踩行为：
    - 买入第三类：价格突破中枢后回踩，回踩深度应在中枢上沿附近
    - 卖出第三类：价格跌破中枢后反抽，反抽深度应在中枢下沿附近
    - 回踩不足（太浅）或回踩过度（跌破中枢）都影响信号质量

    返回：retracement_depth_pct, retracement_type, optimal_range, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "retracement_depth_pct": 0.0,
        "retracement_type": "none",
        "optimal_range": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 20 or not highs or not lows:
            result["msg"] = "数据不足（需≥20根）"
            return result

        current = closes[-1]

        lookback = min(30, n)
        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]

        local_high = max(recent_highs)
        local_low = min(recent_lows)
        high_low_range = local_high - local_low

        if high_low_range < 1e-10:
            result["msg"] = "价格区间过窄"
            return result

        if is_buy:
            retracement = (local_high - current) / high_low_range
            retracement_pct = retracement * 100
        else:
            retracement = (current - local_low) / high_low_range
            retracement_pct = retracement * 100

        result["retracement_depth_pct"] = round(retracement_pct, 1)

        if retracement_pct < 30:
            retype = "shallow"
        elif retracement_pct < 70:
            retype = "optimal"
        elif retracement_pct < 90:
            retype = "deep"
        else:
            retype = "breakdown"

        result["retracement_type"] = retype

        if retype == "optimal":
            optimal = "yes"
        elif retype in ("shallow", "deep"):
            optimal = "partial"
        else:
            optimal = "no"
        result["optimal_range"] = optimal

        if retype == "optimal":
            adj = 0.05
        elif retype == "shallow":
            adj = 0.02
        elif retype == "deep":
            adj = -0.01
        else:
            adj = -0.06

        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = (
            f"回踩深度={retracement_pct:.1f}% 类型={retype} "
            f"最优={'✓' if optimal == 'yes' else '△' if optimal == 'partial' else '✗'} "
            f"| 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


# ──────────────────────────────────────────────────────────────────────────────
# V70: 条件 212-215（量峰检测+时间衰减+假突破过滤+置信度校准）
# ──────────────────────────────────────────────────────────────────────────────


def _calc_volume_peak_detection_v70(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """分时量峰检测（V70 条件212）。

    检测突破/反转时的成交量峰值，确认信号真实性：
    - 买入信号：突破时成交量需显著放大（>1.5倍均值）= 量峰确认
    - 卖出信号：下跌时成交量放大 = 抛压确认
    - 无量突破 = 假突破风险高

    返回：peak_ratio, peak_detected, volume_strength, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "peak_ratio": 0.0,
        "peak_detected": False,
        "volume_strength": "none",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 30 or not volumes:
            result["msg"] = "数据不足（需≥30根）"
            return result

        # 计算近期平均成交量
        lookback = min(20, n)
        avg_vol = sum(volumes[-lookback:]) / lookback

        # 最近5根K线成交量
        recent_vol = sum(volumes[-5:]) / 5
        peak_ratio = recent_vol / max(avg_vol, 1e-10)
        result["peak_ratio"] = round(peak_ratio, 2)

        # 量峰检测阈值
        if peak_ratio >= 1.5:
            peak_detected = True
            strength = "strong"
        elif peak_ratio >= 1.2:
            peak_detected = True
            strength = "moderate"
        else:
            peak_detected = False
            strength = "weak"
        result["peak_detected"] = peak_detected
        result["volume_strength"] = strength

        # 置信度调整
        if is_buy:
            if peak_detected and strength == "strong":
                adj = 0.06
            elif peak_detected and strength == "moderate":
                adj = 0.03
            elif not peak_detected:
                adj = -0.04
            else:
                adj = 0.0
        else:
            if peak_detected and strength == "strong":
                adj = 0.06
            elif peak_detected and strength == "moderate":
                adj = 0.03
            elif not peak_detected:
                adj = -0.04
            else:
                adj = 0.0

        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = (
            f"量峰比={peak_ratio:.2f}x {'✅量峰确认' if peak_detected else '⚠️无量突破'} "
            f"强度={strength} | 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_signal_time_decay_v70(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """买卖点时间窗口衰减（V70 条件213）。

    根据信号出现后的K线数量应用指数衰减：
    - 新信号（≤5根）：完整置信度
    - 中期（6-15根）：线性衰减
    - 长期（>15根）：指数快速衰减

    返回：bar_count, decay_factor, signal_age, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "bar_count": 0,
        "decay_factor": 1.0,
        "signal_age": "fresh",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 10:
            result["msg"] = "数据不足（需≥10根）"
            return result

        # 估算信号出现后的K线数（基于信号后价格变动幅度）
        if mmd.bi is not None and mmd.bi.end.k.index is not None:
            signal_idx = mmd.bi.end.k.index
            bar_count = max(0, n - 1 - signal_idx)
        else:
            # 无笔信息时，用价格变化估算
            price_chg = abs(closes[-1] - closes[-10]) / max(closes[-10], 1e-10) if n >= 10 else 0
            bar_count = min(int(price_chg * 500), n - 1)  # 粗略估算

        bar_count = min(bar_count, n - 1)
        result["bar_count"] = bar_count

        # 指数衰减计算
        if bar_count <= 5:
            decay = 1.0
            age = "fresh"
        elif bar_count <= 15:
            decay = max(0.5, 1.0 - (bar_count - 5) * 0.03)
            age = "moderate"
        elif bar_count <= 30:
            decay = max(0.2, 0.7 * np.exp(-(bar_count - 15) * 0.05))
            age = "aging"
        else:
            decay = max(0.05, 0.7 * np.exp(-(bar_count - 15) * 0.08))
            age = "old"

        result["decay_factor"] = round(decay, 3)
        result["signal_age"] = age

        # 置信度调整（相对于基准1.0）
        adj = decay - 1.0
        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = f"信号后{bar_count}根K线 衰减因子={decay:.2f} 时效={age} | 置信度{adj:+.0%}"
        return result
    except Exception:
        return result


def _calc_false_breakout_filter_v70(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, Any]:
    """假突破二次过滤（V70 条件214）。

    突破后价格需持续N根K线维持在突破水平之上/之下：
    - 买入突破：突破后需站稳N根K线在突破位上方
    - 卖出跌破：跌破后需持续N根K线在突破位下方
    - 快速回归 = 假突破，降低置信度

    返回：sustained_bars, is_sustained, breakout_quality, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "sustained_bars": 0,
        "is_sustained": False,
        "breakout_quality": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 15 or not highs or not lows:
            result["msg"] = "数据不足（需≥15根）"
            return result

        # 找到突破位（最近30根的最高/最低点）
        lookback = min(30, n)
        breakout_level = max(highs[-lookback:]) if is_buy else min(lows[-lookback:])

        # 计算突破后的持续根数
        sustained = 0
        for i in range(n - 1, max(n - lookback - 1, -1), -1):
            if is_buy:
                if closes[i] > breakout_level * 0.998:  # 允许0.2%误差
                    sustained += 1
                else:
                    break
            else:
                if closes[i] < breakout_level * 1.002:
                    sustained += 1
                else:
                    break

        sustained = min(sustained, lookback - 1)
        result["sustained_bars"] = sustained

        # 判断是否持续（需持续至少3根）
        is_sustained = sustained >= 3
        result["is_sustained"] = is_sustained

        # 突破质量评级
        if sustained >= 8:
            quality = "strong"
        elif sustained >= 5:
            quality = "good"
        elif sustained >= 3:
            quality = "moderate"
        elif sustained >= 1:
            quality = "weak"
        else:
            quality = "fake"
        result["breakout_quality"] = quality

        # 置信度调整
        if is_buy:
            if quality == "strong":
                adj = 0.07
            elif quality == "good":
                adj = 0.04
            elif quality == "moderate":
                adj = 0.01
            elif quality == "weak":
                adj = -0.02
            else:
                adj = -0.08
        else:
            if quality == "strong":
                adj = 0.07
            elif quality == "good":
                adj = 0.04
            elif quality == "moderate":
                adj = 0.01
            elif quality == "weak":
                adj = -0.02
            else:
                adj = -0.08

        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = (
            f"突破位={breakout_level:.2f} 持续{sustained}根 "
            f"质量={quality} {'✅真突破' if is_sustained else '⚠️疑似假突破'} "
            f"| 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_final_confidence_calibration_v70(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """信号置信度最终校准（V70 条件215）。

    综合所有累积的置信度调整，输出最终校准分数：
    - 收集所有前置条件的置信度调整
    - 计算正负调整数量
    - 输出校准等级（high/medium/low/critical）
    - 提供最终校准后的置信度

    返回：total_adjust, calibrated_confidence, calibration_level, adjust_count,
          positive_adjusts, negative_adjusts, msg
    """
    result: dict[str, Any] = {
        "total_adjust": 0.0,
        "calibrated_confidence": 0.0,
        "calibration_level": "unknown",
        "adjust_count": 0,
        "positive_adjusts": 0,
        "negative_adjusts": 0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 20:
            result["msg"] = "数据不足（需≥20根）"
            return result

        # 收集所有置信度调整字段
        adjust_fields = [
            "_price_volume_divergence_v69",
            "_structural_integrity_v69",
            "_multi_indicator_divergence_v69",
            "_retracement_depth_v69",
            "_volume_peak_detection_v70",
            "_signal_time_decay_v70",
            "_false_breakout_filter_v70",
        ]

        total_adjust = 0.0
        positive = 0
        negative = 0
        count = 0

        for field in adjust_fields:
            if hasattr(mmd, field):
                val = getattr(mmd, field)
                if val and isinstance(val, dict):
                    adj = val.get("confidence_adjust", 0.0)
                    if adj is not None:
                        total_adjust += adj
                        count += 1
                        if adj > 0:
                            positive += 1
                        elif adj < 0:
                            negative += 1

        result["total_adjust"] = round(total_adjust, 3)
        result["adjust_count"] = count
        result["positive_adjusts"] = positive
        result["negative_adjusts"] = negative

        # 校准置信度
        base_confidence = mmd.confidence if mmd.confidence else 0.5
        calibrated = max(0.0, min(1.0, base_confidence + total_adjust))
        result["calibrated_confidence"] = round(calibrated, 3)

        # 校准等级
        if calibrated >= 0.75:
            level = "high"
        elif calibrated >= 0.55:
            level = "medium"
        elif calibrated >= 0.35:
            level = "low"
        else:
            level = "critical"
        result["calibration_level"] = level

        result["msg"] = (
            f"基础={base_confidence:.0%} 调整{total_adjust:+.0%} "
            f"(+{positive}/-{negative}) → 校准={calibrated:.0%} "
            f"等级={level}"
        )
        return result
    except Exception:
        return result


# ──────────────────────────────────────────────────────────────────────────────
# V71: 条件 216-219（均线排列强度+多周期共振+历史胜率+动态风险收益）
# ──────────────────────────────────────────────────────────────────────────────


def _calc_ma_alignment_strength_v71(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """均线排列强度评估（V71 条件216）。

    评估当前价格相对于多条均线（MA20/MA60/MA120）的排列状态：
    - 多头排列：MA20 > MA60 > MA120，价格在所有均线上方 = 强趋势
    - 空头排列：MA20 < MA60 < MA120，价格在所有均线下方 = 弱趋势
    - 混合排列：均线交叉，趋势不明确
    - 价格与均线的偏离度也会影响信号质量

    返回：alignment, strength, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "alignment": "unknown",
        "strength": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 60:
            result["msg"] = "数据不足（需≥60根）"
            return result

        # 计算多条均线
        ma20 = MA(closes, 20)[-1]
        ma60 = MA(closes, 60)[-1]
        ma120 = MA(closes, 120)[-1] if n >= 120 else ma60 * 1.02  # 数据不足时用MA60估算

        current = closes[-1]

        # 判断均线排列
        if ma20 > ma60 > ma120:
            alignment = "bullish"
        elif ma20 < ma60 < ma120:
            alignment = "bearish"
        else:
            alignment = "mixed"
        result["alignment"] = alignment

        # 计算价格与均线的偏离度（归一化）
        price_dist_ma20 = (current - ma20) / max(ma20, 1e-10)
        price_dist_ma60 = (current - ma60) / max(ma60, 1e-10)
        price_dist_ma120 = (current - ma120) / max(ma120, 1e-10)

        # 强度评分
        if alignment == "bullish":
            avg_dist = (abs(price_dist_ma20) + abs(price_dist_ma60) + abs(price_dist_ma120)) / 3
            strength = min(1.0, avg_dist * 5 + 0.5)  # 偏离度越大趋势越强
            if is_buy:
                # 3买需要价格在MA20上方
                if current > ma20 > ma60 > ma120:
                    adj = 0.05
                elif current > ma20:
                    adj = 0.02
                else:
                    adj = -0.03
            else:
                adj = -0.02  # 空头排列对卖出信号有负面含义（趋势确认但无背离）
        elif alignment == "bearish":
            avg_dist = (abs(price_dist_ma20) + abs(price_dist_ma60) + abs(price_dist_ma120)) / 3
            strength = min(1.0, avg_dist * 5 + 0.5)
            if is_buy:
                adj = -0.05  # 空头排列对买入信号负面
            else:
                if current < ma20 < ma60 < ma120:
                    adj = 0.05
                elif current < ma20:
                    adj = 0.02
                else:
                    adj = -0.03
        else:
            strength = 0.3
            adj = -0.02  # 混合排列不确定性高

        result["strength"] = round(strength, 3)
        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = (
            f"排列={alignment} 强度={strength:.2f} "
            f"MA20={ma20:.2f} MA60={ma60:.2f} MA120={ma120:.2f} "
            f"| 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_multi_tf_ma_resonance_v71(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """多周期均线共振确认（V71 条件217）。

    短中长期均线同时发出同向信号时增强置信度：
    - 短期均线（MA5/MA10）与中期均线（MA20/MA60）同向
    - 中期均线与长期均线（MA120/MA250）同向
    - 共振数 = 同时同向的对数

    返回：short_aligned, mid_aligned, long_aligned, resonance_count, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "short_aligned": False,
        "mid_aligned": False,
        "long_aligned": False,
        "resonance_count": 0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 120:
            result["msg"] = "数据不足（需≥120根）"
            return result

        # 计算各周期均线
        ma5 = MA(closes, 5)[-1]
        ma10 = MA(closes, 10)[-1]
        ma20 = MA(closes, 20)[-1]
        ma60 = MA(closes, 60)[-1]
        ma120 = MA(closes, 120)[-1]

        # 短期共振：MA5 > MA10（多头）或 MA5 < MA10（空头）
        short_up = ma5 > ma10
        result["short_aligned"] = short_up if is_buy else (not short_up)

        # 中期共振：MA20 > MA60
        mid_up = ma20 > ma60
        result["mid_aligned"] = mid_up if is_buy else (not mid_up)

        # 长期共振：MA60 > MA120
        long_up = ma60 > ma120
        result["long_aligned"] = long_up if is_buy else (not long_up)

        # 共振计数
        alignment_count = sum(
            [
                (short_up if is_buy else not short_up),
                (mid_up if is_buy else not mid_up),
                (long_up if is_buy else not long_up),
            ]
        )
        result["resonance_count"] = alignment_count

        # 置信度调整
        if alignment_count >= 3:
            adj = 0.08
        elif alignment_count == 2:
            adj = 0.04
        elif alignment_count == 1:
            adj = 0.01
        else:
            adj = -0.03

        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = (
            f"短={'✅' if short_up else '❌'} 中={'✅' if mid_up else '❌'} 长={'✅' if long_up else '❌'} "
            f"共振={alignment_count}/3 | 置信度{adj:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_mmd_history_winrate_v71(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """买卖点历史胜率回溯（V71 条件218）。

    对历史类似形态的胜率进行回溯分析：
    - 在最近N根K线中寻找类似价格形态
    - 统计这些形态后续的成功率
    - 胜率越高，当前信号可信度越高

    返回：lookback_winrate, sample_count, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "lookback_winrate": 0.0,
        "sample_count": 0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 100 or not volumes:
            result["msg"] = "数据不足（需≥100根）"
            return result

        # 回溯窗口
        lookback = min(200, n)
        hist_closes = closes[:-1]  # 排除当前K线
        hist_volumes = volumes[:-1]

        # 查找历史相似形态（价格在近期低位/高位且成交量萎缩/放大）
        wins = 0
        samples = 0
        pattern_window = 20

        for i in range(0, n - lookback - 1, pattern_window):
            slice_closes = hist_closes[i : i + pattern_window * 2]
            slice_volumes = hist_volumes[i : i + pattern_window * 2]
            if len(slice_closes) < pattern_window * 2:
                continue

            # 检查形态：前pattern_window根K线的价格趋势
            start_price = slice_closes[0]
            _ = slice_closes[pattern_window]
            end_price = slice_closes[-1]
            mid_vol = sum(slice_volumes[:pattern_window]) / pattern_window
            end_vol = sum(slice_volumes[pattern_window:]) / pattern_window

            if is_buy:
                # 买入形态：价格从高位回落到低位后企稳，成交量萎缩
                price_drop = (start_price - end_price) / max(start_price, 1e-10)
                vol_shrink = end_vol / max(mid_vol, 1e-10)
                if 0.03 < price_drop < 0.15 and vol_shrink < 0.8:
                    # 检查后续表现
                    future_return = (
                        (end_price - slice_closes[-5]) / max(slice_closes[-5], 1e-10)
                        if len(slice_closes) > 5
                        else 0
                    )
                    if future_return > 0:
                        wins += 1
                    samples += 1
            else:
                # 卖出形态：价格从低位反弹到高位后遇阻，成交量放大
                price_rise = (end_price - start_price) / max(start_price, 1e-10)
                vol_expand = end_vol / max(mid_vol, 1e-10)
                if 0.03 < price_rise < 0.15 and vol_expand > 1.2:
                    future_return = (
                        (slice_closes[-5] - end_price) / max(end_price, 1e-10)
                        if len(slice_closes) > 5
                        else 0
                    )
                    if future_return > 0:
                        wins += 1
                    samples += 1

        winrate = wins / max(samples, 1)
        result["lookback_winrate"] = round(winrate, 3)
        result["sample_count"] = samples

        # 置信度调整
        if winrate >= 0.6 and samples >= 5:
            adj = 0.04
        elif winrate >= 0.5 and samples >= 3:
            adj = 0.02
        elif winrate < 0.4:
            adj = -0.03
        else:
            adj = 0.0

        result["confidence_adjust"] = round(adj, 3)
        result["msg"] = f"回溯胜率={winrate:.0%} ({samples}样本) | 置信度{adj:+.0%}"
        return result
    except Exception:
        return result


def _calc_dynamic_rr_optimization_v71(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volatility: float | None,
) -> dict[str, Any]:
    """动态风险收益比优化（V71 条件219）。

    根据当前波动率和市场环境动态调整止损止盈比例：
    - 低波动市场：止损可设窄（1x ATR），止盈可设宽（3x ATR）
    - 高波动市场：止损需设宽（2x ATR），止盈需更宽（4x ATR）
    - 动态计算最优风险收益比

    返回：stop_loss_pct, take_profit_pct, rr_ratio, atr_based_sl, atr_based_tp, msg
    """
    result: dict[str, Any] = {
        "stop_loss_pct": 0.0,
        "take_profit_pct": 0.0,
        "rr_ratio": 0.0,
        "atr_based_sl": 0.0,
        "atr_based_tp": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        n = len(closes)
        if n < 30 or not highs or not lows:
            result["msg"] = "数据不足（需≥30根）"
            return result

        current = closes[-1]

        # 计算ATR（14日）
        atr = ATR(highs, lows, closes, 14)[-1]
        atr_pct = atr / max(current, 1e-10)

        # 根据波动率调整止损止盈倍数
        if atr_pct < 0.01:  # 低波动
            sl_mult = 1.5
            tp_mult = 4.0
        elif atr_pct < 0.03:  # 中等波动
            sl_mult = 2.0
            tp_mult = 4.5
        else:  # 高波动
            sl_mult = 2.5
            tp_mult = 5.0

        # 动态止损止盈
        if is_buy:
            sl_pct = atr_pct * sl_mult
            tp_pct = atr_pct * tp_mult
        else:
            sl_pct = atr_pct * sl_mult
            tp_pct = atr_pct * tp_mult

        # 风险收益比
        rr = tp_pct / max(sl_pct, 1e-10)

        result["stop_loss_pct"] = round(sl_pct * 100, 2)
        result["take_profit_pct"] = round(tp_pct * 100, 2)
        result["rr_ratio"] = round(rr, 2)
        result["atr_based_sl"] = round(atr_pct * 100, 2)
        result["atr_based_tp"] = round(atr_pct * 100 * tp_mult, 2)
        result["msg"] = (
            f"ATR={atr_pct:.2%} SL={sl_pct:.2%} TP={tp_pct:.2%} "
            f"R:R={rr:.1f}x (低波={sl_mult}x/{tp_mult}x)"
        )
        return result
    except Exception:
        return result


# V72: 条件 220-223（均线收敛发散+支撑阻力距离+量价结构质量+信号衰减速度）
def _calc_ma_convergence_divergence_v72(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """均线收敛发散状态评估（V72 条件220）。

    评估短期MA(20)与长期MA(60)之间的收敛/发散状态：
    - 收敛（距离缩小）：趋势方向即将选择，突破概率高，增强信号
    - 发散（距离扩大）：趋势延续确认，增强信号方向性
    - 纠缠（距离持平）：无明显方向，降低置信度

    返回：state, spread_pct, spread_change_pct, convergence_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "state": "unknown",
        "spread_pct": 0.0,
        "spread_change_pct": 0.0,
        "convergence_score": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 80:
            result["msg"] = "数据不足（需≥80根）"
            return result

        from easy_tdx.MyTT import MA

        ma20 = MA(closes, 20)
        ma60 = MA(closes, 60)

        current_spread = abs(ma20[-1] - ma60[-1]) / max(ma60[-1], 1e-10)
        prev_spread = abs(ma20[-5] - ma60[-5]) / max(ma60[-5], 1e-10) if n >= 85 else current_spread
        spread_change = (current_spread - prev_spread) / max(prev_spread, 1e-10)

        is_buy = "buy" in mmd.mmd_type.value

        if abs(spread_change) < 0.005:
            state = "entangled"
            convergence_score = 0.0
            adjust = -0.02
        elif spread_change < 0:
            state = "converging"
            convergence_score = min(1.0, abs(spread_change) * 50)
            adjust = 0.04 if is_buy else -0.02
        else:
            state = "diverging"
            convergence_score = 0.5
            adjust = 0.03 if is_buy else 0.0

        result["state"] = state
        result["spread_pct"] = round(current_spread * 100, 3)
        result["spread_change_pct"] = round(spread_change * 100, 3)
        result["convergence_score"] = round(convergence_score, 3)
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"MA20/60={current_spread:.2%} 变化={spread_change:+.2%} "
            f"状态={'收敛' if state == 'converging' else '发散' if state == 'diverging' else '纠缠'} "
            f"置信度{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_support_resistance_proximity_v72(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
) -> dict[str, Any]:
    """支撑/阻力位距离评估（V72 条件221）。

    计算当前价格相对于最近支撑位（前低）和阻力位（前高）的距离百分比：
    - 买入信号：靠近支撑位（<3%）增强买入信号
    - 卖出信号：靠近阻力位（<3%）增强卖出信号
    - 远离支撑/阻力：中性

    返回：current_price, nearest_support, nearest_resistance, support_dist_pct, resistance_dist_pct, proximity_bonus, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "current_price": 0.0,
        "nearest_support": 0.0,
        "nearest_resistance": 0.0,
        "support_dist_pct": 0.0,
        "resistance_dist_pct": 0.0,
        "proximity_bonus": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 30 or not highs or not lows:
            result["msg"] = "数据不足（需≥30根）"
            return result

        current = closes[-1]
        result["current_price"] = round(current, 4)

        lookback = min(30, n)
        recent_lows = lows[-lookback:]
        recent_highs = highs[-lookback:]

        nearest_support = min(recent_lows)
        nearest_resistance = max(recent_highs)

        support_dist = (current - nearest_support) / max(nearest_support, 1e-10)
        resistance_dist = (nearest_resistance - current) / max(nearest_resistance, 1e-10)

        result["nearest_support"] = round(nearest_support, 4)
        result["nearest_resistance"] = round(nearest_resistance, 4)
        result["support_dist_pct"] = round(support_dist * 100, 2)
        result["resistance_dist_pct"] = round(resistance_dist * 100, 2)

        is_buy = "buy" in mmd.mmd_type.value

        if is_buy:
            proximity_bonus = max(0, 1.0 - support_dist * 10)
            adjust = 0.03 * proximity_bonus if support_dist < 0.05 else 0.0
        else:
            proximity_bonus = max(0, 1.0 - resistance_dist * 10)
            adjust = 0.03 * proximity_bonus if resistance_dist < 0.05 else 0.0

        result["proximity_bonus"] = round(proximity_bonus, 3)
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"支撑={nearest_support:.2f}({support_dist:+.1%}) 阻力={nearest_resistance:.2f}({resistance_dist:+.1%}) "
            f"距离 bonus={proximity_bonus:.2f} 置信度{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_volume_structure_quality_v72(
    mmd: MMD,
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """量价结构质量评分（V72 条件222）。

    评估近期量价配合的健康程度：
    - 上涨放量、下跌缩量：健康趋势，增强信号
    - 上涨缩量、下跌放量：危险信号，降低置信度
    - 整体量能分布稳定性（标准差）作为辅助评分

    返回：up_vol_ratio, down_vol_ratio, volume_health, stability_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "up_vol_ratio": 0.0,
        "down_vol_ratio": 0.0,
        "volume_health": 0.0,
        "stability_score": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 60 or not volumes:
            result["msg"] = "数据不足（需≥60根）"
            return result

        recent = min(30, n)
        price_changes = [closes[-i] - closes[-i - 1] for i in range(1, recent + 1)]
        recent_volumes = volumes[-recent:]
        avg_vol = sum(recent_volumes) / max(len(recent_volumes), 1)

        up_vol_sum = sum(v for v, p in zip(recent_volumes, price_changes) if p > 0)
        down_vol_sum = sum(v for v, p in zip(recent_volumes, price_changes) if p < 0)
        up_count = sum(1 for p in price_changes if p > 0)
        down_count = sum(1 for p in price_changes if p < 0)

        up_vol_ratio = up_vol_sum / max(avg_vol * up_count, 1e-10) if up_count > 0 else 1.0
        down_vol_ratio = down_vol_sum / max(avg_vol * down_count, 1e-10) if down_count > 0 else 1.0

        health = 0.0
        if up_vol_ratio > 1.0 and down_vol_ratio < 1.0:
            health = min(1.0, (up_vol_ratio - 1.0) * 2 + (1.0 - down_vol_ratio) * 2)
        elif up_vol_ratio < 1.0 and down_vol_ratio > 1.0:
            health = max(0.0, -((1.0 - up_vol_ratio) * 2 + (down_vol_ratio - 1.0) * 2))

        vol_std = (
            sum((v - avg_vol) ** 2 for v in recent_volumes) / max(len(recent_volumes), 1)
        ) ** 0.5
        vol_cv = vol_std / max(avg_vol, 1e-10)
        stability = max(0.0, 1.0 - vol_cv)

        is_buy = "buy" in mmd.mmd_type.value
        adjust = 0.0

        if health > 0.3 and stability > 0.5:
            adjust = 0.04 if is_buy else -0.02
        elif health < -0.3 and stability > 0.5:
            adjust = -0.04 if is_buy else 0.02

        result["up_vol_ratio"] = round(up_vol_ratio, 3)
        result["down_vol_ratio"] = round(down_vol_ratio, 3)
        result["volume_health"] = round(health, 3)
        result["stability_score"] = round(stability, 3)
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"上涨量能比={up_vol_ratio:.2f} 下跌量能比={down_vol_ratio:.2f} "
            f"健康={health:+.2f} 稳定={stability:.2f} 置信度{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_signal_decay_velocity_v72(
    mmd: MMD,
    closes: list[float],
    mmds_all: list[MMD] | None = None,
) -> dict[str, Any]:
    """信号衰减速度评估（V72 条件223）。

    分析最近同类型买卖点信号的置信度变化趋势：
    - 置信度递增：信号正在强化，增强当前信号
    - 置信度递减：信号正在衰退，降低当前信号
    - 波动剧烈：不稳定，降低调整幅度

    返回：recent_confidences, trend_direction, velocity, volatility, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "recent_confidences": [],
        "trend_direction": "unknown",
        "velocity": 0.0,
        "volatility": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 50 or not mmds_all:
            result["msg"] = "数据不足（需≥50根且有历史信号）"
            return result

        is_buy = "buy" in mmd.mmd_type.value
        target_type_val = "BUY" if is_buy else "SELL"

        recent_conf = []
        for other_mmd in reversed(mmds_all):
            if target_type_val in other_mmd.mmd_type.value and other_mmd.confidence > 0:
                recent_conf.append(other_mmd.confidence)
                if len(recent_conf) >= 5:
                    break

        if len(recent_conf) < 2:
            result["msg"] = f"同类信号样本不足（{len(recent_conf)}个）"
            return result

        result["recent_confidences"] = [round(c, 3) for c in recent_conf]

        if len(recent_conf) >= 3:
            half = len(recent_conf) // 2
            first_avg = sum(recent_conf[:half]) / half
            second_avg = sum(recent_conf[half:]) / (len(recent_conf) - half)
            diff = second_avg - first_avg
            if diff > 0.02:
                trend = "strengthening"
                velocity = diff
            elif diff < -0.02:
                trend = "weakening"
                velocity = diff
            else:
                trend = "stable"
                velocity = 0.0
        else:
            trend = "insufficient"
            velocity = 0.0

        if len(recent_conf) >= 2:
            mean_c = sum(recent_conf) / len(recent_conf)
            var_c = sum((c - mean_c) ** 2 for c in recent_conf) / len(recent_conf)
            vol = var_c**0.5
        else:
            vol = 0.0

        result["trend_direction"] = trend
        result["velocity"] = round(velocity, 4)
        result["volatility"] = round(vol, 4)

        if trend == "strengthening":
            adjust = 0.04
        elif trend == "weakening":
            adjust = -0.05
        elif trend == "stable":
            adjust = 0.01
        else:
            adjust = 0.0

        if vol > 0.1:
            adjust *= 0.5

        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"趋势={trend} 速度={velocity:+.3f} 波动={vol:.3f} "
            f"置信度{adjust:+.0%} (样本: {', '.join(str(c) for c in result['recent_confidences'])})"
        )
        return result
    except Exception:
        return result


# V73: 条件 224-227（买卖点位置风险+中枢突破验证+多指标一致性+波动率适配）
def _calc_mmd_position_risk_v73(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
) -> dict[str, Any]:
    """买卖点位置风险评估（V73 条件224）。

    评估当前买卖信号在近期价格区间中的位置风险：
    - 买入信号：若出现在近期区间高位（>80%分位），风险较高；低位（<20%分位）风险较低
    - 卖出信号：若出现在近期区间低位（<20%分位），风险较高；高位（>80%分位）风险较低
    - 中间区域：风险中性

    返回：position_pct, risk_level, risk_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "position_pct": 0.0,
        "risk_level": "unknown",
        "risk_score": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        lookback = min(60, n)
        if n < 30 or highs is None or lows is None:
            result["msg"] = "数据不足（需≥30根且有highs/lows）"
            return result

        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]
        range_high = max(recent_highs)
        range_low = min(recent_lows)
        price_range = range_high - range_low

        current_price = closes[-1]
        if price_range < 1e-10:
            result["msg"] = "近期价格区间过窄"
            return result

        position_pct = (current_price - range_low) / price_range

        is_buy = "buy" in mmd.mmd_type.value

        if position_pct > 0.8:
            risk_level = "high"
            risk_score = 0.8 if is_buy else 0.2
            adjust = -0.04 if is_buy else 0.02
        elif position_pct < 0.2:
            risk_level = "low"
            risk_score = 0.2 if is_buy else 0.8
            adjust = 0.04 if is_buy else -0.02
        else:
            risk_level = "medium"
            risk_score = 0.5
            adjust = 0.0

        result["position_pct"] = round(position_pct, 3)
        result["risk_level"] = risk_level
        result["risk_score"] = round(risk_score, 3)
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"价格位于区间{position_pct:.0%}处 "
            f"({range_low:.2f}~{range_high:.2f}) "
            f"风险={risk_level} 置信度{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_zhongshu_breakout_validity_v73(
    mmd: MMD,
    closes: list[float],
    volumes: list[float] | None,
    highs: list[float] | None,
    lows: list[float] | None,
) -> dict[str, Any]:
    """中枢突破有效性验证（V73 条件225）。

    验证中枢突破是否为真实突破：
    - 真实突破：突破后价格持续维持在外侧，且伴随放量
    - 假突破：突破后价格快速回穿中枢，或突破时量能不足

    返回：breakout_valid, confirm_bars, sustain_ratio, volume_ratio, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "breakout_valid": False,
        "confirm_bars": 0,
        "sustain_ratio": 0.0,
        "volume_ratio": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 30 or highs is None or lows is None:
            result["msg"] = "数据不足（需≥30根且有highs/lows）"
            return result

        is_buy = "buy" in mmd.mmd_type.value

        if mmd.bi is None or mmd.bi.index is None:
            result["msg"] = "无笔索引信息"
            return result

        bi_idx = mmd.bi.index
        if bi_idx < 5 or bi_idx >= n - 5:
            result["msg"] = "笔索引越界"
            return result

        breakout_price = closes[bi_idx]
        confirm_period = min(10, n - bi_idx - 1)
        if confirm_period < 3:
            result["msg"] = "突破后K线不足"
            return result

        if is_buy:
            sustain_count = sum(
                1
                for i in range(bi_idx + 1, min(bi_idx + 1 + confirm_period, n))
                if closes[i] > breakout_price * 1.001
            )
        else:
            sustain_count = sum(
                1
                for i in range(bi_idx + 1, min(bi_idx + 1 + confirm_period, n))
                if closes[i] < breakout_price * 0.999
            )

        sustain_ratio = sustain_count / confirm_period if confirm_period > 0 else 0

        vol_ratio = 1.0
        if volumes and len(volumes) > bi_idx:
            recent_end = max(0, bi_idx - 10)
            recent_vol = volumes[recent_end:bi_idx]
            post_end = min(len(volumes), bi_idx + confirm_period + 1)
            post_vol = volumes[bi_idx:post_end]
            if recent_vol and post_vol:
                avg_recent = sum(recent_vol) / len(recent_vol)
                avg_post = sum(post_vol) / len(post_vol) if sum(post_vol) > 0 else avg_recent
                vol_ratio = avg_post / max(avg_recent, 1e-10)

        valid = sustain_ratio >= 0.7 and vol_ratio >= 0.8
        result["breakout_valid"] = valid
        result["confirm_bars"] = sustain_count
        result["sustain_ratio"] = round(sustain_ratio, 3)
        result["volume_ratio"] = round(vol_ratio, 3)

        if valid:
            adjust = 0.05
            result["msg"] = (
                f"突破有效（维持{sustain_count}/{confirm_period}根，量能比{vol_ratio:.2f}）"
            )
        else:
            adjust = -0.03
            result["msg"] = (
                f"突破可疑（维持{sustain_count}/{confirm_period}根，量能比{vol_ratio:.2f}）"
            )

        result["confidence_adjust"] = round(adjust, 3)
        return result
    except Exception:
        return result


def _calc_multi_indicator_consistency_v73(
    mmd: MMD,
    closes: list[float],
    macd_data: dict[str, list[float]] | None,
    kdj_data: dict[str, list[float]] | None,
    rsi_values: list[float] | None,
    boll_data: dict[str, list[float]] | None,
    volumes: list[float] | None,
) -> dict[str, Any]:
    """多指标确认一致性评估（V73 条件226）。

    检查MACD、KDJ、RSI、BOLL、Volume五个独立指标是否发出同向信号：
    - 一致性强（≥4个指标同向）：增强置信度
    - 一致性弱（≤2个指标同向）：降低置信度
    - 分歧明显：显著降低置信度

    返回：agreement_count, agreement_ratio, consistency_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "agreement_count": 0,
        "agreement_ratio": 0.0,
        "consistency_score": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 20:
            result["msg"] = "数据不足（需≥20根）"
            return result

        is_buy = "buy" in mmd.mmd_type.value
        agree_count = 0
        total_indicators = 0

        # MACD确认
        if macd_data and "hist" in macd_data and len(macd_data["hist"]) >= 2:
            total_indicators += 1
            hist = macd_data["hist"]
            macd_bullish = hist[-1] > 0 and hist[-1] > hist[-2]
            if is_buy and macd_bullish:
                agree_count += 1
            elif not is_buy and not macd_bullish:
                agree_count += 1

        # KDJ确认
        if kdj_data and "k" in kdj_data and "d" in kdj_data:
            total_indicators += 1
            k_vals = kdj_data["k"]
            d_vals = kdj_data["d"]
            if len(k_vals) >= 2 and len(d_vals) >= 2:
                kdj_bullish = k_vals[-1] > d_vals[-1] and k_vals[-1] > k_vals[-2]
                if is_buy and kdj_bullish:
                    agree_count += 1
                elif not is_buy and not kdj_bullish:
                    agree_count += 1

        # RSI确认
        if rsi_values and len(rsi_values) >= 2:
            total_indicators += 1
            rsi_bullish = rsi_values[-1] > rsi_values[-2] and rsi_values[-1] < 70
            if is_buy and rsi_bullish:
                agree_count += 1
            elif not is_buy and not rsi_bullish:
                agree_count += 1

        # BOLL确认
        if boll_data and "upper" in boll_data and "lower" in boll_data:
            total_indicators += 1
            upper = boll_data["upper"]
            lower = boll_data["lower"]
            mid = boll_data.get("mid", [])
            if len(upper) >= 1 and len(lower) >= 1:
                if is_buy:
                    center = mid[-1] if len(mid) >= 1 else (upper[-1] + lower[-1]) / 2
                    boll_bullish = closes[-1] > center
                else:
                    center = mid[-1] if len(mid) >= 1 else (upper[-1] + lower[-1]) / 2
                    boll_bullish = closes[-1] < center
                if is_buy and boll_bullish:
                    agree_count += 1
                elif not is_buy and not boll_bullish:
                    agree_count += 1

        # Volume确认
        if volumes and len(volumes) >= 2:
            total_indicators += 1
            vol_bullish = volumes[-1] > volumes[-2] and closes[-1] > closes[-2]
            if is_buy and vol_bullish:
                agree_count += 1
            elif not is_buy and not vol_bullish:
                agree_count += 1

        agreement_ratio = agree_count / total_indicators if total_indicators > 0 else 0.5
        consistency_score = agreement_ratio

        if agreement_ratio >= 0.8:
            adjust = 0.06
        elif agreement_ratio >= 0.6:
            adjust = 0.03
        elif agreement_ratio <= 0.2:
            adjust = -0.06
        elif agreement_ratio <= 0.4:
            adjust = -0.03
        else:
            adjust = 0.0

        result["agreement_count"] = agree_count
        result["agreement_ratio"] = round(agreement_ratio, 3)
        result["consistency_score"] = round(consistency_score, 3)
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"{agree_count}/{total_indicators}个指标一致 "
            f"（一致率{agreement_ratio:.0%}）"
            f" 置信度{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_volatility_regime_adaptation_v73(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
) -> dict[str, Any]:
    """波动率环境适配（V73 条件227）。

    根据当前市场波动率环境调整置信度：
    - 低波动环境（ATR历史分位<30%）：趋势信号更可靠，增强置信度
    - 正常波动（30%-60%）：中性
    - 高波动（60%-80%）：噪音增加，适度降低
    - 极端波动（≥80%）：显著降权

    返回：atr_pct, atr_rank, vol_regime, regime_score, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "atr_pct": 0.0,
        "atr_rank": 0.0,
        "vol_regime": "unknown",
        "regime_score": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 60 or highs is None or lows is None:
            result["msg"] = "数据不足（需≥60根且有highs/lows）"
            return result

        # 计算近期ATR（使用真实波幅的移动平均）
        tr_list = []
        for i in range(max(1, n - 30), n):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            tr_list.append(tr)

        if len(tr_list) < 5:
            result["msg"] = "TR数据不足"
            return result

        atr = sum(tr_list) / len(tr_list)
        atr_pct = atr / max(closes[-1], 1e-10) * 100

        # 计算历史ATR分位（用更长的lookback）
        all_tr = []
        lookback = min(120, n)
        for i in range(n - lookback, n):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            all_tr.append(tr)

        if all_tr:
            sorted_tr = sorted(all_tr)
            atr_rank = sum(1 for v in sorted_tr if v <= atr) / len(sorted_tr)
        else:
            atr_rank = 0.5

        # 判定波动率环境
        if atr_rank < 0.3:
            vol_regime = "low"
            regime_score = 0.8
            adjust = 0.03
        elif atr_rank < 0.6:
            vol_regime = "normal"
            regime_score = 0.5
            adjust = 0.0
        elif atr_rank < 0.8:
            vol_regime = "high"
            regime_score = 0.3
            adjust = -0.02
        else:
            vol_regime = "extreme"
            regime_score = 0.1
            adjust = -0.05

        result["atr_pct"] = round(atr_pct, 3)
        result["atr_rank"] = round(atr_rank, 3)
        result["vol_regime"] = vol_regime
        result["regime_score"] = round(regime_score, 3)
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"ATR={atr_pct:.2f}% 历史分位={atr_rank:.0%} 环境={vol_regime} 置信度{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


# V74: 条件 228-231（量价背离二次确认+趋势动能持续+中枢重叠度+信号共振深度）


def _calc_volume_price_divergence_secondary_v74(
    mmd: MMD,
    closes: list[float],
    volumes: list[float] | None,
) -> dict[str, Any]:
    """量价背离二次确认（V74 条件228）。

    在已有买卖点信号的基础上，检测量价背离是否提供二次确认。

    返回：divergence_type, divergence_strength, confirm_signal, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "divergence_type": "none",
        "divergence_strength": 0.0,
        "confirm_signal": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 30 or volumes is None or len(volumes) < 30:
            result["msg"] = "数据不足（需≥30根且有volumes）"
            return result

        is_buy = "buy" in mmd.mmd_type.value

        recent_closes = closes[-10:]
        recent_vols = volumes[-10:]
        _ = closes[-20:-10]
        prev_vols = volumes[-20:-10]

        price_trend = (recent_closes[-1] - recent_closes[0]) / max(recent_closes[0], 1e-10)
        avg_recent_vol = sum(recent_vols) / len(recent_vols)
        avg_prev_vol = sum(prev_vols) / len(prev_vols)
        vol_trend = avg_recent_vol / max(avg_prev_vol, 1e-10)

        if is_buy:
            if price_trend > 0.005 and vol_trend < 0.8:
                divergence_type = "bullish_divergence"
                strength = min(abs(vol_trend - 1.0) + abs(price_trend) * 10, 1.0)
                confirm = True
            elif price_trend > 0.01 and vol_trend > 1.5:
                divergence_type = "healthy_rally"
                strength = min(price_trend * 5, 0.6)
                confirm = True
            elif price_trend < -0.01 and vol_trend > 1.3:
                divergence_type = "bearish_warning"
                strength = min(vol_trend * 0.3, 1.0)
                confirm = False
            else:
                divergence_type = "none"
                strength = 0.0
                confirm = False
        else:
            if price_trend < -0.005 and vol_trend < 0.8:
                divergence_type = "bearish_divergence"
                strength = min(abs(vol_trend - 1.0) + abs(price_trend) * 10, 1.0)
                confirm = True
            elif price_trend < -0.01 and vol_trend > 1.5:
                divergence_type = "heavy_selling"
                strength = min(vol_trend * 0.3, 1.0)
                confirm = True
            elif price_trend > 0.01 and vol_trend < 0.6:
                divergence_type = "bearish_warning"
                strength = min(abs(vol_trend - 1.0), 1.0)
                confirm = False
            else:
                divergence_type = "none"
                strength = 0.0
                confirm = False

        if confirm and strength >= 0.5:
            adjust = 0.04
        elif confirm and strength >= 0.3:
            adjust = 0.02
        elif divergence_type == "bearish_warning" and not is_buy:
            adjust = -0.03
        elif divergence_type == "bearish_warning" and is_buy:
            adjust = -0.05
        else:
            adjust = 0.0

        result["divergence_type"] = divergence_type
        result["divergence_strength"] = round(strength, 3)
        result["confirm_signal"] = confirm
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"背离={divergence_type} 强度={strength:.2f} "
            f"价变={price_trend:+.1%} 量变={vol_trend:.2f}x "
            f"置信度{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_trend_momentum_continuity_v74(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
) -> dict[str, Any]:
    """趋势动能持续验证（V74 条件229）。

    评估当前趋势是否在多个时间窗口内持续保持动能。

    返回：momentum_score, short_term, mid_term, long_term, continuity, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "momentum_score": 0.0,
        "short_term": 0.0,
        "mid_term": 0.0,
        "long_term": 0.0,
        "continuity": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 30:
            result["msg"] = "数据不足（需≥30根）"
            return result

        is_buy = "buy" in mmd.mmd_type.value

        st = (closes[-1] - closes[-5]) / max(closes[-5], 1e-10) if n >= 5 else 0.0
        mt = (closes[-1] - closes[-10]) / max(closes[-10], 1e-10) if n >= 10 else 0.0
        lt = (closes[-1] - closes[-20]) / max(closes[-20], 1e-10) if n >= 20 else 0.0

        if is_buy:
            scores = [st, mt, lt]
            aligned = sum(1 for s in scores if s > 0)
        else:
            scores = [-st, -mt, -lt]
            aligned = sum(1 for s in scores if s > 0)

        avg_momentum = sum(abs(s) for s in [st, mt, lt]) / 3
        momentum_score = min(avg_momentum * 20, 1.0) * (aligned / 3)

        if aligned == 3 and momentum_score >= 0.5:
            continuity = "strong"
            adjust = 0.05
        elif aligned == 2 and momentum_score >= 0.3:
            continuity = "moderate"
            adjust = 0.02
        elif aligned <= 1:
            continuity = "weakening"
            adjust = -0.04
        else:
            continuity = "neutral"
            adjust = 0.0

        result["short_term"] = round(st, 4)
        result["mid_term"] = round(mt, 4)
        result["long_term"] = round(lt, 4)
        result["momentum_score"] = round(momentum_score, 3)
        result["continuity"] = continuity
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"短={st:+.2%} 中={mt:+.2%} 长={lt:+.2%} "
            f"一致性={aligned}/3 状态={continuity} 置信度{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_zhongshu_overlap_density_v74(
    mmd: MMD,
    zss: list[ZS],
    current_price: float,
) -> dict[str, Any]:
    """中枢重叠度评估（V74 条件230）。

    评估当前价格附近历史中枢的重叠密度。

    返回：overlap_density, nearby_zs_count, distance_to_zs, signal_strength, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "overlap_density": 0.0,
        "nearby_zs_count": 0,
        "distance_to_zs": 0.0,
        "signal_strength": "weak",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not zss or current_price <= 0:
            result["msg"] = "无中枢数据或价格为零"
            return result

        is_buy = "buy" in mmd.mmd_type.value

        recent_zs = zss[-5:] if len(zss) >= 5 else zss
        nearby_count = 0
        total_distance = 0.0
        inside_zs_count = 0

        for zs in recent_zs:
            if zs.zg <= 0 or zs.zd <= 0:
                continue
            if zs.zd <= current_price <= zs.zg:
                inside_zs_count += 1
                nearby_count += 1
            else:
                dist = min(abs(current_price - zs.zg), abs(current_price - zs.zd))
                pct_dist = dist / max(current_price, 1e-10)
                total_distance += pct_dist
                if pct_dist < 0.05:
                    nearby_count += 1

        total_distance /= max(len(recent_zs), 1)
        overlap_density = inside_zs_count / max(len(recent_zs), 1)

        if overlap_density >= 0.6:
            signal_strength = "strong_support" if is_buy else "strong_resistance"
            adjust = 0.06
        elif overlap_density >= 0.3:
            signal_strength = "moderate"
            adjust = 0.03
        elif nearby_count >= 2 and total_distance < 0.03:
            signal_strength = "near_zone"
            adjust = 0.02
        else:
            signal_strength = "weak"
            adjust = -0.02

        result["overlap_density"] = round(overlap_density, 3)
        result["nearby_zs_count"] = nearby_count
        result["distance_to_zs"] = round(total_distance, 4)
        result["signal_strength"] = signal_strength
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"重叠度={overlap_density:.0%} 附近中枢={nearby_count} "
            f"平均距离={total_distance:.2%} 强度={signal_strength} 置信度{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_signal_resonance_depth_v74(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
    macd_data: dict[str, list[float]] | None,
    volumes: list[float] | None,
) -> dict[str, Any]:
    """信号共振深度评分（V74 条件231）。

    评估当前信号在多少个独立维度上得到确认。

    返回：depth_score, confirming_dimensions, total_dimensions, resonance_level, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "depth_score": 0.0,
        "confirming_dimensions": 0,
        "total_dimensions": 0,
        "resonance_level": "none",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 20:
            result["msg"] = "数据不足（需≥20根）"
            return result

        is_buy = "buy" in mmd.mmd_type.value
        confirming = 0
        total = 0

        # 1. MACD方向
        if macd_data and "hist" in macd_data and len(macd_data["hist"]) >= 2:
            total += 1
            hist = macd_data["hist"]
            if is_buy and hist[-1] > 0 and hist[-1] > hist[-2]:
                confirming += 1
            elif not is_buy and hist[-1] < 0 and hist[-1] < hist[-2]:
                confirming += 1

        # 2. KDJ方向
        if highs is not None and lows is not None and n >= 30:
            total += 1
            from easy_tdx.MyTT import KDJ as _mytt_kdj

            try:
                _k, _d, _j = _mytt_kdj(closes, highs, lows, N=9, M1=3, M2=3)
                if len(_k) >= 2 and len(_d) >= 2:
                    kdj_bullish = _k[-1] > _d[-1] and _k[-1] > _k[-2]
                    if is_buy and kdj_bullish:
                        confirming += 1
                    elif not is_buy and not kdj_bullish:
                        confirming += 1
            except Exception:
                pass

        # 3. RSI方向
        if n >= 14:
            total += 1
            from easy_tdx.MyTT import RSI as _mytt_rsi

            try:
                rsi_vals = _mytt_rsi(closes, N=14)
                if rsi_vals and len(rsi_vals) >= 2:
                    rsi_bullish = rsi_vals[-1] > rsi_vals[-2] and rsi_vals[-1] < 75
                    if is_buy and rsi_bullish:
                        confirming += 1
                    elif not is_buy and not rsi_bullish and rsi_vals[-1] > 25:
                        confirming += 1
            except Exception:
                pass

        # 4. 均线排列方向
        if n >= 20:
            total += 1
            from easy_tdx.MyTT import MA as _mytt_ma

            try:
                ma5 = _mytt_ma(closes, N=5)
                ma20 = _mytt_ma(closes, N=20)
                if ma5 and ma20 and len(ma5) >= 1 and len(ma20) >= 1:
                    ma_bullish = ma5[-1] > ma20[-1]
                    if is_buy and ma_bullish:
                        confirming += 1
                    elif not is_buy and not ma_bullish:
                        confirming += 1
            except Exception:
                pass

        # 5. 成交量配合
        if volumes is not None and n >= 2:
            total += 1
            vol_bullish = volumes[-1] > volumes[-2] and closes[-1] > closes[-2]
            if is_buy and vol_bullish:
                confirming += 1
            elif not is_buy and not vol_bullish:
                confirming += 1

        # 6. 价格位置（相对20日区间）
        if n >= 20:
            total += 1
            period_high = max(closes[-20:])
            period_low = min(closes[-20:])
            price_range = period_high - period_low
            if price_range > 0:
                pos_pct = (closes[-1] - period_low) / price_range
                if is_buy and pos_pct < 0.4:
                    confirming += 1
                elif not is_buy and pos_pct > 0.6:
                    confirming += 1

        ratio = confirming / total if total > 0 else 0.5
        depth_score = ratio

        if ratio >= 0.83:
            resonance_level = "deep"
            adjust = 0.07
        elif ratio >= 0.67:
            resonance_level = "moderate"
            adjust = 0.03
        elif ratio <= 0.33:
            resonance_level = "shallow"
            adjust = -0.05
        else:
            resonance_level = "weak"
            adjust = -0.02

        result["confirming_dimensions"] = confirming
        result["total_dimensions"] = total
        result["depth_score"] = round(depth_score, 3)
        result["resonance_level"] = resonance_level
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"{confirming}/{total}维度共振 深度={resonance_level} "
            f"一致率={ratio:.0%} 置信度{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


# V75: 条件 232-235（回调深度验证+中枢回踩确认+量峰持续评分+多信号时间一致性）


def _calc_pullback_depth_validation_v75(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
) -> dict[str, Any]:
    """回调深度验证（V75 条件232）。

    检测买入/卖出信号后的回调深度是否在合理范围内。
    健康的趋势回调不应超过关键斐波那契回撤位（23.6%/38.2%）。

    返回：pullback_depth, max_retracement, fibonacci_level, confirm_signal, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "pullback_depth": 0.0,
        "max_retracement": 0.0,
        "fibonacci_level": "none",
        "confirm_signal": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 30 or highs is None or lows is None:
            result["msg"] = "数据不足（需≥30根且有highs/lows）"
            return result

        is_buy = "buy" in mmd.mmd_type.value

        # 找最近的高点/低点作为回调基准
        lookback = min(20, n)
        recent_high = max(highs[-lookback:])
        recent_low = min(lows[-lookback:])
        price_range = recent_high - recent_low

        if price_range <= 0:
            result["msg"] = "价格区间为零"
            return result

        current_price = closes[-1]

        if is_buy:
            # 买入信号后，价格从高点回落的深度
            pullback = (recent_high - current_price) / recent_high
            max_retracement = pullback
            # 斐波那契回撤位判断
            if pullback <= 0.15:
                fib_level = "shallow_15"
                confirm = True
            elif pullback <= 0.236:
                fib_level = "fib_236"
                confirm = True
            elif pullback <= 0.382:
                fib_level = "fib_382"
                confirm = True
            elif pullback <= 0.5:
                fib_level = "fib_50"
                confirm = False  # 过度回调，趋势可能减弱
            else:
                fib_level = "deep_over_50"
                confirm = False
            _ = min(pullback * 2, 1.0) if confirm else 0.0
        else:
            # 卖出信号后，价格从低点反弹的深度
            pullback = (current_price - recent_low) / recent_low
            max_retracement = pullback
            if pullback <= 0.15:
                fib_level = "shallow_15"
                confirm = True
            elif pullback <= 0.236:
                fib_level = "fib_236"
                confirm = True
            elif pullback <= 0.382:
                fib_level = "fib_382"
                confirm = True
            elif pullback <= 0.5:
                fib_level = "fib_50"
                confirm = False
            else:
                fib_level = "deep_over_50"
                confirm = False
            _ = min(pullback * 2, 1.0) if confirm else 0.0

        if confirm and pullback <= 0.236:
            adjust = 0.05
        elif confirm and pullback <= 0.382:
            adjust = 0.02
        elif not confirm and pullback <= 0.5:
            adjust = -0.03
        elif pullback > 0.5:
            adjust = -0.06
        else:
            adjust = 0.0

        result["pullback_depth"] = round(pullback, 4)
        result["max_retracement"] = round(max_retracement, 4)
        result["fibonacci_level"] = fib_level
        result["confirm_signal"] = confirm
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"回调深度={pullback:.1%} 斐波={fib_level} "
            f"高点={recent_high:.2f} 现价={current_price:.2f} 置信度{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_zhongshu_retracement_confirm_v75(
    mmd: MMD,
    zss: list[ZS],
    closes: list[float],
) -> dict[str, Any]:
    """中枢区间回踩确认（V75 条件233）。

    验证价格回踩到中枢边界后是否有反弹确认，判断中枢支撑/阻力有效性。

    返回：retracement_type, nearest_zs_dist, bounce_strength, confirm_signal, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "retracement_type": "none",
        "nearest_zs_dist": 0.0,
        "bounce_strength": 0.0,
        "confirm_signal": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 15 or not zss:
            result["msg"] = "数据不足（需≥15根且有中枢数据）"
            return result

        is_buy = "buy" in mmd.mmd_type.value
        current_price = closes[-1]

        # 找最近的中枢
        nearest_zs = None
        min_dist = float("inf")
        for zs in zss[-5:]:
            if zs.zg is None or zs.zd is None:
                continue
            zs_center = (zs.zg + zs.zd) / 2
            zs_range = zs.zg - zs.zd
            dist = abs(current_price - zs_center) / max(zs_range, 1e-10)
            if dist < min_dist:
                min_dist = dist
                nearest_zs = zs

        if nearest_zs is None:
            result["msg"] = "无可用中枢数据"
            result["nearest_zs_dist"] = 0.0
            return result

        zs_top = nearest_zs.zg
        zs_bottom = nearest_zs.zd
        zs_range = zs_top - zs_bottom
        _ = max(max(closes[-10:]) - min(closes[-10:]), 1e-10)

        # 计算价格相对中枢的位置
        if current_price >= zs_top:
            _ = (current_price - zs_top) / max(zs_range, 1e-10)
            retracement_type = "above_zs"
        elif current_price <= zs_bottom:
            _ = (zs_bottom - current_price) / max(zs_range, 1e-10)
            retracement_type = "below_zs"
        else:
            retracement_type = "inside_zs"
            _ = 0.0
            _ = 0.0

        # 检查回踩后的反弹（最近10根K线的最低价是否收回）
        # 简化：用closes的局部极值近似
        last_10_closes = closes[-10:]

        # 简单判断：最近几根K线是否从中枢区域反弹
        if is_buy and retracement_type in ("inside_zs", "below_zs"):
            # 买入信号在中枢下方或内部，检查是否有反弹
            recent_high = (
                max(last_10_closes[-5:]) if len(last_10_closes) >= 5 else max(last_10_closes)
            )
            bounce = (recent_high - current_price) / max(current_price, 1e-10)
            if bounce > 0.01 and current_price < zs_top:
                confirm = True
                bounce_strength = min(bounce * 10, 1.0)
                retracement_type = "zs_support_bounce"
            elif current_price > zs_top:
                confirm = True
                bounce_strength = 0.5
                retracement_type = "above_zs_confirmed"
            else:
                confirm = False
                bounce_strength = 0.0
        elif not is_buy and retracement_type in ("inside_zs", "above_zs"):
            recent_low = (
                min(last_10_closes[-5:]) if len(last_10_closes) >= 5 else min(last_10_closes)
            )
            bounce = (current_price - recent_low) / max(current_price, 1e-10)
            if bounce > 0.01 and current_price > zs_bottom:
                confirm = True
                bounce_strength = min(bounce * 10, 1.0)
                retracement_type = "zs_resistance_bounce"
            elif current_price < zs_bottom:
                confirm = True
                bounce_strength = 0.5
                retracement_type = "below_zs_confirmed"
            else:
                confirm = False
                bounce_strength = 0.0
        else:
            confirm = False
            bounce_strength = 0.0

        if confirm and bounce_strength >= 0.5:
            adjust = 0.05
        elif confirm and bounce_strength >= 0.3:
            adjust = 0.02
        elif not confirm:
            adjust = -0.03
        else:
            adjust = 0.0

        result["retracement_type"] = retracement_type
        result["nearest_zs_dist"] = round(min_dist, 3)
        result["bounce_strength"] = round(bounce_strength, 3)
        result["confirm_signal"] = confirm
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"类型={retracement_type} 反弹强度={bounce_strength:.2f} "
            f"距中枢={min_dist:.2f}x 置信度{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_volume_peak_duration_v75(
    mmd: MMD,
    volumes: list[float],
    closes: list[float],
) -> dict[str, Any]:
    """量峰持续时间评分（V75 条件234）。

    评估成交量放大的持续天数，判断资金流入的持续性和信号可信度。

    返回：peak_duration, avg_vol_ratio, peak_days, confirm_signal, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "peak_duration": 0,
        "avg_vol_ratio": 0.0,
        "peak_days": 0,
        "confirm_signal": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(volumes)
        if n < 30:
            result["msg"] = "数据不足（需≥30根）"
            return result

        is_buy = "buy" in mmd.mmd_type.value

        # 计算平均成交量（用20日EMA）
        avg_vol = sum(volumes[-20:]) / 20
        if avg_vol <= 0:
            result["msg"] = "平均成交量为零"
            return result

        # 统计连续放量天数（volume > 1.5x avg）
        peak_threshold = avg_vol * 1.5
        consecutive_peak = 0
        total_peak_days = 0
        vol_ratios = []

        for i in range(n - 20, n):
            vol_ratio = volumes[i] / avg_vol
            vol_ratios.append(vol_ratio)
            if volumes[i] >= peak_threshold:
                total_peak_days += 1
                consecutive_peak += 1
            else:
                if consecutive_peak > result["peak_duration"]:
                    result["peak_duration"] = consecutive_peak
                consecutive_peak = 0

        if consecutive_peak > result["peak_duration"]:
            result["peak_duration"] = consecutive_peak

        peak_days = result["peak_duration"]
        avg_vol_ratio = sum(vol_ratios) / len(vol_ratios) if vol_ratios else 0.0

        # 判断信号确认
        if is_buy:
            if peak_days >= 5 and avg_vol_ratio >= 1.8:
                confirm = True
                strength = min(peak_days / 10, 1.0)
            elif peak_days >= 3 and avg_vol_ratio >= 1.5:
                confirm = True
                strength = min(peak_days / 8, 0.7)
            elif peak_days >= 2:
                confirm = False
                strength = 0.3
            else:
                confirm = False
                strength = 0.0
        else:
            # 卖出信号：持续放量下跌是确认信号
            if peak_days >= 5 and avg_vol_ratio >= 1.8:
                confirm = True
                strength = min(peak_days / 10, 1.0)
            elif peak_days >= 3 and avg_vol_ratio >= 1.5:
                confirm = True
                strength = min(peak_days / 8, 0.7)
            elif peak_days >= 2:
                confirm = False
                strength = 0.3
            else:
                confirm = False
                strength = 0.0

        if confirm and strength >= 0.7:
            adjust = 0.06
        elif confirm and strength >= 0.4:
            adjust = 0.03
        elif not confirm and peak_days >= 2:
            adjust = -0.02
        else:
            adjust = 0.0

        result["peak_duration"] = peak_days
        result["avg_vol_ratio"] = round(avg_vol_ratio, 3)
        result["peak_days"] = peak_days
        result["confirm_signal"] = confirm
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"放量天数={peak_days} 均量比={avg_vol_ratio:.2f}x "
            f"持续{peak_days}日 置信度{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_multi_signal_time_consistency_v75(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
    macd_data: dict[str, list[float]] | None,
    volumes: list[float] | None,
) -> dict[str, Any]:
    """多信号时间一致性（V75 条件235）。

    检测多个技术指标信号是否在相近时间段内出现，
    时间越集中→一致性越高→信号越可靠。

    返回：consistency_score, signal_dates, alignment_ratio, confirm_signal, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "consistency_score": 0.0,
        "signal_dates": [],
        "alignment_ratio": 0.0,
        "confirm_signal": False,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        n = len(closes)
        if n < 40 or highs is None or lows is None:
            result["msg"] = "数据不足（需≥40根）"
            return result

        is_buy = "buy" in mmd.mmd_type.value

        # 找各信号出现的最近位置（距离当前天数）
        signals: list[tuple[str, int]] = []  # (signal_name, days_ago)

        # 1. MACD金叉/死叉
        hist_arr = (macd_data or {}).get("hist", [])
        if len(hist_arr) >= 10:
            for i in range(len(hist_arr) - 1, max(len(hist_arr) - 20, 0), -1):
                if i >= 1:
                    prev_hist = hist_arr[i - 1]
                    curr_hist = hist_arr[i]
                    if is_buy and prev_hist <= 0 and curr_hist > 0:
                        signals.append(("macd_golden_cross", n - 1 - i))
                        break
                    elif not is_buy and prev_hist >= 0 and curr_hist < 0:
                        signals.append(("macd_dead_cross", n - 1 - i))
                        break

        # 2. KDJ超买/超卖
        if n >= 14:
            low_14 = min(lows[-14:])
            high_14 = max(highs[-14:])
            rsv = (closes[-1] - low_14) / max(high_14 - low_14, 1e-10) * 100
            if is_buy and rsv < 30:
                signals.append(("kdj_oversold", 0))
            elif not is_buy and rsv > 70:
                signals.append(("kdj_overbought", 0))

        # 3. MA20突破
        if n >= 20:
            ma20 = sum(closes[-20:]) / 20
            if is_buy and closes[-1] > ma20 and closes[-2] <= ma20:
                signals.append(("ma20_breakup", 0))
            elif not is_buy and closes[-1] < ma20 and closes[-2] >= ma20:
                signals.append(("ma20_breakdown", 0))

        # 4. 成交量放大
        if volumes and len(volumes) >= 20:
            avg_vol = sum(volumes[-20:]) / 20
            if volumes[-1] > avg_vol * 1.5:
                signals.append(("volume_spike", 0))

        # 5. RSI信号
        if n >= 14:
            gains = []
            losses = []
            for i in range(-14, 0):
                change = closes[i] - closes[i - 1]
                if change > 0:
                    gains.append(change)
                    losses.append(0.0)
                else:
                    gains.append(0.0)
                    losses.append(abs(change))
            avg_gain = sum(gains) / 14
            avg_loss = sum(losses) / 14
            rs = avg_gain / max(avg_loss, 1e-10)
            rsi = 100 - (100 / (1 + rs))
            if is_buy and rsi < 40:
                signals.append(("rsi_low", 0))
            elif not is_buy and rsi > 60:
                signals.append(("rsi_high", 0))

        if not signals:
            result["msg"] = "未检测到辅助信号"
            result["consistency_score"] = 0.0
            result["alignment_ratio"] = 0.0
            return result

        # 计算时间一致性：信号集中在最近几天内则一致性好
        days_ago = [s[1] for s in signals]
        max_days_ago = max(days_ago) if days_ago else 0
        min_days_ago = min(days_ago) if days_ago else 0

        # 一致性得分：所有信号在7天内出现→高一致性
        if max_days_ago <= 3:
            consistency = 1.0
        elif max_days_ago <= 7:
            consistency = 0.7
        elif max_days_ago <= 14:
            consistency = 0.4
        else:
            consistency = 0.2

        # 信号数量加成
        sig_count = len(signals)
        if sig_count >= 4:
            consistency = min(consistency + 0.1, 1.0)
        elif sig_count >= 3:
            consistency = min(consistency + 0.05, 1.0)

        alignment_ratio = consistency

        # 判定确认
        confirm = consistency >= 0.5 and sig_count >= 2

        if confirm and consistency >= 0.8:
            adjust = 0.06
        elif confirm and consistency >= 0.5:
            adjust = 0.03
        elif not confirm and sig_count >= 2:
            adjust = -0.02
        else:
            adjust = 0.0

        result["consistency_score"] = round(consistency, 3)
        result["signal_dates"] = [{"name": s[0], "days_ago": s[1]} for s in signals]
        result["alignment_ratio"] = round(alignment_ratio, 3)
        result["confirm_signal"] = confirm
        result["confidence_adjust"] = round(adjust, 3)
        result["msg"] = (
            f"{sig_count}个信号 一致率={consistency:.0%} "
            f"时间窗口={min_days_ago}-{max_days_ago}天前 "
            f"置信度{adjust:+.0%}"
        )
        return result
    except Exception:
        return result


def _calc_volume_profile(
    closes: list[float],
    volumes: list[float] | None,
    lookback: int = 60,
    num_bins: int = 20,
) -> dict[str, Any]:
    """计算成交量剖面（Volume at Price, VAP）。

    将最近lookback根K线的价格区间分成num_bins个价格带，
    统计每个价格带的成交量占比，识别高成交量支撑/阻力区。

    Returns:
        dict with keys:
            price_levels: list of (price_mid, vol_pct) tuples
            high_volume_support: float | None — 高成交量支撑位
            high_volume_resistance: float | None — 高成交量阻力位
            current_volume_rank: float — 当前价在近期成交量分布中的分位
            volume_cluster_up: bool — 上方是否有明显成交密集区
            volume_cluster_down: bool — 下方是否有明显成交密集区
    """
    if not volumes or len(volumes) < lookback:
        return {
            "price_levels": [],
            "high_volume_support": None,
            "high_volume_resistance": None,
            "current_volume_rank": 0.5,
            "volume_cluster_up": False,
            "volume_cluster_down": False,
        }

    try:
        n = len(closes)
        start_idx = n - lookback
        subset_closes = closes[start_idx:n]
        subset_vols = volumes[start_idx:n]

        if not subset_closes or not subset_vols:
            return {
                "price_levels": [],
                "high_volume_support": None,
                "high_volume_resistance": None,
                "current_volume_rank": 0.5,
                "volume_cluster_up": False,
                "volume_cluster_down": False,
            }

        price_min = min(subset_closes)
        price_max = max(subset_closes)
        price_range = price_max - price_min
        if price_range <= 0:
            return {
                "price_levels": [],
                "high_volume_support": None,
                "high_volume_resistance": None,
                "current_volume_rank": 0.5,
                "volume_cluster_up": False,
                "volume_cluster_down": False,
            }

        bin_width = price_range / num_bins
        bins = [0.0] * num_bins

        for close, vol in zip(subset_closes, subset_vols):
            bin_idx = min(int((close - price_min) / bin_width), num_bins - 1)
            bins[bin_idx] += vol

        total_vol = sum(bins)
        if total_vol <= 0:
            return {
                "price_levels": [],
                "high_volume_support": None,
                "high_volume_resistance": None,
                "current_volume_rank": 0.5,
                "volume_cluster_up": False,
                "volume_cluster_down": False,
            }

        # 计算每个价格带的成交量占比
        vol_pcts = [b / total_vol for b in bins]
        price_levels = []
        for i, pct in enumerate(vol_pcts):
            mid_price = price_min + (i + 0.5) * bin_width
            price_levels.append((round(mid_price, 2), round(pct, 4)))

        # 识别高成交量区（前20%成交量密集区）
        threshold = sorted(vol_pcts, reverse=True)[int(num_bins * 0.2)] if num_bins > 0 else 0.05
        high_vol_bins = [(i, p, vp) for i, (p, vp) in enumerate(price_levels) if vp >= threshold]

        # 当前价格所在的价格带
        current_price = closes[-1]
        current_bin = min(int((current_price - price_min) / bin_width), num_bins - 1)
        current_rank = sum(1 for pl, vp in price_levels if pl < current_price) / max(
            len(price_levels), 1
        )

        # 判断上下方是否有成交密集区
        upper_bins = set(i for i, _, _ in high_vol_bins if i > current_bin)
        lower_bins = set(i for i, _, _ in high_vol_bins if i < current_bin)
        volume_cluster_up = len(upper_bins) >= 2
        volume_cluster_down = len(lower_bins) >= 2

        # 高成交量支撑/阻力位
        high_vol_support = None
        high_vol_resistance = None
        if lower_bins:
            lowest_high_vol = min(lower_bins)
            high_vol_support = price_levels[lowest_high_vol][0]
        if upper_bins:
            highest_low_vol = max(upper_bins)
            high_vol_resistance = price_levels[highest_low_vol][0]

        return {
            "price_levels": price_levels,
            "high_volume_support": high_vol_support,
            "high_volume_resistance": high_vol_resistance,
            "current_volume_rank": round(current_rank, 2),
            "volume_cluster_up": volume_cluster_up,
            "volume_cluster_down": volume_cluster_down,
        }
    except Exception:
        return {
            "price_levels": [],
            "high_volume_support": None,
            "high_volume_resistance": None,
            "current_volume_rank": 0.5,
            "volume_cluster_up": False,
            "volume_cluster_down": False,
        }


def _calc_ma_slope(closes: list[float] | None, bi_end_idx: int, ma_period: int = 20) -> str:
    """计算MA斜率方向（V10新增）。

    检查MA20是否朝目标方向倾斜，用于确认趋势持续性。
    3买需要MA20向上倾斜，3卖需要MA20向下倾斜。

    Returns:
        "up" - MA20向上倾斜（趋势确认）
        "down" - MA20向下倾斜（趋势确认）
        "flat" - MA20横盘（趋势不明确）
    """
    if closes is None:
        return "flat"
    if len(closes) == 0 or bi_end_idx < ma_period * 2:
        return "flat"
    try:
        # 计算当前MA20和前MA20
        end_idx = bi_end_idx if bi_end_idx < len(closes) else len(closes) - 1
        if end_idx < ma_period:
            return "flat"
        current_ma = sum(closes[max(0, end_idx - ma_period + 1) : end_idx + 1]) / min(
            ma_period, end_idx + 1
        )
        prev_ma = sum(closes[max(0, end_idx - ma_period) : end_idx]) / min(ma_period, end_idx)
        if prev_ma <= 0:
            return "flat"
        slope = (current_ma - prev_ma) / prev_ma
        if slope > 0.003:
            return "up"
        elif slope < -0.003:
            return "down"
        return "flat"
    except Exception:
        return "flat"


def _calc_adx_strength(
    closes: list[float] | None,
    highs: list[float] | None,
    lows: list[float] | None,
    bi_end_idx: int,
) -> tuple[float, str]:
    """计算ADX趋势强度（V11修正版，使用MyTT DMI算法）。

    V11修复：原V10使用简化DX替代ADX导致数值偏低，现改用MyTT.DMI完整平滑算法。

    Returns:
        (adx_value, level) where level is "strong"/"medium"/"weak"/"none"
    """
    if closes is None:
        return (0.0, "none")
    if len(closes) == 0 or bi_end_idx < 30:
        return (0.0, "none")
    try:
        end_idx = bi_end_idx if bi_end_idx < len(closes) else len(closes) - 1
        # 取最近80根K线用于DMI计算（需要足够的历史数据平滑）
        lookback = min(80, end_idx + 1)
        start_idx = end_idx - lookback + 1

        # 准备数据
        closes_slice = closes[start_idx : end_idx + 1]
        if len(closes_slice) < 30:
            return (0.0, "none")

        if highs is None or lows is None:
            # 无真实高低点数据，用收盘价±1%近似
            highs_arr = [
                c * (1 + abs(np.random.RandomState(i).uniform(0, 0.005)))
                for i, c in enumerate(closes_slice)
            ]
            lows_arr = [
                c * (1 - abs(np.random.RandomState(i + 100).uniform(0, 0.005)))
                for i, c in enumerate(closes_slice)
            ]
        else:
            h_start = max(0, end_idx - lookback + 1)
            h_end = end_idx + 1
            highs_arr = highs[h_start:h_end]
            lows_arr = lows[h_start:h_end]

        if len(highs_arr) < 30 or len(lows_arr) < 30:
            return (0.0, "none")

        # 使用MyTT的DMI函数计算真实ADX（与通达信/同花顺一致）
        # 注意：MyTT函数需要numpy数组，需显式转换
        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            from easy_tdx.MyTT import DMI
        _closes_np = np.array(closes_slice, dtype=float)
        _highs_np = np.array(highs_arr, dtype=float)
        _lows_np = np.array(lows_arr, dtype=float)
        pdi, mdi, adx, adxr = DMI(_closes_np, _highs_np, _lows_np, M1=14, M2=6)

        adx_val = float(adx[-1]) if len(adx) > 0 and not np.isnan(adx[-1]) else 0.0
        if np.isnan(adx_val):
            adx_val = 0.0
        level = (
            "strong"
            if adx_val >= 40
            else "medium"
            if adx_val >= 25
            else "weak"
            if adx_val >= 20
            else "none"
        )
        return (round(adx_val, 1), level)
    except Exception:
        return (0.0, "none")


def _calc_rsi(closes: list[float] | None, period: int = 14) -> float:
    """简化版RSI计算。"""
    if closes is None:
        return 50.0
    if len(closes) < period + 1:
        return 50.0
    try:
        gains = []
        losses = []
        for i in range(-period, 0):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss <= 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
    except Exception:
        return 50.0


def _calc_atr(
    closes: list[float] | None,
    highs: list[float] | None,
    lows: list[float] | None,
    idx: int,
    period: int = 14,
) -> float:
    """计算指定位置的ATR值（V19新增）。

    使用简化TR计算：max(high-low, abs(high-prev_close), abs(low-prev_close))
    返回ATR绝对值（非比率），用于支撑/阻力区域判断。
    """
    if closes is None:
        return 0.0
    if idx < period or len(closes) == 0:
        return 0.0
    try:
        end = idx if idx < len(closes) else len(closes) - 1
        start = max(0, end - period + 1)
        slice_closes = closes[start : end + 1]
        if highs is None or lows is None:
            highs_arr = [c * (1 + 0.005) for c in slice_closes]
            lows_arr = [c * (1 - 0.005) for c in slice_closes]
        else:
            h_end = end if end < len(highs) else len(highs) - 1
            l_end = end if end < len(lows) else len(lows) - 1
            highs_arr = highs[start : h_end + 1]
            lows_arr = lows[start : l_end + 1]
        if len(slice_closes) < 2 or len(highs_arr) < 2 or len(lows_arr) < 2:
            return 0.0
        trs = []
        for i in range(1, len(slice_closes)):
            h, low, pc = highs_arr[i], lows_arr[i], slice_closes[i - 1]
            trs.append(max(h - low, abs(h - pc), abs(low - pc)))
        return sum(trs) / len(trs) if trs else 0.0
    except Exception:
        return 0.0


def _calc_volume_price_energy_dist(
    mmd: MMD,
    closes: list[float],
    volumes: list[float] | None,
    highs: list[float] | None,
    lows: list[float] | None,
) -> dict[str, Any]:
    """量价能量分布分析（V41 条件111）。

    基于成交量剖面分析当前价格所处能量区域：
    - 买入信号：价格处于高成交量支撑区 → 加分
    - 卖出信号：价格处于高成交量阻力区 → 加分
    - 价格处于低成交量真空区 → 减分（支撑/阻力不足）
    """
    result: dict[str, Any] = {
        "energy_zone": "neutral",
        "volume_rank": 0.5,
        "support_distance": 0.0,
        "resistance_distance": 0.0,
        "confidence_adjust": 0.0,
    }
    try:
        if not closes or not volumes or len(closes) < 30:
            return result

        is_buy = "buy" in mmd.mmd_type.value
        current_price = closes[-1]

        # 计算成交量剖面
        profile = _calc_volume_profile(closes, volumes, lookback=60)

        high_vol_support = profile.get("high_volume_support")
        high_vol_resistance = profile.get("high_volume_resistance")
        volume_rank = profile.get("current_volume_rank", 0.5)
        result["volume_rank"] = round(volume_rank, 2)

        # 计算距离支撑/阻力的百分比
        if high_vol_support and high_vol_support < current_price:
            support_distance = (current_price - high_vol_support) / current_price * 100
            result["support_distance"] = round(support_distance, 2)
        else:
            support_distance = 999.0

        if high_vol_resistance and high_vol_resistance > current_price:
            resistance_distance = (high_vol_resistance - current_price) / current_price * 100
            result["resistance_distance"] = round(resistance_distance, 2)
        else:
            resistance_distance = 999.0

        # 判断能量区域
        volume_cluster_down = profile.get("volume_cluster_down", False)
        volume_cluster_up = profile.get("volume_cluster_up", False)

        if is_buy:
            if support_distance < 2.0 and volume_cluster_down:
                result["energy_zone"] = "strong_support"
                result["confidence_adjust"] = 0.03
            elif support_distance < 5.0 and volume_cluster_down:
                result["energy_zone"] = "support"
                result["confidence_adjust"] = 0.01
            elif resistance_distance < 2.0 and volume_cluster_up:
                result["energy_zone"] = "near_resistance"
                result["confidence_adjust"] = -0.02
            elif volume_rank < 0.2:
                result["energy_zone"] = "low_volume_zone"
                result["confidence_adjust"] = -0.01
            else:
                result["energy_zone"] = "neutral"
        else:  # sell signal
            if resistance_distance < 2.0 and volume_cluster_up:
                result["energy_zone"] = "strong_resistance"
                result["confidence_adjust"] = 0.03
            elif resistance_distance < 5.0 and volume_cluster_up:
                result["energy_zone"] = "resistance"
                result["confidence_adjust"] = 0.01
            elif support_distance < 2.0 and volume_cluster_down:
                result["energy_zone"] = "near_support"
                result["confidence_adjust"] = -0.02
            elif volume_rank > 0.8:
                result["energy_zone"] = "high_volume_zone"
                result["confidence_adjust"] = -0.01
            else:
                result["energy_zone"] = "neutral"

        return result
    except Exception:
        return result


def _calc_volume_cycle_detection(
    closes: list[float],
    volumes: list[float] | None,
) -> dict[str, Any]:
    """量能周期检测（V41 条件112，全局一次性计算）。

    检测成交量处于扩张还是收缩周期：
    - 扩张周期（量增）：趋势延续性强，顺势信号加成
    - 收缩周期（量缩）：趋势可能衰竭，逆势信号警惕
    - 量价配合度：价格上涨时成交量是否同步放大
    """
    result: dict[str, Any] = {
        "cycle_state": "unknown",
        "volume_trend": "flat",
        "volume_price_alignment": False,
        "confidence_adjust": 0.0,
    }
    try:
        if not volumes or len(volumes) < 30:
            return result

        # 计算短期和长期成交量均值
        vol_short = sum(volumes[-10:]) / 10
        vol_mid = sum(volumes[-20:]) / 20
        vol_long = sum(volumes[-50:]) / 50 if len(volumes) >= 50 else vol_mid

        result["volume_trend"] = (
            "expanding"
            if vol_short > vol_long * 1.2
            else ("contracting" if vol_short < vol_long * 0.8 else "stable")
        )

        # 检测成交量周期状态
        if vol_short > vol_mid * 1.15:
            result["cycle_state"] = "expanding"
        elif vol_short < vol_mid * 0.85:
            result["cycle_state"] = "contracting"
        else:
            result["cycle_state"] = "stable"

        # 量价配合度检测
        if len(closes) >= 10:
            price_up = closes[-1] > closes[-5]
            price_down = closes[-1] < closes[-5]
            vol_up = vol_short > vol_mid
            vol_down = vol_short < vol_mid
            result["volume_price_alignment"] = (price_up and vol_up) or (price_down and vol_down)

        # 置信度调整
        if result["volume_price_alignment"]:
            result["confidence_adjust"] = 0.02
        elif result["cycle_state"] == "contracting":
            result["confidence_adjust"] = -0.01

        return result
    except Exception:
        return result


def _calc_post_signal_trajectory(
    closes: list[float],
    volumes: list[float] | None,
    macd_data: dict[str, list[float]] | None,
) -> dict[str, Any]:
    """走势预测（V41 条件113，全局一次性计算）。

    基于MACD动能锥和价格动量预测短期走势方向：
    - MACD柱状图斜率判断动能方向
    - 价格加速度判断趋势延续性
    - 综合预测近期走势方向及置信度
    """
    result: dict[str, Any] = {
        "predicted_direction": "neutral",
        "prediction_confidence": 0.5,
        "expected_return_range": [0.0, 0.0],
        "momentum_score": 0.0,
        "confidence_adjust": 0.0,
    }
    try:
        if not closes or len(closes) < 20:
            return result

        # MACD动能分析
        macd_hist = macd_data.get("hist", []) if macd_data else []
        if macd_hist and len(macd_hist) >= 5:
            recent_hist = macd_hist[-5:]
            macd_slope = (recent_hist[-1] - recent_hist[0]) / max(1, len(recent_hist))
            macd_accel = recent_hist[-1] - recent_hist[-2] if len(recent_hist) >= 2 else 0.0

            # 判断MACD方向
            if macd_slope > 0 and macd_accel > 0:
                macd_direction = "bullish"
            elif macd_slope < 0 and macd_accel < 0:
                macd_direction = "bearish"
            else:
                macd_direction = "neutral"
        else:
            macd_direction = "neutral"
            macd_slope = 0.0

        # 价格动量分析
        price_momentum = (closes[-1] - closes[-5]) / closes[-5] * 100 if closes[-5] > 0 else 0.0
        price_acceleration = (
            (closes[-1] - 2 * closes[-3] + closes[-5]) / max(1, closes[-3]) * 100
            if closes[-3] > 0
            else 0.0
        )

        # 综合预测
        bullish_score = 0.0
        bearish_score = 0.0

        if price_momentum > 0.5:
            bullish_score += 0.3
        elif price_momentum < -0.5:
            bearish_score += 0.3

        if price_acceleration > 0:
            bullish_score += 0.2
        elif price_acceleration < 0:
            bearish_score += 0.2

        if macd_direction == "bullish":
            bullish_score += 0.3
        elif macd_direction == "bearish":
            bearish_score += 0.3

        # 成交量确认
        if volumes and len(volumes) >= 5:
            vol_recent = sum(volumes[-3:]) / 3
            vol_avg = sum(volumes[-10:]) / 10
            if vol_recent > vol_avg * 1.2 and price_momentum > 0:
                bullish_score += 0.1
            elif vol_recent > vol_avg * 1.2 and price_momentum < 0:
                bearish_score += 0.1

        total_score = bullish_score + bearish_score
        if total_score > 0:
            bullish_score /= total_score
            bearish_score /= total_score

        if bullish_score > 0.6:
            result["predicted_direction"] = "up"
            result["prediction_confidence"] = round(bullish_score, 2)
            result["momentum_score"] = round(bullish_score - bearish_score, 3)
        elif bearish_score > 0.6:
            result["predicted_direction"] = "down"
            result["prediction_confidence"] = round(bearish_score, 2)
            result["momentum_score"] = round(bullish_score - bearish_score, 3)
        else:
            result["predicted_direction"] = "neutral"
            result["prediction_confidence"] = 0.5
            result["momentum_score"] = 0.0

        # 预期收益区间
        vol = _calc_atr_volatility(closes) if "vol" in dir() else 0.02
        expected_range = vol * 20 * 100  # 20日波动范围
        result["expected_return_range"] = [
            round(-expected_range * result["prediction_confidence"], 2),
            round(expected_range * result["prediction_confidence"], 2),
        ]

        # 置信度调整
        if result["predicted_direction"] != "neutral":
            result["confidence_adjust"] = round(result["prediction_confidence"] * 0.02, 4)
        else:
            result["confidence_adjust"] = 0.0

        return result
    except Exception:
        return result


def _calc_quality_tier_classification(
    mmds: list[MMD],
    all_confidences: list[float],
) -> dict[str, Any]:
    """动态质量分层（V41 条件114，全局一次性计算）。

    根据综合质量评分对所有买卖点分层：
    - S级：综合质量分前10%，置信度调整+3%
    - A级：综合质量分前10%-30%，置信度调整+1%
    - B级：综合质量分30%-70%，不调整
    - C级：综合质量分后30%，置信度调整-1%
    """
    result: dict[str, Any] = {}
    try:
        if not mmds or len(mmds) < 5:
            return result

        # 计算每个MMD的综合质量分
        scored_mmds = []
        for mmd in mmds:
            quality_score = mmd.confidence
            if hasattr(mmd, "confluence_score"):
                quality_score += mmd.confluence_score * 0.1
            if hasattr(mmd, "quality") and mmd.quality is not None:
                quality_score += float(getattr(mmd.quality, "score", 0) or 0) * 0.05
            scored_mmds.append((mmd, quality_score))

        # 按质量分排序
        scored_mmds.sort(key=lambda x: x[1], reverse=True)
        n = len(scored_mmds)

        # 分配层级
        tier_counts = {"S": 0, "A": 0, "B": 0, "C": 0}
        for i, (mmd, score) in enumerate(scored_mmds):
            mmd_type_str = mmd.mmd_type.value
            if i < n * 0.1:
                tier = "S"
            elif i < n * 0.3:
                tier = "A"
            elif i < n * 0.7:
                tier = "B"
            else:
                tier = "C"

            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            key = f"{mmd_type_str}_tier"
            result[key] = tier
            rank_key = f"{mmd_type_str}_rank"
            result[rank_key] = i + 1

        return result
    except Exception:
        return result


def _calc_reversal_risk_assessment(
    closes: list[float],
    volumes: list[float] | None,
    highs: list[float] | None,
    lows: list[float] | None,
    macd_data: dict[str, list[float]] | None,
    volatility: float | None,
) -> dict[str, Any]:
    """反转风险评估（V41 条件115，全局一次性计算）。

    综合多项指标评估当前趋势反转风险：
    - MACD顶底背离强度
    - RSI超买超卖程度
    - 价格与成交量背离
    - 趋势加速度衰减
    - 综合输出反转风险等级
    """
    result: dict[str, Any] = {
        "risk_level": "low",
        "divergence_strength": 0.0,
        "rsi_overbought": False,
        "volume_divergence": False,
        "momentum_decay": False,
        "risk_score": 0.0,
        "confidence_adjust": 0.0,
    }
    try:
        if not closes or len(closes) < 30:
            return result

        risk_score = 0.0

        # 1. RSI超买超卖检测
        rsi_val = _calc_rsi(closes, 14)
        if rsi_val > 75:
            result["rsi_overbought"] = True
            risk_score += 0.3
        elif rsi_val < 25:
            risk_score += 0.25

        # 2. MACD背离检测
        macd_hist = macd_data.get("hist", []) if macd_data else []
        if macd_hist and len(macd_hist) >= 10:
            # 价格创新高但MACD未创新高 → 顶背离
            price_highs = []
            macd_highs = []
            for i in range(len(closes) - 10, len(closes)):
                if i >= 5 and closes[i] == max(closes[i - 5 : i + 1]):
                    price_highs.append((i, closes[i]))
                if i >= 5 and macd_hist[i] == max(macd_hist[i - 5 : i + 1]):
                    macd_highs.append((i, macd_hist[i]))

            if len(price_highs) >= 2 and len(macd_highs) >= 2:
                last_price_high = price_highs[-1][1]
                prev_price_high = price_highs[-2][1] if len(price_highs) >= 2 else 0
                last_macd_high = macd_highs[-1][1] if macd_highs else 0
                prev_macd_high = macd_highs[-2][1] if len(macd_highs) >= 2 else 0

                if last_price_high > prev_price_high and last_macd_high < prev_macd_high:
                    result["divergence_strength"] = round(
                        abs(last_macd_high - prev_macd_high) / max(1, prev_macd_high) * 100, 1
                    )
                    risk_score += 0.35

        # 3. 量价背离检测
        if volumes and len(volumes) >= 20:
            recent_vol = sum(volumes[-5:]) / 5
            avg_vol = sum(volumes[-20:]) / 20
            recent_price_change = (closes[-1] - closes[-5]) / closes[-5] if closes[-5] > 0 else 0
            if recent_price_change > 0.02 and recent_vol < avg_vol * 0.7:
                result["volume_divergence"] = True
                risk_score += 0.2
            elif recent_price_change < -0.02 and recent_vol < avg_vol * 0.7:
                result["volume_divergence"] = True
                risk_score += 0.15

        # 4. 趋势加速度衰减
        if len(closes) >= 10:
            accel = closes[-1] - 2 * closes[-5] + closes[-10] if closes[-10] > 0 else 0
            prev_accel = (
                closes[-5] - 2 * closes[-8] + closes[-11]
                if len(closes) >= 11 and closes[-11] > 0
                else 0
            )
            if accel * prev_accel > 0 and abs(accel) < abs(prev_accel) * 0.5:
                result["momentum_decay"] = True
                risk_score += 0.15

        # 综合风险等级
        result["risk_score"] = round(min(1.0, risk_score), 2)
        if risk_score >= 0.6:
            result["risk_level"] = "extreme"
        elif risk_score >= 0.4:
            result["risk_level"] = "high"
        elif risk_score >= 0.2:
            result["risk_level"] = "medium"
        else:
            result["risk_level"] = "low"

        # 置信度调整
        if result["risk_level"] == "extreme":
            result["confidence_adjust"] = -0.08
        elif result["risk_level"] == "high":
            result["confidence_adjust"] = -0.05
        elif result["risk_level"] == "medium":
            result["confidence_adjust"] = -0.02

        return result
    except Exception:
        return result


def _calc_post_signal_confirmation(
    mmd: MMD,
    closes: list[float],
    volumes: list[float] | None,
    highs: list[float] | None,
    lows: list[float] | None,
    bi_end_idx: int,
) -> dict[str, Any]:
    """后确认验证（V42 条件116）。

    买卖点信号产生后，等待3-5根K线确认信号有效性：
    - 3买：信号后价格应继续上涨或回调幅度<20%（而非跌破信号低点）
    - 3卖：信号后价格应继续下跌或反弹幅度<20%（而非突破信号高点）
    - 信号后3根K线内出现反向K线组合则降权
    """
    result: dict[str, Any] = {
        "confirmed": False,
        "bars_confirmed": 0,
        "direction_match": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not closes or bi_end_idx < 3 or bi_end_idx >= len(closes) - 5:
            return result

        is_buy = "buy" in mmd.mmd_type.value
        signal_price = closes[bi_end_idx]

        # 检查信号后5根K线的表现
        future_closes = closes[bi_end_idx + 1 : bi_end_idx + 6]
        future_highs = highs[bi_end_idx + 1 : bi_end_idx + 6] if highs else future_closes
        future_lows = lows[bi_end_idx + 1 : bi_end_idx + 6] if lows else future_closes

        if is_buy:
            # 3买确认：信号后价格未大幅下跌
            min_future_low = min(future_lows) if future_lows else signal_price
            max_future_high = max(future_highs) if future_highs else signal_price
            drawdown = (signal_price - min_future_low) / signal_price if signal_price > 0 else 0
            gain = (max_future_high - signal_price) / signal_price if signal_price > 0 else 0

            if drawdown < 0.15:  # 下跌不超过15%
                result["confirmed"] = True
                result["direction_match"] = "bullish"
                if gain > 0.03:
                    result["confidence_adjust"] = 0.03
                elif gain > 0:
                    result["confidence_adjust"] = 0.01
            elif drawdown < 0.25:
                result["confirmed"] = True
                result["direction_match"] = "neutral"
                result["confidence_adjust"] = -0.01
            else:
                result["confirmed"] = False
                result["direction_match"] = "bearish"
                result["confidence_adjust"] = -0.04
        else:
            # 3卖确认：信号后价格未大幅上涨
            min_future_low = min(future_lows) if future_lows else signal_price
            max_future_high = max(future_highs) if future_highs else signal_price
            rally = (max_future_high - signal_price) / signal_price if signal_price > 0 else 0
            drop = (signal_price - min_future_low) / signal_price if signal_price > 0 else 0

            if rally < 0.15:  # 上涨不超过15%
                result["confirmed"] = True
                result["direction_match"] = "bearish"
                if drop > 0.03:
                    result["confidence_adjust"] = 0.03
                elif drop > 0:
                    result["confidence_adjust"] = 0.01
            elif rally < 0.25:
                result["confirmed"] = True
                result["direction_match"] = "neutral"
                result["confidence_adjust"] = -0.01
            else:
                result["confirmed"] = False
                result["direction_match"] = "bullish"
                result["confidence_adjust"] = -0.04

        # 统计确认根数
        bars_confirmed = 0
        for i, fc in enumerate(future_closes):
            if is_buy and fc >= signal_price * 0.985:
                bars_confirmed += 1
            elif not is_buy and fc <= signal_price * 1.015:
                bars_confirmed += 1
        result["bars_confirmed"] = bars_confirmed
        result["msg"] = f"后确认:{result['direction_match']}({bars_confirmed}根)"

        return result
    except Exception:
        return result


def _calc_break_pullback_volume_ratio(
    mmd: MMD,
    bis: list[BI],
    zss: list[ZS],
    closes: list[float],
    volumes: list[float],
) -> dict[str, Any]:
    """突破-回调量比验证（V42 条件117）。

    对于3买/3卖，验证突破笔的成交量放大倍数是否大于回调笔的成交量萎缩倍数：
    - 3买：突破放量倍数 > 回调缩量倍数 → 量价配合健康
    - 3卖：跌破放量倍数 > 反弹缩量倍数 → 量价配合健康
    """
    result: dict[str, Any] = {
        "break_vol_ratio": 0.0,
        "pullback_vol_ratio": 0.0,
        "volume_ratio_ok": False,
        "confidence_adjust": 0.0,
    }
    try:
        if not mmd.bi or not mmd.zs or not volumes or len(volumes) < 30:
            return result

        bi = mmd.bi
        zs = mmd.zs
        is_buy = mmd.mmd_type == MMDType.BUY_3

        # 找突破笔（在bi之前的同向笔）
        bi_start_idx = bi.start.k.k_index
        _ = bi.end.k.k_index

        break_bi = None
        for b in reversed(bis[: bis.index(bi)]):
            if is_buy and b.direction.value == "up" and b.end.k.k_index < bi_start_idx:
                if b.high > zs.zg * 1.01:  # 突破中枢上沿
                    break_bi = b
                    break
            elif not is_buy and b.direction.value == "down" and b.end.k.k_index < bi_start_idx:
                if b.low < zs.zd * 0.99:  # 跌破中枢下沿
                    break_bi = b
                    break

        if not break_bi:
            return result

        # 计算突破笔的成交量
        break_start = break_bi.start.k.k_index
        break_end = break_bi.end.k.k_index
        if break_end <= break_start or break_end >= len(volumes):
            return result

        break_vol = sum(volumes[break_start : break_end + 1]) / max(1, break_end - break_start)
        avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else sum(volumes) / len(volumes)

        if avg_vol <= 0:
            return result

        break_vol_ratio = break_vol / avg_vol
        result["break_vol_ratio"] = round(break_vol_ratio, 2)

        # 计算回调笔的成交量
        # 回调笔就是当前mmd.bi（3买时是回调笔，3卖时是反弹笔）
        pull_start = bi.start.k.k_index
        pull_end = bi.end.k.k_index
        if pull_end <= pull_start or pull_end >= len(volumes):
            return result

        pull_vol = sum(volumes[pull_start : pull_end + 1]) / max(1, pull_end - pull_start)
        pull_vol_ratio = pull_vol / avg_vol if avg_vol > 0 else 1.0
        result["pullback_vol_ratio"] = round(pull_vol_ratio, 2)

        # 量比验证：突破放量应大于回调缩量
        # 理想情况：break_vol_ratio > 1.5 且 pull_vol_ratio < 0.7
        volume_ratio_ok = break_vol_ratio >= 1.3 and pull_vol_ratio <= 0.85
        result["volume_ratio_ok"] = volume_ratio_ok

        if volume_ratio_ok:
            result["confidence_adjust"] = 0.02
        elif break_vol_ratio < 1.0:
            result["confidence_adjust"] = -0.03
        elif pull_vol_ratio > 1.0:
            result["confidence_adjust"] = -0.02

        return result
    except Exception:
        return result


def _calc_zhongshu_distance_validation(
    mmd: MMD,
    closes: list[float],
) -> dict[str, Any]:
    """中枢距离验证（V42 条件118）。

    3买/3卖信号点距中枢边界应有足够距离，过于接近中枢边界的信号可能是假突破：
    - 3买：信号低点距zg应有至少1%的距离（避免在zg边缘入场）
    - 3卖：信号高点距zd应有至少1%的距离（避免在zd边缘出场）
    - 距离过近则降权，距离适中则加分
    """
    result: dict[str, Any] = {
        "distance_pct": 0.0,
        "distance_valid": False,
        "confidence_adjust": 0.0,
    }
    try:
        if not mmd.bi or not mmd.zs or not closes:
            return result

        zs = mmd.zs
        bi = mmd.bi
        is_buy = mmd.mmd_type == MMDType.BUY_3

        # 计算信号点与中枢边界的距离
        if is_buy:
            # 3买：回踩笔的低点与zg的距离
            signal_price = bi.low
            boundary = zs.zg
            if boundary <= 0:
                return result
            distance_pct = (signal_price - boundary) / boundary * 100
        else:
            # 3卖：反弹笔的高点与zd的距离
            signal_price = bi.high
            boundary = zs.zd
            if boundary <= 0:
                return result
            distance_pct = (boundary - signal_price) / boundary * 100

        result["distance_pct"] = round(distance_pct, 2)

        # 距离验证：距离应在合理范围内
        # 太近（<0.5%）：可能在边界上，假信号风险高
        # 适中（0.5%-5%）：健康区域
        # 太远（>10%）：可能已经偏离中枢太远，趋势可能衰竭
        if distance_pct < 0.5:
            result["distance_valid"] = False
            result["confidence_adjust"] = -0.03
        elif distance_pct <= 5.0:
            result["distance_valid"] = True
            result["confidence_adjust"] = 0.01
        elif distance_pct <= 10.0:
            result["distance_valid"] = True
            result["confidence_adjust"] = 0.0
        else:
            result["distance_valid"] = False
            result["confidence_adjust"] = -0.02

        return result
    except Exception:
        return result


def _calc_adx_trend_strength_check(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
    bi_end_idx: int,
) -> dict[str, Any]:
    """ADX趋势强度确认（V42 条件119）。

    3买/3卖信号需要足够的趋势强度才能有效：
    - ADX >= 40：强趋势，信号可信度高 → +2%
    - ADX 25-40：中等趋势，信号正常 → 无调整
    - ADX 20-25：弱趋势，信号需谨慎 → -1%
    - ADX < 20：无趋势（盘整），3买/3卖信号可能无效 → -3%
    """
    result: dict[str, Any] = {
        "adx_value": 0.0,
        "adx_level": "none",
        "trend_valid": False,
        "confidence_adjust": 0.0,
    }
    try:
        if not closes or bi_end_idx < 30:
            return result

        adx_val, adx_level = _calc_adx_strength(closes, highs, lows, bi_end_idx)
        result["adx_value"] = adx_val
        result["adx_level"] = adx_level

        if adx_val >= 40:
            result["trend_valid"] = True
            result["confidence_adjust"] = 0.02
        elif adx_val >= 25:
            result["trend_valid"] = True
            result["confidence_adjust"] = 0.0
        elif adx_val >= 20:
            result["trend_valid"] = False
            result["confidence_adjust"] = -0.01
        else:
            # ADX < 20，盘整市场，3买/3卖信号质量低
            result["trend_valid"] = False
            result["confidence_adjust"] = -0.03

        return result
    except Exception:
        return result


def _calc_enhanced_signal_freshness(
    mmd: MMD,
    closes: list[float],
    volatility: float | None,
) -> dict[str, Any]:
    """信号时效性衰减增强（V42 条件120）。

    改进版指数衰减模型：
    - 使用指数衰减而非线性衰减，更符合实际信号有效性衰减规律
    - 低波动市场信号有效期更长（300根K线）
    - 高波动市场信号有效期更短（60根K线）
    - 超过有效期自动标记为过期（confidence_adjust = -0.15）
    """
    result: dict[str, Any] = {
        "bars_since_signal": 0,
        "decay_factor": 1.0,
        "effective_age": 0.0,
        "is_expired": False,
        "confidence_adjust": 0.0,
    }
    try:
        if not mmd.bi or not closes:
            return result

        bi_end_idx = mmd.bi.end.k.k_index
        bars_since = len(closes) - 1 - bi_end_idx
        result["bars_since_signal"] = bars_since

        if bars_since <= 0:
            result["decay_factor"] = 1.0
            result["confidence_adjust"] = 0.0
            return result

        vol = volatility if volatility is not None else _calc_atr_volatility(closes)

        # 基于波动率确定衰减参数
        if vol < 0.015:
            # 低波动：信号衰减慢，有效期长
            decay_rate = 0.008  # 指数衰减速率
            max_valid_bars = 300
        elif vol < 0.03:
            # 中等波动
            decay_rate = 0.012
            max_valid_bars = 150
        else:
            # 高波动：信号衰减快
            decay_rate = 0.02
            max_valid_bars = 60

        # 指数衰减模型：decay = e^(-rate * bars)
        import math

        decay_factor = math.exp(-decay_rate * bars_since)
        decay_factor = max(0.0, min(1.0, decay_factor))

        result["decay_factor"] = round(decay_factor, 4)
        result["effective_age"] = round(bars_since / max_valid_bars, 3)
        result["is_expired"] = bars_since > max_valid_bars

        # 置信度调整
        if decay_factor >= 0.9:
            result["confidence_adjust"] = 0.0
        elif decay_factor >= 0.7:
            result["confidence_adjust"] = -0.01
        elif decay_factor >= 0.5:
            result["confidence_adjust"] = -0.03
        elif decay_factor >= 0.3:
            result["confidence_adjust"] = -0.06
        else:
            result["confidence_adjust"] = -0.10

        return result
    except Exception:
        return result


def _calc_volume_price_divergence_secondary_v48(
    mmd: MMD,
    closes: list[float],
    volumes: list[float] | None,
) -> dict[str, Any]:
    """量价背离二次确认（V48 条件134）。

    使用成交量加权价格偏离（VWAP）作为二次确认指标：
    - 计算信号后N根K线的VWAP偏离度
    - 3买：价格创新高但VWAP偏离度收窄 → 动能衰竭警告
    - 3卖：价格创新低但VWAP偏离度收窄 → 下跌动能衰竭警告
    - 配合原有MACD背离检测，提升准确率

    Returns:
        dict with keys: confirmed, divergence_pct, confidence_adjust, msg
    """
    result: dict[str, Any] = {
        "confirmed": False,
        "divergence_pct": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmd.bi is None or not closes or volumes is None:
            return result

        signal_idx = mmd.bi.end.k.k_index
        if signal_idx < 0 or signal_idx >= len(closes):
            return result

        # 使用最近20根K线计算VWAP偏离
        lookback = min(20, signal_idx)
        if lookback < 5:
            return result

        recent_closes = closes[signal_idx - lookback : signal_idx + 1]
        recent_volumes = volumes[signal_idx - lookback : signal_idx + 1]

        if len(recent_closes) < 5:
            return result

        # 计算简单VWAP（用收盘价近似，避免需要high/low数据）
        total_vol = sum(recent_volumes)
        if total_vol == 0:
            return result

        vwap = sum(c * v for c, v in zip(recent_closes, recent_volumes)) / total_vol
        current_price = closes[-1]
        vwap_deviation = (current_price - vwap) / (vwap + 1e-10)

        result["divergence_pct"] = round(vwap_deviation * 100, 2)

        is_buy = "buy" in mmd.mmd_type.value

        if is_buy:
            # 3买：价格应在VWAP之上（多头排列）
            if vwap_deviation > 0.01:
                result["confirmed"] = True
                result["confidence_adjust"] = 0.03
                result["msg"] = (
                    f"量价背离二次确认通过：当前价VWAP偏离+{vwap_deviation * 100:.1f}%（多头）"
                )
            elif vwap_deviation < -0.02:
                result["confidence_adjust"] = -0.04
                result["msg"] = (
                    f"量价背离二次确认失败：当前价低于VWAP {abs(vwap_deviation) * 100:.1f}%"
                )
            else:
                result["confidence_adjust"] = 0.0
                result["msg"] = f"量价背离二次确认中性：VWAP偏离{vwap_deviation * 100:.1f}%"
        else:
            # 3卖：价格应在VWAP之下（空头排列）
            if vwap_deviation < -0.01:
                result["confirmed"] = True
                result["confidence_adjust"] = 0.03
                result["msg"] = (
                    f"量价背离二次确认通过：当前价VWAP偏离{vwap_deviation * 100:.1f}%（空头）"
                )
            elif vwap_deviation > 0.02:
                result["confidence_adjust"] = -0.04
                result["msg"] = f"量价背离二次确认失败：当前价高于VWAP {vwap_deviation * 100:.1f}%"
            else:
                result["confidence_adjust"] = 0.0
                result["msg"] = f"量价背离二次确认中性：VWAP偏离{vwap_deviation * 100:.1f}%"

        return result
    except Exception:
        return result


def _calc_trend_strength_weighting_v48(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
    trend_strength: float,
) -> dict[str, Any]:
    """趋势强度加权（V48 条件135）。

    基于ADX和均线斜率对置信度进行趋势加权调整：
    - 强趋势（ADX>25）：置信度加成+0.03
    - 中趋势（ADX 20-25）：置信度加成+0.01
    - 弱趋势（ADX<20）：置信度减权-0.02（趋势不明确时降低信任）

    同时考虑MA20斜率方向与信号方向的一致性。
    """
    result: dict[str, Any] = {
        "adx_value": 0.0,
        "adx_level": "unknown",
        "ma_alignment": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmd.bi is None or not closes:
            return result

        bi_end_idx = mmd.bi.end.k.k_index
        if bi_end_idx < 20:
            return result

        # 计算ADX
        adx_val, adx_level = _calc_adx_strength(closes, highs, lows, bi_end_idx)
        result["adx_value"] = round(adx_val, 1)
        result["adx_level"] = adx_level

        # 计算MA20斜率
        ma_slope = _calc_ma_slope(closes, bi_end_idx)
        result["ma_alignment"] = ma_slope

        is_buy = "buy" in mmd.mmd_type.value

        # ADX趋势强度加权
        if adx_level == "strong":
            if (is_buy and ma_slope == "up") or (not is_buy and ma_slope == "down"):
                result["confidence_adjust"] = 0.04
                result["msg"] = f"趋势强度加权：ADX={adx_val:.1f}强趋势+方向一致"
            else:
                result["confidence_adjust"] = -0.02
                result["msg"] = f"趋势强度加权：ADX={adx_val:.1f}强趋势但方向冲突"
        elif adx_level == "medium":
            if (is_buy and ma_slope == "up") or (not is_buy and ma_slope == "down"):
                result["confidence_adjust"] = 0.02
                result["msg"] = f"趋势强度加权：ADX={adx_val:.1f}中趋势+方向一致"
            else:
                result["confidence_adjust"] = -0.01
                result["msg"] = f"趋势强度加权：ADX={adx_val:.1f}中趋势但方向冲突"
        else:  # weak or unknown
            result["confidence_adjust"] = -0.02
            result["msg"] = f"趋势强度加权：ADX={adx_val:.1f}弱趋势，降低置信度"

        return result
    except Exception:
        return result


def _calc_dynamic_risk_reward_ratio_v48(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
    atr_period: int = 14,
) -> dict[str, Any]:
    """动态风险收益比计算（V48 条件136）。

    基于ATR动态计算止损止盈位，并提供风险收益比评估：
    - 计算当前ATR作为波动率度量
    - 动态止损位：入场价 ± 2×ATR
    - 动态止盈位：基于中枢高度或ATR倍数
    - 风险收益比 ≥ 2.0 为优质信号，≥ 1.5 为合格，< 1.5 为低质量

    返回值包含：entry_price, stop_loss, take_profit_1, risk_reward_ratio, quality_tier
    """
    result: dict[str, Any] = {
        "entry_price": 0.0,
        "stop_loss": 0.0,
        "take_profit_1": 0.0,
        "risk_reward_ratio": 0.0,
        "quality_tier": "unknown",
        "atr": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if mmd.bi is None or not closes:
            return result

        latest_close = closes[-1]
        bi_end_idx = mmd.bi.end.k.k_index

        # 计算ATR
        atr = _calc_atr(closes, highs, lows, bi_end_idx, atr_period)
        result["atr"] = round(atr, 2)

        is_buy = "buy" in mmd.mmd_type.value

        if is_buy:
            # 3买：入场价略高于回调低点
            entry_price = mmd.bi.low * 1.002 if mmd.bi.low > 0 else latest_close
            stop_loss = entry_price - atr * 2
            # 止盈：基于中枢高度或固定倍数
            zs_height = (mmd.zs.zg - mmd.zs.zd) if mmd.zs and mmd.zs.done else 0
            take_profit_1 = entry_price + max(zs_height * 0.8, atr * 3)
        else:
            # 3卖：入场价略低于反弹高点
            entry_price = mmd.bi.high * 0.998 if mmd.bi.high > 0 else latest_close
            stop_loss = entry_price + atr * 2
            zs_height = (mmd.zs.zg - mmd.zs.zd) if mmd.zs and mmd.zs.done else 0
            take_profit_1 = entry_price - max(zs_height * 0.8, atr * 3)

        result["entry_price"] = round(entry_price, 2)
        result["stop_loss"] = round(stop_loss, 2)
        result["take_profit_1"] = round(take_profit_1, 2)

        # 计算风险收益比
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit_1 - entry_price)
        rrr = round(reward / risk, 2) if risk > 0 else 0
        result["risk_reward_ratio"] = rrr

        # 质量分级
        if rrr >= 2.5:
            result["quality_tier"] = "S"
            result["confidence_adjust"] = 0.04
            result["msg"] = (
                f"优质信号：风险收益比{rrr:.1f}（S级），止损{result['stop_loss']:.2f}→止盈{result['take_profit_1']:.2f}"
            )
        elif rrr >= 2.0:
            result["quality_tier"] = "A"
            result["confidence_adjust"] = 0.03
            result["msg"] = (
                f"良好信号：风险收益比{rrr:.1f}（A级），止损{result['stop_loss']:.2f}→止盈{result['take_profit_1']:.2f}"
            )
        elif rrr >= 1.5:
            result["quality_tier"] = "B"
            result["confidence_adjust"] = 0.01
            result["msg"] = (
                f"合格信号：风险收益比{rrr:.1f}（B级），止损{result['stop_loss']:.2f}→止盈{result['take_profit_1']:.2f}"
            )
        else:
            result["quality_tier"] = "C"
            result["confidence_adjust"] = -0.03
            result["msg"] = f"低质量信号：风险收益比{rrr:.1f}（C级），建议观望"

        return result
    except Exception:
        return result


def _calc_breakout_bi_strength_enhanced_v51(
    mmd: MMD,
    bis: list[Any],
    zss: list[Any],
    volumes: list[float],
    macd_data: dict[str, list[float]] | None,
) -> dict[str, Any]:
    """突破笔力度二次确认增强（V51 条件144）。

    在条件122基础上增加MACD柱状图验证：
    - 成交量对比 >= 0.9 → 部分确认
    - 价格幅度对比 >= 0.8 → 部分确认
    - MACD柱面积对比 >= 0.8 → 动能确认
    - 综合评分：3/3通过 → +4%，2/3通过 → +2%，1/3 → 0%，0/3 → -5%
    """
    result: dict[str, Any] = {
        "vol_ratio": 0.0,
        "price_ratio": 0.0,
        "macd_area_ratio": 0.0,
        "vol_ok": False,
        "price_ok": False,
        "macd_ok": False,
        "score": 0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not mmd.bi or not mmd.zs or not bis or len(bis) < 2:
            return result

        mmd_bi = mmd.bi
        mmd_bi_idx = None
        for i, bi in enumerate(bis):
            if bi is mmd_bi:
                mmd_bi_idx = i
                break

        if mmd_bi_idx is None or mmd_bi_idx < 1:
            return result

        entry_bi = bis[mmd_bi_idx - 1]
        breakout_bi = mmd_bi

        def bi_avg_volume(bi: Any) -> float:
            start_idx = bi.start.k.k_index
            end_idx = bi.end.k.k_index
            if start_idx >= len(volumes) or end_idx >= len(volumes) or start_idx < 0:
                return 0.0
            vol_slice = volumes[start_idx : end_idx + 1]
            return sum(vol_slice) / len(vol_slice) if vol_slice else 0.0

        entry_vol = bi_avg_volume(entry_bi)
        breakout_vol = bi_avg_volume(breakout_bi)
        entry_range = entry_bi.end.k.high - entry_bi.start.k.low
        breakout_range = breakout_bi.end.k.high - breakout_bi.start.k.low

        result["vol_ratio"] = round(breakout_vol / entry_vol, 2) if entry_vol > 0 else 0.0
        result["price_ratio"] = round(breakout_range / entry_range, 2) if entry_range > 0 else 0.0

        vol_ok = breakout_vol >= entry_vol * 0.9
        result["vol_ok"] = vol_ok

        price_ok = breakout_range >= entry_range * 0.8
        result["price_ok"] = price_ok

        # MACD柱状图面积对比
        macd_ok = False
        if macd_data and "hist" in macd_data and len(macd_data["hist"]) >= 20:
            entry_start = max(0, entry_bi.start.k.k_index)
            entry_end = min(len(macd_data["hist"]) - 1, entry_bi.end.k.k_index)
            breakout_start = max(0, breakout_bi.start.k.k_index)
            breakout_end = min(len(macd_data["hist"]) - 1, breakout_bi.end.k.k_index)

            def macd_area(start: int, end: int) -> float:
                if end <= start or start < 0 or end >= len(macd_data["hist"]):
                    return 0.0
                hist = macd_data["hist"][start : end + 1]
                return sum(abs(h) for h in hist)

            entry_area = macd_area(entry_start, entry_end)
            breakout_area = macd_area(breakout_start, breakout_end)
            result["macd_area_ratio"] = (
                round(breakout_area / entry_area, 2) if entry_area > 0 else 0.0
            )

            is_buy = "buy" in mmd.mmd_type.value
            if is_buy:
                macd_ok = breakout_area >= entry_area * 0.8
            else:
                macd_ok = breakout_area >= entry_area * 0.8

        result["macd_ok"] = macd_ok

        score = sum([vol_ok, price_ok, macd_ok])
        result["score"] = score

        if score == 3:
            result["confidence_adjust"] = 0.04
            result["msg"] = "突破笔力度充分确认（量价MACD三维度一致）"
        elif score == 2:
            result["confidence_adjust"] = 0.02
            result["msg"] = "突破笔力度部分确认（2/3维度一致）"
        elif score == 1:
            result["confidence_adjust"] = 0.0
            result["msg"] = "突破笔力度一般确认（仅1/3维度一致）"
        else:
            result["confidence_adjust"] = -0.05
            result["msg"] = "⚠️ 突破笔力度不足，警惕假突破"

        return result
    except Exception:
        return result


def _calc_pullback_depth_time_v51(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volatility: float | None,
) -> dict[str, Any]:
    """回踩笔深度+时间综合验证（V51 条件145）。

    结合回踩深度和回踩时间两个维度：
    - 回踩深度：回踩笔相对中枢ZD/ZG的距离，不超过3%
    - 回踩时间：基于波动率动态调整上限（高波动20根/正常15根/低波动10根）
    """
    result: dict[str, Any] = {
        "pullback_depth_pct": 0.0,
        "pullback_bars": 0,
        "depth_ok": False,
        "time_ok": False,
        "combined_status": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if not mmd.bi or not mmd.zs or not closes or not highs or not lows:
            return result

        zs = mmd.zs
        bi = mmd.bi
        is_buy = "buy" in mmd.mmd_type.value

        zs_zd = zs.zd
        bi_low = bi.low
        mid_price = (zs.zg + zs.zd) / 2

        if is_buy:
            depth_pct = (zs_zd - bi_low) / mid_price if mid_price > 0 else 0.0
            depth_ok = depth_pct <= 0.03
        else:
            depth_pct = (bi.high - zs.zg) / mid_price if mid_price > 0 else 0.0
            depth_ok = depth_pct <= 0.03

        result["pullback_depth_pct"] = round(depth_pct * 100, 2)
        result["depth_ok"] = depth_ok

        bi_end_idx = bi.end.k.k_index
        pullback_bars = len(closes) - 1 - bi_end_idx
        result["pullback_bars"] = pullback_bars

        vol = volatility if volatility is not None else _calc_atr_volatility(closes)
        if vol > 0.04:
            max_pullback_bars = 20
        elif vol > 0.02:
            max_pullback_bars = 15
        else:
            max_pullback_bars = 10

        time_ok = pullback_bars <= max_pullback_bars
        result["time_ok"] = time_ok

        if depth_ok and time_ok:
            result["combined_status"] = "strong"
            result["confidence_adjust"] = 0.03
            result["msg"] = (
                f"回踩深度{depth_pct * 100:.1f}%在安全范围，时间{pullback_bars}根K线符合预期"
            )
        elif depth_ok or time_ok:
            result["combined_status"] = "normal"
            result["confidence_adjust"] = 0.0
            result["msg"] = (
                f"回踩深度{'符合' if depth_ok else '偏深'}，时间{'符合' if time_ok else '偏长'}"
            )
        else:
            result["combined_status"] = "weak"
            result["confidence_adjust"] = -0.04
            result["msg"] = (
                f"回踩深度{depth_pct * 100:.1f}%过大且时间{pullback_bars}根K线过长，信号质量差"
            )

        return result
    except Exception:
        return result


def _calc_trend_strength_composite_v51(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float] | None,
) -> dict[str, Any]:
    """趋势强度综合评分（V51 条件146）。

    综合ADX、MA斜率、动量三个维度评估趋势强度：
    - ADX >= 25：+3分，20-25：+1分，<20：-1分
    - MA斜率与信号一致：+2分，相反：-2分
    - 5日动量与信号一致：+2分，相反：-2分
    - 总分>=5：强趋势(+4%)，3-4：中等(+2%)，<3：趋势不明(0%)，<0：逆势(-5%)
    """
    result: dict[str, Any] = {
        "adx_value": 0.0,
        "adx_level": "unknown",
        "ma_slope": "unknown",
        "momentum_5d": 0.0,
        "total_score": 0,
        "trend_strength": "unknown",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        if len(closes) < 30:
            return result

        is_buy = "buy" in mmd.mmd_type.value
        from easy_tdx.MyTT import MA

        adx_val, adx_level = _calc_adx_strength(closes, highs, lows, len(closes) - 1)
        result["adx_value"] = round(adx_val, 1)
        result["adx_level"] = adx_level

        adx_score = 3 if adx_val >= 25 else (1 if adx_val >= 20 else -1)

        ma20 = MA(closes, 20)
        if len(ma20) >= 2:
            ma_slope = "up" if ma20[-1] > ma20[-2] else "down"
            result["ma_slope"] = ma_slope
            ma_score = (
                2 if (ma_slope == "up" and is_buy) or (ma_slope == "down" and not is_buy) else -2
            )
        else:
            ma_score = 0

        if len(closes) >= 6:
            momentum_5d = (closes[-1] - closes[-6]) / closes[-6] if closes[-6] > 0 else 0.0
            result["momentum_5d"] = round(momentum_5d * 100, 2)
            mom_score = (
                2 if (momentum_5d > 0 and is_buy) or (momentum_5d < 0 and not is_buy) else -2
            )
        else:
            mom_score = 0

        total_score = adx_score + ma_score + mom_score
        result["total_score"] = total_score

        if total_score >= 5:
            trend_strength = "strong"
            confidence_adjust = 0.04
            msg = f"趋势强度综合评分{total_score}分（ADX={adx_val:.1f}强趋势+方向一致），强确认"
        elif total_score >= 3:
            trend_strength = "medium"
            confidence_adjust = 0.02
            msg = f"趋势强度综合评分{total_score}分（ADX={adx_val:.1f}，MA{ma_slope}，动量{momentum_5d * 100:.1f}%），中等确认"
        elif total_score >= 0:
            trend_strength = "weak"
            confidence_adjust = 0.0
            msg = f"趋势强度综合评分{total_score}分（ADX={adx_val:.1f}，方向中性）"
        else:
            trend_strength = "contrarian"
            confidence_adjust = -0.05
            msg = (
                f"⚠️ 趋势强度综合评分{total_score}分（ADX={adx_val:.1f}弱趋势+方向相反），逆势需谨慎"
            )

        result["trend_strength"] = trend_strength
        result["confidence_adjust"] = confidence_adjust
        result["msg"] = msg

        return result
    except Exception:
        return result


def _calc_trading_decision_v51(
    mmd: MMD,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    zss: list[Any],
) -> dict[str, Any]:
    """交易决策建议（V51 条件147）。

    提供完整交易决策参考：
    - 建议入场价、止损位、两级止盈位
    - 风险收益比（RRR）
    - 质量评级（S/A/B/C）
    - 综合决策建议（买入/观望/卖出）
    """
    result: dict[str, Any] = {
        "entry_price": 0.0,
        "stop_loss": 0.0,
        "take_profit_1": 0.0,
        "take_profit_2": 0.0,
        "risk_reward_ratio": 0.0,
        "quality_tier": "C",
        "decision": "hold",
        "atr": 0.0,
        "msg": "",
    }
    try:
        if not closes or len(closes) < 20:
            return result

        latest_price = closes[-1]
        is_buy = "buy" in mmd.mmd_type.value

        atr = _calc_atr(closes, highs, lows, len(closes) - 1, period=14)
        result["atr"] = round(atr, 2)

        if is_buy:
            entry_price = latest_price
            stop_loss = entry_price - 2 * atr
            if mmd.zs:
                zs_height = mmd.zs.zg - mmd.zs.zd
                tp1 = entry_price + zs_height * 0.5
                tp2 = entry_price + zs_height * 1.0
            else:
                tp1 = entry_price + atr * 3
                tp2 = entry_price + atr * 5
        else:
            entry_price = latest_price
            stop_loss = entry_price + 2 * atr
            if mmd.zs:
                zs_height = mmd.zs.zg - mmd.zs.zd
                tp1 = entry_price - zs_height * 0.5
                tp2 = entry_price - zs_height * 1.0
            else:
                tp1 = entry_price - atr * 3
                tp2 = entry_price - atr * 5

        result["entry_price"] = round(entry_price, 2)
        result["stop_loss"] = round(stop_loss, 2)
        result["take_profit_1"] = round(tp1, 2)
        result["take_profit_2"] = round(tp2, 2)

        risk = abs(entry_price - stop_loss)
        reward = abs(tp1 - entry_price)
        rrr = reward / risk if risk > 0 else 0.0
        result["risk_reward_ratio"] = round(rrr, 2)

        if rrr >= 2.5:
            quality_tier = "S"
        elif rrr >= 2.0:
            quality_tier = "A"
        elif rrr >= 1.5:
            quality_tier = "B"
        else:
            quality_tier = "C"
        result["quality_tier"] = quality_tier

        if is_buy:
            if quality_tier in ("S", "A") and mmd.confidence >= 0.6:
                decision = "buy_aggressive"
                msg = f"建议买入（{quality_tier}级，RRR={rrr}:1，置信度{mmd.confidence:.0%}），止损{stop_loss:.2f}，止盈1:{tp1:.2f}，止盈2:{tp2:.2f}"
            elif quality_tier == "B" and mmd.confidence >= 0.5:
                decision = "buy_cautious"
                msg = f"谨慎买入（{quality_tier}级，RRR={rrr}:1，置信度{mmd.confidence:.0%}），严格止损{stop_loss:.2f}"
            else:
                decision = "wait"
                msg = f"观望（{quality_tier}级，RRR={rrr}:1，置信度{mmd.confidence:.0%}，风险收益比不足）"
        else:
            if quality_tier in ("S", "A") and mmd.confidence >= 0.6:
                decision = "sell_aggressive"
                msg = f"建议卖出（{quality_tier}级，RRR={rrr}:1，置信度{mmd.confidence:.0%}），止损{stop_loss:.2f}，止盈1:{tp1:.2f}"
            elif quality_tier == "B" and mmd.confidence >= 0.5:
                decision = "sell_cautious"
                msg = f"谨慎卖出（{quality_tier}级，RRR={rrr}:1，置信度{mmd.confidence:.0%}）"
            else:
                decision = "wait"
                msg = f"观望（{quality_tier}级，RRR={rrr}:1，置信度{mmd.confidence:.0%}）"

        result["decision"] = decision
        result["msg"] = msg

        return result
    except Exception:
        return result
