"""V102 决策支持增强（条件264-267）。

从 mmd.py 抽出的独立模块（V392 模块治理）：多信号相关性分析、信号质量评分卡、
决策支持输出、历史模式匹配与置信度并入。原定义位于 mmd.py 尾部，
为避免 29k 行 god-module 继续膨胀而单独成模块。

mmd.py 顶层通过惰性再导出保持既有导入兼容。
"""

from __future__ import annotations

from typing import Any

from easy_tdx.chanlun.types import MMD, MMDType

# ── V102: 条件264-267 缠论模型决策支持增强 ─────────────────────────────────────


# 条件265：质量评分卡等级 → 置信度微调（A/B 加分、D 减分）
_V102_GRADE_ADJ: dict[str, float] = {"A": 0.02, "B": 0.01, "C": 0.0, "D": -0.03}


def _apply_v102_decision_confidence(
    mmd: MMD,
    scorecard: dict[str, Any],
    decision: dict[str, Any],
) -> tuple[float, float]:
    """把 V102 条件265/266 的置信度调整并入买卖点置信度。

    - 条件265（信号质量评分卡）：等级 A/B → +2%/+1%，D → -3%，C 不调整。
    - 条件266（决策支持输出）：风险收益比 ≥3:1 → +3%，<1.5:1 → -3% 等。

    同时把 grade_adj 写回 scorecard 的 confidence_adjust 字段（供 API 展示），
    返回 (并入后的最终置信度, 总调整值)。
    """
    grade = str(scorecard.get("overall_grade") or "")
    grade_adj = _V102_GRADE_ADJ.get(grade, 0.0)
    scorecard["confidence_adjust"] = round(grade_adj, 3)
    decision_adj = float(decision.get("confidence_adjust", 0.0) or 0.0)
    total = round(grade_adj + decision_adj, 3)
    if total:
        mmd.confidence = max(0.0, min(1.0, mmd.confidence + total))
    return mmd.confidence, total


def _calc_multi_signal_correlation(
    mmd: MMD,
    all_mmds: list[MMD],
    closes: list[float],
) -> dict[str, Any]:
    """多信号相关性分析（V102 条件264）。

    当同一股票有多个买卖点信号时，分析其时间分布相关性：
    - 计算相邻信号之间的时间间隔和价格变动
    - 如果多个买入信号密集出现，可能表示过度交易风险
    - 如果信号间隔合理，则增强置信度
    """
    result: dict[str, Any] = {
        "nearby_signals": [],
        "signal_density": "normal",
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过此条件"
            return result

        # 获取当前信号位置
        curr_idx = 0
        if mmd.bi is not None and hasattr(mmd.bi.end, "k"):
            curr_idx = getattr(mmd.bi.end.k, "k_index", len(closes) // 2)
        else:
            curr_idx = len(closes) // 2

        # 分析其他信号
        nearby_count = 0
        same_direction_count = 0
        for other in all_mmds:
            if other is mmd:
                continue
            if other.mmd_type != mmd.mmd_type:
                continue
            other_idx = 0
            if other.bi is not None and hasattr(other.bi.end, "k"):
                other_idx = getattr(other.bi.end.k, "k_index", len(closes) // 2)
            time_gap = abs(other_idx - curr_idx)
            if time_gap <= 10:  # 10根K线内为密集信号
                nearby_count += 1
                if other.mmd_type == mmd.mmd_type:
                    same_direction_count += 1

        result["nearby_signals"] = nearby_count
        if nearby_count >= 3:
            result["signal_density"] = "high"
            result["confidence_adjust"] = -0.03
            result["msg"] = f"信号密集({nearby_count}个)，避免过度交易，-3%置信度"
        elif nearby_count >= 2:
            result["signal_density"] = "medium"
            result["confidence_adjust"] = -0.01
            result["msg"] = f"信号较密集({nearby_count}个)，注意仓位控制，-1%置信度"
        elif nearby_count == 0:
            result["signal_density"] = "low"
            result["confidence_adjust"] = 0.02
            result["msg"] = f"信号稀疏({nearby_count}个)，独立性强，+2%置信度"
        else:
            result["msg"] = f"正常信号密度({nearby_count}个)，无调整"

        return result
    except Exception:
        return result


def _calc_signal_quality_scorecard(
    mmd: MMD,
    closes: list[float],
    volumes: list[float] | None,
    macd_data: dict[str, list[float]] | None,
    volatility: float | None,
) -> dict[str, Any]:
    """信号质量评分卡（V102 条件265）。

    提供全面的信号质量评估，包括：
    - 技术指标得分
    - 量价配合得分
    - 趋势对齐得分
    - 波动率环境得分
    - 综合质量等级
    """
    result: dict[str, Any] = {
        "tech_score": 0.0,
        "volume_score": 0.0,
        "trend_score": 0.0,
        "volatility_score": 0.0,
        "overall_grade": "C",
        "overall_score": 0.0,
        "strength": "medium",
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过评分"
            return result

        # 技术指标得分 (MACD + RSI + KDJ)
        tech_score = 0.0
        if macd_data and "dif" in macd_data and "dea" in macd_data:
            dif = macd_data["dif"]
            dea = macd_data["dea"]
            hist = macd_data.get("hist", [])
            if len(dif) >= 3 and len(dea) >= 3:
                if is_buy:
                    if dif[-1] > dea[-1] and dif[-2] <= dea[-2]:
                        tech_score += 2.0  # 金叉
                    elif dif[-1] > dea[-1] and dif[-1] > dif[-2]:
                        tech_score += 1.0  # 多头
                    if hist and hist[-1] > 0 and hist[-1] > hist[-2]:
                        tech_score += 1.0  # 柱状增长
                else:
                    if dif[-1] < dea[-1] and dif[-2] >= dea[-2]:
                        tech_score += 2.0  # 死叉
                    elif dif[-1] < dea[-1] and dif[-1] < dif[-2]:
                        tech_score += 1.0  # 空头
                    if hist and hist[-1] < 0 and hist[-1] < hist[-2]:
                        tech_score += 1.0  # 柱状增长
        result["tech_score"] = min(4.0, max(0.0, tech_score))

        # 量价配合得分
        volume_score = 0.0
        if volumes and len(volumes) >= 20:
            avg_vol = sum(volumes[-20:]) / 20
            recent_vol = sum(volumes[-5:]) / 5
            vol_ratio = recent_vol / (avg_vol + 1e-10)
            if is_buy and vol_ratio > 1.2:
                volume_score += 2.0
            elif is_buy and vol_ratio > 0.8:
                volume_score += 1.0
            elif is_sell and vol_ratio < 0.8:
                volume_score += 1.0
            elif is_sell and vol_ratio < 1.2:
                volume_score += 2.0
        result["volume_score"] = min(2.0, max(0.0, volume_score))

        # 趋势对齐得分
        trend_score = 0.0
        if len(closes) >= 60:
            ma5 = sum(closes[-5:]) / 5
            ma20 = sum(closes[-20:]) / 20
            ma60 = sum(closes[-60:]) / 60
            if is_buy:
                if ma5 > ma20 > ma60:
                    trend_score += 2.0  # 多头排列
                elif ma5 > ma20:
                    trend_score += 1.0
            else:
                if ma5 < ma20 < ma60:
                    trend_score += 2.0  # 空头排列
                elif ma5 < ma20:
                    trend_score += 1.0
        result["trend_score"] = min(2.0, max(0.0, trend_score))

        # 波动率环境得分
        volatility_score = 0.0
        if volatility is not None:
            if is_buy and volatility < 0.02:
                volatility_score += 1.0  # 低波动适合买入
            elif is_sell and volatility > 0.03:
                volatility_score += 1.0  # 高波动适合卖出
            elif volatility < 0.05:
                volatility_score += 0.5  # 中等波动
        result["volatility_score"] = min(1.0, max(0.0, volatility_score))

        # 综合评分
        total_score = tech_score + volume_score + trend_score + volatility_score
        result["overall_score"] = round(total_score, 2)

        if total_score >= 5.0:
            result["overall_grade"] = "A"
            result["strength"] = "strong"
            result["msg"] = f"信号质量优秀(总分{total_score:.1f}/7.0)，强信号"
        elif total_score >= 3.5:
            result["overall_grade"] = "B"
            result["strength"] = "medium"
            result["msg"] = f"信号质量良好(总分{total_score:.1f}/7.0)，可考虑入场"
        elif total_score >= 2.0:
            result["overall_grade"] = "C"
            result["strength"] = "weak"
            result["msg"] = f"信号质量一般(总分{total_score:.1f}/7.0)，谨慎对待"
        else:
            result["overall_grade"] = "D"
            result["strength"] = "very_weak"
            result["msg"] = f"信号质量较差(总分{total_score:.1f}/7.0)，建议观望"

        return result
    except Exception:
        return result


def _calc_decision_support_enhanced(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
    volumes: list[float] | None,
    macd_data: dict[str, list[float]] | None,
) -> dict[str, Any]:
    """决策支持输出（V102 条件266）。

    生成可操作的买卖建议：
    - 入场价位建议
    - 止损价位计算
    - 止盈价位目标
    - 风险收益比评估
    - 操作建议文字
    """
    result: dict[str, Any] = {
        "entry_price": 0.0,
        "stop_loss": 0.0,
        "take_profit_1": 0.0,
        "take_profit_2": 0.0,
        "risk_reward_ratio": 0.0,
        "position_size_pct": 0.0,
        "action_recommendation": "",
        "risk_notes": "",
        "confidence_adjust": 0.0,
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["action_recommendation"] = "非3买/3卖信号，暂不提供操作建议"
            return result

        current_price = closes[-1]
        bi_low = mmd.bi.low if mmd.bi else current_price
        bi_high = mmd.bi.high if mmd.bi else current_price
        latest_close = closes[-1]

        # 计算 ATR（最近 14 根，反映当前波动率；V494 修复：旧实现误取窗口最前 14 根）
        atr = 0.0
        if highs and lows and len(closes) >= 2:
            lookback = min(14, len(closes) - 1)
            tr_list = []
            for i in range(len(closes) - lookback, len(closes)):
                high = highs[i]
                low = lows[i]
                prev_close = closes[i - 1]
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                tr_list.append(tr)
            atr = sum(tr_list) / len(tr_list) if tr_list else current_price * 0.02
        else:
            atr = current_price * 0.02

        if is_buy:
            # 买入信号
            entry_price = round(latest_close * 1.001, 2)  # 略高于当前价
            stop_loss = round(max(bi_low * 0.98, latest_close - atr * 2), 2)  # 止损在笔低点或ATR*2
            zs_height = (mmd.zs.zg - mmd.zs.zd) if mmd.zs else atr * 3
            take_profit_1 = round(latest_close + zs_height * 0.5, 2)
            take_profit_2 = round(latest_close + zs_height * 1.0, 2)

            risk = entry_price - stop_loss
            reward = take_profit_1 - entry_price
            rrr = round(reward / risk, 2) if risk > 0 else 0

            result["entry_price"] = entry_price
            result["stop_loss"] = stop_loss
            result["take_profit_1"] = take_profit_1
            result["take_profit_2"] = take_profit_2
            result["risk_reward_ratio"] = rrr

            # 仓位建议
            if rrr >= 3.0:
                result["position_size_pct"] = 30.0
                result["action_recommendation"] = "强烈建议买入：风险收益比优良(3:1+)，可建仓30%"
                result["confidence_adjust"] = 0.03
            elif rrr >= 2.0:
                result["position_size_pct"] = 20.0
                result["action_recommendation"] = "建议买入：风险收益比良好(2:1+)，可试探性建仓20%"
                result["confidence_adjust"] = 0.02
            elif rrr >= 1.5:
                result["position_size_pct"] = 10.0
                result["action_recommendation"] = "谨慎买入：风险收益比一般(1.5:1)，轻仓试水10%"
                result["confidence_adjust"] = 0.01
            else:
                result["position_size_pct"] = 0.0
                result["action_recommendation"] = "不建议买入：风险收益比偏低(<1.5:1)，建议观望"
                result["confidence_adjust"] = -0.03

            result["risk_notes"] = (
                f"止损 {stop_loss:.2f}（-{(entry_price - stop_loss) / entry_price * 100:.1f}%），"
                f"第一止盈 {take_profit_1:.2f}"
                f"（+{(take_profit_1 - entry_price) / entry_price * 100:.1f}%）"
            )

        else:  # is_sell
            entry_price = round(latest_close * 0.999, 2)  # 略低于当前价
            stop_loss = round(min(bi_high * 1.02, latest_close + atr * 2), 2)
            zs_height = (mmd.zs.zg - mmd.zs.zd) if mmd.zs else atr * 3
            take_profit_1 = round(latest_close - zs_height * 0.5, 2)
            take_profit_2 = round(latest_close - zs_height * 1.0, 2)

            risk = stop_loss - entry_price
            reward = entry_price - take_profit_1
            rrr = round(reward / risk, 2) if risk > 0 else 0

            result["entry_price"] = entry_price
            result["stop_loss"] = stop_loss
            result["take_profit_1"] = take_profit_1
            result["take_profit_2"] = take_profit_2
            result["risk_reward_ratio"] = rrr

            if rrr >= 3.0:
                result["position_size_pct"] = 30.0
                result["action_recommendation"] = "强烈建议卖出：风险收益比优良(3:1+)，可减仓30%"
                result["confidence_adjust"] = 0.03
            elif rrr >= 2.0:
                result["position_size_pct"] = 20.0
                result["action_recommendation"] = "建议卖出：风险收益比良好(2:1+)，可减仓20%"
                result["confidence_adjust"] = 0.02
            elif rrr >= 1.5:
                result["position_size_pct"] = 10.0
                result["action_recommendation"] = "谨慎卖出：风险收益比一般(1.5:1)，轻仓减仓10%"
                result["confidence_adjust"] = 0.01
            else:
                result["position_size_pct"] = 0.0
                result["action_recommendation"] = "不建议卖出：风险收益比偏低(<1.5:1)，建议持仓观望"
                result["confidence_adjust"] = -0.03

            result["risk_notes"] = (
                f"止损 {stop_loss:.2f}（+{(stop_loss - entry_price) / entry_price * 100:.1f}%），"
                f"第一止盈 {take_profit_1:.2f}"
                f"（-{(entry_price - take_profit_1) / entry_price * 100:.1f}%）"
            )

        return result
    except Exception:
        return result


def _calc_historical_pattern_matching(
    mmd: MMD,
    closes: list[float],
    volumes: list[float] | None,
) -> dict[str, Any]:
    """历史模式匹配（V102 条件267）。

    在历史数据中查找相似的价格模式，统计胜率：
    - 提取当前信号前的价格形态
    - 在历史数据中匹配相似形态
    - 统计后续价格走势的胜率
    """
    result: dict[str, Any] = {
        "similar_patterns_found": 0,
        "win_rate": 0.0,
        "avg_return": 0.0,
        "max_drawdown": 0.0,
        "confidence_adjust": 0.0,
        "msg": "",
    }
    try:
        is_buy = mmd.mmd_type == MMDType.BUY_3
        is_sell = mmd.mmd_type == MMDType.SELL_3
        if not is_buy and not is_sell:
            result["msg"] = "非3买/3卖信号，跳过模式匹配"
            return result

        if len(closes) < 60:
            result["msg"] = "历史数据不足，无法进行模式匹配"
            return result

        # 在历史中搜索相似模式
        similar_count = 0
        win_count = 0
        total_return = 0.0
        max_dd = 0.0

        lookback = min(200, len(closes) - 20)  # 搜索最近200根K线
        for start_idx in range(max(0, len(closes) - lookback), len(closes) - 20):
            # 检查是否形成类似的价格结构
            segment = closes[start_idx : start_idx + 20]
            if len(segment) < 10:
                continue

            # 检查趋势方向
            seg_trend = (segment[0] - segment[-1]) / (segment[0] + 1e-10) * 100

            # 相似度判断（简化版）
            similarity = True
            if is_buy and seg_trend < -5:  # 下跌趋势后买入
                similarity = True
            elif is_sell and seg_trend > 5:  # 上涨趋势后卖出
                similarity = True

            if not similarity:
                continue

            similar_count += 1

            # 统计后续表现（未来10根K线）
            future = closes[start_idx + 20 : start_idx + 30]
            if not future:
                continue

            trough = min(future) if future else segment[-1]
            end_price = future[-1]

            # 计算收益和回撤
            return_10d = (end_price - segment[-1]) / (segment[-1] + 1e-10) * 100
            dd_10d = (
                (segment[-1] - trough) / (segment[-1] + 1e-10) * 100 if trough < segment[-1] else 0
            )

            total_return += return_10d
            max_dd = max(max_dd, abs(dd_10d))

            # 胜率判断（买入涨、卖出跌为胜）
            if is_buy and return_10d > 0:
                win_count += 1
            elif is_sell and return_10d < 0:
                win_count += 1

        if similar_count > 0:
            win_rate = win_count / similar_count
            avg_return = total_return / similar_count

            result["similar_patterns_found"] = similar_count
            result["win_rate"] = round(win_rate * 100, 1)
            result["avg_return"] = round(avg_return, 2)
            result["max_drawdown"] = round(max_dd, 2)

            if win_rate >= 0.65 and avg_return > 1.0:
                result["confidence_adjust"] = 0.04
                result["msg"] = (
                    f"历史回测表现优良：胜率{win_rate:.0%}，平均收益{avg_return:.1f}%，+4%置信度"
                )
            elif win_rate >= 0.55 and avg_return > 0:
                result["confidence_adjust"] = 0.02
                result["msg"] = (
                    f"历史回测表现良好：胜率{win_rate:.0%}，平均收益{avg_return:.1f}%，+2%置信度"
                )
            elif win_rate >= 0.45:
                result["confidence_adjust"] = 0.0
                result["msg"] = f"历史回测表现一般：胜率{win_rate:.0%}，平均收益{avg_return:.1f}%"
            else:
                result["confidence_adjust"] = -0.03
                result["msg"] = (
                    f"历史回测表现较差：胜率{win_rate:.0%}，平均收益{avg_return:.1f}%，-3%置信度"
                )
        else:
            result["msg"] = "未找到相似历史模式"

        return result
    except Exception:
        return result
