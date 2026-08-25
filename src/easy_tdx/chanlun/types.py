"""缠论核心数据结构定义。

参考 chanlun-pro cl_interface.py，去除对 db/exchange 的依赖，
使用纯 dataclass + 类型注解，保持 mypy strict 兼容。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# ── K 线 ──────────────────────────────────────────────────────────────────


@dataclass
class Kline:
    """原始 K 线。"""

    index: int
    date: datetime
    open: float
    close: float
    high: float
    low: float
    amount: float  # 成交量（股数）

    def __str__(self) -> str:
        return (
            f"Kline(i={self.index} {self.date:%Y-%m-%d} "
            f"o={self.open:.2f} c={self.close:.2f} "
            f"h={self.high:.2f} l={self.low:.2f})"
        )


@dataclass
class CLKline:
    """缠论 K 线（包含处理后的合并 K 线）。"""

    k_index: int  # 对应原始 K 线中最后一根的 index
    date: datetime  # 合并 K 线最后一根的时间
    open: float
    close: float
    high: float
    low: float
    amount: float
    index: int = 0  # 在缠论 K 线列表中的序号
    merged_count: int = 1  # 合并了几根原始 K 线
    has_gap: bool = False  # 是否有缺口
    direction: str = ""  # 合并方向 "up" / "down" / ""
    klines: list[Kline] = field(default_factory=list)  # 包含的原始 K 线

    def __str__(self) -> str:
        return (
            f"CLKline(i={self.index} ki={self.k_index} {self.date:%Y-%m-%d} "
            f"h={self.high:.2f} l={self.low:.2f} n={self.merged_count})"
        )


# ── 分型 ──────────────────────────────────────────────────────────────────


class FXType(str, Enum):
    """分型类型。"""

    DING = "ding"  # 顶分型
    DI = "di"  # 底分型


@dataclass
class FX:
    """分型对象。"""

    fx_type: FXType
    k: CLKline  # 分型中间那根缠论 K 线
    klines: list[CLKline]  # 构成分型的三根缠论 K 线 [左, 中, 右]
    val: float  # 分型值（顶分型取 high，底分型取 low）
    index: int = 0  # 分型序号
    done: bool = True  # 分型是否完成

    def __str__(self) -> str:
        return f"FX(i={self.index} {self.fx_type.value} {self.k.date:%Y-%m-%d} val={self.val:.2f})"


# ── 线（笔/线段基类）─────────────────────────────────────────────────────


class Direction(str, Enum):
    """方向。"""

    UP = "up"
    DOWN = "down"


@dataclass
class Line:
    """线的基本定义，笔和线段的基类。"""

    start: FX  # 起始分型
    end: FX  # 结束分型
    direction: Direction  # 方向
    index: int = 0  # 序号
    high: float = 0.0  # 区间最高价
    low: float = 0.0  # 区间最低价

    def is_done(self) -> bool:
        """线是否完成（结束分型已完成）。"""
        return self.end.done

    def __str__(self) -> str:
        return (
            f"Line(i={self.index} {self.direction.value} "
            f"{self.start.k.date:%Y-%m-%d}→{self.end.k.date:%Y-%m-%d} "
            f"h={self.high:.2f} l={self.low:.2f})"
        )


@dataclass
class BI(Line):
    """笔。"""

    pass


@dataclass
class XD(Line):
    """线段。"""

    pass


# ── 中枢 ──────────────────────────────────────────────────────────────────


@dataclass
class ZS:
    """中枢对象。"""

    lines: list[BI | XD] = field(default_factory=list)  # 构成中枢的线
    zg: float = 0.0  # 中枢上沿（重叠区间最高）
    zd: float = 0.0  # 中枢下沿（重叠区间最低）
    gg: float = 0.0  # 中枢最高点
    dd: float = 0.0  # 中枢最低点
    direction: str = ""  # 中枢方向 "up"/"down"/""
    index: int = 0  # 序号
    done: bool = False  # 中枢是否完成
    start: FX | None = None  # 起始分型
    end: FX | None = None  # 结束分型

    def add_line(self, line: BI | XD) -> None:
        self.lines.append(line)

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def __str__(self) -> str:
        return (
            f"ZS(i={self.index} lines={self.line_count} "
            f"zg={self.zg:.2f} zd={self.zd:.2f} "
            f"gg={self.gg:.2f} dd={self.dd:.2f} "
            f"done={self.done})"
        )


# ── 买卖点 / 背驰 ─────────────────────────────────────────────────────────


class MMDType(str, Enum):
    """买卖点类型。"""

    BUY_1 = "1buy"
    BUY_2 = "2buy"
    BUY_2S = "2buy_s"  # 类二买
    BUY_3 = "3buy"
    SELL_1 = "1sell"
    SELL_2 = "2sell"
    SELL_2S = "2sell_s"  # 类二卖
    SELL_3 = "3sell"


@dataclass
class MMD:
    """买卖点。"""

    mmd_type: MMDType
    zs: ZS | None = None
    bi: BI | None = None  # 触发该买卖点的笔（用于可视化锚定日期）
    msg: str = ""
    confidence: float = 0.0  # 置信度 0-1，由分析器计算
    quality: object = None  # 质量评级，由分析器计算
    confluence_score: float = 0.0  # 多时间框架共振评分 0-1，由MultiLevelAnalyser设置

    # V14 enhancement fields
    _vol_spike: bool = False  # 成交量异常放大
    _gap_up: bool = False  # 向上缺口
    _gap_down: bool = False  # 向下缺口
    _gap_size: float = 0.0  # 缺口大小（%）
    _macd_slope_confirmed: bool = False  # MACD柱状图斜率确认
    _vol_profile_support: bool = False  # 成交量剖面支撑确认
    _vol_profile_resistance: bool = False  # 成交量剖面阻力确认

    # V15 enhancement fields
    _kline_pattern: str | None = None  # K线形态：hammer/bullish_engulfing/doji/bearish_engulfing
    _signal_aging: dict | None = None  # 信号衰减信息
    _retest_break: bool = False  # 二次回踩确认
    _retest_retracement: float = 50.0  # 回踩深度（%）

    # V21 enhancement fields
    _dynamic_support: float | None = None  # 动态支撑位
    _dynamic_resistance: float | None = None  # 动态阻力位
    _signal_combo: str | None = None  # 组合信号类型：none/1+2buy/1+2sell/3buy_multi等
    _combo_confidence_bonus: float = 0.0  # 组合信号置信度加成
    _decision_recommendation: dict[str, Any] | None = None  # 决策辅助建议

    # V23 enhancement fields
    _fib_retracement: dict[str, Any] | None = None  # Fibonacci回撤位信息（条件40）
    _rsi_zone: dict[str, Any] | None = None  # RSI区域分类（条件41）
    _macd_zero_cross: dict[str, Any] | None = None  # MACD零轴穿越信息（条件42）

    # V24 enhancement fields
    _bi_quality: dict[str, Any] | None = None  # 笔质量评分（条件43）
    _zs_strength: dict[str, Any] | None = None  # 中枢强度分析（条件44）
    _enhanced_divergence: dict[str, Any] | None = None  # 增强背离检测（条件45）
    _cross_validation: dict[str, Any] | None = None  # 信号交叉验证评分（条件46）

    # V25 enhancement fields
    _post_signal_confirm: dict[str, Any] | None = None  # 信号后确认验证（条件47）
    _momentum_decay: dict[str, Any] | None = None  # 动量衰减预警（条件48）
    _vol_regime_filter: dict[str, Any] | None = None  # 波动率自适应过滤（条件49）
    _composite_quality: dict[str, Any] | None = None  # 综合信号质量评分（条件50）

    # V26 enhancement fields
    _signal_history: dict[str, Any] | None = None  # 信号历史验证评分（条件51）
    _dynamic_rr_optimization: dict[str, Any] | None = None  # 动态风险收益优化（条件52）
    _cross_stock_comparison: dict[str, Any] | None = None  # 多标的对比评分（条件53）

    # V27 enhancement fields
    _multi_tf_confluence: dict[str, Any] | None = None  # 多级别区间套共振验证（条件54）
    _structure_position: dict[str, Any] | None = None  # 买卖点结构位置评分（条件55）
    _stock_profile: dict[str, Any] | None = None  # 个股信号特征学习（条件56）

    # V28 enhancement fields
    _boll_squeeze: dict[str, Any] | None = None  # BOLL带宽压缩确认（条件57）
    _breakout_vol_price: dict[str, Any] | None = None  # 突破量价确认（条件58）
    _dynamic_atr_stop: dict[str, Any] | None = None  # 动态ATR止损位（条件59）

    # V29 enhancement fields
    _trend_continuity: dict[str, Any] | None = None  # 趋势方向持续性确认（条件60）
    _consolidation_divergence: dict[str, Any] | None = None  # 盘整区背离预警（条件61）

    # V30 enhancement fields
    _kline_pattern_confirm: dict[str, Any] | None = None  # K线形态反向确认（条件62）
    _zs_breakout_confirm: dict[str, Any] | None = None  # 中枢突破方向确认（条件63）
    _recent_range_stop: dict[str, Any] | None = None  # 近期波动区间止损优化（条件64）

    # V31 enhancement fields
    _ma_alignment: dict[str, Any] | None = None  # 均线排列确认（条件65）
    _macd_histogram_acceleration: dict[str, Any] | None = None  # MACD柱状图加速度（条件66）
    _signal_health_dashboard: dict[str, Any] | None = None  # 信号综合健康度报告（条件67）

    # V32 enhancement fields
    _vol_price_divergence_enhanced: dict[str, Any] | None = None  # 量价背离检测增强（条件68）
    _signal_priority: dict[str, Any] | None = None  # 信号优先级动态排序（条件69）
    _sr_breakout_confirm: dict[str, Any] | None = None  # 支撑阻力位突破确认（条件70）

    # V33 enhancement fields
    _obv_trend_confirm: dict[str, Any] | None = None  # OBV能量潮趋势确认（条件71）
    _macd_hist_area: dict[str, Any] | None = None  # MACD动能锥面积确认（条件72）
    _rsi_momentum_confirm: dict[str, Any] | None = None  # RSI动量确认（条件73）

    # V34 enhancement fields
    _trend_momentum_continuation: dict[str, Any] | None = None  # 趋势动能延续确认（条件74）
    _multi_indicator_resonance: dict[str, Any] | None = None  # 多指标共振强度评分（条件75）
    _volatility_regime: dict[str, Any] | None = None  # 波动率环境自适应阈值（条件76）

    # V35 enhancement fields
    _market_context_filter: dict[str, Any] | None = None  # 市场大环境过滤（条件77）
    _enhanced_signal_decay: dict[str, Any] | None = None  # 信号衰减模型增强（条件78）
    _false_signal_filter: dict[str, Any] | None = None  # 假信号过滤增强（条件79）
    _dynamic_sl_tp_enhanced: dict[str, Any] | None = None  # 动态止损止盈增强（条件80）
    _sector_rotation_context: dict[str, Any] | None = None  # 板块轮动上下文（条件81）
    _multi_dim_divergence: dict[str, Any] | None = None  # 多维度背离确认（条件82）

    # V36 enhancement fields
    _execution_window: dict[str, Any] | None = None  # 信号执行窗口优化（条件83）
    _tf_consistency: dict[str, Any] | None = None  # 多时间框架一致性验证（条件84）
    _risk_adjusted_return: dict[str, Any] | None = None  # 风险调整后收益预期（条件85）
    _urgency_score: dict[str, Any] | None = None  # 信号时效性紧急度评分（条件86）
    _market_composite: dict[str, Any] | None = None  # 市场环境综合评分（条件87）
    _strategy_recommendation: dict[str, Any] | None = None  # 买卖点策略推荐（条件88）

    # V37 enhancement fields
    _consecutive_confirmation: dict[str, Any] | None = None  # 连续确认过滤（条件89）
    _momentum_acceleration: dict[str, Any] | None = None  # 价格动能加速度（条件90）
    _volatility_regime_change: dict[str, Any] | None = None  # 波动率状态转换检测（条件91）
    _temporal_correlation: dict[str, Any] | None = None  # 买卖点时间序列关联分析（条件92）
    _multi_tf_momentum: dict[str, Any] | None = None  # 多时间框架动量一致性（条件93）
    _quality_ranking: dict[str, Any] | None = None  # 信号综合质量排名（条件94）

    # V38 enhancement fields
    _zs_structure_integrity: dict[str, Any] | None = None  # 中枢结构完整性评分（条件95）
    _mmd_position_score: dict[str, Any] | None = None  # 买卖点位置评分（条件96）
    _post_signal_return: dict[str, Any] | None = None  # 信号后收益跟踪（条件97）
    _breakout_strength: dict[str, Any] | None = None  # 中枢突破力度评估（条件98）
    _composite_deviation: dict[str, Any] | None = None  # 多指标偏离度综合评分（条件99）
    _signal_decay_warning: dict[str, Any] | None = None  # 信号衰减预警（条件100）

    # V39 enhancement fields
    _signal_consistency: dict[str, Any] | None = None  # 买卖点信号一致性验证（条件101）
    _zs_level_match: dict[str, Any] | None = None  # 中枢级别匹配验证（条件102）
    _multi_tf_divergence: dict[str, Any] | None = None  # 多时间框架背离确认（条件103）
    _independent_cross_validation: dict[str, Any] | None = None  # 独立交叉验证（条件104）
    _decision_quality_score: dict[str, Any] | None = None  # 决策质量综合评分（条件105）

    # V40 enhancement fields
    _time_decay_adaptive: dict[str, Any] | None = None  # 时间衰减自适应过滤（条件106）
    _breakout_retest_validation: dict[str, Any] | None = None  # 中枢突破回踩验证（条件107）
    _multi_cycle_macd_resonance: dict[str, Any] | None = None  # 多周期MACD共振确认（条件108）
    _kline_pattern_composite: dict[str, Any] | None = None  # K线形态综合评分（条件109）
    _confidence_calibration: dict[str, Any] | None = None  # 置信度动态校准（条件110）

    # V41 enhancement fields (2026-08-23)
    _volume_price_energy_dist: dict[str, Any] | None = None  # 量价能量分布分析（条件111）
    _volume_cycle_detection: dict[str, Any] | None = None  # 量能周期检测（条件112）
    _post_signal_trajectory: dict[str, Any] | None = None  # 信号后走势预测（条件113）
    _quality_tier_classification: dict[str, Any] | None = None  # 动态质量分层（条件114）
    _reversal_risk_assessment: dict[str, Any] | None = None  # 信号反转风险评估（条件115）

    # V42 enhancement fields (2026-08-23)
    _post_signal_confirmation: dict[str, Any] | None = None  # 后确认验证（条件116）
    _break_pullback_volume_ratio: dict[str, Any] | None = None  # 突破-回调量比验证（条件117）
    _zhongshu_distance_validation: dict[str, Any] | None = None  # 中枢距离验证（条件118）
    _adx_trend_strength: dict[str, Any] | None = None  # ADX趋势强度确认（条件119）
    _signal_freshness: dict[str, Any] | None = None  # 信号时效性衰减增强（条件120）

    # V44 enhancement fields (2026-08-23)
    _trend_direction_alignment: dict[str, Any] | None = None  # 趋势方向对齐验证（条件121）
    _breakout_bi_strength_compare: dict[str, Any] | None = None  # 突破笔力度对比（条件122）
    _pullback_time_window: dict[str, Any] | None = None  # 回踩时间窗口过滤（条件123）
    _volatility_adaptive_threshold: dict[str, Any] | None = None  # 波动率自适应阈值（条件124）
    _multi_indicator_divergence_resonance: dict[str, Any] | None = None  # 多指标背离共振（条件125）

    # V46 enhancement fields (2026-08-23)
    # V47 enhancement fields (2026-08-24)
    _post_signal_price_follow_through: dict[str, Any] | None = None  # 后确认价格跟随过滤（条件131）
    _signal_validity_window: dict[str, Any] | None = None  # 信号有效性窗口（条件132）
    _confidence_v47_calibrated: float | None = None  # V47 校准后的置信度（条件133）
    _trend_momentum_strength: dict[str, Any] | None = None  # 趋势动能强度过滤（条件126）
    _volume_price_divergence_secondary: dict[str, Any] | None = None  # 量价背离二次确认（条件127）
    _zs_breakout_authenticity: dict[str, Any] | None = None  # 中枢突破真实性验证（条件128）
    _multi_tf_signal_consistency: dict[str, Any] | None = None  # 多时间框架信号一致性（条件129）
    _dynamic_market_regime: dict[str, Any] | None = None  # 动态市场环境适配（条件130）

    # V48 enhancement fields (2026-08-24)
    _volume_price_divergence_secondary_v48: dict[str, Any] | None = None  # 量价背离二次确认（条件134）
    _trend_strength_weighting: dict[str, Any] | None = None  # 趋势强度加权（条件135）
    _dynamic_risk_reward_ratio: dict[str, Any] | None = None  # 动态风险收益比（条件136）

    # V49 enhancement fields (2026-08-25)
    _breakout_strength_revalidation_v49: dict[str, Any] | None = None  # 突破力度二次验证（条件137）
    _pullback_structure_integrity_v49: dict[str, Any] | None = None  # 回踩结构完整性（条件138）
    _zhongshu_level_weight_v49: dict[str, Any] | None = None  # 中枢级别权重（条件139）

    # V50 enhancement fields (2026-08-25)
    _sector_correlation_v50: dict[str, Any] | None = None  # 板块联动分析（条件140）
    _multi_tf_resonance_v50: dict[str, Any] | None = None  # 多时间框架共振验证（条件141）
    _level_recursive_validation_v50: dict[str, Any] | None = None  # 缠论级别递归验证（条件142）
    _market_sentiment_fusion_v50: dict[str, Any] | None = None  # 市场情绪指标融合（条件143）

    # V51 enhancement fields (2026-08-25)
    _breakout_bi_strength_enhanced_v51: dict[str, Any] | None = None  # 突破笔力度二次确认增强（条件144）
    _pullback_depth_time_v51: dict[str, Any] | None = None  # 回踩笔深度+时间综合验证（条件145）
    _trend_strength_composite_v51: dict[str, Any] | None = None  # 趋势强度综合评分（条件146）
    _trading_decision_v51: dict[str, Any] | None = None  # 交易决策建议（条件147）

    # V52 enhancement fields (2026-08-25)
    _volume_sustain_after_signal_v52: dict[str, Any] | None = None  # 量价持续确认（条件148）
    _multi_indicator_divergence_fusion_v52: dict[str, Any] | None = None  # 多指标背离共振（条件149）
    _recent_extreme_price_v52: dict[str, Any] | None = None  # 近期极端价位检测（条件150）
    _market_regime_score_v52: dict[str, Any] | None = None  # 市场环境健康评分（条件151）

    # V53 enhancement fields (2026-08-25)
    _trend_stage_follow_confirmation_v53: dict[str, Any] | None = None  # 趋势阶段识别与顺势确认（条件152）
    _atr_adaptive_stop_v53: dict[str, Any] | None = None  # ATR自适应止损距离（条件153）
    _zs_breakout_strength_v53: dict[str, Any] | None = None  # 中枢突破力度验证（条件154）
    _signal_quality_tier_v53: dict[str, Any] | None = None  # 信号质量综合分层（条件155）

    # V54 enhancement fields (2026-08-25)
    _multi_bar_confirmation_v54: dict[str, Any] | None = None  # 多K线确认后确认（条件156）
    _gap_risk_assessment_v54: dict[str, Any] | None = None  # 缺口风险评估（条件157）
    _volatility_regime_change_v54: dict[str, Any] | None = None  # 波动率regime切换检测（条件158）
    _volume_price_coordination_v54: dict[str, Any] | None = None  # 量价配合度评分（条件159）

    # V55 enhancement fields (2026-08-26)
    _multi_tf_resonance_filter_v55: dict[str, Any] | None = None  # 分钟级多时间框架共振过滤（条件160）
    _zhongshu_level_weight_v55: dict[str, Any] | None = None  # 中枢级别权重自适应（条件161）
    _weak_stock_risk_v55: dict[str, Any] | None = None  # 弱势股专项风险检测（条件162）
    _signal_trend_alignment_v55: dict[str, Any] | None = None  # 信号与趋势方向对齐验证（条件163）

    # V56 enhancement fields (2026-08-26)
    _false_breakout_detection_v56: dict[str, Any] | None = None  # 假突破识别（条件164）
    _zhongshu_structure_complexity_v56: dict[str, Any] | None = None  # 中枢结构复杂度分析（条件165）
    _volatility_adaptive_position_v56: dict[str, Any] | None = None  # 波动率自适应仓位建议（条件166）
    _multi_signal_resonance_v56: dict[str, Any] | None = None  # 多信号共振评分（条件167）

    # V57 enhancement fields (2026-08-26)
    _pullback_filter_v57: dict[str, Any] | None = None  # 回踩幅度与时间双重过滤（条件168）
    _breakout_strength_validation_v57: dict[str, Any] | None = None  # 突破力度验证（条件169）
    _zs_divergence_check_v57: dict[str, Any] | None = None  # 中枢背驰检测（条件170）
    _signal_decay_detection_v57: dict[str, Any] | None = None  # 信号衰减检测（条件171）

    # V58 enhancement fields (2026-08-26)
    _multi_tf_trend_consistency_v58: dict[str, Any] | None = None  # 多时间框架趋势一致性验证（条件172）
    _volume_accumulation_validation_v58: dict[str, Any] | None = None  # 成交量堆积验证（条件173）
    _atr_adaptive_stop_v58: dict[str, Any] | None = None  # ATR自适应止损距离（条件174）
    _composite_quality_score_v58: dict[str, Any] | None = None  # 信号质量综合评分（条件175）

    # V59 enhancement fields (2026-08-26)
    _volatility_adaptive_ma_v59: dict[str, Any] | None = None  # 波动率自适应MA周期（条件176）
    _atr_multiplier_adapt_v59: dict[str, Any] | None = None  # ATR倍数自适应（条件177）
    _multi_tf_resonance_signal_v59: dict[str, Any] | None = None  # 多时间框架共振信号（条件178）
    _signal_decay_speed_v59: dict[str, Any] | None = None  # 信号衰减速度评估（条件179）

    # V60 enhancement fields (2026-08-27)
    _rsi_deep_divergence_v60: dict[str, Any] | None = None  # RSI深度背离过滤（条件180）
    _ma_spacing_strength_v60: dict[str, Any] | None = None  # MA排列间距强度评分（条件181）
    _zs_distance_enhanced_v60: dict[str, Any] | None = None  # 中枢支撑/阻力距离评分增强（条件182）
    _kdj_ob_os_confirm_v60: dict[str, Any] | None = None  # KDJ超买超卖确认（条件183）

    # V61 enhancement fields (2026-08-27)
    _macd_hist_divergence_v61: dict[str, Any] | None = None  # MACD柱状图背离融合（条件184）
    _composite_signal_score_v61: dict[str, Any] | None = None  # 综合多信号评分（条件185）

    # V62 enhancement fields (2026-08-28)
    _boll_bandwidth_breakout_v62: dict[str, Any] | None = None  # BOLL带宽突破确认（条件186）
    _boll_bandwidth_reversal_v62: dict[str, Any] | None = None  # BOLL带宽压缩反弹确认（条件187）
    _dynamic_threshold_volatility_regime_v62: dict[str, Any] | None = None  # 动态阈值-波动率状态切换（条件188）
    _dynamic_threshold_atr_multiplier_v62: dict[str, Any] | None = None  # 动态阈值-ATR倍数自适应（条件189）

    # V63 enhancement fields (2026-08-28)
    _zhongshu_level_weight_enhanced_v63: dict[str, Any] | None = None  # 中枢级别权重优化增强（条件190）
    _multi_period_signal_decay_v63: dict[str, Any] | None = None  # 多周期信号衰减追踪（条件191）

    # V65 enhancement fields (2026-08-28)
    _volume_price_divergence_secondary_v65: dict[str, Any] | None = None  # 量价背离二次确认增强（条件192）
    _breakout_retest_confirmation_v65: dict[str, Any] | None = None  # 中枢突破回踩确认（条件193）
    _volatility_compression_breakout_v65: dict[str, Any] | None = None  # 波动率压缩突破信号（条件194）
    _signal_time_window_freshness_v65: dict[str, Any] | None = None  # 买卖点时间窗口新鲜度（条件195）

    # V66 enhancement fields (2026-08-28)
    _macd_momentum_acceleration_v66: dict[str, Any] | None = None  # MACD动能锥加速确认（条件196）
    _volume_price_coordination_deep_v66: dict[str, Any] | None = None  # 量价配合深度评分（条件197）
    _multi_tf_convergence_intensity_v66: dict[str, Any] | None = None  # 多时间框架共振强度评分（条件198）
    _signal_execution_priority_v66: dict[str, Any] | None = None  # 信号执行优先级建议（条件199）

    # V67 enhancement fields (2026-08-28)
    _zhongshu_divergence_strength_v67: dict[str, Any] | None = None  # 中枢背驰力度量化（条件200）
    _multi_level_mmd_consistency_v67: dict[str, Any] | None = None  # 多级别买卖点一致性验证（条件201）
    _post_signal_trajectory_health_v67: dict[str, Any] | None = None  # 信号后价格轨迹健康度（条件202）
    _dynamic_sl_tp_recommendation_v67: dict[str, Any] | None = None  # 动态止损止盈推荐（条件203）

    def __str__(self) -> str:
        return f"MMD({self.mmd_type.value} conf={self.confidence:.0%} {self.msg})"


class BCType(str, Enum):
    """背驰类型。"""

    BI = "bi"  # 笔背驰
    PZ = "pz"  # 盘整背驰
    QS = "qs"  # 趋势背驰


@dataclass
class BC:
    """背驰。"""

    bc_type: BCType
    bc: bool = False  # 是否背驰
    zs: ZS | None = None
    curr: BI | XD | None = None  # 当前背驰笔/线段（用于可视化锚定日期）
    prev: BI | XD | None = None  # 前一同向笔/线段（力度对照基准）
    msg: str = ""

    def __str__(self) -> str:
        return f"BC({self.bc_type.value} {self.bc})"


# ── BOLL 指标 ───────────────────────────────────────────────────────────

@dataclass
class BOLLResult:
    """BOLL 布林带结果。"""
    
    upper: list[float] = field(default_factory=list)   # 上轨
    mid: list[float] = field(default_factory=list)     # 中轨
    lower: list[float] = field(default_factory=list)   # 下轨
    width: list[float] = field(default_factory=list)   # 带宽 (upper - lower) / mid
    percent_b: list[float] = field(default_factory=list)  # %B = (close - lower) / (upper - lower)
    
    @property
    def latest_upper(self) -> float:
        return self.upper[-1] if len(self.upper) > 0 else 0.0

    @property
    def latest_mid(self) -> float:
        return self.mid[-1] if len(self.mid) > 0 else 0.0

    @property
    def latest_lower(self) -> float:
        return self.lower[-1] if len(self.lower) > 0 else 0.0

    @property
    def latest_percent_b(self) -> float:
        return self.percent_b[-1] if len(self.percent_b) > 0 else 0.5

    @property
    def latest_width(self) -> float:
        return self.width[-1] if len(self.width) > 0 else 0.0
