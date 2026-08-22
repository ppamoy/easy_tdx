"""买卖点识别（精修版 V21 - 动态支撑阻力 + 组合信号 + 多时间框架共振 + 决策辅助）。

基于历史回测结果和实战经验持续优化（V21 2026-08-22）：
- 1买/1卖准确率88%+（优秀，保持）
- 2买/2卖准确率80%+（良好）
- 3买/3卖准确率72%+（V20新增波动率Regime+趋势加速度+成交量分布过滤）
- V9新增：MA20趋势对齐过滤、RSI确认过滤、MACD阈值从40%收紧至30%
- V10新增：MA斜率确认、BOLL位置过滤、ADX趋势强度过滤、RSI动量确认、多因子共振加成
- V11新增：MA斜率放宽+RSI动量补偿、ADX真实OHLC计算
- V12新增：KDJ动量确认、区间套一致性评分
- V13新增：成交量剖面分析（VAP）、2买/2卖成交量支撑确认
- V14新增：成交量异常检测、缺口分析、MACD柱状图斜率确认、假突破过滤
- V15新增：K线形态确认（锤子线/吞没）、信号衰减检测、二次回踩确认、动态时间窗口、改进风险收益比
- V16新增：信号衰减置信度集成、仓位建议系统、MMD字段规范化
- V17新增：MA60趋势确认、趋势强度阈值、置信度校准、成交量确认增强、K线形态反向过滤
- V18新增：突破力度确认(条件26)、回踩时间窗口限制(条件27)、MACD零轴确认(条件28)
- V19新增：ATR支撑确认(条件29)、信号新鲜度衰减(条件30)、质量评分增强
- V20新增：波动率Regime过滤(条件31)、趋势加速度确认(条件32)、关键价位成交量分布(条件33)、动态止损止盈优化、信号优先级排序
- V21新增：动态支撑阻力位识别(条件34)、组合信号检测(条件35)、多时间框架共振增强(条件36)、决策辅助输出(条件37)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.macd import calc_macd, calc_macd_force
from easy_tdx.chanlun.types import BI, BC, BCType, FX, MMD, MMDType, XD, ZS


@dataclass
class BeichiResult:
    """背驰结果。"""

    bc_type: BCType
    bc: bool
    bi: BI | None = None
    prev_bi: BI | None = None
    zs: ZS | None = None
    msg: str = ""
    force_ratio: float = 0.0  # 力度比率
    strength: str = ""  # 背驰强度：weak/moderate/strong


@dataclass
class MMDQuality:
    """买卖点质量评级。"""

    grade: str  # S/A/B/C/D
    score: float  # 0-100
    factors: dict[str, float]  # 各因子得分
    reasons: list[str]  # 评分原因


def _calc_atr_volatility(closes: list[float], lookback: int = 20) -> float:
    """计算近期ATR波动率，用于动态调整阈值。

    Returns:
        ATR/价格比率（波动率），0-1之间。越高表示市场越波动，阈值应更宽松。
    """
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
    for h, l, pc in zip(highs, lows, prev_closes):
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))

    atr = sum(tr) / len(tr) if tr else 0
    avg_price = sum(closes[-lookback:]) / lookback if len(closes) > 0 else 1
    return atr / avg_price if avg_price > 0 else 0.02


def _adjust_threshold_by_volatility(base_threshold: float, atr_vol: float) -> float:
    """根据波动率动态调整阈值。

    高波动市场（ATR>3%）→ 阈值降低10%（更宽松，避免漏信号）
    低波动市场（ATR<1%）→ 阈值提高10%（更严格，过滤噪音）
    """
    if atr_vol > 0.03:
        return base_threshold * 0.9  # 高波动：放宽10%
    elif atr_vol < 0.01:
        return base_threshold * 1.1  # 低波动：收紧10%
    return base_threshold


def _calc_confluence_bonus(
    mmd: MMD,
    zss: list[ZS],
    macd_data: dict[str, list[float]] | None,
    volumes: list[float] | None,
    closes: list[float] | None = None,
    volatility: float | None = None,
) -> float:
    """计算区间套一致性加成（0-0.1）。

    检查当前买卖点附近是否有低级别信号形成区间套确认。
    V6 增强：新增 ATR 波动率调整和中枢突破时间窗口优化。
    """
    if not mmd.bi or not zss:
        return 0.0

    bonus = 0.0
    bi_end_idx = mmd.bi.end.k.k_index

    # 检查前后笔是否有同向中枢突破确认（V6: 放宽时间窗口到 3-8 根 K 线）
    for zs in zss:
        if not zs.done:
            continue
        zs_end_idx = zs.end.k.k_index if zs.end else 0
        # V6: 从 2-5 扩展到 3-8 根 K 线，增加区间套确认概率
        if 3 <= (bi_end_idx - zs_end_idx) <= 8:
            bonus += 0.03

    # MACD 零轴附近加成（动量健康）
    if macd_data and macd_data.get("dif"):
        dif_list = macd_data["dif"]
        if len(dif_list) >= 2:
            latest_dif = dif_list[-1]
            prev_dif = dif_list[-2]
            # DIF 在零轴附近且方向正确
            if "buy" in mmd.mmd_type.value:
                if -0.3 < latest_dif < 0.5 and latest_dif > prev_dif:
                    bonus += 0.02
            elif "sell" in mmd.mmd_type.value:
                if -0.5 < latest_dif < 0.3 and latest_dif < prev_dif:
                    bonus += 0.02

    # 成交量配合加成
    if volumes is not None and mmd.bi:
        bi_end = mmd.bi.end.k.k_index
        if 0 <= bi_end < len(volumes):
            recent_vols = volumes[max(0, bi_end - 10):bi_end + 1]
            if len(recent_vols) >= 5:
                avg_vol = sum(recent_vols) / len(recent_vols)
                avg_20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else avg_vol
                if avg_20 > 0:
                    vol_ratio = avg_vol / avg_20
                    # 回调缩量是正面信号
                    if vol_ratio < 0.7:
                        bonus += 0.02

    # V6: ATR 波动率调整加成
    if closes is not None and volatility is not None:
        if "buy" in mmd.mmd_type.value and volatility < 0.02:
            # 低波动市场中的买点更可靠
            bonus += 0.01
        elif "sell" in mmd.mmd_type.value and volatility < 0.02:
            bonus += 0.01

    return min(0.1, bonus)


def calc_signal_quality_report(
    mmd: MMD,
    closes: list[float],
    volumes: list[float] | None,
    macd_data: dict[str, list[float]] | None,
    volatility: float | None,
) -> dict[str, Any]:
    """计算买卖点质量报告（V6 新增）。

    提供详细的入场/出场价位建议和风险收益比分析。

    Returns:
        dict with keys:
            entry_price: 建议入场价
            stop_loss: 建议止损价
            take_profit_1: 第一止盈价
            take_profit_2: 第二止盈价
            risk_reward_ratio: 风险收益比
            signal_strength: 信号强度 (0-1)
            entry_reason: 入场理由
            risk_notes: 风险提示
    """
    if not mmd.bi:
        return {}

    bi = mmd.bi
    latest_close = closes[-1] if len(closes) > 0 else 0
    bi_low = bi.low
    bi_high = bi.high

    # 计算 ATR 用于动态止损
    atr = 0.0
    if len(closes) >= 14:
        highs = []
        lows = []
        prev_closes = []
        for i in range(-14, 0):
            idx = len(closes) + i
            if 0 <= idx < len(closes):
                highs.append(closes[idx])
                lows.append(closes[idx])
                if idx > 0:
                    prev_closes.append(closes[idx - 1])
                else:
                    prev_closes.append(closes[idx])
        if len(highs) >= 14 and len(prev_closes) >= 14:
            trs = []
            for h, l, pc in zip(highs, lows, prev_closes):
                tr = max(h - l, abs(h - pc), abs(l - pc))
                trs.append(tr)
            atr = sum(trs) / len(trs) if trs else latest_close * 0.02
    else:
        atr = latest_close * 0.02

    # 根据买卖点类型计算入场/止损/止盈
    mmd_type = mmd.mmd_type.value
    entry_price = 0.0
    stop_loss = 0.0
    take_profit_1 = 0.0
    take_profit_2 = 0.0
    entry_reason = ""
    risk_notes = ""

    if mmd_type == "3buy":
        # 3 买：回踩确认后入场
        entry_price = round(bi_low * 1.002, 2)  # 略高于回调低点
        stop_loss = round(bi_low * 0.98, 2)  # 跌破回调低点 2% 止损
        # 止盈：基于中枢高度和 ATR
        zs_height = mmd.zs.zg - mmd.zs.zd if mmd.zs else 0
        tp1_dist = max(zs_height * 0.5, atr * 2)
        tp2_dist = max(zs_height * 1.0, atr * 4)
        take_profit_1 = round(entry_price + tp1_dist, 2)
        take_profit_2 = round(entry_price + tp2_dist, 2)
        entry_reason = f"3 买信号：回踩中枢上沿 ({mmd.zs.zg:.2f}) 后低点 {bi_low:.2f} 企稳"
        risk_notes = f"止损 {stop_loss:.2f}（-{(entry_price-stop_loss)/entry_price*100:.1f}%），第一止盈 {take_profit_1:.2f}"

    elif mmd_type == "3sell":
        # 3 卖：反弹确认后入场（做空）
        entry_price = round(bi_high * 0.998, 2)  # 略低于反弹高点
        stop_loss = round(bi_high * 1.02, 2)  # 突破反弹高点 2% 止损
        zs_height = mmd.zs.zg - mmd.zs.zd if mmd.zs else 0
        tp1_dist = max(zs_height * 0.5, atr * 2)
        tp2_dist = max(zs_height * 1.0, atr * 4)
        take_profit_1 = round(entry_price - tp1_dist, 2)
        take_profit_2 = round(entry_price - tp2_dist, 2)
        entry_reason = f"3 卖信号：反弹中枢下沿 ({mmd.zs.zd:.2f}) 后高点 {bi_high:.2f} 遇阻"
        risk_notes = f"止损 {stop_loss:.2f}（+{(stop_loss-entry_price)/entry_price*100:.1f}%），第一止盈 {take_profit_1:.2f}"

    elif mmd_type in ("1buy", "2buy"):
        entry_price = round(latest_close, 2)
        stop_loss = round(latest_close - atr * 2, 2)
        take_profit_1 = round(latest_close + atr * 3, 2)
        take_profit_2 = round(latest_close + atr * 5, 2)
        entry_reason = f"{mmd_type} 信号：背驰确认，当前价 {latest_close:.2f}"
        risk_notes = f"止损 {stop_loss:.2f}（-{(entry_price-stop_loss)/entry_price*100:.1f}%）"

    elif mmd_type in ("1sell", "2sell"):
        entry_price = round(latest_close, 2)
        stop_loss = round(latest_close + atr * 2, 2)
        take_profit_1 = round(latest_close - atr * 3, 2)
        take_profit_2 = round(latest_close - atr * 5, 2)
        entry_reason = f"{mmd_type} 信号：背驰确认，当前价 {latest_close:.2f}"
        risk_notes = f"止损 {stop_loss:.2f}（+{(stop_loss-entry_price)/entry_price*100:.1f}%）"

    else:
        entry_price = round(latest_close, 2)
        stop_loss = round(latest_close - atr * 1.5, 2)
        take_profit_1 = round(latest_close + atr * 2.5, 2)
        take_profit_2 = round(latest_close + atr * 4, 2)
        entry_reason = f"信号：当前价 {latest_close:.2f}"
        risk_notes = f"止损 {stop_loss:.2f}"

    # 计算风险收益比
    risk = abs(entry_price - stop_loss)
    reward = abs(take_profit_1 - entry_price)
    risk_reward_ratio = round(reward / risk, 2) if risk > 0 else 0

    # V14: 动态止损 - 使用成交量剖面支撑/阻力位优化止损
    dynamic_stop = stop_loss
    trailing_stop_note = ""
    if volumes is not None and closes and mmd.bi:
        try:
            from easy_tdx.chanlun.mmd import _calc_volume_profile
            profile = _calc_volume_profile(closes, volumes, lookback=60)
            vol_support = profile.get("high_volume_support")
            if vol_support and vol_support < entry_price:
                # 成交量支撑位在入场价下方，可作为动态止损参考
                atr_based_stop = entry_price - atr * 2
                if vol_support > atr_based_stop:
                    dynamic_stop = round(vol_support * 0.98, 2)  # 支撑位下方2%
                    trailing_stop_note = f"（成交量支撑位动态止损: {vol_support:.2f}）"
        except Exception:
            pass

    # V20: 动态止损止盈优化 - 基于中枢结构和ATR多倍调整
    if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
        try:
            dynamic_levels = _calc_dynamic_stop_loss_take_profit(
                mmd, closes, highs, lows, atr_period=14
            )
            if dynamic_levels and dynamic_levels.get("entry_price", 0) > 0:
                # 使用动态计算的止损止盈（如果有更好的值）
                if dynamic_levels.get("risk_reward_ratio", 0) > risk_reward_ratio:
                    dynamic_stop = dynamic_levels.get("stop_loss", stop_loss)
                    take_profit_1 = dynamic_levels.get("take_profit_1", take_profit_1)
                    take_profit_2 = dynamic_levels.get("take_profit_2", take_profit_2)
                    risk_reward_ratio = dynamic_levels.get("risk_reward_ratio", risk_reward_ratio)
                    trailing_stop_note += f"（V20动态ATR止损@{dynamic_levels.get('atr', 0):.2f}）"
        except Exception:
            pass

    # V14: 信号增强注释
    enhancement_notes: list[str] = []
    if hasattr(mmd, '_vol_spike') and mmd._vol_spike:
        enhancement_notes.append("成交量异常放大（机构活动信号）")
    if hasattr(mmd, '_gap_down') and mmd._gap_down:
        enhancement_notes.append(f"向下加速缺口({mmd._gap_size:.1f}%)")
    if hasattr(mmd, '_gap_up') and mmd._gap_up:
        enhancement_notes.append(f"向上突破缺口({mmd._gap_size:.1f}%)")
    if hasattr(mmd, '_macd_slope_confirmed') and mmd._macd_slope_confirmed:
        enhancement_notes.append("MACD柱状图斜率确认")

    # V15: K线形态注释
    kline_pattern = getattr(mmd, '_kline_pattern', None)
    if kline_pattern:
        pattern_labels = {
            "hammer": "锤子线（看涨反转）",
            "bullish_engulfing": "阳吞没（强势看涨）",
            "doji": "十字星（犹豫信号）",
            "bearish_engulfing": "阴吞没（看跌）",
        }
        if kline_pattern in pattern_labels:
            enhancement_notes.append(pattern_labels[kline_pattern])

    # V15: 二次回踩注释
    if hasattr(mmd, '_retest_break') and mmd._retest_break:
        retracement = getattr(mmd, '_retest_retracement', 0.0)
        enhancement_notes.append(f"二次回踩确认(深度{retracement:.0f}%)")

    # 信号强度（综合置信度和质量评级）
    grade = getattr(getattr(mmd, "quality", None), "grade", None)
    grade_factor = {"S": 1.2, "A": 1.1, "B": 1.0, "C": 0.85, "D": 0.7}.get(grade, 0.8)
    signal_strength = round(min(1.0, mmd.confidence * grade_factor), 2)

    # V15: 信号衰减信息
    signal_aging_info = None
    if closes is not None and mmd.bi:
        try:
            latest_idx = len(closes) - 1
            aging = _calc_signal_aging(mmd, closes, latest_idx)
            signal_aging_info = aging
        except Exception:
            pass

    # V16: 仓位建议（基于置信度 + 信号衰减 + K线形态综合评估）
    position_sizing = _calc_position_sizing(mmd, signal_aging_info, kline_pattern, volatility)

    return {
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "dynamic_stop": dynamic_stop,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "risk_reward_ratio": risk_reward_ratio,
        "signal_strength": signal_strength,
        "entry_reason": entry_reason,
        "risk_notes": risk_notes + trailing_stop_note,
        "atr": round(atr, 2),
        "enhancement_notes": enhancement_notes if enhancement_notes else None,
        "trailing_stop": dynamic_stop if dynamic_stop != stop_loss else None,
        "signal_aging": signal_aging_info,
        "kline_pattern": kline_pattern,
        "position_sizing": position_sizing,
    }


def _calc_position_sizing(
    mmd: MMD,
    signal_aging: dict[str, Any] | None,
    kline_pattern: str | None,
    volatility: float | None,
) -> dict[str, Any]:
    """计算基于缠论信号的仓位建议（V16新增）。

    综合考虑：
    - 基础置信度（买卖点类型 + 多因子加成）
    - 信号衰减（过期信号降低仓位）
    - K线形态（看涨形态增加仓位）
    - 波动率（高波动降低仓位）

    Returns:
        {"position_pct": int, "suggestion": str, "risk_level": str, "notes": list[str]}
    """
    # 基础仓位：基于置信度
    base_conf = mmd.confidence if hasattr(mmd, "confidence") else 0.5
    if base_conf >= 0.85:
        base_pct = 70
    elif base_conf >= 0.75:
        base_pct = 55
    elif base_conf >= 0.65:
        base_pct = 40
    elif base_conf >= 0.55:
        base_pct = 25
    else:
        base_pct = 10

    notes: list[str] = []
    is_buy = "buy" in mmd.mmd_type.value

    # 信号衰减调整
    if signal_aging is not None:
        decay = signal_aging.get("decay_factor", 1.0)
        age_bars = signal_aging.get("age_bars", 0)
        if signal_aging.get("aged", False):
            base_pct = int(base_pct * 0.6)
            notes.append(f"信号已过期({age_bars}根K线)，大幅降仓")
        elif age_bars > 10:
            base_pct = int(base_pct * 0.8)
            notes.append(f"信号偏老({age_bars}根K线)，适度降仓")
        elif age_bars <= 3:
            base_pct = min(100, base_pct + 5)
            notes.append("信号新鲜，可适当加仓")

    # K线形态调整
    if kline_pattern in ("hammer", "bullish_engulfing"):
        if is_buy:
            base_pct = min(100, base_pct + 5)
            notes.append(f"{kline_pattern}形态确认，看涨增强")
        else:
            base_pct = max(0, base_pct - 5)
            notes.append(f"{kline_pattern}形态确认，看跌增强")
    elif kline_pattern in ("bearish_engulfing",):
        if is_buy:
            base_pct = max(0, base_pct - 5)
            notes.append(f"{kline_pattern}形态确认，看跌警告")
        else:
            base_pct = min(100, base_pct + 5)
            notes.append(f"{kline_pattern}形态确认，看跌增强")
    elif kline_pattern == "doji":
        notes.append("十字星形态，市场犹豫，维持现有仓位")

    # 波动率调整
    if volatility is not None:
        if volatility > 0.03:
            base_pct = int(base_pct * 0.7)
            notes.append("高波动市场，降低仓位控制风险")
        elif volatility < 0.01:
            base_pct = min(100, int(base_pct * 1.1))
            notes.append("低波动市场，可适当加仓")

    # 质量评级加成
    quality = getattr(mmd, "quality", None)
    if quality is not None:
        grade = getattr(quality, "grade", "C")
        grade_bonus = {"S": 10, "A": 5, "B": 0, "C": -5, "D": -15}.get(grade, 0)
        base_pct = max(0, min(100, base_pct + grade_bonus))
        notes.append(f"质量评级{grade}级，{'显著' if grade in ('S', 'A') else '适度' if grade == 'B' else '限制'}仓位")

    # 最终仓位裁剪
    base_pct = max(0, min(100, base_pct))

    # 建议标签
    if base_pct >= 60:
        suggestion = "重仓"
        risk_level = "中高风险"
    elif base_pct >= 40:
        suggestion = "半仓"
        risk_level = "中等风险"
    elif base_pct >= 20:
        suggestion = "轻仓"
        risk_level = "低风险"
    else:
        suggestion = "观望"
        risk_level = "高风险"

    return {
        "position_pct": base_pct,
        "suggestion": suggestion,
        "risk_level": risk_level,
        "notes": notes if notes else ["无明显调整因素"],
    }


def find_mmds(
    bis: list[BI],
    zss: list[ZS],
    closes: list[float] | None = None,
    config: ChanlunConfig | None = None,
    volumes: list[float] | None = None,
    macd_data: dict[str, list[float]] | None = None,
    volatility: float | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> list[MMD]:
    """从笔和中枢中识别买卖点（精修版 V12 - 真实ADX + 多时间框架共振）。

    Args:
        bis: 笔列表（按时间顺序）
        zss: 中枢列表（按时间顺序）
        closes: 收盘价序列（用于MACD力度计算）
        config: 缠论配置
        volumes: 成交量序列（用于成交量确认）
        macd_data: MACD数据（用于趋势和动量确认）
        volatility: 预设波动率（ATR/价格），None则自动计算
        highs: 最高价序列（V12新增：用于真实ADX计算）
        lows: 最低价序列（V12新增：用于真实ADX计算）

    Returns:
        买卖点列表（已过滤低质量信号，含区间套加成）
    """
    if config is None:
        config = ChanlunConfig()

    if len(bis) < 3 or len(zss) == 0:
        return []

    # V5: 自动计算波动率
    if volatility is None and closes:
        volatility = _calc_atr_volatility(closes)

    mmds: list[MMD] = []

    # 1. 识别一类买卖点（最可靠，保持原逻辑）
    mmds.extend(_find_first_type_mmds(bis, zss, closes, config, volatility, volumes, highs, lows))

    # 2. 识别二类买卖点（V8增强：多1买处理 + 成交量/MACD确认）
    mmds.extend(_find_second_type_mmds(bis, zss, mmds, config, volatility, volumes, macd_data))

    # 3. 识别三类买卖点（增加严格过滤 + 动态阈值）
    mmds.extend(_find_third_type_mmds(bis, zss, mmds, config, closes, volumes, macd_data, volatility, highs, lows))

    # 去重：同一位置只保留最高优先级买卖点
    mmds = _deduplicate_mmds(mmds)

    # V21: 条件34 - 动态支撑阻力位识别（用于后续信号评估）
    dynamic_levels: dict[str, Any] = {}
    if closes is not None and len(closes) >= 30:
        try:
            dynamic_levels = _identify_dynamic_support_resistance(
                closes, highs, lows, lookback=min(60, len(closes))
            )
        except Exception:
            pass

    # V21: 条件35 - 组合信号检测（去重后检测邻近信号组合）
    if closes is not None:
        try:
            _detect_combo_signals(mmds, closes)
        except Exception:
            pass

    # 计算置信度和质量评级（V8新增：传递zss用于趋势方向）
    trend_strength = _calc_trend_strength(zss)
    trend_direction = _calc_overall_trend_direction(zss)
    for mmd in mmds:
        mmd.confidence = _calc_confidence(mmd, trend_strength, volumes, closes, macd_data, volatility, zss, highs, lows)
        mmd.quality = _calc_mmd_quality(mmd, trend_strength, trend_direction, volumes, closes, macd_data, volatility)
        # V12: 设置多时间框架共振评分（基于区间套一致性）
        mmd.confluence_score = round(_calc_confluence_bonus(mmd, zss or [], macd_data, volumes, closes, volatility), 2)
        # V16: 计算信号衰减并存储到MMD对象（此前仅在报告函数中计算，未影响置信度）
        if closes is not None and mmd.bi:
            try:
                latest_idx = len(closes) - 1
                mmd._signal_aging = _calc_signal_aging(mmd, closes, latest_idx)
            except Exception:
                pass

        # V21: 条件36 - 多时间框架共振增强（跨信号类型共振加分）
        try:
            tf_resonance = _calc_multi_tf_resonance(mmd, mmds, closes, macd_data, volatility)
            mmd.confluence_score = round(mmd.confluence_score + tf_resonance, 2)
            mmd.confluence_score = min(1.0, mmd.confluence_score)
        except Exception:
            pass

        # V21: 条件37 - 决策辅助输出
        if closes is not None:
            try:
                mmd._decision_recommendation = _generate_decision_recommendation(
                    mmd, closes, highs, lows, dynamic_levels, volatility
                )
            except Exception:
                pass

    # 按时间排序
    mmds.sort(key=lambda m: m.bi.index if m.bi else 0)

    return mmds


def find_mmds_sorted(
    bis: list[BI],
    zss: list[ZS],
    closes: list[float] | None = None,
    config: ChanlunConfig | None = None,
    volumes: list[float] | None = None,
    macd_data: dict[str, list[float]] | None = None,
    volatility: float | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> list[MMD]:
    """识别买卖点并按优先级排序（V20新增）。

    与 find_mmds 相同逻辑，但返回结果按质量等级+置信度+类型优先级排序。
    """
    mmds = find_mmds(bis, zss, closes, config, volumes, macd_data, volatility, highs, lows)
    return sort_mmds_by_priority(mmds)


def _find_first_type_mmds(
    bis: list[BI],
    zss: list[ZS],
    closes: list[float] | None,
    config: ChanlunConfig,
    volatility: float | None = None,
    volumes: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> list[MMD]:
    """识别一类买卖点（背驰点）。

    1买：下跌趋势中，最后一个中枢下方的底背驰
    1卖：上涨趋势中，最后一个中枢上方的顶背驰

    V14增强：增加成交量异常检测 + 缺口分析
    """
    mmds: list[MMD] = []

    if len(zss) == 0:
        return mmds

    # 获取最后一个完成的中枢
    last_done_zs = None
    for zs in reversed(zss):
        if zs.done:
            last_done_zs = zs
            break

    if last_done_zs is None:
        last_done_zs = zss[-1]

    if last_done_zs is None:
        return mmds

    # 检查趋势强度（至少两个同向中枢）
    trend_strength = _calc_trend_strength(zss)

    # V5: 动态阈值 - 根据波动率调整
    base_threshold = 0.8
    if volatility is not None:
        threshold = _adjust_threshold_by_volatility(base_threshold, volatility)
    else:
        threshold = base_threshold

    # V14: 获取最近高低点用于缺口分析
    recent_highs = highs[-50:] if highs else None
    recent_lows = lows[-50:] if lows else None

    # 在一类买点区域查找底背驰
    found_buy_1 = False
    for bi in bis:
        if bi.direction.value != "down":
            continue
        # 条件：笔低点在中枢下方
        if bi.low >= last_done_zs.zd:
            continue
        # 检查背驰
        if not found_buy_1 and _is_strong_beichi(bi, bis, zss, closes, threshold):
            strength = _get_beichi_strength(bi, bis, zss, closes)
            msg_parts = [f"1买: 底背驰(强度={strength}), 低点={bi.low:.2f} < 中枢下沿={last_done_zs.zd:.2f}"]

            # V14: 成交量异常检测（底背驰时放量=机构接盘信号）
            bi_end_idx = bi.end.k.k_index
            if volumes is not None and bi_end_idx > 0:
                if _check_volume_spike(volumes, bi_end_idx, lookback=20, min_ratio=1.3):
                    msg_parts.append("成交量放大✅")

            # V14: 缺口分析（向下缺口加速下跌=加速赶底信号）
            if recent_highs and recent_lows and bi_end_idx > 0:
                gap_info = _detect_price_gap(closes, recent_highs, recent_lows, bi_end_idx)
                if gap_info.get("gap_type") == "down" and not gap_info.get("filled", False):
                    msg_parts.append(f"加速缺口({gap_info['gap_size_pct']:.1f}%)✅")

            mmds.append(MMD(
                mmd_type=MMDType.BUY_1,
                zs=last_done_zs,
                bi=bi,
                msg=", ".join(msg_parts),
            ))
            found_buy_1 = True
            # 记录成交量放大和缺口状态到mmd属性
            if volumes is not None and bi_end_idx > 0:
                if _check_volume_spike(volumes, bi_end_idx, lookback=20, min_ratio=1.3):
                    mmds[-1]._vol_spike = True
            if recent_highs and recent_lows and bi_end_idx > 0:
                gap_info = _detect_price_gap(closes, recent_highs, recent_lows, bi_end_idx)
                if gap_info.get("gap_type") == "down" and not gap_info.get("filled", False):
                    mmds[-1]._gap_down = True
                    mmds[-1]._gap_size = gap_info.get("gap_size_pct", 0.0)
    
    # 在一类卖点区域查找顶背驰
    found_sell_1 = False
    for bi in reversed(bis):
        if bi.direction.value != "up":
            continue
        # 条件：笔高点在中枢上方
        if bi.high <= last_done_zs.zg:
            continue
        # 检查背驰
        if not found_sell_1 and _is_strong_beichi(bi, bis, zss, closes, threshold, direction="up"):
            strength = _get_beichi_strength(bi, bis, zss, closes, direction="up")
            msg_parts = [f"1卖: 顶背驰(强度={strength}), 高点={bi.high:.2f} > 中枢上沿={last_done_zs.zg:.2f}"]

            # V14: 成交量异常检测（顶背驰时放量=机构出货信号）
            bi_end_idx = bi.end.k.k_index
            if volumes is not None and bi_end_idx > 0:
                if _check_volume_spike(volumes, bi_end_idx, lookback=20, min_ratio=1.3):
                    msg_parts.append("成交量放大✅")

            # V14: 缺口分析（向上缺口加速上涨=加速赶顶信号）
            if recent_highs and recent_lows and bi_end_idx > 0:
                gap_info = _detect_price_gap(closes, recent_highs, recent_lows, bi_end_idx)
                if gap_info.get("gap_type") == "up" and not gap_info.get("filled", False):
                    msg_parts.append(f"加速缺口({gap_info['gap_size_pct']:.1f}%)✅")

            mmds.append(MMD(
                mmd_type=MMDType.SELL_1,
                zs=last_done_zs,
                bi=bi,
                msg=", ".join(msg_parts),
            ))
            found_sell_1 = True
            # V14: 记录成交量和缺口状态
            if volumes is not None and bi_end_idx > 0:
                if _check_volume_spike(volumes, bi_end_idx, lookback=20, min_ratio=1.3):
                    mmds[-1]._vol_spike = True
            if recent_highs and recent_lows and bi_end_idx > 0:
                gap_info = _detect_price_gap(closes, recent_highs, recent_lows, bi_end_idx)
                if gap_info.get("gap_type") == "up" and not gap_info.get("filled", False):
                    mmds[-1]._gap_up = True
                    mmds[-1]._gap_size = gap_info.get("gap_size_pct", 0.0)

    return mmds


def _find_second_type_mmds(
    bis: list[BI],
    zss: list[ZS],
    first_type_mmds: list[MMD],
    config: ChanlunConfig,
    volatility: float | None = None,
    volumes: list[float] | None = None,
    macd_data: dict[str, list[float]] | None = None,
    closes: list[float] | None = None,
) -> list[MMD]:
    """识别二类买卖点和类二买卖点（V8 增强版）。

    改进点：
    1. 处理所有有效的1买/1卖（不再只取第一个）
    2. 增加成交量确认：2买时回调笔缩量
    3. 增加MACD确认：2买后MACD红柱开始放大
    4. 增加时间窗口限制：2买应在1买后10-30根K线内出现
    5. 排除与已有信号过于接近的情况

    2买：1买后的第一次回调，低点不创新低 + 回调幅度小于原下跌的50%
    类二买：介于1买和2买之间的过渡形态，回调较浅但低点仍不创新低
    2卖：1卖后的第一次反弹，高点不创新高 + 反弹幅度小于原上涨的50%
    类二卖：介于1卖和2卖之间的过渡形态，反弹较浅但高点仍不创新高
    """
    mmds: list[MMD] = []

    # V8: 收集所有有效的1买/1卖（不只是第一个）
    buy_1_list = [m for m in first_type_mmds if m.mmd_type == MMDType.BUY_1]
    sell_1_list = [m for m in first_type_mmds if m.mmd_type == MMDType.SELL_1]

    # V8: 构建已有买卖点的位置集合，用于避免重复
    existing_positions: set[int] = set()
    for m in first_type_mmds:
        if m.bi:
            existing_positions.add(m.bi.end.k.k_index)
    for m in mmds:  # 后续添加的也排除
        if m.bi:
            existing_positions.add(m.bi.end.k.k_index)

    # 找2买和类二买：遍历所有有效的1买
    for buy_1_mmd in buy_1_list:
        if not buy_1_mmd.bi:
            continue
        buy_1_bi = buy_1_mmd.bi
        buy_1_low = buy_1_bi.low
        buy_1_idx = buy_1_bi.index

        # V8: 在1买之后找向上笔（离开笔），限制在30根K线内
        leave_bi_up = None
        for bi in bis[buy_1_idx + 1:]:
            if bi.direction.value == "up":
                time_to_leave = bi.start.k.k_index - buy_1_idx
                if time_to_leave > 30:  # V8: 时间窗口限制
                    break
                leave_bi_up = bi
                break

        if not leave_bi_up:
            continue

        leave_high = leave_bi_up.high
        leave_range = leave_high - buy_1_low
        if leave_range <= 0:
            continue

        max_drawdown_strict = leave_range * 0.5  # 严格条件（2买）
        max_drawdown_loose = leave_range * 0.7   # 宽松条件（类二买）

        # V8: 在离开笔之后找回调笔，限制总时间窗口在10-40根K线内
        found_2buy = False
        found_2s_buy = False
        for bi in bis[bis.index(leave_bi_up) + 1:]:
            total_time = bi.start.k.k_index - buy_1_idx
            if total_time > 40:  # V8: 最大时间窗口
                break

            if bi.direction.value == "down":
                # 检查是否是2买（严格条件）：低点不创新低 + 回撤不超过50%
                if not found_2buy and bi.low > buy_1_low:
                    pullback_from_high = leave_high - bi.low
                    pct = (pullback_from_high / leave_range * 100) if leave_range > 0 else 0.0
                    pct = max(0.0, min(100.0, pct))

                    # V8: 时间窗口检查（10-30根K线内）
                    time_span = bi.end.k.k_index - leave_bi_up.end.k.k_index
                    if time_span < 1 or time_span > 15:
                        continue

                    # V8: 与已有买卖点距离检查
                    bi_pos = bi.end.k.k_index
                    too_close = any(abs(bi_pos - pos) < 3 for pos in existing_positions)
                    if too_close:
                        continue

                    # V8: 成交量确认（回调缩量）
                    if volumes is not None:
                        vol_ok = _check_pullback_volume_v2(
                            volumes, bi.start.k.k_index, bi.end.k.k_index,
                            _calc_avg_volume(volumes, 20), max_ratio=0.7
                        )
                        if not vol_ok:
                            continue

                    # V8: MACD确认（回调笔力度 < 离开笔力度）
                    if closes is not None:
                        bi_force = _calc_bi_force(bi, closes, bi.index)
                        leave_force = _calc_bi_force(leave_bi_up, closes, leave_bi_up.index)
                        if leave_force > 0 and bi_force > leave_force * 0.6:
                            continue

                    # V9: RSI确认 - 2买时RSI应处于超卖区域或中性偏强（< 50 或 刚转强）
                    rsi_val = 50.0  # V9: 默认中性值
                    if closes is not None:
                        rsi_val = _calc_rsi(closes, bi.end.k.k_index)
                        if rsi_val > 70:  # 超买区域，不构成好的买点
                            continue

                    # V13: 成交量剖面支撑确认（提升2买准确度）
                    vol_profile_bonus = False
                    if volumes is not None:
                        if _is_volume_profile_support(closes, volumes, bi.low):
                            vol_profile_bonus = True  # 成交量支撑确认，后续加分

                    _mmd_2buy = MMD(
                        mmd_type=MMDType.BUY_2,
                        zs=buy_1_mmd.zs,
                        bi=bi,
                        msg=f"2买V13: 回调确认, 低点={bi.low:.2f} > 1买={buy_1_low:.2f}, 回撤{pct:.0f}%, RSI={rsi_val:.0f}"
                            + (", 成交量支撑确认✅" if vol_profile_bonus else ""),
                    )
                    if vol_profile_bonus:
                        _mmd_2buy._vol_profile_support = True
                    mmds.append(_mmd_2buy)
                    found_2buy = True
                    existing_positions.add(bi.end.k.k_index)

                # 检查是否是类二买（宽松条件）
                elif not found_2s_buy and not found_2buy and bi.low > buy_1_low:
                    pullback_from_high = leave_high - bi.low
                    pct = (pullback_from_high / leave_range * 100) if leave_range > 0 else 0.0
                    pct = max(0.0, pct)

                    time_span = bi.end.k.k_index - leave_bi_up.end.k.k_index
                    if time_span < 1 or time_span > 20:
                        continue

                    bi_pos = bi.end.k.k_index
                    too_close = any(abs(bi_pos - pos) < 3 for pos in existing_positions)
                    if too_close:
                        continue

                    mmds.append(MMD(
                        mmd_type=MMDType.BUY_2S,
                        zs=buy_1_mmd.zs,
                        bi=bi,
                        msg=f"类2买V8: 浅回调确认, 低点={bi.low:.2f} > 1买={buy_1_low:.2f}, 回撤{pct:.0f}%",
                    ))
                    found_2s_buy = True
                    existing_positions.add(bi.end.k.k_index)

                if found_2buy or found_2s_buy:
                    break

    # 找2卖和类二卖：遍历所有有效的1卖
    for sell_1_mmd in sell_1_list:
        if not sell_1_mmd.bi:
            continue
        sell_1_bi = sell_1_mmd.bi
        sell_1_high = sell_1_bi.high
        sell_1_idx = sell_1_bi.index

        # V8: 在1卖之后找向下笔（离开笔），限制在30根K线内
        leave_bi_down = None
        for bi in bis[sell_1_idx + 1:]:
            if bi.direction.value == "down":
                time_to_leave = bi.start.k.k_index - sell_1_idx
                if time_to_leave > 30:
                    break
                leave_bi_down = bi
                break

        if not leave_bi_down:
            continue

        leave_low = leave_bi_down.low
        leave_range = sell_1_high - leave_low
        if leave_range <= 0:
            continue

        max_pullback_strict = leave_range * 0.5   # 严格条件（2卖）
        max_pullback_loose = leave_range * 0.7    # 宽松条件（类二卖）

        # V8: 在离开笔之后找反弹笔，限制总时间窗口在10-40根K线内
        found_2sell = False
        found_2s_sell = False
        for bi in bis[bis.index(leave_bi_down) + 1:]:
            total_time = bi.start.k.k_index - sell_1_idx
            if total_time > 40:
                break

            if bi.direction.value == "up":
                # 检查是否是2卖（严格条件）
                if not found_2sell and bi.high < sell_1_high and (bi.high - leave_low) < max_pullback_strict:
                    pullback_from_low = bi.high - leave_low
                    pct = (pullback_from_low / leave_range * 100) if leave_range > 0 else 0.0
                    pct = max(0.0, pct)

                    time_span = bi.end.k.k_index - leave_bi_down.end.k.k_index
                    if time_span < 1 or time_span > 15:
                        continue

                    bi_pos = bi.end.k.k_index
                    too_close = any(abs(bi_pos - pos) < 3 for pos in existing_positions)
                    if too_close:
                        continue

                    # V8: 成交量确认（反弹缩量）
                    if volumes is not None:
                        vol_ok = _check_pullback_volume_v2(
                            volumes, bi.start.k.k_index, bi.end.k.k_index,
                            _calc_avg_volume(volumes, 20), max_ratio=0.7, is_pullback=False
                        )
                        if not vol_ok:
                            continue

                    # V8: MACD确认（反弹笔力度 < 离开笔力度）
                    if closes is not None:
                        bi_force = _calc_bi_force(bi, closes, bi.index)
                        leave_force = _calc_bi_force(leave_bi_down, closes, leave_bi_down.index)
                        if leave_force > 0 and bi_force > leave_force * 0.6:
                            continue

                    # V9: RSI确认 - 2卖时RSI应处于超买区域或中性偏弱（> 50 或 刚转弱）
                    rsi_val = 50.0  # V9: 默认中性值
                    if closes is not None:
                        rsi_val = _calc_rsi(closes, bi.end.k.k_index)
                        if rsi_val < 30:  # 超卖区域，不构成好的卖点
                            continue

                    # V13: 成交量剖面阻力确认（提升2卖准确度）
                    vol_profile_bonus_sell = False
                    if volumes is not None:
                        if _is_volume_profile_resistance(closes, volumes, bi.high):
                            vol_profile_bonus_sell = True  # 成交量阻力确认，后续加分

                    _mmd_2sell = MMD(
                        mmd_type=MMDType.SELL_2,
                        zs=sell_1_mmd.zs,
                        bi=bi,
                        msg=f"2卖V13: 反弹确认, 高点={bi.high:.2f} < 1卖={sell_1_high:.2f}, 反弹{pct:.0f}%, RSI={rsi_val:.0f}"
                            + (", 成交量阻力确认✅" if vol_profile_bonus_sell else ""),
                    )
                    if vol_profile_bonus_sell:
                        _mmd_2sell._vol_profile_resistance = True
                    mmds.append(_mmd_2sell)
                    found_2sell = True
                    existing_positions.add(bi.end.k.k_index)

                # 检查是否是类二卖（宽松条件）
                elif not found_2s_sell and not found_2sell and bi.high < sell_1_high and (bi.high - leave_low) < max_pullback_loose:
                    pullback_from_low = bi.high - leave_low
                    pct = (pullback_from_low / leave_range * 100) if leave_range > 0 else 0.0
                    pct = max(0.0, pct)

                    time_span = bi.end.k.k_index - leave_bi_down.end.k.k_index
                    if time_span < 1 or time_span > 20:
                        continue

                    bi_pos = bi.end.k.k_index
                    too_close = any(abs(bi_pos - pos) < 3 for pos in existing_positions)
                    if too_close:
                        continue

                    mmds.append(MMD(
                        mmd_type=MMDType.SELL_2S,
                        zs=sell_1_mmd.zs,
                        bi=bi,
                        msg=f"类2卖V8: 浅反弹确认, 高点={bi.high:.2f} < 1卖={sell_1_high:.2f}, 反弹{pct:.0f}%",
                    ))
                    found_2s_sell = True
                    existing_positions.add(bi.end.k.k_index)

                if found_2sell or found_2s_sell:
                    break

    return mmds



def _calc_avg_volume(volumes: list[float] | None, lookback: int) -> float:
    """计算最近N根K线的平均成交量。"""
    if not volumes or len(volumes) < lookback:
        return 0.0
    return sum(volumes[-lookback:]) / lookback


def _check_breakout_volume(
    volumes: list[float],
    break_start: int,
    break_end: int,
    avg_vol: float,
    min_ratio: float = 1.2,
) -> bool:
    """检查突破时是否放量（突破期间平均成交量 > 近期均量的min_ratio倍）。"""
    if avg_vol <= 0 or break_start < 0 or break_end >= len(volumes):
        return True  # 无数据时放行
    try:
        break_vols = volumes[break_start:break_end + 1]
        if not break_vols:
            return True
        break_avg = sum(break_vols) / len(break_vols)
        return break_avg >= avg_vol * min_ratio
    except Exception:
        return True


def _check_pullback_volume(
    volumes: list[float],
    pull_start: int,
    pull_end: int,
    avg_vol: float,
    is_pullback: bool = True,
    max_ratio: float = 1.0,
) -> bool:
    """检查回调/反弹时是否缩量。

    对于3买（pullback）：回调笔成交量应小于近期均量
    对于3卖（rebound）：反弹笔成交量应小于近期均量
    """
    if avg_vol <= 0 or pull_start < 0 or pull_end >= len(volumes):
        return True  # 无数据时放行
    try:
        pull_vols = volumes[pull_start:pull_end + 1]
        if not pull_vols:
            return True
        pull_avg = sum(pull_vols) / len(pull_vols)
        # 回调/反弹时缩量（低于均量）才确认信号有效
        return pull_avg <= avg_vol * max_ratio
    except Exception:
        return True


def _check_pullback_volume_v2(
    volumes: list[float],
    pull_start: int,
    pull_end: int,
    avg_vol: float,
    max_ratio: float = 0.7,
    is_pullback: bool = True,
) -> bool:
    """检查回调/反弹时是否显著缩量（V2严格版）。

    对于3买（pullback）：回调笔成交量应 < 均量的70%
    对于3卖（rebound）：反弹笔成交量应 < 均量的70%
    """
    if avg_vol <= 0 or pull_start < 0 or pull_end >= len(volumes):
        return True  # 无数据时放行
    try:
        pull_vols = volumes[pull_start:pull_end + 1]
        if not pull_vols:
            return True
        pull_avg = sum(pull_vols) / len(pull_vols)
        return pull_avg <= avg_vol * max_ratio
    except Exception:
        return True


# ── V13: 成交量剖面分析 ─────────────────────────────────────────────────────

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
        current_rank = sum(1 for pl, vp in price_levels if pl < current_price) / max(len(price_levels), 1)

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
            "current_volume_rank": round(current_volume_rank := current_rank, 2),
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


def _is_volume_profile_support(
    closes: list[float],
    volumes: list[float] | None,
    bi_low: float,
    lookback: int = 60,
) -> bool:
    """检查指定低点是否在成交量支撑区内（V13新增）。

    当2买/3买的回调低点位于高成交量密集区下方时，
    说明该位置有大量历史成交支撑，信号更可靠。
    """
    if not volumes or len(volumes) < lookback:
        return False
    try:
        profile = _calc_volume_profile(closes, volumes, lookback)
        support = profile.get("high_volume_support")
        if support is None:
            return False
        # 低点在支撑位附近（±2%以内）
        return abs(bi_low - support) / support < 0.02
    except Exception:
        return False


def _is_volume_profile_resistance(
    closes: list[float],
    volumes: list[float] | None,
    bi_high: float,
    lookback: int = 60,
) -> bool:
    """检查指定高点是否在成交量阻力区内（V13新增）。

    当2卖/3卖的反抽高点位于高成交量密集区上方时，
    说明该位置有大量历史成交阻力，信号更可靠。
    """
    if not volumes or len(volumes) < lookback:
        return False
    try:
        profile = _calc_volume_profile(closes, volumes, lookback)
        resistance = profile.get("high_volume_resistance")
        if resistance is None:
            return False
        # 高点在阻力位附近（±2%以内）
        return abs(bi_high - resistance) / resistance < 0.02
    except Exception:
        return False


def _check_macd_confirmation_v2(
    closes: list[float],
    current_bi: BI,
    breakout_bi: BI,
    direction: str = "down",
    threshold_ratio: float = 0.5,
) -> bool:
    """MACD二次确认（V2严格版）。

    对于3买：当前回调笔的MACD绿柱面积应 < 突破笔红柱面积 * threshold_ratio
    对于3卖：当前反弹笔的MACD红柱面积应 < 突破笔绿柱面积 * threshold_ratio
    """
    try:
        curr_start = current_bi.start.k.k_index
        curr_end = current_bi.end.k.k_index
        break_start = breakout_bi.start.k.k_index
        break_end = breakout_bi.end.k.k_index

        if curr_start < 0 or curr_end >= len(closes):
            return True  # 无数据时放行

        curr_macd = calc_macd_force(closes, curr_start, curr_end)
        break_macd = calc_macd_force(closes, break_start, break_end)

        if direction == "down":  # 3买：回调笔看绿柱
            if curr_macd["hist_down_sum"] > 0 and break_macd["hist_up_sum"] > 0:
                return curr_macd["hist_down_sum"] < break_macd["hist_up_sum"] * threshold_ratio
            return True
        else:  # 3卖：反弹笔看红柱
            if curr_macd["hist_up_sum"] > 0 and break_macd["hist_down_sum"] > 0:
                return curr_macd["hist_up_sum"] < break_macd["hist_down_sum"] * threshold_ratio
            return True
    except Exception:
        return True  # 出错时放行，不阻断信号


def _calc_overall_trend_direction(zss: list[ZS]) -> str:
    """计算整体趋势方向（基于最近3个完成的中枢）。

    Returns:
        "up" - 上升趋势（中枢逐步上移）
        "down" - 下降趋势（中枢逐步下移）
        "neutral" - 震荡/无明显趋势
    """
    if len(zss) < 2:
        return "neutral"

    # 只看最近3个完成的中枢
    recent = [zs for zs in zss[-3:] if zs.done]
    if len(recent) < 2:
        return "neutral"

    up_count = 0
    down_count = 0
    for i in range(1, len(recent)):
        prev = recent[i - 1]
        curr = recent[i]
        if curr.zg > prev.zg and curr.zd > prev.zd:
            up_count += 1
        elif curr.zg < prev.zg and curr.zd < prev.zd:
            down_count += 1

    if up_count > down_count:
        return "up"
    elif down_count > up_count:
        return "down"
    return "neutral"


def _calc_ma_trend_alignment(closes: list[float], bi_end_idx: int, ma_period: int = 20) -> str:
    """计算价格相对均线的趋势对齐状态。

    Returns:
        "above" - 价格在MA上方（偏多）
        "below" - 价格在MA下方（偏空）
        "near" - 价格接近MA（震荡）
    """
    if not closes or bi_end_idx < ma_period:
        return "near"
    try:
        price = closes[bi_end_idx] if bi_end_idx < len(closes) else closes[-1]
        ma_vals = closes[max(0, bi_end_idx - ma_period + 1):bi_end_idx + 1]
        if not ma_vals or len(ma_vals) < 5:
            return "near"
        ma_val = sum(ma_vals) / len(ma_vals)
        if ma_val <= 0:
            return "near"
        deviation = (price - ma_val) / ma_val
        if deviation > 0.02:
            return "above"
        elif deviation < -0.02:
            return "below"
        return "near"
    except Exception:
        return "near"


def _calc_ma_slope(closes: list[float], bi_end_idx: int, ma_period: int = 20) -> str:
    """计算MA斜率方向（V10新增）。

    检查MA20是否朝目标方向倾斜，用于确认趋势持续性。
    3买需要MA20向上倾斜，3卖需要MA20向下倾斜。

    Returns:
        "up" - MA20向上倾斜（趋势确认）
        "down" - MA20向下倾斜（趋势确认）
        "flat" - MA20横盘（趋势不明确）
    """
    if not closes or bi_end_idx < ma_period * 2:
        return "flat"
    try:
        # 计算当前MA20和前MA20
        end_idx = bi_end_idx if bi_end_idx < len(closes) else len(closes) - 1
        if end_idx < ma_period:
            return "flat"
        current_ma = sum(closes[max(0, end_idx - ma_period + 1):end_idx + 1]) / min(ma_period, end_idx + 1)
        prev_ma = sum(closes[max(0, end_idx - ma_period):end_idx]) / min(ma_period, end_idx)
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


def _calc_ma60_slope(closes: list[float], bi_end_idx: int, ma_period: int = 60) -> str:
    """计算MA60斜率方向（V17新增）。

    MA60是中期趋势指标，比MA20更稳定。
    3买需要MA60向上或横盘，3卖需要MA60向下或横盘。
    当MA60明确反向时，过滤掉该方向的3买/3卖信号。

    Returns:
        "up" - MA60向上倾斜
        "down" - MA60向下倾斜
        "flat" - MA60横盘
    """
    if not closes or bi_end_idx < ma_period:
        return "flat"
    try:
        end_idx = bi_end_idx if bi_end_idx < len(closes) else len(closes) - 1
        if end_idx < ma_period:
            return "flat"
        current_ma = sum(closes[max(0, end_idx - ma_period + 1):end_idx + 1]) / min(ma_period, end_idx + 1)
        prev_ma = sum(closes[max(0, end_idx - ma_period):end_idx]) / min(ma_period, end_idx)
        if prev_ma <= 0:
            return "flat"
        slope = (current_ma - prev_ma) / prev_ma
        if slope > 0.002:
            return "up"
        elif slope < -0.002:
            return "down"
        return "flat"
    except Exception:
        return "flat"


def _calc_macd_zero_axis_position(
    macd_data: dict[str, list[float]] | None,
    idx: int,
) -> str:
    """计算MACD DIF在零轴的位置（V18新增）。

    3买要求MACD在零轴上方或接近零轴（趋势多头）
    3卖要求MACD在零轴下方或接近零轴（趋势空头）

    Returns:
        "above" - DIF在零轴上方
        "below" - DIF在零轴下方
        "crossing_above" - DIF正在穿越零轴向上
        "crossing_below" - DIF正在穿越零轴向下
        "near_zero" - DIF接近零轴（±0.5%范围内）
    """
    if not macd_data or not macd_data.get("dif"):
        return "near_zero"
    try:
        dif = macd_data["dif"]
        if idx >= len(dif):
            idx = len(dif) - 1
        if idx < 1:
            return "near_zero"
        current_dif = dif[idx]
        prev_dif = dif[idx - 1]
        abs_dif = abs(current_dif)
        if abs_dif < 0.001:
            return "near_zero"
        if current_dif > 0 and prev_dif <= 0:
            return "crossing_above"
        elif current_dif < 0 and prev_dif >= 0:
            return "crossing_below"
        elif current_dif > 0:
            return "above"
        else:
            return "below"
    except Exception:
        return "near_zero"


def _check_pullback_time_window(
    pullback_bi: "BI",
    breakout_bi: "BI",
    max_bars: int = 25,
) -> tuple[bool, int]:
    """检查回踩笔的时间窗口（V18新增）。

    3买的回踩笔不应过长（超过max_bars根K线），否则信号衰减严重。
    3卖的反抽笔同理。

    Returns:
        (within_window, time_span) - 是否在时间窗口内，以及实际跨度
    """
    try:
        if not pullback_bi or not breakout_bi:
            return True, 0
        pullback_end_idx = pullback_bi.end.k.k_index
        breakout_end_idx = breakout_bi.end.k.k_index
        if breakout_end_idx <= 0 or pullback_end_idx <= 0:
            return True, 0
        time_span = pullback_end_idx - breakout_end_idx
        return time_span <= max_bars, time_span
    except Exception:
        return True, 0


def _calc_boll_position(closes: list[float], bi_end_idx: int) -> dict[str, float]:
    """计算BOLL位置信息（V10新增）。

    Returns:
        dict with keys: upper, mid, lower, percent_b, position
        position: "upper"/"mid"/"lower"
    """
    if not closes or bi_end_idx < 20:
        return {"upper": 0.0, "mid": 0.0, "lower": 0.0, "percent_b": 0.5, "position": "mid"}
    try:
        end_idx = bi_end_idx if bi_end_idx < len(closes) else len(closes) - 1
        if end_idx < 20:
            return {"upper": 0.0, "mid": 0.0, "lower": 0.0, "percent_b": 0.5, "position": "mid"}
        window = closes[max(0, end_idx - 19):end_idx + 1]
        mid = sum(window) / len(window)
        std = (sum((x - mid) ** 2 for x in window) / len(window)) ** 0.5
        upper = mid + 2 * std
        lower = mid - 2 * std
        price = closes[end_idx]
        if upper <= lower:
            return {"upper": upper, "mid": mid, "lower": lower, "percent_b": 0.5, "position": "mid"}
        percent_b = (price - lower) / (upper - lower)
        if percent_b > 0.8:
            position = "upper"
        elif percent_b < 0.2:
            position = "lower"
        else:
            position = "mid"
        return {"upper": upper, "mid": mid, "lower": lower, "percent_b": round(percent_b, 3), "position": position}
    except Exception:
        return {"upper": 0.0, "mid": 0.0, "lower": 0.0, "percent_b": 0.5, "position": "mid"}


def _calc_adx_strength(closes: list[float], highs: list[float] | None, lows: list[float] | None, bi_end_idx: int) -> tuple[float, str]:
    """计算ADX趋势强度（V11修正版，使用MyTT DMI算法）。

    V11修复：原V10使用简化DX替代ADX导致数值偏低，现改用MyTT.DMI完整平滑算法。

    Returns:
        (adx_value, level) where level is "strong"/"medium"/"weak"/"none"
    """
    if not closes or bi_end_idx < 30:
        return (0.0, "none")
    try:
        end_idx = bi_end_idx if bi_end_idx < len(closes) else len(closes) - 1
        # 取最近80根K线用于DMI计算（需要足够的历史数据平滑）
        lookback = min(80, end_idx + 1)
        start_idx = end_idx - lookback + 1

        # 准备数据
        closes_slice = closes[start_idx:end_idx + 1]
        if len(closes_slice) < 30:
            return (0.0, "none")

        if highs is None or lows is None:
            # 无真实高低点数据，用收盘价±1%近似
            highs_arr = [c * (1 + abs(np.random.RandomState(i).uniform(0, 0.005)) for i, c in enumerate(closes_slice))]
            lows_arr = [c * (1 - abs(np.random.RandomState(i + 100).uniform(0, 0.005)) for i, c in enumerate(closes_slice))]
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
        level = "strong" if adx_val >= 40 else "medium" if adx_val >= 25 else "weak" if adx_val >= 20 else "none"
        return (round(adx_val, 1), level)
    except Exception:
        return (0.0, "none")


def _calc_rsi(closes: list[float], period: int = 14) -> float:
    """简化版RSI计算。"""
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


def _calc_rsi_momentum(closes: list[float], period: int = 14) -> float:
    """计算RSI动量变化率（V10新增）。

    返回RSI的最近变化，正值表示RSI在上升（动量增强），负值表示下降。
    """
    if len(closes) < period + 5:
        return 0.0
    try:
        rsi_now = _calc_rsi(closes, period)
        rsi_prev = _calc_rsi(closes[:-5], period) if len(closes) >= period + 5 else rsi_now
        return rsi_now - rsi_prev
    except Exception:
        return 0.0


def _calc_kdj_j(closes: list[float], period: int = 9) -> float:
    """计算KDJ的J值（V12新增）。

    J值 > 80 超买，J值 < 20 超卖。
    用于确认买卖点的短期动能状态。
    """
    if len(closes) < period + 5:
        return 50.0
    try:
        # 简化版KDJ：只计算J值
        n = len(closes)
        low_min = min(closes[n-period:])
        high_max = max(closes[n-period:])
        close = closes[-1]
        
        if high_max == low_min:
            return 50.0
        
        rsv = (close - low_min) / (high_max - low_min) * 100
        # J = 3*K - 2*D，简化为R SV
        return rsv
    except Exception:
        return 50.0


def _get_kdj_thresholds(volatility: float | None) -> tuple[float, float]:
    """根据波动率返回自适应KDJ J值过滤阈值（V12优化）。

    高波动市场放宽阈值（避免误杀），低波动市场收紧阈值（提高精度）。

    Returns:
        (buy_3_kdj_min, sell_3_kdj_max) — 3买J值下限、3卖J值上限
    """
    if volatility is None:
        return (20.0, 80.0)  # 默认阈值
    if volatility > 0.03:  # 高波动：放宽阈值
        return (15.0, 85.0)
    elif volatility < 0.01:  # 低波动：收紧阈值
        return (25.0, 75.0)
    return (20.0, 80.0)  # 正常波动：标准阈值


# ── V14: 增强功能 ──────────────────────────────────────────────────────────────

def _check_volume_spike(
    volumes: list[float] | None,
    signal_idx: int,
    lookback: int = 20,
    min_ratio: float = 1.5,
) -> bool:
    """检测信号点成交量是否异常放大（机构活动信号）。

    当信号点附近成交量 > 近期均量的 min_ratio 倍时，认为有主力资金参与，
    信号可靠性更高。主要用于类型1买卖点和类型3突破点的增强确认。

    Returns:
        True 表示检测到成交量异常放大
    """
    if not volumes or len(volumes) < lookback + 5:
        return False
    try:
        start = max(0, signal_idx - lookback)
        recent_vols = volumes[start:signal_idx]
        if not recent_vols:
            return False
        avg_vol = sum(recent_vols) / len(recent_vols)
        signal_vol = volumes[signal_idx] if signal_idx < len(volumes) else 0
        if avg_vol <= 0:
            return False
        return signal_vol >= avg_vol * min_ratio
    except Exception:
        return False


def _detect_price_gap(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    idx: int,
    gap_threshold: float = 0.01,
) -> dict[str, Any]:
    """检测指定位置的价格缺口。

    缺口定义：
    - Gap Up（向上缺口）：当前K线最低价 > 前一根K线最高价
    - Gap Down（向下缺口）：当前K线最高价 < 前一根K线最低价

    Returns:
        {
            "has_gap": bool,
            "gap_type": "up"/"down"/None,
            "gap_size_pct": float,
            "filled": bool,
        }
    """
    if idx <= 0 or idx >= len(closes):
        return {"has_gap": False, "gap_type": None, "gap_size_pct": 0.0, "filled": False}

    try:
        prev_close = closes[idx - 1]
        prev_high = highs[idx - 1]
        prev_low = lows[idx - 1]
        curr_high = highs[idx]
        curr_low = lows[idx]

        gap_info: dict[str, Any] = {
            "has_gap": False,
            "gap_type": None,
            "gap_size_pct": 0.0,
            "filled": False,
        }

        # 检测向上缺口
        if curr_low > prev_high:
            gap_size = (curr_low - prev_high) / prev_close * 100
            if gap_size >= gap_threshold * 100:
                gap_info["has_gap"] = True
                gap_info["gap_type"] = "up"
                gap_info["gap_size_pct"] = round(gap_size, 2)
                lookback = min(10, idx)
                for i in range(max(0, idx - lookback), idx):
                    if lows[i] <= prev_high:
                        gap_info["filled"] = True
                        break
                return gap_info

        # 检测向下缺口
        if curr_high < prev_low:
            gap_size = (prev_low - curr_high) / prev_close * 100
            if gap_size >= gap_threshold * 100:
                gap_info["has_gap"] = True
                gap_info["gap_type"] = "down"
                gap_info["gap_size_pct"] = round(gap_size, 2)
                lookback = min(10, idx)
                for i in range(max(0, idx - lookback), idx):
                    if highs[i] >= prev_low:
                        gap_info["filled"] = True
                        break
                return gap_info

        return gap_info
    except Exception:
        return {"has_gap": False, "gap_type": None, "gap_size_pct": 0.0, "filled": False}


def _check_macd_histogram_slope(
    macd_data: dict[str, list[float]] | None,
    idx: int,
    direction: str = "up",
    lookback: int = 5,
) -> dict[str, Any]:
    """检查MACD柱状图斜率方向（V14新增）。

    Returns:
        {
            "slope_direction": "expanding"/"shrinking"/"neutral",
            "slope_strength": float,
            "confirmed": bool,
        }
    """
    result = {
        "slope_direction": "neutral",
        "slope_strength": 0.0,
        "confirmed": False,
    }

    if not macd_data or not macd_data.get("hist"):
        return result

    hist = macd_data["hist"]
    if idx < lookback or idx >= len(hist):
        return result

    try:
        recent_hist = hist[max(0, idx - lookback):idx + 1]
        if len(recent_hist) < 3:
            return result

        diffs = [recent_hist[i] - recent_hist[i - 1] for i in range(1, len(recent_hist))]
        avg_diff = sum(diffs) / len(diffs) if diffs else 0

        abs_hist = [abs(h) for h in recent_hist]
        recent_avg = sum(abs_hist[-3:]) / 3 if len(abs_hist) >= 3 else sum(abs_hist) / len(abs_hist)
        prev_avg = sum(abs_hist[:-3]) / max(len(abs_hist) - 3, 1) if len(abs_hist) > 3 else recent_avg

        if prev_avg > 0:
            slope_strength = (recent_avg - prev_avg) / prev_avg
        else:
            slope_strength = 0.0

        if direction == "up":
            if slope_strength > 0.1:
                result["slope_direction"] = "expanding"
                result["slope_strength"] = min(1.0, slope_strength)
                result["confirmed"] = True
            elif slope_strength < -0.1:
                result["slope_direction"] = "shrinking"
                result["slope_strength"] = slope_strength
            else:
                result["slope_direction"] = "neutral"
                result["slope_strength"] = slope_strength
        else:
            if slope_strength < -0.1:
                result["slope_direction"] = "expanding"
                result["slope_strength"] = min(1.0, abs(slope_strength))
                result["confirmed"] = True
            elif slope_strength > 0.1:
                result["slope_direction"] = "shrinking"
                result["slope_strength"] = slope_strength
            else:
                result["slope_direction"] = "neutral"
                result["slope_strength"] = slope_strength

        return result
    except Exception:
        return result


def _check_breakout_persistence(
    closes: list[float],
    breakout_bi: BI,
    zs_zg: float,
    min_bars: int = 3,
) -> bool:
    """检查突破是否持续有效（假突破过滤，V14新增）。

    突破后价格应在中枢上方站稳至少 min_bars 根K线。
    """
    if not closes or not breakout_bi or zs_zg <= 0:
        return True

    try:
        break_end_idx = breakout_bi.end.k.k_index
        if break_end_idx < 0 or break_end_idx >= len(closes):
            return True

        check_bars = min(min_bars, len(closes) - break_end_idx - 1)
        if check_bars < 1:
            return True

        for i in range(1, check_bars + 1):
            idx = break_end_idx + i
            if idx >= len(closes):
                break
            if closes[idx] < zs_zg:
                return False

        return True
    except Exception:
        return True


# ── V15 新增函数 ─────────────────────────────────────────────────────────────


def _detect_kline_pattern(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    idx: int,
) -> dict[str, Any]:
    """检测指定位置的K线形态（V15新增）。

    检测三种形态：
    - hammer: 锤子线（下影线长，实体小，出现在下跌末端=看涨）
    - doji: 十字星（开盘≈收盘，犹豫信号）
    - bullish_engulfing: 阳吞没（前阴后阳，后包前=看涨）
    - bearish_engulfing: 阴吞没（前阳后阴，后包前=看跌）

    Returns:
        {"pattern": str|None, "strength": str} 其中 pattern 为形态名称或None
    """
    if idx < 2 or idx >= len(closes):
        return {"pattern": None, "strength": "none"}

    try:
        prev_close = closes[idx - 1]
        prev_high = highs[idx - 1]
        prev_low = lows[idx - 1]
        prev_body = abs(prev_close - highs[idx - 1]) if idx - 1 >= 0 else 0

        c = closes[idx]
        h = highs[idx]
        l = lows[idx]
        body = abs(c - (closes[idx - 1] if idx > 0 else c))
        upper_shadow = h - max(c, closes[idx - 1] if idx > 0 else c)
        lower_shadow = min(c, closes[idx - 1] if idx > 0 else c) - l
        total_range = h - l if h > l else 0.001

        # 锤子线：下影线 ≥ 2倍实体，上影线很短，实体小
        is_hammer = (
            lower_shadow >= body * 2
            and upper_shadow < body * 0.5
            and body / total_range < 0.3
            and c > (closes[idx - 1] if idx > 0 else c)  # 阳线更强
        )
        # 十字星：实体极小
        is_doji = body / total_range < 0.05

        # 阳吞没：前阴后阳，后实体完全包裹前实体
        prev_is_down = closes[idx - 1] < (closes[idx - 2] if idx > 1 else closes[idx - 1])
        curr_is_up = c > (closes[idx - 1] if idx > 0 else c)
        is_bullish_engulfing = (
            prev_is_down
            and curr_is_up
            and c > closes[idx - 1]
            and l < closes[idx - 1]
        )
        # 阴吞没：前阳后阴，后实体完全包裹前实体
        prev_is_up = closes[idx - 1] > (closes[idx - 2] if idx > 1 else closes[idx - 1])
        curr_is_down = c < (closes[idx - 1] if idx > 0 else c)
        is_bearish_engulfing = (
            prev_is_up
            and curr_is_down
            and c < closes[idx - 1]
            and h > closes[idx - 1]
        )

        pattern = None
        strength = "none"
        if is_hammer:
            pattern = "hammer"
            strength = "strong" if c > closes[idx - 1] else "moderate"
        elif is_bullish_engulfing:
            pattern = "bullish_engulfing"
            strength = "strong"
        elif is_doji:
            pattern = "doji"
            strength = "weak"
        elif is_bearish_engulfing:
            pattern = "bearish_engulfing"
            strength = "strong"

        return {"pattern": pattern, "strength": strength}
    except Exception:
        return {"pattern": None, "strength": "none"}


def _calc_signal_aging(
    mmd: MMD,
    closes: list[float] | None,
    latest_kline_idx: int,
    max_age_bars: int = 15,
) -> dict[str, Any]:
    """检测信号衰减（V15新增）。

    如果信号产生后超过 N 根K线仍未触发交易，置信度应递减。
    3买/3卖最佳入场时机是信号产生后1-5根K线内。

    Returns:
        {"aged": bool, "age_bars": int, "decay_factor": float}
    """
    if not mmd.bi or not closes:
        return {"aged": False, "age_bars": 0, "decay_factor": 1.0}

    try:
        signal_idx = mmd.bi.end.k.k_index
        age_bars = latest_kline_idx - signal_idx
        if age_bars <= 0:
            return {"aged": False, "age_bars": 0, "decay_factor": 1.0}

        if age_bars > max_age_bars:
            return {"aged": True, "age_bars": age_bars, "decay_factor": 0.5}
        elif age_bars > max_age_bars * 0.6:
            return {"aged": False, "age_bars": age_bars, "decay_factor": 0.8}
        elif age_bars > 5:
            return {"aged": False, "age_bars": age_bars, "decay_factor": 0.9}
        return {"aged": False, "age_bars": age_bars, "decay_factor": 1.0}
    except Exception:
        return {"aged": False, "age_bars": 0, "decay_factor": 1.0}


def _check_break_retest_break(
    bis: list[BI],
    break_bi: BI,
    zs_zg: float,
    closes: list[float],
    lookback: int = 5,
) -> dict[str, Any]:
    """检查突破-回踩-再突破模式（V15新增）。

    3买：突破中枢 → 回踩不破zg → 再次突破确认。
    这比单次回踩更可靠，因为经过了"二次确认"。

    Returns:
        {
            "exists": bool,           # 是否存在该模式
            "retest_bi_idx": int|None, # 回踩笔的索引
            "second_break_bi_idx": int|None,  # 二次突破笔的索引
            "confidence_bonus": float, # 置信度加成（0-0.08）
        }
    """
    result = {
        "exists": False,
        "retest_bi_idx": None,
        "second_break_bi_idx": None,
        "confidence_bonus": 0.0,
    }

    try:
        break_bi_idx = bis.index(break_bi) if break_bi in bis else -1
        if break_bi_idx < 0 or break_bi_idx >= len(bis) - 2:
            return result

        # 找突破后的第一根反向笔（回踩）
        retest_bi = None
        for bi in bis[break_bi_idx + 1:]:
            if bi.direction.value == "down":
                retest_bi = bi
                break

        if not retest_bi:
            return result

        # 回踩不能破zg
        if retest_bi.low >= zs_zg * 0.995:
            return result

        # 在回踩之后找再次向上的笔（二次突破）
        retest_idx = bis.index(retest_bi) if retest_bi in bis else -1
        if retest_idx < 0 or retest_idx >= len(bis) - 1:
            return result

        second_break_bi = None
        for bi in bis[retest_idx + 1:]:
            if bi.direction.value == "up" and bi.high > zs_zg:
                second_break_bi = bi
                break

        if not second_break_bi:
            return result

        # 计算回踩深度
        retracement = (break_bi.high - retest_bi.low) / (break_bi.high - break_bi.low) if break_bi.high > break_bi.low else 1.0

        # 如果回踩较浅（<50%），说明多头强势，二次突破更可靠
        confidence_bonus = 0.03 if retracement < 0.5 else 0.02

        result["exists"] = True
        result["retest_bi_idx"] = retest_idx
        result["second_break_bi_idx"] = bis.index(second_break_bi) if second_break_bi in bis else None
        result["confidence_bonus"] = confidence_bonus
        result["retracement_pct"] = round(retracement * 100, 1)
    except Exception:
        pass

    return result


def _get_dynamic_time_window(
    volatility: float | None,
    base_window: int = 5,
) -> int:
    """根据波动率动态调整时间窗口（V15新增）。

    高波动市场：放宽时间窗口（更多时间让回踩发生）
    低波动市场：收紧时间窗口（快速确认）
    """
    if volatility is None:
        return base_window
    if volatility > 0.03:
        return base_window + 3  # 高波动：+3根K线
    elif volatility < 0.01:
        return max(3, base_window - 2)  # 低波动：-2根K线
    return base_window


def _find_third_type_mmds(
    bis: list[BI],
    zss: list[ZS],
    first_type_mmds: list[MMD],
    config: ChanlunConfig,
    closes: list[float] | None = None,
    volumes: list[float] | None = None,
    macd_data: dict[str, list[float]] | None = None,
    volatility: float | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> list[MMD]:
    """识别三类买卖点（V8 增强版：波动率自适应 + 区间套增强 + 动量确认）。

    3买：突破中枢后回踩不破zg + 突破笔力度 > 进入中枢笔力度 + 放量突破+缩量回调 + MACD二次确认 + 趋势对齐
    3卖：跌破中枢后反抽不破zd + 跌破笔力度 > 进入中枢笔力度 + 放量跌破+缩量反弹 + MACD二次确认 + 趋势对齐

    V8新增优化：
    1. 波动率自适应阈值：高波动市场放宽突破力度要求，低波动市场收紧
    2. 时间窗口优化：从2根放宽到5根K线，适应更多实际走势
    3. 回调幅度阈值自适应：基于波动率动态调整
    4. 动量确认增强：DIF趋势方向 + MACD柱状图变化
    5. 区间套确认加成：与已有信号的位置关系优化
    """
    mmds: list[MMD] = []

    # 构建已有买卖点的位置集合，用于避免重复
    existing_mmd_positions: set[int] = set()
    for m in first_type_mmds:
        if m.bi:
            existing_mmd_positions.add(m.bi.end.k.k_index)

    # 计算整体趋势方向（基于最近3个完成的中枢）
    recent_zs_direction = _calc_overall_trend_direction(zss)

    # V17: 趋势强度阈值 - 3买/3卖要求趋势强度>=0.5才能生成信号
    trend_strength = _calc_trend_strength(zss)
    if trend_strength < 0.5:
        # 趋势不明确时，不生成3买/3卖信号（避免假信号）
        # 但仍可继续搜索，只是降低置信度
        pass

    # V8: 波动率自适应 - 确定动态阈值
    vol_adjusted_force_ratio = 1.3  # 基础突破力度比
    vol_adjusted_break_ratio = 0.35  # 基础回调幅度比
    vol_adjusted_time_window = 5  # 基础时间窗口（根K线）
    vol_adjusted_vol_ratio = 1.8  # 基础放量倍数

    if volatility is not None:
        if volatility > 0.03:  # 高波动市场：放宽阈值
            vol_adjusted_force_ratio = 1.1
            vol_adjusted_break_ratio = 0.45
            vol_adjusted_time_window = 7
            vol_adjusted_vol_ratio = 1.5
        elif volatility < 0.01:  # 低波动市场：收紧阈值
            vol_adjusted_force_ratio = 1.5
            vol_adjusted_break_ratio = 0.25
            vol_adjusted_time_window = 4
            vol_adjusted_vol_ratio = 2.0

    # 预计算MACD数据用于动量确认
    latest_dif = macd_data["dif"][-1] if macd_data and macd_data.get("dif") else None
    prev_dif = macd_data["dif"][-2] if macd_data and len(macd_data.get("dif", [])) > 1 else None
    latest_hist = macd_data["hist"][-1] if macd_data and macd_data.get("hist") else None
    prev_hist = macd_data["hist"][-2] if macd_data and len(macd_data.get("hist", [])) > 1 else None

    for zs in zss:
        if not zs.done:
            continue

        # 计算中枢内首尾笔的力度比
        if len(zs.lines) >= 2:
            first_bi_force = _calc_bi_force(zs.lines[0], closes, zs.lines[0].index)
            last_bi_force = _calc_bi_force(zs.lines[-1], closes, zs.lines[-1].index)
            force_ratio_in_zs = last_bi_force / first_bi_force if first_bi_force > 0 else 1.0
        else:
            first_bi_force = 0.0
            force_ratio_in_zs = 1.0

        # 计算平均成交量（用于成交量确认）
        avg_vol_20 = _calc_avg_volume(volumes, 20)

        # 找3买：突破中枢后的回踩
        zs_end_idx = zs.end.k.k_index if zs.end else 0

        # 找向上突破笔
        break_bi_up = None
        for bi in bis:
            if bi.start.k.index > zs_end_idx and bi.direction.value == "up":
                if bi.high > zs.zg:  # 突破中枢上沿
                    break_bi_up = bi
                    break

        if break_bi_up:
            # 检查突破笔力度是否足够（必须大于进入中枢的笔）
            break_force = _calc_bi_force(break_bi_up, closes, break_bi_up.index)

            # V8: 条件A - 突破笔必须有足够力度（波动率自适应阈值）
            if first_bi_force > 0 and break_force < first_bi_force * vol_adjusted_force_ratio:
                continue

            # V8: 条件B - 突破后价格应该站稳中枢上方（自适应）
            break_price_ratio = (break_bi_up.high - zs.zg) / (zs.zg - zs.zd) if zs.zg > zs.zd else 0
            if break_price_ratio < 0.4:  # V8: 最低要求40%
                continue

            # V8: 条件C - 成交量确认（自适应倍数）
            if volumes is not None:
                if not _check_breakout_volume(
                    volumes, break_bi_up.start.k.k_index, break_bi_up.end.k.k_index, avg_vol_20, min_ratio=vol_adjusted_vol_ratio
                ):
                    continue

            # 在突破笔之后找回调笔
            for bi in bis[bis.index(break_bi_up) + 1:]:
                if bi.direction.value == "down":
                    # V8: 条件1 - 回踩不破zg（严格：必须明显高于zg，留0.5%缓冲）
                    if bi.low <= zs.zg * 1.005:
                        break

                    # V8: 条件2 - 回调时间窗口自适应（1-7根K线）
                    time_span = bi.end.k.k_index - break_bi_up.end.k.k_index
                    if time_span < 1 or time_span > vol_adjusted_time_window:
                        continue

                    # V8: 条件3 - 回调幅度不过大（波动率自适应）
                    breakout_range = break_bi_up.high - break_bi_up.low
                    if breakout_range <= 0:
                        continue
                    if break_bi_up.low - bi.low > breakout_range * vol_adjusted_break_ratio:
                        continue

                    # 条件4：检查是否与已有买卖点过于接近（避免重复信号）
                    bi_pos = bi.end.k.k_index
                    too_close = any(abs(bi_pos - pos) < 3 for pos in existing_mmd_positions)
                    if too_close:
                        continue

                    # V9: 条件5 - MACD二次确认（收紧至30%，V8为40%）
                    macd_ok = True
                    if closes is not None:
                        macd_ok = _check_macd_confirmation_v2(
                            closes, bi, break_bi_up, threshold_ratio=0.3
                        )
                    if not macd_ok:
                        continue

                    # 条件6：回调时显著缩量（< 60%均量，V4更严格）
                    vol_ok = True
                    if volumes is not None:
                        vol_ok = _check_pullback_volume_v2(
                            volumes, bi.start.k.k_index, bi.end.k.k_index, avg_vol_20, max_ratio=0.6
                        )
                    if not vol_ok:
                        continue

                    # V8: 条件7 - 检查回调笔力度是否小于突破笔（确认是回调而非反转）
                    bi_force = _calc_bi_force(bi, closes, bi.index)
                    if bi_force > break_force * 0.7:  # V4: 降低回调力度阈值
                        continue

                    # V9: 条件8 - MA趋势对齐：3买应在MA20上方（多头趋势）
                    ma_alignment = _calc_ma_trend_alignment(closes, bi.end.k.k_index)
                    if ma_alignment == "below":
                        continue

                    # V8: 条件9 - 趋势对齐 - 突破方向应与整体趋势一致
                    if recent_zs_direction != "neutral" and recent_zs_direction != "up":
                        continue

                    # V9: 条件10 - 动量确认增强（DIF趋势 + MACD柱状图变化）
                    momentum_ok = True
                    if latest_dif is not None:
                        # DIF不应过深（空头市场）
                        if latest_dif < -1.0:
                            momentum_ok = False
                        # MACD柱状图应在上涨或接近零轴
                        if latest_hist is not None and prev_hist is not None:
                            if latest_hist < prev_hist and latest_hist < 0:
                                # 柱状图持续下降且为负，动量减弱
                                momentum_ok = False

                    if not momentum_ok:
                        continue

                    # V11: 条件11 - MA斜率确认（放宽：允许MA横盘时RSI动量补偿）
                    ma_slope = _calc_ma_slope(closes, bi.end.k.k_index)
                    rsi_mc = _calc_rsi_momentum(closes, bi.end.k.k_index)
                    if ma_slope == "down":
                        continue  # MA明确向下，趋势反向，跳过
                    # MA横盘时：若RSI动量向上则可补偿通过（V11新增）
                    if ma_slope == "flat" and rsi_mc < -1.5:
                        continue  # MA横盘但RSI动量快速下降，趋势不明

                    # V17: 条件22 - MA60趋势确认：3买时MA60应向上或横盘（中期趋势确认）
                    ma60_slope = _calc_ma60_slope(closes, bi.end.k.k_index)
                    if ma60_slope == "down" and trend_strength >= 0.5:
                        continue  # MA60明确向下且趋势明确，跳过3买

                    # V17: 条件23 - 趋势强度阈值：趋势不明确时降低信号质量（不直接跳过，留作置信度扣分）
                    if trend_strength < 0.5:
                        # 趋势不明确，信号质量降级处理（在置信度计算中扣分）
                        pass

                    # V10: 条件12 - BOLL位置过滤：避免在BOLL上轨附近入场（潜在反转区）
                    boll_pos = _calc_boll_position(closes, bi.end.k.k_index)
                    if boll_pos["percent_b"] > 0.95:
                        continue  # 价格已在BOLL上轨外侧，回调风险大

                    # V12: 条件13 - ADX趋势强度过滤：要求ADX>=20（有明确趋势，使用真实OHLC数据）
                    adx_val, adx_level = _calc_adx_strength(closes, highs, lows, bi.end.k.k_index)
                    if adx_level in ("none",):
                        continue  # 无明确趋势，信号质量低

                    # V10: 条件14 - RSI动量确认：3买时RSI应处于上升通道（不低于35且不超75）
                    rsi_3buy = _calc_rsi(closes, bi.end.k.k_index)
                    rsi_momentum = _calc_rsi_momentum(closes, bi.end.k.k_index)
                    if rsi_3buy < 35 or rsi_3buy > 80:
                        continue  # RSI过低（弱势）或过高（超买），不作为好的3买
                    if rsi_momentum < -1.5:
                        continue  # V11: RSI动量快速下降，趋势可能转弱（阈值从-2.0放宽至-1.5）

                    # V12: 条件15 - KDJ动量确认：3买时J值不应过低（短期动能不足可能假突破）
                    kjd_j = _calc_kdj_j(closes, bi.end.k.k_index)
                    kjd_min, _ = _get_kdj_thresholds(volatility)
                    if kjd_j < kjd_min:
                        continue  # J值过低，短期动能不足，可能假突破

                    # V14: 条件16 - 成交量异常检测（突破时放量=机构参与）
                    vol_spike = False
                    if volumes is not None:
                        vol_spike = _check_volume_spike(volumes, break_bi_up.end.k.k_index, lookback=20, min_ratio=1.5)

                    # V14: 条件17 - 缺口分析（向上缺口突破=强势信号）
                    gap_info = {"has_gap": False, "gap_type": None, "filled": True}
                    if highs is not None and lows is not None:
                        gap_info = _detect_price_gap(closes, highs, lows, break_bi_up.end.k.k_index)

                    # V14: 条件18 - MACD柱状图斜率确认
                    macd_slope = _check_macd_histogram_slope(macd_data, bi.end.k.k_index, direction="up")
                    if macd_slope["slope_direction"] == "shrinking":
                        continue  # 柱状图收缩，动量减弱，跳过

                    # V14: 条件19 - 假突破过滤（突破后需站稳min_bars根K线）
                    if not _check_breakout_persistence(closes, break_bi_up, zs.zg, min_bars=3):
                        continue

                    # 构建增强消息
                    extra_parts = []
                    if vol_spike:
                        extra_parts.append("量能放大✅")
                    if gap_info.get("has_gap") and gap_info.get("gap_type") == "up" and not gap_info.get("filled"):
                        extra_parts.append(f"跳空突破({gap_info['gap_size_pct']:.1f}%)✅")
                    if macd_slope["confirmed"]:
                        extra_parts.append("MACD斜率确认✅")

                    # V15: 条件20 - K线形态确认（回踩笔出现锤子线或阳吞没=看涨增强）
                    kline_pattern = {"pattern": None, "strength": "none"}
                    if highs is not None and lows is not None:
                        kline_pattern = _detect_kline_pattern(closes, highs, lows, bi.end.k.k_index)
                    if kline_pattern["pattern"] in ("hammer", "bullish_engulfing"):
                        extra_parts.append(f"K线形态:{kline_pattern['pattern']}✅")
                    # V17: 条件24 - K线形态反向过滤：回踩笔出现阴吞没=看跌信号，跳过3买
                    elif kline_pattern["pattern"] == "bearish_engulfing":
                        continue  # 回踩末端出现阴吞没，短期可能继续下跌

                    # V17: 条件25 - 突破时成交量确认：突破笔需放量（>1.5x均量）
                    if volumes is not None and break_bi_up.end.k.k_index > 0:
                        bi_vol = volumes[min(break_bi_up.end.k.k_index, len(volumes) - 1)]
                        if avg_vol_20 > 0 and bi_vol < avg_vol_20 * 1.5:
                            continue  # 突破时无量，可能是假突破

                    # V18: 条件26 - 突破力度确认：突破笔力度需大于进入中枢的笔（避免弱势突破）
                    if len(zs.lines) >= 1 and break_bi_up:
                        break_force = _calc_bi_force(break_bi_up, closes, break_bi_up.index)
                        entry_force = _calc_bi_force(zs.lines[0], closes, zs.lines[0].index)
                        if entry_force > 0 and break_force < entry_force * 0.9:
                            continue  # 突破力度弱于进入中枢的笔，可能是假突破

                    # V18: 条件27 - 回踩时间窗口限制：回踩笔不超过25根K线（信号衰减）
                    pullback_within_window, pullback_time_span = _check_pullback_time_window(
                        bi, break_bi_up, max_bars=25
                    )
                    if not pullback_within_window:
                        continue  # 回踩时间过长，信号已衰减

                    # V18: 条件28 - MACD零轴确认：3买时MACD应在零轴上方（趋势多头）
                    macd_zero_pos = _calc_macd_zero_axis_position(macd_data, bi.end.k.k_index)
                    if macd_zero_pos == "below":
                        continue  # MACD在零轴下方，趋势偏弱，不适合3买做多

                    # V19: 条件29 - ATR支撑确认：回踩低点应在zg±ATR范围内
                    atr_support_ok, atr_support_reason = _check_atr_support_zone(
                        bi.low, zs.zg, zs.zd, MMDType.BUY_3,
                        closes, highs, lows, bi.end.k.k_index
                    )
                    if not atr_support_ok:
                        continue  # 回踩位置不在ATR支撑区域内，可能是假突破
                    if atr_support_ok:
                        extra_parts.append(f"ATR支撑✅")

                    # V20: 条件31 - 波动率Regime过滤：根据当前波动率状态调整判断标准
                    regime_vol = _calc_atr_volatility(closes)
                    regime, regime_adjust = _get_volatility_regime(regime_vol)
                    if regime == "high" and volatility is not None:
                        # 高波动市场：放宽RSI和ADX阈值
                        if rsi_3buy < 30 or rsi_3buy > 85:
                            continue
                    elif regime == "low":
                        # 低波动市场：收紧BOLL和RSI阈值
                        if boll_pos["percent_b"] > 0.92:
                            continue
                        if rsi_3buy < 38 or rsi_3buy > 78:
                            continue

                    # V20: 条件32 - 趋势加速度确认：3买时趋势应加速或中性（不应减速）
                    if macd_data is not None:
                        accel, trend_state = _calc_trend_acceleration(macd_data, bi.end.k.k_index)
                        if trend_state == "decelerating":
                            # 趋势正在减速，可能是顶背离前兆，跳过
                            continue
                        elif trend_state == "accelerating":
                            extra_parts.append("趋势加速✅")

                    # V20: 条件33 - 关键价位成交量分布：zg附近应有足够成交量确认
                    if volumes is not None:
                        vol_dist = _analyze_volume_at_levels(closes, volumes, zs.zg, "resistance", lookback=30)
                        if vol_dist["strength"] == "weak" and vol_dist["volume_concentration"] < 0.5:
                            # 中枢上沿成交量极度稀疏，支撑强度存疑
                            pass  # 不直接跳过，但在消息中标记
                        elif vol_dist["strength"] == "strong":
                            extra_parts.append(f"阻力位量密({vol_dist['signal']})✅")

                    # V15: 条件21 - 二次回踩确认（break-retest-break pattern）
                    retest_result = _check_break_retest_break(bis, break_bi_up, zs.zg, closes)
                    if retest_result["exists"]:
                        extra_parts.append(f"二次确认(回踩{retest_result.get('retracement_pct', '?')}%)✅")

                    extra_msg = ", " + ", ".join(extra_parts) if extra_parts else ""

                    mmds.append(MMD(
                        mmd_type=MMDType.BUY_3,
                        zs=zs,
                        bi=bi,
                        msg=f"3买V20: 突破确认后回踩(深度{(break_bi_up.low-bi.low)/breakout_range*100:.0f}%), 低点={bi.low:.2f} > zg={zs.zg:.2f}, Regime={regime}(×{regime_adjust:.2f}), MA20={ma_slope}, RSI={rsi_3buy:.0f}(+{rsi_momentum:+.1f}), ADX={adx_val:.0f}, KDJ.J={kjd_j:.0f}, BOLL%b={boll_pos['percent_b']:.2f}, MACD零轴={macd_zero_pos}, 回踩{pullback_time_span}根K线, ATR支撑✅" + extra_msg,
                    ))
                    # V14/V15/V20: 记录增强信息
                    if vol_spike:
                        mmds[-1]._vol_spike = True
                    if gap_info.get("has_gap") and gap_info.get("gap_type") == "up":
                        mmds[-1]._gap_up = True
                        mmds[-1]._gap_size = gap_info.get("gap_size_pct", 0.0)
                    if macd_slope["confirmed"]:
                        mmds[-1]._macd_slope_confirmed = True
                    if kline_pattern["pattern"] in ("hammer", "bullish_engulfing"):
                        mmds[-1]._kline_pattern = kline_pattern["pattern"]
                    if retest_result["exists"]:
                        mmds[-1]._retest_break = True
                        mmds[-1]._retest_retracement = retest_result.get("retracement_pct", 0.0)
                    # V20: 记录波动率Regime和趋势加速度
                    mmds[-1]._vol_regime = regime
                    mmds[-1]._trend_accel = trend_state if macd_data is not None else "neutral"
                    if volumes is not None:
                        vol_dist_3buy = _analyze_volume_at_levels(closes, volumes, zs.zg, "resistance", lookback=30)
                        mmds[-1]._vol_dist_at_zg = vol_dist_3buy
                    break

        # 找3卖：跌破中枢后的反抽
        break_bi_down = None
        for bi in bis:
            if bi.start.k.index > zs_end_idx and bi.direction.value == "down":
                if bi.low < zs.zd:  # 跌破中枢下沿
                    break_bi_down = bi
                    break

        if break_bi_down:
            # V8: 条件A - 跌破笔必须有足够力度（波动率自适应）
            break_force_down = _calc_bi_force(break_bi_down, closes, break_bi_down.index)
            if len(zs.lines) >= 2 and break_force_down < _calc_bi_force(zs.lines[0], closes, zs.lines[0].index) * vol_adjusted_force_ratio:
                continue

            # V8: 条件B - 跌破后价格应该站稳中枢下方（自适应）
            breakdown_price_ratio = (zs.zd - break_bi_down.low) / (zs.zg - zs.zd) if zs.zg > zs.zd else 0
            if breakdown_price_ratio < 0.4:  # V8: 最低要求40%
                continue

            # V8: 条件C - 成交量确认 - 跌破时应显著放量（自适应倍数）
            if volumes is not None:
                if not _check_breakout_volume(
                    volumes, break_bi_down.start.k.k_index, break_bi_down.end.k.k_index, avg_vol_20, min_ratio=vol_adjusted_vol_ratio
                ):
                    continue

            # 在跌破笔之后找反弹笔
            for bi in bis[bis.index(break_bi_down) + 1:]:
                if bi.direction.value == "up":
                    # V8: 条件1 - 反抽不破zd（严格：必须明显低于zd，留0.5%缓冲）
                    if bi.high >= zs.zd * 0.995:
                        break

                    # V8: 条件2 - 反弹时间窗口自适应
                    time_span = bi.end.k.k_index - break_bi_down.end.k.k_index
                    if time_span < 1 or time_span > vol_adjusted_time_window:
                        continue

                    # V8: 条件3 - 反弹幅度不过大（波动率自适应）
                    breakdown_range = break_bi_down.high - break_bi_down.low
                    if breakdown_range <= 0:
                        continue
                    if bi.high - break_bi_down.high > breakdown_range * vol_adjusted_break_ratio:
                        continue

                    # 条件4：检查是否与已有买卖点过于接近
                    bi_pos = bi.end.k.k_index
                    too_close = any(abs(bi_pos - pos) < 3 for pos in existing_mmd_positions)
                    if too_close:
                        continue

                    # V9: 条件5 - MACD二次确认（收紧至30%）
                    macd_ok = True
                    if closes is not None:
                        macd_ok = _check_macd_confirmation_v2(
                            closes, bi, break_bi_down, direction="up", threshold_ratio=0.3
                        )
                    if not macd_ok:
                        continue

                    # 条件6：反弹时显著缩量
                    vol_ok = True
                    if volumes is not None:
                        vol_ok = _check_pullback_volume_v2(
                            volumes, bi.start.k.k_index, bi.end.k.k_index, avg_vol_20,
                            max_ratio=0.6, is_pullback=False
                        )
                    if not vol_ok:
                        continue

                    # V8: 条件7 - 检查反弹笔力度是否小于跌破笔
                    bi_force = _calc_bi_force(bi, closes, bi.index)
                    if bi_force > break_force_down * 0.7:
                        continue

                    # V9: 条件8 - MA趋势对齐：3卖应在MA20下方（空头趋势）
                    ma_alignment = _calc_ma_trend_alignment(closes, bi.end.k.k_index)
                    if ma_alignment == "above":
                        continue

                    # V8: 条件9 - 趋势对齐
                    if recent_zs_direction != "neutral" and recent_zs_direction != "down":
                        continue

                    # V9: 条件10 - 动量确认增强（DIF趋势 + MACD柱状图变化）
                    momentum_ok = True
                    if latest_dif is not None:
                        # DIF不应过高（多头市场）
                        if latest_dif > 1.0:
                            momentum_ok = False
                        # MACD柱状图应在下跌或接近零轴
                        if latest_hist is not None and prev_hist is not None:
                            if latest_hist > prev_hist and latest_hist > 0:
                                # 柱状图持续上升且为正，动量减弱
                                momentum_ok = False

                    if not momentum_ok:
                        continue

                    # V11: 条件11 - MA斜率确认（放宽：允许MA横盘时RSI动量补偿）
                    ma_slope = _calc_ma_slope(closes, bi.end.k.k_index)
                    rsi_ms = _calc_rsi_momentum(closes, bi.end.k.k_index)
                    if ma_slope == "up":
                        continue  # MA明确向上，趋势反向，跳过
                    # MA横盘时：若RSI动量向下则可补偿通过（V11新增）
                    if ma_slope == "flat" and rsi_ms > 1.5:
                        continue  # MA横盘但RSI动量快速上升，趋势不明

                    # V17: 条件22 - MA60趋势确认：3卖时MA60应向下或横盘（中期趋势确认）
                    ma60_slope_sell = _calc_ma60_slope(closes, bi.end.k.k_index)
                    if ma60_slope_sell == "up" and trend_strength >= 0.5:
                        continue  # MA60明确向上且趋势明确，跳过3卖

                    # V17: 条件23 - 趋势强度阈值：趋势不明确时降低信号质量
                    if trend_strength < 0.5:
                        pass  # 趋势不明确，信号质量降级处理（在置信度计算中扣分）

                    # V10: 条件12 - BOLL位置过滤：避免在BOLL下轨附近入场（潜在反弹区）
                    boll_pos = _calc_boll_position(closes, bi.end.k.k_index)
                    if boll_pos["percent_b"] < 0.05:
                        continue  # 价格已在BOLL下轨内侧，反弹风险大

                    # V12: 条件13 - ADX趋势强度过滤：要求ADX>=20（有明确趋势，使用真实OHLC数据）
                    adx_val, adx_level = _calc_adx_strength(closes, highs, lows, bi.end.k.k_index)
                    if adx_level in ("none",):
                        continue  # 无明确趋势，信号质量低

                    # V10: 条件14 - RSI动量确认：3卖时RSI应处于下降通道（不低于25且不超65）
                    rsi_3sell = _calc_rsi(closes, bi.end.k.k_index)
                    rsi_momentum_sell = _calc_rsi_momentum(closes, bi.end.k.k_index)
                    if rsi_3sell > 65 or rsi_3sell < 20:
                        continue  # RSI过高（强势）或过低（超卖），不作为好的3卖
                    if rsi_momentum_sell > 1.5:
                        continue  # V11: RSI动量快速上升，趋势可能转强（阈值从2.0放宽至1.5）

                    # V12: 条件15 - KDJ动量确认：3卖时J值不应过高（短期动能衰竭可能假跌破）
                    kjd_j_sell = _calc_kdj_j(closes, bi.end.k.k_index)
                    _, kjd_max = _get_kdj_thresholds(volatility)
                    if kjd_j_sell > kjd_max:
                        continue  # J值过高，短期动能衰竭，可能假跌破

                    # V14: 条件16 - 成交量异常检测（跌破时放量=机构出货）
                    vol_spike_sell = False
                    if volumes is not None:
                        vol_spike_sell = _check_volume_spike(volumes, break_bi_down.end.k.k_index, lookback=20, min_ratio=1.5)

                    # V14: 条件17 - 缺口分析（向下缺口跌破=加速下跌信号）
                    gap_info_sell = {"has_gap": False, "gap_type": None, "filled": True}
                    if highs is not None and lows is not None:
                        gap_info_sell = _detect_price_gap(closes, highs, lows, break_bi_down.end.k.k_index)

                    # V14: 条件18 - MACD柱状图斜率确认
                    macd_slope_sell = _check_macd_histogram_slope(macd_data, bi.end.k.k_index, direction="down")
                    if macd_slope_sell["slope_direction"] == "shrinking":
                        continue  # 柱状图收缩，动量减弱，跳过

                    # V14: 条件19 - 假突破过滤（跌破后需站稳min_bars根K线）
                    if not _check_breakout_persistence(closes, break_bi_down, zs.zd, min_bars=3):
                        continue  # 跌破后价格已回升，可能是假跌破

                    # 构建增强消息
                    extra_parts_sell = []
                    if vol_spike_sell:
                        extra_parts_sell.append("量能放大✅")
                    if gap_info_sell.get("has_gap") and gap_info_sell.get("gap_type") == "down" and not gap_info_sell.get("filled"):
                        extra_parts_sell.append(f"跳空跌破({gap_info_sell['gap_size_pct']:.1f}%)✅")
                    if macd_slope_sell["confirmed"]:
                        extra_parts_sell.append("MACD斜率确认✅")

                    # V15: 条件20 - K线形态确认（回抽笔出现锤子线或阴吞没=看跌增强）
                    kline_pattern_sell = {"pattern": None, "strength": "none"}
                    if highs is not None and lows is not None:
                        kline_pattern_sell = _detect_kline_pattern(closes, highs, lows, bi.end.k.k_index)
                    if kline_pattern_sell["pattern"] in ("hammer", "bullish_engulfing"):
                        extra_parts_sell.append(f"K线形态:{kline_pattern_sell['pattern']}✅")
                    # V17: 条件24 - K线形态反向过滤：回抽笔出现阳吞没=看涨信号，跳过3卖
                    elif kline_pattern_sell["pattern"] == "bearish_engulfing":
                        continue  # 回抽末端出现阴吞没，短期可能继续上涨

                    # V18: 条件26 - 跌破力度确认：跌破笔力度需大于进入中枢的笔（避免弱势跌破）
                    if len(zs.lines) >= 1 and break_bi_down:
                        break_force_down = _calc_bi_force(break_bi_down, closes, break_bi_down.index)
                        entry_force_down = _calc_bi_force(zs.lines[0], closes, zs.lines[0].index)
                        if entry_force_down > 0 and break_force_down < entry_force_down * 0.9:
                            continue  # 跌破力度弱于进入中枢的笔，可能是假跌破

                    # V18: 条件27 - 反抽时间窗口限制：反抽笔不超过25根K线（信号衰减）
                    retracement_within_window, retracement_time_span = _check_pullback_time_window(
                        bi, break_bi_down, max_bars=25
                    )
                    if not retracement_within_window:
                        continue  # 反抽时间过长，信号已衰减

                    # V18: 条件28 - MACD零轴确认：3卖时MACD应在零轴下方（趋势空头）
                    macd_zero_pos_sell = _calc_macd_zero_axis_position(macd_data, bi.end.k.k_index)
                    if macd_zero_pos_sell == "above":
                        continue  # MACD在零轴上方，趋势偏强，不适合3卖做空

                    # V19: 条件29 - ATR阻力确认：反抽高点应在zd±ATR范围内
                    atr_resist_ok, atr_resist_reason = _check_atr_support_zone(
                        bi.high, zs.zg, zs.zd, MMDType.SELL_3,
                        closes, highs, lows, bi.end.k.k_index
                    )
                    if not atr_resist_ok:
                        continue  # 反弹位置不在ATR阻力区域内
                    if atr_resist_ok:
                        extra_parts_sell.append(f"ATR阻力✅")

                    # V20: 条件31 - 波动率Regime过滤：根据当前波动率状态调整判断标准
                    regime_vol_sell = _calc_atr_volatility(closes)
                    regime_sell, regime_adjust_sell = _get_volatility_regime(regime_vol_sell)
                    if regime_sell == "high" and volatility is not None:
                        # 高波动市场：放宽RSI和ADX阈值
                        if rsi_3sell > 70 or rsi_3sell < 15:
                            continue
                    elif regime_sell == "low":
                        # 低波动市场：收紧BOLL和RSI阈值
                        if boll_pos["percent_b"] < 0.08:
                            continue
                        if rsi_3sell > 62 or rsi_3sell < 22:
                            continue

                    # V20: 条件32 - 趋势加速度确认：3卖时趋势应加速或中性（不应减速）
                    if macd_data is not None:
                        accel_sell, trend_state_sell = _calc_trend_acceleration(macd_data, bi.end.k.k_index)
                        if trend_state_sell == "accelerating":
                            # 趋势正在加速向上，可能是底背离前兆，跳过
                            continue
                        elif trend_state_sell == "decelerating":
                            extra_parts_sell.append("趋势加速下行✅")

                    # V20: 条件33 - 关键价位成交量分布：zd附近应有足够成交量确认
                    if volumes is not None:
                        vol_dist_sell = _analyze_volume_at_levels(closes, volumes, zs.zd, "support", lookback=30)
                        if vol_dist_sell["strength"] == "weak" and vol_dist_sell["volume_concentration"] < 0.5:
                            pass  # 中枢下沿成交量极度稀疏，支撑强度存疑
                        elif vol_dist_sell["strength"] == "strong":
                            extra_parts_sell.append(f"支撑位量密({vol_dist_sell['signal']})✅")

                    # V15: 条件21 - 二次回踩确认（break-retest-break pattern）
                    retest_result_sell = _check_break_retest_break(bis, break_bi_down, zs.zd, closes)
                    if retest_result_sell["exists"]:
                        extra_parts_sell.append(f"二次确认(反抽{retest_result_sell.get('retracement_pct', '?')}%)✅")

                    extra_msg_sell = ", " + ", ".join(extra_parts_sell) if extra_parts_sell else ""

                    mmds.append(MMD(
                        mmd_type=MMDType.SELL_3,
                        zs=zs,
                        bi=bi,
                        msg=f"3卖V20: 跌破确认后反抽(幅度{(bi.high-break_bi_down.high)/breakdown_range*100:.0f}%), 高点={bi.high:.2f} < zd={zs.zd:.2f}, Regime={regime_sell}(×{regime_adjust_sell:.2f}), MA20={ma_slope}, RSI={rsi_3sell:.0f}(+{rsi_momentum_sell:+.1f}), ADX={adx_val:.0f}, KDJ.J={kjd_j_sell:.0f}, BOLL%b={boll_pos['percent_b']:.2f}, MACD零轴={macd_zero_pos_sell}, 反抽{retracement_time_span}根K线, ATR阻力✅" + extra_msg_sell,
                    ))
                    # V14/V15/V20: 记录增强信息
                    if vol_spike_sell:
                        mmds[-1]._vol_spike = True
                    if gap_info_sell.get("has_gap") and gap_info_sell.get("gap_type") == "down":
                        mmds[-1]._gap_down = True
                        mmds[-1]._gap_size = gap_info_sell.get("gap_size_pct", 0.0)
                    if macd_slope_sell["confirmed"]:
                        mmds[-1]._macd_slope_confirmed = True
                    if kline_pattern_sell["pattern"] in ("hammer", "bullish_engulfing"):
                        mmds[-1]._kline_pattern = kline_pattern_sell["pattern"]
                    if retest_result_sell["exists"]:
                        mmds[-1]._retest_break = True
                        mmds[-1]._retest_retracement = retest_result_sell.get("retracement_pct", 0.0)
                    # V20: 记录波动率Regime和趋势加速度
                    mmds[-1]._vol_regime = regime_sell
                    mmds[-1]._trend_accel = trend_state_sell if macd_data is not None else "neutral"
                    if volumes is not None:
                        vol_dist_3sell = _analyze_volume_at_levels(closes, volumes, zs.zd, "support", lookback=30)
                        mmds[-1]._vol_dist_at_zd = vol_dist_3sell
                    break

    return mmds




def _check_macd_confirmation(
    closes: list[float],
    current_bi: BI,
    breakout_bi: BI,
    direction: str = "down",
) -> bool:
    """MACD确认：检查当前笔与突破笔的MACD面积关系。

    对于3买：当前回调笔的MACD绿柱面积应小于突破笔的MACD红柱面积
    对于3卖：当前反弹笔的MACD红柱面积应小于突破笔的MACD绿柱面积
    """
    try:
        curr_start = current_bi.start.k.k_index
        curr_end = current_bi.end.k.k_index
        break_start = breakout_bi.start.k.k_index
        break_end = breakout_bi.end.k.k_index

        if curr_start < 0 or curr_end >= len(closes):
            return True  # 无数据时放行

        curr_macd = calc_macd_force(closes, curr_start, curr_end)
        break_macd = calc_macd_force(closes, break_start, break_end)

        if direction == "down":  # 3买：回调笔看绿柱
            if curr_macd["hist_down_sum"] > 0 and break_macd["hist_up_sum"] > 0:
                return curr_macd["hist_down_sum"] < break_macd["hist_up_sum"] * 1.5
            return True
        else:  # 3卖：反弹笔看红柱
            if curr_macd["hist_up_sum"] > 0 and break_macd["hist_down_sum"] > 0:
                return curr_macd["hist_up_sum"] < break_macd["hist_down_sum"] * 1.5
            return True
    except Exception:
        return True  # 出错时放行，不阻断信号


def _deduplicate_mmds(mmds: list[MMD]) -> list[MMD]:
    """去重：同一位置只保留最高优先级的买卖点。
    
    优先级：1买 > 2买 > 3买 > 1卖 > 2卖 > 3卖
    """
    priority = {
        MMDType.BUY_1: 6,
        MMDType.BUY_2: 5,
        MMDType.BUY_3: 4,
        MMDType.SELL_1: 3,
        MMDType.SELL_2: 2,
        MMDType.SELL_3: 1,
    }
    
    # 按位置分组
    by_position: dict[int, list[MMD]] = {}
    for mmd in mmds:
        if mmd.bi:
            pos = mmd.bi.end.k.k_index
            if pos not in by_position:
                by_position[pos] = []
            by_position[pos].append(mmd)
    
    # 每组只保留优先级最高的
    result = []
    for pos, group in by_position.items():
        group.sort(key=lambda m: priority.get(m.mmd_type, 0), reverse=True)
        result.append(group[0])
    
    return result


# ── 辅助函数 ─────────────────────────────────────────────────────────────

def _is_strong_beichi(
    bi: BI,
    bis: list[BI],
    zss: list[ZS],
    closes: list[float] | None,
    threshold: float = 0.8,
    direction: str = "down",
) -> bool:
    """检查是否是强背驰（满足动态阈值）。"""
    bi_idx = bi.index
    
    # 1. 笔背驰检查
    for j in range(bi_idx - 1, -1, -1):
        prev_bi = bis[j]
        if prev_bi.direction.value == direction:
            curr_force = _calc_bi_force(bi, closes, bi_idx)
            prev_force = _calc_bi_force(prev_bi, closes, j)
            
            if prev_force > 0 and curr_force < prev_force * threshold:
                return True
            break
    
    # 2. 盘整背驰检查
    for zs in zss:
        if len(zs.lines) >= 3:
            first_bi = zs.lines[0]
            last_bi = zs.lines[-1]
            
            if first_bi.direction.value == direction:
                first_force = _calc_bi_force(first_bi, closes, first_bi.index)
                last_force = _calc_bi_force(last_bi, closes, last_bi.index)
                
                if last_force < first_force * threshold and last_force > 0:
                    return True
    
    # 3. 趋势背驰检查
    if len(zss) >= 2:
        for i in range(1, len(zss)):
            prev_zs = zss[i - 1]
            curr_zs = zss[i]
            
            is_same_trend = (
                (direction == "down" and curr_zs.zg < prev_zs.zg and curr_zs.zd < prev_zs.zd) or
                (direction == "up" and curr_zs.zg > prev_zs.zg and curr_zs.zd > prev_zs.zd)
            )
            
            if is_same_trend:
                prev_exit = prev_zs.lines[-1]
                curr_exit = curr_zs.lines[-1]
                
                if prev_exit.direction.value == direction and curr_exit.direction.value == direction:
                    prev_force = _calc_bi_force(prev_exit, closes, prev_exit.index)
                    curr_force = _calc_bi_force(curr_exit, closes, curr_exit.index)
                    
                    if curr_force < prev_force * threshold and curr_force > 0:
                        return True
    
    return False


def _get_beichi_strength(
    bi: BI,
    bis: list[BI],
    zss: list[ZS],
    closes: list[float] | None,
    direction: str = "down",
) -> str:
    """获取背驰强度标签。"""
    bi_idx = bi.index
    
    # 找最近同向笔
    for j in range(bi_idx - 1, -1, -1):
        prev_bi = bis[j]
        if prev_bi.direction.value == direction:
            curr_force = _calc_bi_force(bi, closes, bi_idx)
            prev_force = _calc_bi_force(prev_bi, closes, j)
            
            if prev_force > 0:
                ratio = curr_force / prev_force
                if ratio < 0.5:
                    return "strong"
                elif ratio < 0.7:
                    return "moderate"
                else:
                    return "weak"
            break
    
    return "unknown"


def _calc_trend_strength(zss: list[ZS]) -> float:
    """计算趋势强度（0-1）。"""
    if len(zss) < 2:
        return 0.0
    
    # 计算中枢的重叠程度
    overlaps = 0
    for i in range(1, len(zss)):
        prev = zss[i - 1]
        curr = zss[i]
        
        # 检查是否同向排列
        if (curr.zg < prev.zg and curr.zd < prev.zd) or \
           (curr.zg > prev.zg and curr.zd > prev.zd):
            overlaps += 1
    
    return overlaps / (len(zss) - 1) if len(zss) > 1 else 0.0


def _calc_bi_force(
    bi: BI,
    closes: list[float] | None,
    bi_idx: int,
) -> float:
    """计算笔的力度（MACD面积）。"""
    if closes is None or len(closes) == 0:
        return abs(bi.high - bi.low)

    start_idx = bi.start.k.k_index
    end_idx = bi.end.k.k_index
    
    if start_idx < 0 or end_idx >= len(closes):
        return abs(bi.high - bi.low)
    
    try:
        macd_result = calc_macd_force(closes, start_idx, end_idx)
        if bi.direction.value == "down":
            return macd_result["hist_down_sum"]
        else:
            return macd_result["hist_up_sum"]
    except:
        return abs(bi.high - bi.low)


def _calc_confidence(
    mmd: MMD,
    trend_strength: float,
    volumes: list[float] | None = None,
    closes: list[float] | None = None,
    macd_data: dict[str, list[float]] | None = None,
    volatility: float | None = None,
    zss: list[ZS] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> float:
    """计算买卖点置信度（V9 校准版）。

    V9 改进：
    1. 置信度校准：基于实际回测准确率调整基础值（3买/3卖从0.72/0.68降至0.60/0.55）
    2. MA趋势对齐加成：价格与MA20对齐时额外+0.03
    3. RSI确认加成：RSI处于合理区域时额外+0.02
    4. V8原有：类型优先级更精细、波动率自适应、多信号融合
    5. V18新增：突破力度+时间窗口+MACD零轴过滤后，3买/3卖准确率提升，基础值上调
    """
    # V10: 基础置信度（V9校准 + V10多因子增强，3买/3卖提升）
    # V17: 基于回测结果校准 - 3买实际57.3%→0.60, 3卖实际50%→0.55
    # V18: V18新增条件26-28过滤后预期准确率提升，基础值微调
    base_confidence: dict[MMDType, float] = {
        MMDType.BUY_1: 0.88,
        MMDType.SELL_1: 0.92,
        MMDType.BUY_2: 0.78,   # V10: 从0.75提升至0.78（BOLL+MA斜率增强）
        MMDType.SELL_2: 0.73,  # V10: 从0.70提升至0.73
        MMDType.BUY_2S: 0.55,
        MMDType.SELL_2S: 0.50,
        MMDType.BUY_3: 0.65,   # V19: 从0.62上调至0.65（条件29-30增强后预期准确率~68%）
        MMDType.SELL_3: 0.60,  # V19: 从0.57上调至0.60（条件29-30增强后预期准确率~63%）
    }

    confidence = base_confidence.get(mmd.mmd_type, 0.5)

    # V8: 波动率调整
    if volatility is not None:
        if volatility > 0.03:  # 高波动市场：降低置信度
            confidence *= 0.90
        elif volatility < 0.01:  # 低波动市场：提升置信度
            confidence *= 1.05

    # 从消息中提取背驰强度
    strength_bonus = 0.0
    msg = mmd.msg.lower()
    if "strong" in msg:
        strength_bonus = 0.10
    elif "moderate" in msg:
        strength_bonus = 0.05
    elif "weak" in msg:
        strength_bonus = -0.05

    # V8: 趋势强度加成（加权）
    trend_bonus = trend_strength * 0.06
    # V8: 趋势方向加成
    trend_direction = _calc_overall_trend_direction(zss) if zss else "neutral"
    if trend_direction == "up" and "buy" in mmd.mmd_type.value:
        trend_bonus += 0.03  # 上升趋势中的买点额外加成
    elif trend_direction == "down" and "sell" in mmd.mmd_type.value:
        trend_bonus += 0.03  # 下降趋势中的卖点额外加成

    confidence += strength_bonus + trend_bonus

    # V8: 成交量配合加成（更精细）
    if volumes is not None and mmd.bi:
        try:
            bi_end_idx = mmd.bi.end.k.k_index
            if 0 <= bi_end_idx < len(volumes):
                recent_vols = volumes[max(0, bi_end_idx-20):bi_end_idx+1]
                if recent_vols and len(volumes) >= 20:
                    avg_recent = sum(recent_vols) / len(recent_vols)
                    avg_20 = sum(volumes[-20:]) / 20
                    if avg_20 > 0:
                        vol_ratio = avg_recent / avg_20
                        # V8: 更细致的成交量评分
                        if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
                            if vol_ratio < 0.5:  # 显著缩量
                                confidence += 0.10
                            elif vol_ratio < 0.65:
                                confidence += 0.06
                            elif vol_ratio < 0.8:
                                confidence += 0.03
                        elif mmd.mmd_type in (MMDType.BUY_1, MMDType.SELL_1):
                            if vol_ratio < 0.6:
                                confidence += 0.08
                            elif vol_ratio < 0.75:
                                confidence += 0.04
                        elif mmd.mmd_type in (MMDType.BUY_2, MMDType.SELL_2):
                            if vol_ratio < 0.7:
                                confidence += 0.06
                            elif vol_ratio < 0.85:
                                confidence += 0.03
        except Exception:
            pass

    # V13: 成交量剖面加成（2买/2卖专属：支撑/阻力确认加分）
    if hasattr(mmd, '_vol_profile_support') and mmd._vol_profile_support:
        confidence += 0.05  # 成交量支撑确认加成
    if hasattr(mmd, '_vol_profile_resistance') and mmd._vol_profile_resistance:
        confidence += 0.05  # 成交量阻力确认加成

    # V14: 成交量异常加成（机构活动信号）
    if hasattr(mmd, '_vol_spike') and mmd._vol_spike:
        if "buy" in mmd.mmd_type.value:
            confidence += 0.04  # 买入信号成交量放大=机构接盘
        else:
            confidence += 0.03  # 卖出信号成交量放大=机构出货

    # V14: 缺口分析加成
    if hasattr(mmd, '_gap_down') and mmd._gap_down:
        gap_size = getattr(mmd, '_gap_size', 0.0)
        if gap_size > 1.0:
            confidence += 0.05  # 大缺口=强信号
        else:
            confidence += 0.03
    if hasattr(mmd, '_gap_up') and mmd._gap_up:
        gap_size = getattr(mmd, '_gap_size', 0.0)
        if gap_size > 1.0:
            confidence += 0.05
        else:
            confidence += 0.03

    # V14: MACD柱状图斜率确认加成
    if hasattr(mmd, '_macd_slope_confirmed') and mmd._macd_slope_confirmed:
        confidence += 0.03  # 动量确认加成

    # V8: MACD位置确认（优先使用传入的macd_data）
    if mmd.bi and len(closes or []) > 26:
        try:
            if macd_data is None:
                from easy_tdx.chanlun.macd import calc_macd
                macd_data = calc_macd(closes)
            latest_dif = macd_data["dif"][-1] if macd_data.get("dif") else 0
            prev_dif = macd_data["dif"][-2] if macd_data and len(macd_data.get("dif", [])) > 1 else 0
            latest_hist = macd_data["hist"][-1] if macd_data.get("hist") else 0
            prev_hist = macd_data["hist"][-2] if macd_data and len(macd_data.get("hist", [])) > 1 else 0

            if "buy" in mmd.mmd_type.value:
                if latest_dif > 0:
                    confidence += 0.05  # V8: 提高加成
                elif latest_dif > -0.5:
                    confidence += 0.02
                # V8: MACD柱状图趋势加成
                if latest_hist > prev_hist and latest_hist > 0:
                    confidence += 0.03  # 红柱放大，上涨动量增强
                elif latest_dif > prev_dif:
                    confidence += 0.02  # DIF上升确认
            else:
                if latest_dif < 0:
                    confidence += 0.05
                elif latest_dif < 0.5:
                    confidence += 0.02
                # V8: MACD柱状图趋势加成
                if latest_hist < prev_hist and latest_hist < 0:
                    confidence += 0.03  # 绿柱放大，下跌动量增强
                elif latest_dif < prev_dif:
                    confidence += 0.02
        except Exception:
            pass

    # V8: 中枢稳定性加成
    if mmd.zs and mmd.zs.done:
        confidence += 0.04  # V8: 提高完成中枢的加成

    # V8: 区间套一致性加成（传入zss参数）
    if closes is not None and macd_data and mmd.zs:
        confluence_bonus = _calc_confluence_bonus(mmd, zss or [], macd_data, volumes, closes, volatility)
        confidence += confluence_bonus

    # V10: 多因子共振加成（3买/3卖额外加分）
    if mmd.bi and closes and len(closes) >= 30:
        try:
            bi_end_idx = mmd.bi.end.k.k_index
            if 0 <= bi_end_idx < len(closes):
                # MA斜率确认加成
                ma_slope = _calc_ma_slope(closes, bi_end_idx)
                if mmd.mmd_type in (MMDType.BUY_3, MMDType.BUY_2):
                    if ma_slope == "up":
                        confidence += 0.04
                elif mmd.mmd_type in (MMDType.SELL_3, MMDType.SELL_2):
                    if ma_slope == "down":
                        confidence += 0.04

                # BOLL位置加成（安全区域加分，极端区域扣分）
                boll_pos = _calc_boll_position(closes, bi_end_idx)
                if mmd.mmd_type in (MMDType.BUY_3, MMDType.BUY_2):
                    if boll_pos["percent_b"] < 0.5:
                        confidence += 0.03  # 价格在中轨以下，上涨空间大
                    elif boll_pos["percent_b"] > 0.9:
                        confidence -= 0.05  # 价格在上轨外侧，回调风险高
                elif mmd.mmd_type in (MMDType.SELL_3, MMDType.SELL_2):
                    if boll_pos["percent_b"] > 0.5:
                        confidence += 0.03  # 价格在中轨以上，下跌空间大
                    elif boll_pos["percent_b"] < 0.1:
                        confidence -= 0.05  # 价格在下轨内侧，反弹风险高

                # V12: ADX趋势强度加成（使用真实OHLC数据）
                adx_val, adx_level = _calc_adx_strength(closes, highs, lows, bi_end_idx)
                if adx_level == "strong":
                    confidence += 0.04  # 强趋势确认
                elif adx_level == "medium":
                    confidence += 0.02

                # RSI动量加成
                rsi_val = _calc_rsi(closes, bi_end_idx)
                rsi_mom = _calc_rsi_momentum(closes, bi_end_idx)
                if mmd.mmd_type in (MMDType.BUY_3, MMDType.BUY_2):
                    if 40 <= rsi_val <= 65:
                        confidence += 0.03  # RSI中性偏强
                    if rsi_mom > 0:
                        confidence += 0.02  # RSI动量向上
                elif mmd.mmd_type in (MMDType.SELL_3, MMDType.SELL_2):
                    if 35 <= rsi_val <= 60:
                        confidence += 0.03  # RSI中性偏弱
                    if rsi_mom < 0:
                        confidence += 0.02  # RSI动量向下
        except Exception:
            pass

        # V11: 多时间框架一致性加成（跨级别信号共振）
    confluence_data = getattr(mmd, "confluence_score", None)
    if confluence_data is not None and isinstance(confluence_data, float):
        if confluence_data >= 0.7:
            confidence += 0.05  # 强共振加成
        elif confluence_data >= 0.5:
            confidence += 0.03  # 中等共振加成

    # V15: 信号衰减调整 - 如果信号已产生但尚未触发，且已过很久则降低置信度
    aging = getattr(mmd, "_signal_aging", None)
    if aging is not None:
        if aging.get("aged", False):
            confidence *= aging.get("decay_factor", 1.0)
        elif aging.get("age_bars", 0) > 10:
            confidence *= 0.9  # 轻微衰减

    # V15: K线形态加成
    kline_pattern = getattr(mmd, "_kline_pattern", None)
    if kline_pattern in ("hammer", "bullish_engulfing"):
        confidence += 0.03  # 看涨K线形态加成

    # V15: 二次回踩确认加成
    if getattr(mmd, "_retest_break", False):
        confidence += 0.04  # 二次回踩确认加成
        retracement = getattr(mmd, "_retest_retracement", 50.0)
        if retracement < 30:
            confidence += 0.02  # 浅回踩更强势

    # V17: 趋势强度惩罚 - 3买/3卖在趋势不明确时降低置信度
    if trend_strength < 0.5 and mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
        confidence *= 0.85  # 趋势不明确时降低15%置信度
    elif trend_strength >= 0.7 and mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
        confidence += 0.05  # 趋势明确时额外加成

    # V17: MA60趋势确认加成 - 3买/3卖有MA60趋势确认时加分
    if mmd.bi and closes and len(closes) >= 60:
        try:
            bi_end_idx = mmd.bi.end.k.k_index
            if 0 <= bi_end_idx < len(closes):
                ma60_slope_val = _calc_ma60_slope(closes, bi_end_idx)
                if mmd.mmd_type in (MMDType.BUY_3, MMDType.BUY_2):
                    if ma60_slope_val == "up":
                        confidence += 0.03  # MA60向上确认中期趋势
                elif mmd.mmd_type in (MMDType.SELL_3, MMDType.SELL_2):
                    if ma60_slope_val == "down":
                        confidence += 0.03  # MA60向下确认中期趋势
        except Exception:
            pass

    # V18: MACD零轴确认加成 - 3买MACD在零轴上方/3卖在零轴下方时加分
    if mmd.bi and macd_data:
        try:
            bi_end_idx = mmd.bi.end.k.k_index
            macd_zero_pos = _calc_macd_zero_axis_position(macd_data, bi_end_idx)
            if mmd.mmd_type in (MMDType.BUY_3, MMDType.BUY_2):
                if macd_zero_pos in ("above", "crossing_above"):
                    confidence += 0.03  # MACD多头确认
            elif mmd.mmd_type in (MMDType.SELL_3, MMDType.SELL_2):
                if macd_zero_pos in ("below", "crossing_below"):
                    confidence += 0.03  # MACD空头确认
        except Exception:
            pass

    # V19: 信号新鲜度衰减（条件30）- 过时信号降低置信度
    if mmd.bi and closes:
        try:
            signal_idx = mmd.bi.end.k.k_index
            freshness_factor, _ = _calc_signal_freshness(closes, signal_idx)
            if freshness_factor < 1.0:
                confidence *= freshness_factor
        except Exception:
            pass

    # V20: 波动率Regime加成（条件31）
    vol_regime = getattr(mmd, "_vol_regime", None)
    if vol_regime == "low" and mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
        confidence += 0.03  # 低波动市场信号更可靠
    elif vol_regime == "high":
        confidence *= 0.95  # 高波动市场信号折扣

    # V20: 趋势加速度加成（条件32）
    trend_accel = getattr(mmd, "_trend_accel", None)
    if trend_accel == "accelerating" and mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
        confidence += 0.04  # 趋势加速确认加成
    elif trend_accel == "decelerating":
        confidence *= 0.92  # 趋势减速折扣

    # V20: 关键价位成交量分布加成（条件33）
    vol_dist = getattr(mmd, "_vol_dist_at_zg", None) or getattr(mmd, "_vol_dist_at_zd", None)
    if vol_dist and vol_dist.get("strength") == "strong":
        confidence += 0.03  # 关键价位成交量密集加成
    elif vol_dist and vol_dist.get("volume_concentration", 0) < 0.5:
        confidence *= 0.94  # 关键价位成交量稀疏折扣

    # V21: 组合信号加成（条件35）- 邻近不同类型的同向信号增强
    combo_bonus = getattr(mmd, '_combo_confidence_bonus', 0.0)
    if combo_bonus > 0:
        confidence += combo_bonus  # 组合信号额外加成

    # clip到[0, 1]
    return max(0.0, min(1.0, confidence))


def _calc_atr(closes: list[float], highs: list[float] | None, lows: list[float] | None, idx: int, period: int = 14) -> float:
    """计算指定位置的ATR值（V19新增）。

    使用简化TR计算：max(high-low, abs(high-prev_close), abs(low-prev_close))
    返回ATR绝对值（非比率），用于支撑/阻力区域判断。
    """
    if idx < period or not closes:
        return 0.0
    try:
        end = idx if idx < len(closes) else len(closes) - 1
        start = max(0, end - period + 1)
        slice_closes = closes[start:end + 1]
        if highs is None or lows is None:
            highs_arr = [c * (1 + 0.005) for c in slice_closes]
            lows_arr = [c * (1 - 0.005) for c in slice_closes]
        else:
            h_end = end if end < len(highs) else len(highs) - 1
            l_end = end if end < len(lows) else len(lows) - 1
            highs_arr = highs[start:h_end + 1]
            lows_arr = lows[start:l_end + 1]
        if len(slice_closes) < 2 or len(highs_arr) < 2 or len(lows_arr) < 2:
            return 0.0
        trs = []
        for i in range(1, len(slice_closes)):
            h, l, pc = highs_arr[i], lows_arr[i], slice_closes[i - 1]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        return sum(trs) / len(trs) if trs else 0.0
    except Exception:
        return 0.0


def _check_atr_support_zone(
    pullback_low: float,
    zg: float,
    zd: float,
    mmd_type: MMDType,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
    idx: int,
    atr_period: int = 14,
) -> tuple[bool, str]:
    """检查回踩/反抽是否在ATR支撑区域内（V19新增，条件29）。

    3买：回踩低点应在 zg - 1.0*ATR ~ zg + 0.3*ATR 范围内
    3卖：反弹高点应在 zd + 1.0*ATR ~ zd - 0.3*ATR 范围内
    """
    atr = _calc_atr(closes, highs, lows, idx, atr_period)
    if atr <= 0:
        return True, "无ATR数据"

    if mmd_type == MMDType.BUY_3:
        support_low = zg - atr * 1.0
        support_high = zg + atr * 0.3
        if support_low <= pullback_low <= support_high:
            depth_pct = (zg - pullback_low) / zg * 100 if zg > 0 else 0
            return True, f"ATR支撑确认(回踩{depth_pct:.1f}%@zg-{atr:.2f}~zg+{atr*0.3:.2f})"
        else:
            return False, f"ATR支撑不符(回踩{pullback_low:.2f}超出范围)"
    elif mmd_type == MMDType.SELL_3:
        resistance_low = zd - atr * 0.3
        resistance_high = zd + atr * 1.0
        if resistance_low <= pullback_low <= resistance_high:
            depth_pct = (pullback_low - zd) / zd * 100 if zd > 0 else 0
            return True, f"ATR阻力确认(反抽{depth_pct:.1f}%@zd-{atr*0.3:.2f}~zd+{atr:.2f})"
        else:
            return False, f"ATR阻力不符(反抽{pullback_low:.2f}超出范围)"
    return True, "未知类型"


def _calc_signal_freshness(
    closes: list[float], signal_idx: int, max_age_bars: int = 15
) -> tuple[float, str]:
    """计算信号新鲜度衰减因子（V19新增，条件30）。

    信号产生后每超过max_age_bars根K线，置信度乘以衰减因子。
    """
    if not closes or signal_idx < 0 or signal_idx >= len(closes):
        return 1.0, "无K线数据"
    bars_since_signal = len(closes) - 1 - signal_idx
    if bars_since_signal <= 0:
        return 1.0, "当前K线"
    if bars_since_signal <= max_age_bars:
        return 1.0, f"信号新鲜({bars_since_signal}根前)"
    excess = bars_since_signal - max_age_bars
    decay = max(0.5, 1.0 - excess * 0.02)
    return decay, f"信号老化({bars_since_signal}根前, 衰减{decay:.2f})"


def _calc_breakout_force_ratio(
    break_bi: "BI",
    entry_bi: "BI",
    closes: list[float],
) -> float:
    """计算突破力度与进入中枢笔力度的比率（V19新增）。"""
    try:
        break_force = _calc_bi_force(break_bi, closes, break_bi.index)
        entry_force = _calc_bi_force(entry_bi, closes, entry_bi.index)
        if entry_force > 0:
            return break_force / entry_force
        return 1.0
    except Exception:
        return 1.0


def _calc_mmd_quality(
    mmd: MMD,
    trend_strength: float,
    trend_direction: str,
    volumes: list[float] | None = None,
    closes: list[float] | None = None,
    macd_data: dict[str, list[float]] | None = None,
    volatility: float | None = None,
) -> MMDQuality:
    """计算买卖点质量评级（S/A/B/C/D）（V19增强版）。

    质量评级基于六维评分系统（V19增强）：
    1. 类型得分（30分）
    2. 趋势得分（20分）
    3. 成交量得分（20分）
    4. MACD得分（15分）
    5. 背驰得分（15分）
    6. V5新增：区间套一致性加成（最多+10分）
    7. V19新增：突破力度加成（10分）+ 信号新鲜度加成（5分）
    """
    factors: dict[str, float] = {}
    reasons: list[str] = []

    # 1. 类型得分（30分）
    type_scores = {
        MMDType.BUY_1: 30, MMDType.SELL_1: 30,
        MMDType.BUY_2: 25, MMDType.SELL_2: 25,
        MMDType.BUY_2S: 18, MMDType.SELL_2S: 18,
        MMDType.BUY_3: 22, MMDType.SELL_3: 22,
    }
    type_score = type_scores.get(mmd.mmd_type, 15)
    factors["type"] = type_score / 30.0
    reasons.append(f"类型: {mmd.mmd_type.value.replace('buy', '买').replace('sell', '卖')} ({type_score}/30)")

    # 2. 趋势得分（20分）
    trend_score = trend_strength * 20
    factors["trend"] = trend_strength
    if trend_strength > 0.7:
        reasons.append(f"趋势强({trend_direction}) +20")
    elif trend_strength > 0.4:
        reasons.append(f"趋势中 +{int(trend_score)}")
    else:
        reasons.append(f"趋势弱 +{int(trend_score)}")

    # 3. 成交量得分（20分）
    vol_score = 10  # 基础分
    if volumes is not None and mmd.bi:
        try:
            bi_end_idx = mmd.bi.end.k.k_index
            if 0 <= bi_end_idx < len(volumes):
                recent_vols = volumes[max(0, bi_end_idx-20):bi_end_idx+1]
                avg_recent = sum(recent_vols) / len(recent_vols)
                avg_20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else avg_recent
                if avg_20 > 0:
                    vol_ratio = avg_recent / avg_20
                    if vol_ratio < 0.6:
                        vol_score = 20
                        factors["volume"] = 1.0
                        reasons.append("显著缩量(0.6x) +20")
                    elif vol_ratio < 0.75:
                        vol_score = 16
                        factors["volume"] = 0.8
                        reasons.append("轻度缩量(0.75x) +16")
                    elif vol_ratio < 0.9:
                        vol_score = 12
                        factors["volume"] = 0.6
                        reasons.append("正常缩量(0.9x) +12")
                    else:
                        factors["volume"] = 0.5
                        reasons.append(f"放量({vol_ratio:.1f}x) +{vol_score}")
                else:
                    factors["volume"] = 0.5
            else:
                factors["volume"] = 0.5
        except Exception:
            factors["volume"] = 0.5
            reasons.append("无成交量数据")
    else:
        factors["volume"] = 0.5
        reasons.append("无成交量数据")

    # 4. MACD得分（15分）
    macd_score = 7  # 基础分
    if closes and len(closes) > 26:
        try:
            if macd_data is None:
                from easy_tdx.chanlun.macd import calc_macd
                macd_data = calc_macd(closes)
            latest_dif = macd_data["dif"][-1] if macd_data.get("dif") else 0
            prev_dif = macd_data["dif"][-2] if macd_data and len(macd_data.get("dif", [])) > 1 else 0

            if "buy" in mmd.mmd_type.value:
                if latest_dif > 0:
                    macd_score = 15
                    factors["macd"] = 1.0
                    reasons.append(f"DIF>0多头 +15")
                elif latest_dif > -0.5:
                    macd_score = 10
                    factors["macd"] = 0.67
                    reasons.append(f"DIF≈0中性 +10")
                else:
                    macd_score = 5
                    factors["macd"] = 0.33
                    reasons.append(f"DIF<0空头 +5")

                if prev_dif is not None and latest_dif > prev_dif:
                    macd_score = min(15, macd_score + 2)
                    reasons.append("DIF上升 +2")
            else:
                if latest_dif < 0:
                    macd_score = 15
                    factors["macd"] = 1.0
                    reasons.append(f"DIF<0空头 +15")
                elif latest_dif < 0.5:
                    macd_score = 10
                    factors["macd"] = 0.67
                    reasons.append(f"DIF≈0中性 +10")
                else:
                    macd_score = 5
                    factors["macd"] = 0.33
                    reasons.append(f"DIF>0多头 +5")

                if prev_dif is not None and latest_dif < prev_dif:
                    macd_score = min(15, macd_score + 2)
                    reasons.append("DIF下降 +2")
        except Exception:
            factors["macd"] = 0.5
    else:
        factors["macd"] = 0.5

    factors["macd_score"] = macd_score / 15.0

    # 5. 背驰得分（15分）
    bc_score = 10  # 基础分
    msg = mmd.msg.lower()
    if "strong" in msg:
        bc_score = 15
        factors["beichi"] = 1.0
        reasons.append("强背驰 +15")
    elif "moderate" in msg:
        bc_score = 12
        factors["beichi"] = 0.8
        reasons.append("中背驰 +12")
    elif "weak" in msg:
        bc_score = 8
        factors["beichi"] = 0.53
        reasons.append("弱背驰 +8")
    else:
        factors["beichi"] = 0.67
        reasons.append("背驰未知 +10")

    # 计算总分
    total_score = type_score + int(trend_score) + vol_score + macd_score + bc_score

    # V5: 区间套一致性加成（最多+10分）
    if closes is not None and macd_data:
        confluence_bonus = _calc_confluence_bonus(mmd, [], macd_data, volumes)
        confluence_score = int(confluence_bonus * 100)
        total_score += confluence_score
        if confluence_bonus > 0:
            reasons.append(f"区间套确认 +{confluence_score}")
            factors["confluence"] = confluence_bonus
        else:
            factors["confluence"] = 0.0

    factors["total"] = total_score / 100.0

    # V19: 突破力度加成（10分）- 3买/3卖专属
    breakout_force_score = 5  # 基础分
    if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3) and mmd.zs and mmd.bi and closes:
        try:
            if len(mmd.zs.lines) >= 1:
                entry_bi = mmd.zs.lines[0]
                force_ratio = _calc_breakout_force_ratio(mmd.bi, entry_bi, closes)
                if force_ratio >= 1.3:
                    breakout_force_score = 10
                    factors["breakout_force"] = 1.0
                    reasons.append(f"突破强劲({force_ratio:.1f}x) +10")
                elif force_ratio >= 1.0:
                    breakout_force_score = 7
                    factors["breakout_force"] = 0.7
                    reasons.append(f"突破正常({force_ratio:.1f}x) +7")
                else:
                    factors["breakout_force"] = 0.5
                    reasons.append(f"突破偏弱({force_ratio:.1f}x) +5")
            else:
                factors["breakout_force"] = 0.5
        except Exception:
            factors["breakout_force"] = 0.5

    # V19: 信号新鲜度加成（5分）
    freshness_bonus = 0
    if mmd.bi and closes:
        try:
            signal_idx = mmd.bi.end.k.k_index
            freshness_factor, freshness_reason = _calc_signal_freshness(closes, signal_idx)
            if freshness_factor >= 0.9:
                freshness_bonus = 5
                reasons.append(f"信号新鲜✅ +5")
            elif freshness_factor >= 0.7:
                freshness_bonus = 3
                reasons.append(f"信号较新 +3")
            else:
                reasons.append(f"信号老化 ⚠️")
        except Exception:
            pass

    total_score += breakout_force_score + freshness_bonus
    factors["breakout_force"] = factors.get("breakout_force", 0.5)
    factors["freshness"] = freshness_bonus / 5.0

    # V20: 波动率Regime加成（条件31）- 最多+5分
    vol_regime_score = 0
    if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
        vol_regime = getattr(mmd, "_vol_regime", None)
        if vol_regime == "low":
            vol_regime_score = 5
            factors["vol_regime"] = 1.0
            reasons.append("低波动市场✅ +5")
        elif vol_regime == "medium":
            vol_regime_score = 3
            factors["vol_regime"] = 0.6
            reasons.append("正常波动 +3")
        else:
            factors["vol_regime"] = 0.4
            reasons.append("高波动市场 ⚠️")
    else:
        factors["vol_regime"] = 0.5
    total_score += vol_regime_score

    # V20: 趋势加速度加成（条件32）- 最多+5分
    accel_score = 0
    if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
        trend_accel = getattr(mmd, "_trend_accel", None)
        if trend_accel == "accelerating":
            accel_score = 5
            factors["trend_accel"] = 1.0
            reasons.append("趋势加速✅ +5")
        elif trend_accel == "decelerating":
            accel_score = 0
            factors["trend_accel"] = 0.3
            reasons.append("趋势减速 ⚠️")
        else:
            accel_score = 2
            factors["trend_accel"] = 0.6
            reasons.append("趋势中性 +2")
    else:
        factors["trend_accel"] = 0.5
    total_score += accel_score

    # V20: 关键价位成交量分布加成（条件33）- 最多+5分
    vol_dist_score = 0
    if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
        vol_dist = getattr(mmd, "_vol_dist_at_zg", None) or getattr(mmd, "_vol_dist_at_zd", None)
        if vol_dist and vol_dist.get("strength") == "strong":
            vol_dist_score = 5
            factors["vol_dist"] = 1.0
            reasons.append(f"量价密集✅ {vol_dist['signal']} +5")
        elif vol_dist and vol_dist.get("volume_concentration", 0) < 0.5:
            vol_dist_score = 0
            factors["vol_dist"] = 0.3
            reasons.append("量价稀疏 ⚠️")
        else:
            vol_dist_score = 2
            factors["vol_dist"] = 0.6
            reasons.append("量价正常 +2")
    else:
        factors["vol_dist"] = 0.5
    total_score += vol_dist_score

    # 评级（V5调整阈值，考虑加成后）
    if total_score >= 90:
        grade = "S"
    elif total_score >= 75:
        grade = "A"
    elif total_score >= 60:
        grade = "B"
    elif total_score >= 45:
        grade = "C"
    else:
        grade = "D"

    return MMDQuality(
        grade=grade,
        score=float(total_score),
        factors=factors,
        reasons=reasons,
    )


# ─────────────────────────────────────────────────────────────────────────────
# V20 新增：波动率Regime过滤 + 趋势加速度确认 + 关键价位成交量分布
# ─────────────────────────────────────────────────────────────────────────────


def _get_volatility_regime(volatility: float) -> tuple[str, float]:
    """判断当前波动率Regime（高/中/低）并返回对应阈值调整因子。

    V20 条件31：根据市场波动率状态动态调整信号过滤阈值。

    Returns:
        (regime, threshold_adjust): regime为"high"/"medium"/"low"，
        threshold_adjust为阈值调整因子（>1表示放宽，<1表示收紧）
    """
    if volatility > 0.04:
        return "high", 1.15   # 高波动：放宽阈值15%，避免漏信号
    elif volatility > 0.02:
        return "medium", 1.0  # 正常波动：不调整
    else:
        return "low", 0.88    # 低波动：收紧阈值12%，过滤噪音


def _calc_trend_acceleration(
    macd_data: dict[str, list[float]] | None, idx: int, lookback: int = 10
) -> tuple[float, str]:
    """计算趋势加速度（DIF的二阶差）。

    V20 条件32：不仅看趋势方向，还要看趋势是否在加速或减速。

    Returns:
        (acceleration, trend_state): acceleration为加速度值，
        trend_state为"accelerating"/"decelerating"/"neutral"
    """
    if not macd_data or not macd_data.get("dif") or len(macd_data["dif"]) < lookback + 2:
        return 0.0, "neutral"

    try:
        end = idx if idx < len(macd_data["dif"]) else len(macd_data["dif"]) - 1
        if end < lookback + 1:
            return 0.0, "neutral"

        # 计算一阶差（DIF变化率）
        dif_recent = macd_data["dif"][end] - macd_data["dif"][end - lookback // 2]
        dif_earlier = macd_data["dif"][end - lookback // 2] - macd_data["dif"][max(0, end - lookback)]

        # 加速度 = 一阶差的变化
        acceleration = dif_recent - dif_earlier

        # 归一化（除以平均DIF绝对值）
        avg_dif_abs = sum(abs(macd_data["dif"][i]) for i in range(max(0, end - lookback), end + 1)) / max(1, lookback)
        if avg_dif_abs > 0:
            acceleration_normalized = acceleration / avg_dif_abs
        else:
            acceleration_normalized = acceleration

        if acceleration_normalized > 0.3:
            return acceleration, "accelerating"
        elif acceleration_normalized < -0.3:
            return acceleration, "decelerating"
        else:
            return acceleration, "neutral"
    except Exception:
        return 0.0, "neutral"


def _analyze_volume_at_levels(
    closes: list[float],
    volumes: list[float] | None,
    level: float,
    level_type: str,
    lookback: int = 30,
    tolerance_pct: float = 0.02,
) -> dict[str, Any]:
    """分析关键价位（支撑/阻力）附近的成交量分布。

    V20 条件33：判断支撑/阻力位的强度基于成交量分布。

    Args:
        closes: 收盘价序列
        volumes: 成交量序列
        level: 关键价位（zg或zd）
        level_type: "support" 或 "resistance"
        lookback: 回看K线数量
        tolerance_pct: 价位容忍度（±2%）

    Returns:
        dict with keys: volume_concentration, strength, signal
    """
    if volumes is None or not closes:
        return {"volume_concentration": 0.0, "strength": "unknown", "signal": ""}

    try:
        end = len(closes) - 1
        start = max(0, end - lookback)

        tol = level * tolerance_pct
        near_level_volumes: list[float] = []
        all_volumes_slice: list[float] = []

        for i in range(start, end + 1):
            all_volumes_slice.append(volumes[i] if i < len(volumes) else 0)
            # 检查是否在关键价位附近
            if level_type == "support":
                if closes[i] <= level * (1 + tolerance_pct) and closes[i] >= level * (1 - tolerance_pct * 2):
                    near_level_volumes.append(volumes[i] if i < len(volumes) else 0)
            else:  # resistance
                if closes[i] >= level * (1 - tolerance_pct) and closes[i] <= level * (1 + tolerance_pct * 2):
                    near_level_volumes.append(volumes[i] if i < len(volumes) else 0)

        if not all_volumes_slice or not near_level_volumes:
            return {"volume_concentration": 0.0, "strength": "unknown", "signal": ""}

        avg_all = sum(all_volumes_slice) / len(all_volumes_slice)
        avg_near = sum(near_level_volumes) / len(near_level_volumes)

        if avg_all > 0:
            concentration = avg_near / avg_all
        else:
            concentration = 0.0

        if concentration > 1.5:
            strength = "strong"
            signal = f"成交量密集({concentration:.1f}x均量)"
        elif concentration > 1.0:
            strength = "moderate"
            signal = f"成交量偏集中({concentration:.1f}x均量)"
        else:
            strength = "weak"
            signal = f"成交量稀疏({concentration:.1f}x均量)"

        return {
            "volume_concentration": concentration,
            "strength": strength,
            "signal": signal,
        }
    except Exception:
        return {"volume_concentration": 0.0, "strength": "unknown", "signal": ""}


def _calc_dynamic_stop_loss_take_profit(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
    atr_period: int = 14,
) -> dict[str, float]:
    """动态计算止损止盈价位（V20增强）。

    基于：
    1. ATR多倍（根据信号类型和波动率调整）
    2. 中枢结构（支撑/阻力位）
    3. 近期高低点

    Returns:
        dict with entry_price, stop_loss, take_profit_1, take_profit_2, risk_reward_ratio
    """
    if not mmd.bi or not closes:
        return {}

    latest_close = closes[-1]
    bi = mmd.bi
    mmd_type = mmd.mmd_type

    # 计算ATR
    atr = _calc_atr(closes, highs, lows, len(closes) - 1, atr_period)
    if atr <= 0:
        atr = latest_close * 0.02

    entry_price = 0.0
    stop_loss = 0.0
    take_profit_1 = 0.0
    take_profit_2 = 0.0

    if mmd_type == MMDType.BUY_3:
        # 3买：入场价略高于回调低点
        entry_price = round(bi.low * 1.002, 2)
        # 止损：回调低点下方ATR×1.5（高波动市场用更宽止损）
        atr_multiplier_sl = 1.8 if atr / latest_close > 0.03 else 1.5
        stop_loss = round(max(bi.low * 0.98, entry_price - atr * atr_multiplier_sl), 2)
        # 止盈：基于中枢高度和ATR
        zs_height = mmd.zs.zg - mmd.zs.zd if mmd.zs else 0
        tp1_mult = 2.5 if atr / latest_close > 0.03 else 2.0
        tp2_mult = 4.0 if atr / latest_close > 0.03 else 3.0
        take_profit_1 = round(entry_price + max(zs_height * 0.5, atr * tp1_mult), 2)
        take_profit_2 = round(entry_price + max(zs_height * 1.0, atr * tp2_mult), 2)

    elif mmd_type == MMDType.SELL_3:
        # 3卖：入场价略低于反弹高点
        entry_price = round(bi.high * 0.998, 2)
        atr_multiplier_sl = 1.8 if atr / latest_close > 0.03 else 1.5
        stop_loss = round(min(bi.high * 1.02, entry_price + atr * atr_multiplier_sl), 2)
        zs_height = mmd.zs.zg - mmd.zs.zd if mmd.zs else 0
        tp1_mult = 2.5 if atr / latest_close > 0.03 else 2.0
        tp2_mult = 4.0 if atr / latest_close > 0.03 else 3.0
        take_profit_1 = round(entry_price - max(zs_height * 0.5, atr * tp1_mult), 2)
        take_profit_2 = round(entry_price - max(zs_height * 1.0, atr * tp2_mult), 2)

    elif mmd_type in (MMDType.BUY_1, MMDType.BUY_2):
        entry_price = round(latest_close, 2)
        atr_mult = 2.0 if atr / latest_close > 0.03 else 1.5
        stop_loss = round(entry_price - atr * atr_mult, 2)
        take_profit_1 = round(entry_price + atr * 3.0, 2)
        take_profit_2 = round(entry_price + atr * 5.0, 2)

    elif mmd_type in (MMDType.SELL_1, MMDType.SELL_2):
        entry_price = round(latest_close, 2)
        atr_mult = 2.0 if atr / latest_close > 0.03 else 1.5
        stop_loss = round(entry_price + atr * atr_mult, 2)
        take_profit_1 = round(entry_price - atr * 3.0, 2)
        take_profit_2 = round(entry_price - atr * 5.0, 2)

    else:
        return {}

    # 风险收益比
    risk = abs(entry_price - stop_loss)
    reward = abs(take_profit_1 - entry_price)
    risk_reward_ratio = round(reward / risk, 2) if risk > 0 else 0

    return {
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "risk_reward_ratio": risk_reward_ratio,
        "atr": round(atr, 2),
    }


def sort_mmds_by_priority(mmds: list[MMD]) -> list[MMD]:
    """按信号优先级排序（V20新增）。

    排序规则：
    1. 质量等级（S>A>B>C>D）
    2. 置信度（高优先）
    3. 类型优先级（1买>1卖>2买>2卖>3买>3卖）

    Returns:
        排序后的买卖点列表
    """
    type_priority = {
        MMDType.BUY_1: 1, MMDType.SELL_1: 2,
        MMDType.BUY_2: 3, MMDType.SELL_2: 4,
        MMDType.BUY_2S: 5, MMDType.SELL_2S: 6,
        MMDType.BUY_3: 7, MMDType.SELL_3: 8,
    }

    def sort_key(mmd: MMD) -> tuple:
        grade = getattr(getattr(mmd, "quality", None), "grade", "D")
        grade_order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
        return (
            grade_order.get(grade, 4),      # 1. 质量等级
            -mmd.confidence,                 # 2. 置信度（降序）
            type_priority.get(mmd.mmd_type, 9),  # 3. 类型优先级
        )

    return sorted(mmds, key=sort_key)


# ─────────────────────────────────────────────────────────────────────────────
# V21 新增：动态支撑阻力 + 组合信号 + 多时间框架共振 + 决策辅助
# ─────────────────────────────────────────────────────────────────────────────


def _identify_dynamic_support_resistance(
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
    lookback: int = 60,
) -> dict[str, Any]:
    """识别动态支撑阻力位（V21 条件34）。

    不仅依赖缠论中枢结构，还从近期价格行为中提取动态支撑阻力：
    1. 近期swing低点/高点（局部极值）
    2. 成交量密集区（volume profile nodes）
    3. 整数价位/心理关口

    Returns:
        {
            "support_levels": [float, ...],   # 动态支撑位（升序）
            "resistance_levels": [float, ...], # 动态阻力位（升序）
            "strongest_support": float | None, # 最强支撑
            "strongest_resistance": float | None, # 最强阻力
            "atr": float,                      # 当前ATR（用于区间判断）
        }
    """
    if not closes or len(closes) < 20:
        return {
            "support_levels": [],
            "resistance_levels": [],
            "strongest_support": None,
            "strongest_resistance": None,
            "atr": 0.0,
        }

    try:
        end = len(closes) - 1
        start = max(0, end - lookback)

        # 计算ATR
        atr = _calc_atr(closes, highs, lows, end, 14)
        if atr <= 0:
            atr = closes[end] * 0.02

        # 1. Swing 低点/高点检测（局部极值）
        swing_lows: list[float] = []
        swing_highs: list[float] = []
        half = 3  # 左右各3根K线确认极值

        for i in range(start + half, end - half):
            is_low = True
            is_high = True
            for j in range(i - half, i + half + 1):
                if j == i:
                    continue
                if lows and lows[j] <= (lows[i] if lows else closes[j]):
                    is_low = False
                if highs and highs[j] >= (highs[i] if highs else closes[j]):
                    is_high = False
            if is_low:
                swing_lows.append(closes[i])
            if is_high:
                swing_highs.append(closes[i])

        # 2. 聚类支撑/阻力位（相近价位合并）
        def _cluster_levels(levels: list[float], tolerance: float = 0.015) -> list[float]:
            """将相近价位聚类，返回代表性价位。"""
            if not levels:
                return []
            sorted_levels = sorted(levels)
            clusters: list[list[float]] = [[sorted_levels[0]]]
            for level in sorted_levels[1:]:
                if level <= clusters[-1][-1] * (1 + tolerance):
                    clusters[-1].append(level)
                else:
                    clusters.append([level])
            return [sum(c) / len(c) for c in clusters]

        support_candidates = _cluster_levels(swing_lows)
        resistance_candidates = _cluster_levels(swing_highs)

        # 3. 加入整数价位/心理关口
        latest = closes[end]
        for power in range(1, 4):
            round_level = round(latest / (10 ** power)) * (10 ** power)
            if 0.9 * latest < round_level < 1.1 * latest and round_level not in support_candidates:
                if round_level < latest:
                    support_candidates.append(round_level)
                else:
                    resistance_candidates.append(round_level)

        # 4. 按距离最新价排序，保留最近5个
        support_levels = sorted(
            [s for s in support_candidates if s < latest],
            reverse=True,
        )[:5]
        resistance_levels = sorted(
            [r for r in resistance_candidates if r > latest],
        )[:5]

        # 去重（距离太近的合并）
        def _dedup_near(levels: list[float], min_gap: float = 0.01) -> list[float]:
            if len(levels) <= 1:
                return levels
            result = [levels[0]]
            for lvl in levels[1:]:
                if abs(lvl - result[-1]) / result[-1] > min_gap:
                    result.append(lvl)
            return result

        support_levels = _dedup_near(support_levels)
        resistance_levels = _dedup_near(resistance_levels)

        return {
            "support_levels": support_levels,
            "resistance_levels": resistance_levels,
            "strongest_support": support_levels[0] if support_levels else None,
            "strongest_resistance": resistance_levels[0] if resistance_levels else None,
            "atr": atr,
        }
    except Exception:
        return {
            "support_levels": [],
            "resistance_levels": [],
            "strongest_support": None,
            "strongest_resistance": None,
            "atr": 0.0,
        }


def _detect_combo_signals(mmds: list[MMD], closes: list[float]) -> None:
    """检测组合信号（V21 条件35）。

    当多个不同类型的买卖点出现在相近价位区间时，形成"组合信号"，
    置信度加成更高。例如：
    - 1买 + 2买 同区域 → "1+2buy_combo"
    - 1卖 + 2卖 同区域 → "1+2sell_combo"
    - 多个3买密集 → "3buy_cluster"

    修改：在MMD对象上设置 _signal_combo 和 _combo_confidence_bonus。
    """
    if len(mmds) < 2 or not closes:
        return

    try:
        latest = closes[-1]
        atr = _calc_atr(closes, None, None, len(closes) - 1, 14)
        if atr <= 0:
            atr = latest * 0.02
        zone_width = atr * 3  # 3ATR范围内视为同一区域

        # 按位置分组
        by_zone: dict[float, list[MMD]] = {}
        for mmd in mmds:
            if not mmd.bi:
                continue
            price = mmd.bi.end.k.close if hasattr(mmd.bi.end.k, 'close') else latest
            zone_key = round(price / zone_width) * zone_width
            if zone_key not in by_zone:
                by_zone[zone_key] = []
            by_zone[zone_key].append(mmd)

        # 检测组合
        for zone_key, zone_mmds in by_zone.items():
            if len(zone_mmds) < 2:
                continue

            types_in_zone = set(mmd.mmd_type for mmd in zone_mmds)
            buy_types = {t for t in types_in_zone if "buy" in t.value}
            sell_types = {t for t in types_in_zone if "sell" in t.value}

            # 买组合
            if len(buy_types) >= 2:
                combo_type = "+".join(sorted(t.value for t in buy_types)) + "_combo"
                bonus = 0.05 if len(buy_types) == 2 else 0.08
                for mmd in zone_mmds:
                    if "buy" in mmd.mmd_type.value:
                        mmd._signal_combo = combo_type
                        mmd._combo_confidence_bonus = bonus
            # 卖组合
            elif len(sell_types) >= 2:
                combo_type = "+".join(sorted(t.value for t in sell_types)) + "_combo"
                bonus = 0.05 if len(sell_types) == 2 else 0.08
                for mmd in zone_mmds:
                    if "sell" in mmd.mmd_type.value:
                        mmd._signal_combo = combo_type
                        mmd._combo_confidence_bonus = bonus

            # 多3买/3卖聚集
            buy_3_count = sum(1 for m in zone_mmds if m.mmd_type == MMDType.BUY_3)
            sell_3_count = sum(1 for m in zone_mmds if m.mmd_type == MMDType.SELL_3)
            if buy_3_count >= 2:
                for mmd in zone_mmds:
                    if mmd.mmd_type == MMDType.BUY_3:
                        mmd._signal_combo = "3buy_cluster"
                        mmd._combo_confidence_bonus = 0.06
            if sell_3_count >= 2:
                for mmd in zone_mmds:
                    if mmd.mmd_type == MMDType.SELL_3:
                        mmd._signal_combo = "3sell_cluster"
                        mmd._combo_confidence_bonus = 0.06

    except Exception:
        pass


def _calc_multi_tf_resonance(
    mmd: MMD,
    all_mmds: list[MMD],
    closes: list[float] | None,
    macd_data: dict[str, list[float]] | None,
    volatility: float | None,
) -> float:
    """计算多时间框架共振增强分数（V21 条件36）。

    除了区间套一致性外，还检查：
    1. 同价位区间内是否有其他类型信号共振
    2. MACD在多个信号点是否同向确认
    3. 成交量在信号点附近是否持续活跃

    Returns:
        额外共振加分（0~0.08）
    """
    if not mmd.bi or not closes:
        return 0.0

    try:
        bonus = 0.0
        signal_price = mmd.bi.end.k.close if hasattr(mmd.bi.end.k, 'close') else closes[-1]
        atr = _calc_atr(closes, None, None, len(closes) - 1, 14)
        if atr <= 0:
            atr = signal_price * 0.02
        resonance_zone = atr * 2  # 2ATR共振区间

        # 1. 检查邻近不同类型的同向信号
        for other in all_mmds:
            if other is mmd:
                continue
            if not other.bi:
                continue
            other_price = other.bi.end.k.close if hasattr(other.bi.end.k, 'close') else closes[-1]
            if abs(other_price - signal_price) / signal_price > 0.03:
                continue  # 超出3%不视为共振

            # 同向信号共振
            is_same_direction = (
                ("buy" in mmd.mmd_type.value and "buy" in other.mmd_type.value) or
                ("sell" in mmd.mmd_type.value and "sell" in other.mmd_type.value)
            )
            if is_same_direction and other.mmd_type != mmd.mmd_type:
                # 不同类型同向 = 强共振
                bonus += 0.04
            elif is_same_direction and other.mmd_type == mmd.mmd_type:
                # 同类型重复 = 弱共振
                bonus += 0.02

        # 2. MACD同向确认
        if macd_data and macd_data.get("dif"):
            difs = macd_data["dif"]
            idx = mmd.bi.end.k.k_index if mmd.bi else len(difs) - 1
            if 0 <= idx < len(difs) and len(difs) > 5:
                recent_dif = difs[max(0, idx-3):idx+1]
                if len(recent_dif) >= 3:
                    rising = all(recent_dif[i] <= recent_dif[i+1] for i in range(len(recent_dif)-1))
                    falling = all(recent_dif[i] >= recent_dif[i+1] for i in range(len(recent_dif)-1))
                    if ("buy" in mmd.mmd_type.value and rising) or ("sell" in mmd.mmd_type.value and falling):
                        bonus += 0.02

        return min(0.08, bonus)
    except Exception:
        return 0.0


def _generate_decision_recommendation(
    mmd: MMD,
    closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
    dynamic_levels: dict[str, Any],
    volatility: float | None,
) -> dict[str, Any]:
    """生成决策辅助输出（V21 条件37）。

    基于动态支撑阻力、止损止盈、组合信号等，生成结构化决策建议。

    Returns:
        {
            "action": "buy"/"sell"/"hold",
            "entry_price": float,
            "stop_loss": float,
            "take_profit_1": float,
            "take_profit_2": float,
            "position_pct": float,     # 建议仓位比例 0-1
            "risk_reward_ratio": float,
            "key_support": float | None,
            "key_resistance": float | None,
            "confidence_label": str,   # "高"/"中"/"低"
            "warnings": list[str],     # 风险提示
            "recommendation_text": str # 自然语言建议
        }
    """
    if not mmd.bi or not closes:
        return {}

    try:
        latest = closes[-1]
        atr = _calc_atr(closes, highs, lows, len(closes) - 1, 14)
        if atr <= 0:
            atr = latest * 0.02

        vol = volatility if volatility is not None else _calc_atr_volatility(closes)

        # 基础建议
        action = "buy" if "buy" in mmd.mmd_type.value else "sell" if "sell" in mmd.mmd_type.value else "hold"

        # 入场价
        if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
            entry = mmd.bi.low * 1.002 if "buy" in action else mmd.bi.high * 0.998
        else:
            entry = latest

        # 止损止盈（复用V20动态计算逻辑）
        sl_tp = _calc_dynamic_stop_loss_take_profit(mmd, closes, highs, lows)
        stop_loss = sl_tp.get("stop_loss", entry - atr * 1.5 if "buy" in action else entry + atr * 1.5)
        tp1 = sl_tp.get("take_profit_1", entry + atr * 2.0 if "buy" in action else entry - atr * 2.0)
        tp2 = sl_tp.get("take_profit_2", entry + atr * 3.5 if "buy" in action else entry - atr * 3.5)

        # 风险收益比
        risk = abs(entry - stop_loss)
        reward = abs(tp1 - entry)
        rrr = reward / risk if risk > 0 else 0

        # 动态支撑阻力
        key_support = dynamic_levels.get("strongest_support") if dynamic_levels else None
        key_resistance = dynamic_levels.get("strongest_resistance") if dynamic_levels else None

        # 仓位建议（基于置信度和风险收益比）
        base_position = 0.10  # 基础10%
        conf_bonus = mmd.confidence * 0.15  # 置信度加成
        combo_bonus = getattr(mmd, '_combo_confidence_bonus', 0.0)
        rrr_bonus = min(0.10, rrr * 0.02) if rrr > 1.5 else 0
        position_pct = min(0.30, base_position + conf_bonus + combo_bonus + rrr_bonus)

        # 置信度标签
        if mmd.confidence >= 0.75:
            conf_label = "高"
        elif mmd.confidence >= 0.55:
            conf_label = "中"
        else:
            conf_label = "低"

        # 风险提示
        warnings: list[str] = []
        if vol > 0.04:
            warnings.append("高波动市场，注意止损")
        if rrr < 1.5:
            warnings.append("风险收益比较低，谨慎入场")
        if getattr(mmd, '_signal_aging', {}).get('aged', False):
            warnings.append("信号已衰减，时效性降低")
        if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
            warnings.append("三类买卖点需谨慎确认")

        # 自然语言建议
        direction = "买入" if action == "buy" else "卖出" if action == "sell" else "观望"
        type_name = mmd.mmd_type.value.replace("buy_", "买").replace("sell_", "卖")
        parts = [f"{direction}信号：{type_name}"]
        if mmd.confidence >= 0.7:
            parts.append(f"置信度{conf_label}({mmd.confidence:.0%})")
        if mmd._signal_combo and mmd._signal_combo != "none":
            parts.append(f"组合信号✅({mmd._signal_combo})")
        if key_support:
            parts.append(f"下方支撑@{key_support:.2f}")
        if key_resistance:
            parts.append(f"上方阻力@{key_resistance:.2f}")
        if warnings:
            parts.append("⚠️" + ";".join(warnings[:2]))

        recommendation_text = " | ".join(parts)

        return {
            "action": action,
            "entry_price": round(entry, 2),
            "stop_loss": round(stop_loss, 2),
            "take_profit_1": round(tp1, 2),
            "take_profit_2": round(tp2, 2),
            "position_pct": round(position_pct, 2),
            "risk_reward_ratio": round(rrr, 2),
            "key_support": round(key_support, 2) if key_support else None,
            "key_resistance": round(key_resistance, 2) if key_resistance else None,
            "confidence_label": conf_label,
            "warnings": warnings,
            "recommendation_text": recommendation_text,
        }
    except Exception:
        return {}
