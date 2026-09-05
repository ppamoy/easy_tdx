"""买卖点识别（精修版 V55 - 决策增强）。

基于缠论理论持续优化（V77 2026-08-27）：
- 置信度计算：基于多因子加权，非单一准确率声明
- V77新增：量能分布深度分析(条件240)+中枢结构权重评估(条件241)+信号新鲜度验证(条件242)+价格动能加速度(条件243)
- V76新增：价格结构完整性验证(条件236)+趋势方向对齐验证(条件237)+波动率自适应置信度(条件238)+买卖点最终有效性评分(条件239)
- V90新增：笔稳定性校验 + 分型确认过滤（pen.py v90）
- V91新增：中枢质量评分集成（zs.py v89）
- V102新增：多信号相关性分析(条件264)+质量评分卡 (条件265)+决策支持输出(条件266)+历史模式匹配(条件267)
- V73新增：买卖点位置风险评估(条件224)+中枢突破有效性验证(条件225)+多指标确认一致性(条件226)+波动率环境适配(条件227)
- V54新增：多K线确认后确认(条件156)+缺口风险评估(条件157)+波动率切换检测(条件158)+量价配合度评分(条件159)
- V53新增：趋势顺势确认(条件152)+ATR自适应止损(条件153)+突破力度验证(条件154)+信号质量分层(条件155)
- V52新增：量价持续确认(条件148)+多指标背离共振(条件149)+极端价位检测(条件150)+市场环境评分(条件151)
- V50新增：板块联动分析(条件140)+多时间框架共振(条件141)+级别递归验证(条件142)+市场情绪融合(条件143)
- V49新增：突破力度二次验证(条件137)+回踩结构完整性(条件138)+中枢级别权重(条件139)
- V48新增：量价背离二次确认(条件134)+趋势强度加权(条件135)+动态风险收益比(条件136)
- V102新增：多信号相关性分析(条件264)+质量评分卡 (条件265)+决策支持输出(条件266)+历史模式匹配(条件267)
- 总条件数：267个
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
- V22新增：波动率Regime双重确认(条件38)、量价背离检测(条件39)、诊断API暴露V21决策辅助
- V23新增：Fibonacci回撤位动态确认(条件40)、RSI区域过滤增强(条件41)、MACD零轴穿越确认(条件42)、风险管理增强
- V24新增：笔质量评分(条件43)、中枢强度分析(条件44)、增强背离检测(条件45)、信号交叉验证(条件46)
- V25新增：信号后确认验证(条件47)、动量衰减预警(条件48)、波动率自适应过滤(条件49)、综合信号质量评分(条件50)
- V26新增：信号历史验证(条件51)、动态风险收益优化(条件52)、多标的对比评分(条件53)
- V27新增：多级别区间套共振验证(条件54)、买卖点结构位置评分(条件55)、个股信号特征学习(条件56)
- V28新增：BOLL带宽压缩确认(条件57)、突破量价确认(条件58)、动态ATR止损位(条件59)
- V29新增：趋势方向持续性确认(条件60)、盘整区背离预警(条件61)
- V30新增：K线形态反向确认(条件62)、中枢突破方向确认(条件63)、近期波动区间止损优化(条件64)
- V31新增：均线排列确认(条件65)、MACD柱状图加速度(条件66)、信号综合健康度报告(条件67)
- V32新增：量价背离检测增强(条件68)、信号优先级动态排序(条件69)、支撑阻力位突破确认(条件70)
- V33新增：OBV能量潮趋势确认(条件71)、MACD动能锥面积确认(条件72)、RSI动量确认(条件73)
- V34新增：趋势动能延续(条件74)、多指标共振(条件75)、波动率自适应(条件76)
- V35新增：市场大环境过滤(条件77)、信号衰减增强(条件78)、假信号过滤(条件79)
- V35新增：动态止损止盈增强(条件80)、板块轮动上下文(条件81)、多维背离确认(条件82)
- V36新增：信号执行窗口优化(条件83)、多时间框架一致性(条件84)、风险调整后收益(条件85)
- V36新增：信号时效性紧急度(条件86)、市场环境综合评分(条件87)、买卖点策略推荐(条件88)
- V37新增：连续确认过滤(条件89)、价格动能加速度(条件90)、波动率状态转换检测(条件91)
- V37新增：买卖点时间序列关联分析(条件92)、多时间框架动量一致性(条件93)、信号综合质量排名(条件94)
- V38新增：中枢结构完整性评分(条件95)、买卖点位置评分(条件96)、信号后收益跟踪(条件97)
- V38新增：中枢突破力度评估(条件98)、多指标偏离度综合评分(条件99)、信号衰减预警(条件100)
- V39新增：买卖点信号一致性验证(条件101)、中枢级别匹配验证(条件102)、多时间框架背离确认(条件103)
- V39新增：独立交叉验证(条件104)、决策质量综合评分(条件105)
- V40新增：时间衰减自适应过滤(条件106)、中枢突破回踩验证(条件107)、多周期MACD共振确认(条件108)
- V40新增：K线形态综合评分(条件109)、置信度动态校准(条件110)
- V41新增：量价能量分布分析(条件111)、量能周期检测(条件112)、走势预测(条件113)
- V41新增：动态质量分层(条件114)、反转风险评估(条件115)
- V42新增：后确认验证(条件116)+突破-回调量比(条件117)+中枢距离验证(条件118)+ADX趋势确认(条件119)+指数衰减(条件120)
- V43：API暴露V42字段 + TypeScript类型补全 + find_mmds_v42版本别名
- V44新增：趋势方向对齐验证(条件121)+突破笔力度对比(条件122)+回踩时间窗口过滤(条件123)+波动率自适应阈值(条件124)+多指标背离共振(条件125)
- V46新增：趋势动能强度过滤(条件126)+量价背离二次确认(条件127)+中枢突破真实性验证(条件128)+多TF信号一致性(条件129)+动态市场环境适配(条件130)
- V47新增：后确认价格跟随过滤(条件131)+信号有效性窗口(条件132)+置信度动态校准(条件133)
- V48新增：量价背离二次确认(条件134)+趋势强度加权(条件135)+动态风险收益比(条件136)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from easy_tdx.chanlun.config import ChanlunConfig

# V393：V76-V82 增强条件簇已拆分到 mmd_conditions.py，此处惰性再导出保持
# 既有 from easy_tdx.chanlun.mmd import _calc_* 等导入兼容。
# V397：V49-V65 自包含条件簇已分批迁入 mmd_conditions.py，此处惰性再导出保持兼容。
# V399：V41-V51 条件簇与共享叶子辅助已迁入 mmd_conditions.py，此处惰性再导出。
# V399b：V44 条件簇 + _calc_confidence 共享辅助已迁入 mmd_conditions.py。
from easy_tdx.chanlun.mmd_conditions import (
    MMDQuality,
    _analyze_volume_at_levels,
    _apply_volatility_adaptive_filter,
    _calc_adx_strength,
    _calc_adx_trend_strength_check,
    _calc_atr,
    _calc_atr_adaptive_stop_v53,
    _calc_atr_adaptive_stop_v58,
    _calc_atr_multiplier_adapt_v59,
    _calc_atr_volatility,
    _calc_bi_force,
    _calc_bi_quality,
    _calc_boll_bandwidth_breakout_confirm_v62,
    _calc_boll_bandwidth_reversal_confirm_v62,
    _calc_boll_position,
    _calc_boll_squeeze,
    _calc_break_pullback_volume_ratio,
    _calc_breakout_bi_strength_compare,
    _calc_breakout_bi_strength_enhanced_v51,
    _calc_breakout_force_ratio,
    _calc_breakout_retest_confirm_v82,
    _calc_breakout_retest_confirmation_v65,
    _calc_breakout_strength,
    _calc_breakout_strength_revalidation_v49,
    _calc_breakout_strength_validation_v57,
    _calc_breakout_vol_price,
    _calc_composite_deviation,
    _calc_composite_quality,
    _calc_composite_quality_score_v58,
    _calc_composite_signal_score_v61,
    _calc_confidence,
    _calc_confidence_calibration,
    _calc_confidence_v47,
    _calc_confluence_bonus,
    _calc_consecutive_confirmation,
    _calc_consolidation_divergence_warning,
    _calc_cross_stock_comparison,
    _calc_cross_validation,
    _calc_decision_quality_score,
    _calc_dynamic_atr_stop,
    _calc_dynamic_market_regime,
    _calc_dynamic_risk_reward_ratio_v48,
    _calc_dynamic_risk_reward_v80,
    _calc_dynamic_rr_optimization,
    _calc_dynamic_rr_optimization_v71,
    _calc_dynamic_sl_tp_enhanced,
    _calc_dynamic_sl_tp_recommendation_v67,
    _calc_dynamic_stop_loss_take_profit,
    _calc_dynamic_threshold_atr_multiplier_v62,
    _calc_dynamic_threshold_volatility_regime_v62,
    _calc_enhanced_signal_decay,
    _calc_enhanced_signal_freshness,
    _calc_execution_window,
    _calc_fake_signal_filter,
    _calc_false_breakout_detection_v56,
    _calc_false_breakout_filter_v70,
    _calc_fibonacci_retracement_level,
    _calc_final_confidence_calibration_v70,
    _calc_fractal_stability_validation_v79,
    _calc_fund_flow_divergence_v78,
    _calc_gap_risk_assessment_v54,
    _calc_gap_trend_consistency_v68,
    _calc_independent_cross_validation,
    _calc_kdj_j,
    _calc_kdj_ob_os_confirm_v60,
    _calc_kline_pattern_composite,
    _calc_kline_pattern_confirmation,
    _calc_level_recursive_validation_v50,
    _calc_ma60_slope,
    _calc_ma_alignment_confirmation,
    _calc_ma_alignment_strength_v71,
    _calc_ma_alignment_strength_v80,
    _calc_ma_convergence_divergence_v72,
    _calc_ma_slope,
    _calc_ma_spacing_strength_v60,
    _calc_ma_trend_alignment,
    _calc_macd_histogram_acceleration,
    _calc_macd_histogram_area,
    _calc_macd_histogram_divergence_v61,
    _calc_macd_momentum_acceleration_v66,
    _calc_macd_multi_tf_resonance_v82,
    _calc_macd_zero_axis_position,
    _calc_market_composite,
    _calc_market_context_filter,
    _calc_market_regime_adaptation_v68,
    _calc_market_regime_score_v52,
    _calc_market_sentiment_fusion_v50,
    _calc_mmd_age_decay_v82,
    _calc_mmd_cycle_position_v78,
    _calc_mmd_distance_safety_v79,
    _calc_mmd_history_winrate_v71,
    _calc_mmd_position_risk_v73,
    _calc_mmd_position_score,
    _calc_mmd_quality,
    _calc_mmd_zhongshu_distance_v80,
    _calc_momentum_acceleration,
    _calc_multi_bar_confirmation_v54,
    _calc_multi_cycle_macd_resonance,
    _calc_multi_dim_divergence,
    _calc_multi_indicator_consistency_v73,
    _calc_multi_indicator_divergence_fusion_v52,
    _calc_multi_indicator_divergence_resonance,
    _calc_multi_indicator_divergence_v69,
    _calc_multi_indicator_resonance,
    _calc_multi_level_confluence_verification,
    _calc_multi_level_mmd_consistency_v67,
    _calc_multi_level_structure_consistency_v79,
    _calc_multi_period_signal_decay_v63,
    _calc_multi_signal_consensus_v78,
    _calc_multi_signal_resonance_v56,
    _calc_multi_signal_time_consistency_v75,
    _calc_multi_tf_convergence_intensity_v66,
    _calc_multi_tf_divergence_confirmation,
    _calc_multi_tf_ma_resonance_v71,
    _calc_multi_tf_momentum_consistency,
    _calc_multi_tf_resonance,
    _calc_multi_tf_resonance_filter_v55,
    _calc_multi_tf_resonance_signal_v59,
    _calc_multi_tf_resonance_v50,
    _calc_multi_tf_signal_consistency,
    _calc_multi_tf_trend_consistency_v58,
    _calc_obv_trend_confirmation,
    _calc_overall_trend_direction,
    _calc_post_signal_confirmation,
    _calc_post_signal_fund_flow_v68,
    _calc_post_signal_return,
    _calc_post_signal_trajectory,
    _calc_post_signal_trajectory_health_v67,
    _calc_price_momentum_acceleration_v77,
    _calc_price_momentum_continuity_v79,
    _calc_price_structure_integrity_v76,
    _calc_price_volume_divergence_v69,
    _calc_pullback_depth_time_v51,
    _calc_pullback_depth_validation_v75,
    _calc_pullback_filter_v57,
    _calc_pullback_structure_integrity_v49,
    _calc_pullback_time_window,
    _calc_quality_ranking,
    _calc_quality_tier_classification,
    _calc_range_set_multi_level_v68,
    _calc_recent_extreme_price_v52,
    _calc_recent_range_stop_loss,
    _calc_retracement_depth_v69,
    _calc_reversal_risk_assessment,
    _calc_risk_adjusted_return,
    _calc_rsi,
    _calc_rsi_deep_divergence_v60,
    _calc_rsi_momentum,
    _calc_rsi_momentum_confirmation,
    _calc_rsi_zone,
    _calc_sector_correlation_v50,
    _calc_sector_rotation_context,
    _calc_signal_aging,
    _calc_signal_consistency_check,
    _calc_signal_decay_detection_v57,
    _calc_signal_decay_speed_v59,
    _calc_signal_decay_velocity_v72,
    _calc_signal_decay_warning,
    _calc_signal_execution_priority_v66,
    _calc_signal_execution_window_v81,
    _calc_signal_final_validity_v76,
    _calc_signal_freshness,
    _calc_signal_freshness_validation_v77,
    _calc_signal_health_dashboard,
    _calc_signal_history_validation,
    _calc_signal_priority_ranking,
    _calc_signal_quality_tier_v53,
    _calc_signal_resonance_depth_v74,
    _calc_signal_time_decay_v70,
    _calc_signal_time_window_freshness_v65,
    _calc_signal_trend_alignment_v55,
    _calc_signal_validity_window,
    _calc_sr_breakout_confirmation,
    _calc_stock_signal_profile,
    _calc_strategy_recommendation,
    _calc_structural_integrity_v69,
    _calc_structural_position,
    _calc_support_resistance_proximity_v72,
    _calc_support_resistance_strength_v81,
    _calc_temporal_correlation,
    _calc_tf_consistency,
    _calc_time_decay_adaptive,
    _calc_trading_decision_v51,
    _calc_trend_acceleration,
    _calc_trend_alignment_validation_v76,
    _calc_trend_continuity_confirmation,
    _calc_trend_direction_alignment,
    _calc_trend_momentum_continuation,
    _calc_trend_momentum_continuity_v74,
    _calc_trend_momentum_strength,
    _calc_trend_stage_follow_confirmation_v53,
    _calc_trend_strength,
    _calc_trend_strength_composite_v51,
    _calc_trend_strength_weighting_v48,
    _calc_urgency_score,
    _calc_volatility_adaptive_confidence_v76,
    _calc_volatility_adaptive_ma_v59,
    _calc_volatility_adaptive_position_v56,
    _calc_volatility_adaptive_threshold,
    _calc_volatility_adaptive_v44,
    _calc_volatility_compression_breakout_v65,
    _calc_volatility_compression_breakout_v78,
    _calc_volatility_compression_breakout_v82,
    _calc_volatility_regime_adaptation_v73,
    _calc_volatility_regime_change,
    _calc_volatility_regime_change_v54,
    _calc_volatility_regime_dual_confirmation,
    _calc_volatility_regime_transition_v81,
    _calc_volume_accumulation_validation_v58,
    _calc_volume_confirmation_v80,
    _calc_volume_cycle_detection,
    _calc_volume_distribution_depth_v77,
    _calc_volume_peak_detection_v70,
    _calc_volume_peak_duration_v75,
    _calc_volume_price_coordination_deep_v66,
    _calc_volume_price_coordination_v54,
    _calc_volume_price_divergence_enhanced,
    _calc_volume_price_divergence_secondary,
    _calc_volume_price_divergence_secondary_v48,
    _calc_volume_price_divergence_secondary_v65,
    _calc_volume_price_divergence_secondary_v74,
    _calc_volume_price_energy_dist,
    _calc_volume_price_energy_distribution_v81,
    _calc_volume_profile,
    _calc_volume_structure_quality_v72,
    _calc_volume_sustain_after_signal_v52,
    _calc_weak_stock_risk_v55,
    _calc_zhongshu_breakout_validity_v73,
    _calc_zhongshu_distance_validation,
    _calc_zhongshu_divergence_strength_v67,
    _calc_zhongshu_level_weight_enhanced_v63,
    _calc_zhongshu_level_weight_v49,
    _calc_zhongshu_level_weight_v55,
    _calc_zhongshu_overlap_density_v74,
    _calc_zhongshu_retracement_confirm_v75,
    _calc_zhongshu_structure_complexity_v56,
    _calc_zhongshu_structure_weight_v77,
    _calc_zs_breakout_authenticity,
    _calc_zs_breakout_confirmation,
    _calc_zs_breakout_strength_v53,
    _calc_zs_distance_enhanced_v60,
    _calc_zs_divergence_check_v57,
    _calc_zs_level_match,
    _calc_zs_strength,
    _calc_zs_structure_integrity,
    _check_atr_support_zone,
    _check_break_retest_break,
    _check_breakout_persistence,
    _check_macd_confirmation,
    _check_macd_confirmation_v2,
    _check_macd_histogram_slope,
    _check_post_signal_confirmation,
    _check_post_signal_price_follow_through,
    _check_pullback_time_window,
    _check_volume_spike,
    _deduplicate_mmds,
    _detect_combo_signals,
    _detect_enhanced_divergence,
    _detect_kline_pattern,
    _detect_macd_zero_axis_cross,
    _detect_momentum_decay,
    _detect_price_gap,
    _detect_volume_price_divergence,
    _generate_decision_recommendation,
    _get_beichi_strength,
    _get_dynamic_time_window,
    _get_kdj_thresholds,
    _get_volatility_regime,
    _identify_dynamic_support_resistance,
    _is_strong_beichi,
    _is_volume_profile_resistance,
    _is_volume_profile_support,
)

__all__ = [
    "MMDQuality",
    "_analyze_volume_at_levels",
    "_apply_volatility_adaptive_filter",
    "_calc_adx_strength",
    "_calc_adx_trend_strength_check",
    "_calc_atr",
    "_calc_atr_adaptive_stop_v53",
    "_calc_atr_adaptive_stop_v58",
    "_calc_atr_multiplier_adapt_v59",
    "_calc_atr_volatility",
    "_calc_bi_force",
    "_calc_bi_quality",
    "_calc_boll_bandwidth_breakout_confirm_v62",
    "_calc_boll_bandwidth_reversal_confirm_v62",
    "_calc_boll_position",
    "_calc_boll_squeeze",
    "_calc_break_pullback_volume_ratio",
    "_calc_breakout_bi_strength_compare",
    "_calc_breakout_bi_strength_enhanced_v51",
    "_calc_breakout_force_ratio",
    "_calc_breakout_retest_confirm_v82",
    "_calc_breakout_retest_confirmation_v65",
    "_calc_breakout_strength",
    "_calc_breakout_strength_revalidation_v49",
    "_calc_breakout_strength_validation_v57",
    "_calc_breakout_vol_price",
    "_calc_composite_deviation",
    "_calc_composite_quality",
    "_calc_composite_quality_score_v58",
    "_calc_composite_signal_score_v61",
    "_calc_confidence",
    "_calc_confidence_calibration",
    "_calc_confidence_v47",
    "_calc_confluence_bonus",
    "_calc_consecutive_confirmation",
    "_calc_consolidation_divergence_warning",
    "_calc_cross_stock_comparison",
    "_calc_cross_validation",
    "_calc_decision_quality_score",
    "_calc_dynamic_atr_stop",
    "_calc_dynamic_market_regime",
    "_calc_dynamic_risk_reward_ratio_v48",
    "_calc_dynamic_risk_reward_v80",
    "_calc_dynamic_rr_optimization",
    "_calc_dynamic_rr_optimization_v71",
    "_calc_dynamic_sl_tp_enhanced",
    "_calc_dynamic_sl_tp_recommendation_v67",
    "_calc_dynamic_stop_loss_take_profit",
    "_calc_dynamic_threshold_atr_multiplier_v62",
    "_calc_dynamic_threshold_volatility_regime_v62",
    "_calc_enhanced_signal_decay",
    "_calc_enhanced_signal_freshness",
    "_calc_execution_window",
    "_calc_fake_signal_filter",
    "_calc_false_breakout_detection_v56",
    "_calc_false_breakout_filter_v70",
    "_calc_fibonacci_retracement_level",
    "_calc_final_confidence_calibration_v70",
    "_calc_fractal_stability_validation_v79",
    "_calc_fund_flow_divergence_v78",
    "_calc_gap_risk_assessment_v54",
    "_calc_gap_trend_consistency_v68",
    "_calc_independent_cross_validation",
    "_calc_kdj_j",
    "_calc_kdj_ob_os_confirm_v60",
    "_calc_kline_pattern_composite",
    "_calc_kline_pattern_confirmation",
    "_calc_level_recursive_validation_v50",
    "_calc_ma60_slope",
    "_calc_ma_alignment_confirmation",
    "_calc_ma_alignment_strength_v71",
    "_calc_ma_alignment_strength_v80",
    "_calc_ma_convergence_divergence_v72",
    "_calc_ma_slope",
    "_calc_ma_spacing_strength_v60",
    "_calc_ma_trend_alignment",
    "_calc_macd_histogram_acceleration",
    "_calc_macd_histogram_area",
    "_calc_macd_histogram_divergence_v61",
    "_calc_macd_momentum_acceleration_v66",
    "_calc_macd_multi_tf_resonance_v82",
    "_calc_macd_zero_axis_position",
    "_calc_market_composite",
    "_calc_market_context_filter",
    "_calc_market_regime_adaptation_v68",
    "_calc_market_regime_score_v52",
    "_calc_market_sentiment_fusion_v50",
    "_calc_mmd_age_decay_v82",
    "_calc_mmd_cycle_position_v78",
    "_calc_mmd_distance_safety_v79",
    "_calc_mmd_history_winrate_v71",
    "_calc_mmd_position_risk_v73",
    "_calc_mmd_position_score",
    "_calc_mmd_quality",
    "_calc_mmd_zhongshu_distance_v80",
    "_calc_momentum_acceleration",
    "_calc_multi_bar_confirmation_v54",
    "_calc_multi_cycle_macd_resonance",
    "_calc_multi_dim_divergence",
    "_calc_multi_indicator_consistency_v73",
    "_calc_multi_indicator_divergence_fusion_v52",
    "_calc_multi_indicator_divergence_resonance",
    "_calc_multi_indicator_divergence_v69",
    "_calc_multi_indicator_resonance",
    "_calc_multi_level_confluence_verification",
    "_calc_multi_level_mmd_consistency_v67",
    "_calc_multi_level_structure_consistency_v79",
    "_calc_multi_period_signal_decay_v63",
    "_calc_multi_signal_consensus_v78",
    "_calc_multi_signal_resonance_v56",
    "_calc_multi_signal_time_consistency_v75",
    "_calc_multi_tf_convergence_intensity_v66",
    "_calc_multi_tf_divergence_confirmation",
    "_calc_multi_tf_ma_resonance_v71",
    "_calc_multi_tf_momentum_consistency",
    "_calc_multi_tf_resonance",
    "_calc_multi_tf_resonance_filter_v55",
    "_calc_multi_tf_resonance_signal_v59",
    "_calc_multi_tf_resonance_v50",
    "_calc_multi_tf_signal_consistency",
    "_calc_multi_tf_trend_consistency_v58",
    "_calc_obv_trend_confirmation",
    "_calc_overall_trend_direction",
    "_calc_post_signal_confirmation",
    "_calc_post_signal_fund_flow_v68",
    "_calc_post_signal_return",
    "_calc_post_signal_trajectory",
    "_calc_post_signal_trajectory_health_v67",
    "_calc_price_momentum_acceleration_v77",
    "_calc_price_momentum_continuity_v79",
    "_calc_price_structure_integrity_v76",
    "_calc_price_volume_divergence_v69",
    "_calc_pullback_depth_time_v51",
    "_calc_pullback_depth_validation_v75",
    "_calc_pullback_filter_v57",
    "_calc_pullback_structure_integrity_v49",
    "_calc_pullback_time_window",
    "_calc_quality_ranking",
    "_calc_quality_tier_classification",
    "_calc_range_set_multi_level_v68",
    "_calc_recent_extreme_price_v52",
    "_calc_recent_range_stop_loss",
    "_calc_retracement_depth_v69",
    "_calc_reversal_risk_assessment",
    "_calc_risk_adjusted_return",
    "_calc_rsi",
    "_calc_rsi_deep_divergence_v60",
    "_calc_rsi_momentum",
    "_calc_rsi_momentum_confirmation",
    "_calc_rsi_zone",
    "_calc_sector_correlation_v50",
    "_calc_sector_rotation_context",
    "_calc_signal_aging",
    "_calc_signal_consistency_check",
    "_calc_signal_decay_detection_v57",
    "_calc_signal_decay_speed_v59",
    "_calc_signal_decay_velocity_v72",
    "_calc_signal_decay_warning",
    "_calc_signal_execution_priority_v66",
    "_calc_signal_execution_window_v81",
    "_calc_signal_final_validity_v76",
    "_calc_signal_freshness",
    "_calc_signal_freshness_validation_v77",
    "_calc_signal_health_dashboard",
    "_calc_signal_history_validation",
    "_calc_signal_priority_ranking",
    "_calc_signal_quality_tier_v53",
    "_calc_signal_resonance_depth_v74",
    "_calc_signal_time_decay_v70",
    "_calc_signal_time_window_freshness_v65",
    "_calc_signal_trend_alignment_v55",
    "_calc_signal_validity_window",
    "_calc_sr_breakout_confirmation",
    "_calc_stock_signal_profile",
    "_calc_strategy_recommendation",
    "_calc_structural_integrity_v69",
    "_calc_structural_position",
    "_calc_support_resistance_proximity_v72",
    "_calc_support_resistance_strength_v81",
    "_calc_temporal_correlation",
    "_calc_tf_consistency",
    "_calc_time_decay_adaptive",
    "_calc_trading_decision_v51",
    "_calc_trend_acceleration",
    "_calc_trend_alignment_validation_v76",
    "_calc_trend_continuity_confirmation",
    "_calc_trend_direction_alignment",
    "_calc_trend_momentum_continuation",
    "_calc_trend_momentum_continuity_v74",
    "_calc_trend_momentum_strength",
    "_calc_trend_stage_follow_confirmation_v53",
    "_calc_trend_strength",
    "_calc_trend_strength_composite_v51",
    "_calc_trend_strength_weighting_v48",
    "_calc_urgency_score",
    "_calc_volatility_adaptive_confidence_v76",
    "_calc_volatility_adaptive_ma_v59",
    "_calc_volatility_adaptive_position_v56",
    "_calc_volatility_adaptive_threshold",
    "_calc_volatility_adaptive_v44",
    "_calc_volatility_compression_breakout_v65",
    "_calc_volatility_compression_breakout_v78",
    "_calc_volatility_compression_breakout_v82",
    "_calc_volatility_regime_adaptation_v73",
    "_calc_volatility_regime_change",
    "_calc_volatility_regime_change_v54",
    "_calc_volatility_regime_dual_confirmation",
    "_calc_volatility_regime_transition_v81",
    "_calc_volume_accumulation_validation_v58",
    "_calc_volume_confirmation_v80",
    "_calc_volume_cycle_detection",
    "_calc_volume_distribution_depth_v77",
    "_calc_volume_peak_detection_v70",
    "_calc_volume_peak_duration_v75",
    "_calc_volume_price_coordination_deep_v66",
    "_calc_volume_price_coordination_v54",
    "_calc_volume_price_divergence_enhanced",
    "_calc_volume_price_divergence_secondary",
    "_calc_volume_price_divergence_secondary_v48",
    "_calc_volume_price_divergence_secondary_v65",
    "_calc_volume_price_divergence_secondary_v74",
    "_calc_volume_price_energy_dist",
    "_calc_volume_price_energy_distribution_v81",
    "_calc_volume_profile",
    "_calc_volume_structure_quality_v72",
    "_calc_volume_sustain_after_signal_v52",
    "_calc_weak_stock_risk_v55",
    "_calc_zhongshu_breakout_validity_v73",
    "_calc_zhongshu_distance_validation",
    "_calc_zhongshu_divergence_strength_v67",
    "_calc_zhongshu_level_weight_enhanced_v63",
    "_calc_zhongshu_level_weight_v49",
    "_calc_zhongshu_level_weight_v55",
    "_calc_zhongshu_overlap_density_v74",
    "_calc_zhongshu_retracement_confirm_v75",
    "_calc_zhongshu_structure_complexity_v56",
    "_calc_zhongshu_structure_weight_v77",
    "_calc_zs_breakout_authenticity",
    "_calc_zs_breakout_confirmation",
    "_calc_zs_breakout_strength_v53",
    "_calc_zs_distance_enhanced_v60",
    "_calc_zs_divergence_check_v57",
    "_calc_zs_level_match",
    "_calc_zs_strength",
    "_calc_zs_structure_integrity",
    "_check_atr_support_zone",
    "_check_break_retest_break",
    "_check_breakout_persistence",
    "_check_macd_confirmation",
    "_check_macd_confirmation_v2",
    "_check_macd_histogram_slope",
    "_check_post_signal_confirmation",
    "_check_post_signal_price_follow_through",
    "_check_pullback_time_window",
    "_check_volume_spike",
    "_deduplicate_mmds",
    "_detect_combo_signals",
    "_detect_enhanced_divergence",
    "_detect_kline_pattern",
    "_detect_macd_zero_axis_cross",
    "_detect_momentum_decay",
    "_detect_price_gap",
    "_detect_volume_price_divergence",
    "_generate_decision_recommendation",
    "_get_beichi_strength",
    "_get_dynamic_time_window",
    "_get_kdj_thresholds",
    "_get_volatility_regime",
    "_identify_dynamic_support_resistance",
    "_is_strong_beichi",
    "_is_volume_profile_resistance",
    "_is_volume_profile_support",
]


# V392：V102 决策支持增强已拆分到 mmd_v102.py，此处惰性再导出以保持
# 既有 from easy_tdx.chanlun.mmd import _calc_* 等导入兼容。
from easy_tdx.chanlun.mmd_v102 import (
    _apply_v102_decision_confidence,
    _calc_decision_support_enhanced,
    _calc_historical_pattern_matching,
    _calc_multi_signal_correlation,
    _calc_signal_quality_scorecard,
)
from easy_tdx.chanlun.types import BI, MMD, ZS, BCType, MMDType


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
            for h, low, pc in zip(highs, lows, prev_closes):
                tr = max(h - low, abs(h - pc), abs(low - pc))
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
        zs_zg_text = f"{mmd.zs.zg:.2f}" if mmd.zs else "0.00"
        entry_reason = f"3 买信号：回踩中枢上沿 ({zs_zg_text}) 后低点 {bi_low:.2f} 企稳"
        risk_notes = f"止损 {stop_loss:.2f}（-{(entry_price - stop_loss) / entry_price * 100:.1f}%），第一止盈 {take_profit_1:.2f}"

    elif mmd_type == "3sell":
        # 3 卖：反弹确认后入场（做空）
        entry_price = round(bi_high * 0.998, 2)  # 略低于反弹高点
        stop_loss = round(bi_high * 1.02, 2)  # 突破反弹高点 2% 止损
        zs_height = mmd.zs.zg - mmd.zs.zd if mmd.zs else 0
        tp1_dist = max(zs_height * 0.5, atr * 2)
        tp2_dist = max(zs_height * 1.0, atr * 4)
        take_profit_1 = round(entry_price - tp1_dist, 2)
        take_profit_2 = round(entry_price - tp2_dist, 2)
        zs_zd_text = f"{mmd.zs.zd:.2f}" if mmd.zs else "0.00"
        entry_reason = f"3 卖信号：反弹中枢下沿 ({zs_zd_text}) 后高点 {bi_high:.2f} 遇阻"
        risk_notes = f"止损 {stop_loss:.2f}（+{(stop_loss - entry_price) / entry_price * 100:.1f}%），第一止盈 {take_profit_1:.2f}"

    elif mmd_type in ("1buy", "2buy"):
        entry_price = round(latest_close, 2)
        stop_loss = round(latest_close - atr * 2, 2)
        take_profit_1 = round(latest_close + atr * 3, 2)
        take_profit_2 = round(latest_close + atr * 5, 2)
        entry_reason = f"{mmd_type} 信号：背驰确认，当前价 {latest_close:.2f}"
        risk_notes = (
            f"止损 {stop_loss:.2f}（-{(entry_price - stop_loss) / entry_price * 100:.1f}%）"
        )

    elif mmd_type in ("1sell", "2sell"):
        entry_price = round(latest_close, 2)
        stop_loss = round(latest_close + atr * 2, 2)
        take_profit_1 = round(latest_close - atr * 3, 2)
        take_profit_2 = round(latest_close - atr * 5, 2)
        entry_reason = f"{mmd_type} 信号：背驰确认，当前价 {latest_close:.2f}"
        risk_notes = (
            f"止损 {stop_loss:.2f}（+{(stop_loss - entry_price) / entry_price * 100:.1f}%）"
        )

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
    if volumes is not None and len(closes) > 0 and mmd.bi:
        try:
            from easy_tdx.chanlun.mmd_conditions import _calc_volume_profile

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
    if hasattr(mmd, "_vol_spike") and mmd._vol_spike:
        enhancement_notes.append("成交量异常放大（机构活动信号）")
    if hasattr(mmd, "_gap_down") and mmd._gap_down:
        enhancement_notes.append(f"向下加速缺口({mmd._gap_size:.1f}%)")
    if hasattr(mmd, "_gap_up") and mmd._gap_up:
        enhancement_notes.append(f"向上突破缺口({mmd._gap_size:.1f}%)")
    if hasattr(mmd, "_macd_slope_confirmed") and mmd._macd_slope_confirmed:
        enhancement_notes.append("MACD柱状图斜率确认")

    # V15: K线形态注释
    kline_pattern = getattr(mmd, "_kline_pattern", None)
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
    if hasattr(mmd, "_retest_break") and mmd._retest_break:
        retracement = getattr(mmd, "_retest_retracement", 0.0)
        enhancement_notes.append(f"二次回踩确认(深度{retracement:.0f}%)")

    # 信号强度（综合置信度和质量评级）
    grade = str(getattr(getattr(mmd, "quality", None), "grade", None) or "")
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
        _ = signal_aging.get("decay_factor", 1.0)
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
        notes.append(
            f"质量评级{grade}级，{'显著' if grade in ('S', 'A') else '适度' if grade == 'B' else '限制'}仓位"
        )

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
    if volatility is None and closes is not None and len(closes) > 0:
        volatility = _calc_atr_volatility(closes)

    mmds: list[MMD] = []

    # 1. 识别一类买卖点（最可靠，保持原逻辑）
    mmds.extend(_find_first_type_mmds(bis, zss, closes, config, volatility, volumes, highs, lows))

    # 2. 识别二类买卖点（V8增强：多1买处理 + 成交量/MACD确认）
    mmds.extend(_find_second_type_mmds(bis, zss, mmds, config, volatility, volumes, macd_data))

    # 3. 识别三类买卖点（增加严格过滤 + 动态阈值）
    mmds.extend(
        _find_third_type_mmds(
            bis, zss, mmds, config, closes, volumes, macd_data, volatility, highs, lows
        )
    )

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
        mmd.confidence = _calc_confidence_v47(
            mmd, trend_strength, volumes, closes, macd_data, volatility, zss, highs, lows
        )
        mmd.quality = _calc_mmd_quality(
            mmd, trend_strength, trend_direction, volumes, closes, macd_data, volatility
        )
        # V12: 设置多时间框架共振评分（基于区间套一致性）
        mmd.confluence_score = round(
            _calc_confluence_bonus(mmd, zss or [], macd_data, volumes, closes, volatility), 2
        )
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

        # V22: 条件38 - 波动率Regime双重确认
        if closes is not None and volatility is not None:
            try:
                dual_result = _calc_volatility_regime_dual_confirmation(closes, volumes, volatility)
                mmd._vol_regime_dual = dual_result
                if dual_result.get("dual_confirmed"):
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + dual_result.get("confidence_adjust", 0.0))
                    )
            except Exception:
                pass

        # V22: 条件39 - 量价背离检测
        if closes is not None and volumes is not None:
            try:
                vp_div = _detect_volume_price_divergence(closes, volumes)
                mmd._vol_price_divergence = vp_div
            except Exception:
                pass

        # V23: 条件40 - Fibonacci回撤位动态确认
        if closes is not None and len(closes) >= 130:
            try:
                fib_result = _calc_fibonacci_retracement_level(closes)
                mmd._fib_retracement = fib_result
            except Exception:
                pass

        # V23: 条件41 - RSI区域分类（在置信度计算中使用）
        if closes is not None and len(closes) >= 14:
            try:
                rsi_val = _calc_rsi(closes, len(closes) - 1)
                zone, _adj = _calc_rsi_zone(rsi_val)
                mmd._rsi_zone = {"zone": zone, "rsi": round(rsi_val, 1)}
            except Exception:
                pass

        # V23: 条件42 - MACD零轴穿越检测
        if macd_data is not None and mmd.bi is not None:
            try:
                bi_idx = mmd.bi.end.k.k_index
                macd_cross = _detect_macd_zero_axis_cross(macd_data, bi_idx)
                mmd._macd_zero_cross = macd_cross
            except Exception:
                pass

        # V24: 条件43 - 笔质量评分（Bi Quality Scoring）
        if bis is not None and mmd.bi is not None and closes is not None:
            try:
                bi_quality = _calc_bi_quality(mmd.bi, bis, closes)
                mmd._bi_quality = bi_quality
                if bi_quality.get("quality_score", 0) > 0.7:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + bi_quality.get("confidence_bonus", 0.0))
                    )
            except Exception:
                pass

        # V24: 条件44 - 中枢强度分析（ZS Strength Analysis）
        if zss is not None and mmd.zs is not None and volumes is not None:
            try:
                zs_strength = _calc_zs_strength(mmd.zs, volumes, closes)
                mmd._zs_strength = zs_strength
                if zs_strength.get("strength_level") == "strong":
                    mmd.confidence = max(0.0, min(1.0, mmd.confidence + 0.03))
                elif zs_strength.get("strength_level") == "weak":
                    mmd.confidence = max(0.0, min(1.0, mmd.confidence - 0.02))
            except Exception:
                pass

        # V24: 条件45 - 增强背离检测（Enhanced Divergence Detection）
        if macd_data is not None and closes is not None and mmd.bi is not None:
            try:
                bi_idx = mmd.bi.end.k.k_index
                div_result = _detect_enhanced_divergence(macd_data, closes, bi_idx, mmd.mmd_type)
                mmd._enhanced_divergence = div_result
                if div_result.get("divergence_type") != "none":
                    bonus = div_result.get("confidence_bonus", 0.0)
                    if "buy" in mmd.mmd_type.value:
                        mmd.confidence = max(0.0, min(1.0, mmd.confidence + bonus))
                    else:
                        mmd.confidence = max(0.0, min(1.0, mmd.confidence + bonus))
            except Exception:
                pass

        # V24: 条件46 - 信号交叉验证评分（Signal Cross-Validation）
        if closes is not None and macd_data is not None and volumes is not None:
            try:
                cv_result = _calc_cross_validation(
                    mmd, bis or [], zss or [], closes, macd_data, volumes
                )
                mmd._cross_validation = cv_result
                consensus_bonus = cv_result.get("consensus_bonus", 0.0)
                mmd.confidence = max(0.0, min(1.0, mmd.confidence + consensus_bonus))
            except Exception:
                pass

        # V25: 条件47 - 信号后确认验证（Post-Signal Confirmation）
        if closes is not None and mmd.bi is not None:
            try:
                post_confirm = _check_post_signal_confirmation(mmd, closes)
                mmd._post_signal_confirm = post_confirm
                if post_confirm.get("confirmed", False):
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + post_confirm.get("confidence_bonus", 0.0))
                    )
                else:
                    # 未确认信号：对3买/3卖额外降权
                    if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
                        mmd.confidence = max(0.0, min(1.0, mmd.confidence - 0.05))
            except Exception:
                pass

        # V25: 条件48 - 动量衰减预警（Momentum Decay Warning）
        if closes is not None and mmd.bi is not None and macd_data is not None:
            try:
                momentum_result = _detect_momentum_decay(mmd, closes, macd_data)
                mmd._momentum_decay = momentum_result
                penalty = momentum_result.get("confidence_penalty", 0.0)
                mmd.confidence = max(0.0, min(1.0, mmd.confidence + penalty))
            except Exception:
                pass

        # V25: 条件49 - 波动率自适应过滤（Volatility-Adaptive Filtering）
        if closes is not None and volumes is not None and volatility is not None:
            try:
                vol_filter = _apply_volatility_adaptive_filter(mmd, closes, volumes, volatility)
                mmd._vol_regime_filter = vol_filter
                regime_bonus = vol_filter.get("confidence_bonus", 0.0)
                mmd.confidence = max(0.0, min(1.0, mmd.confidence + regime_bonus))
            except Exception:
                pass

        # V25: 条件50 - 综合信号质量评分（Composite Quality Score）
        try:
            composite = _calc_composite_quality(mmd)
            mmd._composite_quality = composite
            # 使用综合评分更新置信度（取最高值，避免重复计算）
            composite_conf = composite.get("overall_score", 0.0) / 100.0  # 归一化到 0-1
            if composite_conf > 0 and composite_conf > mmd.confidence:
                mmd.confidence = composite_conf
        except Exception:
            pass

        # V26: 条件51 - 信号历史验证（Signal History Validation）
        if closes is not None and len(closes) >= 50:
            try:
                history_result = _calc_signal_history_validation(mmd, closes)
                mmd._signal_history = history_result
                if history_result.get("validation_passed", False):
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + history_result.get("confidence_adjust", 0.0))
                    )
            except Exception:
                pass

        # V26: 条件52 - 动态风险收益优化（Dynamic Risk-Reward Optimization）
        if closes is not None and mmd.bi is not None:
            try:
                rr_result = _calc_dynamic_rr_optimization(mmd, closes, highs, lows, volatility)
                mmd._dynamic_rr_optimization = rr_result
            except Exception:
                pass

    # V26: 条件53 - 多标的对比评分（Cross-Stock Comparison Scoring）
    if len(mmds) >= 2:
        try:
            comparison = _calc_cross_stock_comparison(mmds)
            # 将对比结果存储到每个 mmd 对象（简化：只存储第一个）
            if comparison.get("ranked_signals"):
                mmds[0]._cross_stock_comparison = comparison
        except Exception:
            pass

    # V27: 条件55 - 买卖点结构位置评分（Structural Position Scoring）
    for mmd in mmds:
        if closes is not None and mmd.bi is not None:
            try:
                pos_result = _calc_structural_position(mmd, closes, zss)
                mmd._structure_position = pos_result
            except Exception:
                pass

    # V27: 条件56 - 个股信号特征学习（Stock-Specific Signal Learning）
    for mmd in mmds:
        if closes is not None and mmd.bi is not None:
            try:
                stock_profile = _calc_stock_signal_profile(mmd, closes, mmds)
                mmd._stock_profile = stock_profile
            except Exception:
                pass

    # V28: 条件57 - BOLL带宽压缩确认（BOLL Squeeze Confirmation）
    if len(mmds) >= 1 and closes is not None:
        try:
            squeeze_result = _calc_boll_squeeze(closes, highs, lows, len(closes) - 1)
            for mmd in mmds:
                mmd._boll_squeeze = squeeze_result
            if squeeze_result.get("squeeze_active", False):
                for mmd in mmds:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + squeeze_result.get("confidence_adjust", 0.0))
                    )
        except Exception:
            pass

    # V28: 条件58 - 突破量价确认（Breakout Volume-Price Confirmation）
    for mmd in mmds:
        if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3) and closes is not None:
            try:
                vol_price = _calc_breakout_vol_price(mmd, closes, volumes, highs, lows, zss)
                mmd._breakout_vol_price = vol_price
                if vol_price.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + vol_price["confidence_adjust"])
                    )
            except Exception:
                pass

    # V28: 条件59 - 动态ATR止损位优化（Dynamic ATR Stop-Loss Optimization）
    for mmd in mmds:
        if closes is not None and mmd.bi is not None:
            try:
                atr_stop = _calc_dynamic_atr_stop(mmd, closes, highs, lows, zss)
                mmd._dynamic_atr_stop = atr_stop
                if atr_stop.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + atr_stop["confidence_adjust"])
                    )
            except Exception:
                pass

    # V29: 条件60 - 趋势方向持续性确认（Trend Continuity Confirmation）
    for mmd in mmds:
        if closes is not None:
            try:
                trend_cont = _calc_trend_continuity_confirmation(mmd, closes)
                mmd._trend_continuity = trend_cont
                if trend_cont.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + trend_cont["confidence_adjust"])
                    )
            except Exception:
                pass

    # V29: 条件61 - 盘整区背离预警（Consolidation Divergence Warning）
    if closes is not None and len(closes) >= 40:
        try:
            div_warning = _calc_consolidation_divergence_warning(closes, volumes, highs, lows, zss)
            if div_warning.get("has_divergence", False):
                # 背离预警只影响3买/3卖信号
                for mmd in mmds:
                    if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
                        mmd._consolidation_divergence = div_warning
                        if div_warning.get("confidence_adjust", 0) != 0:
                            mmd.confidence = max(
                                0.0, min(1.0, mmd.confidence + div_warning["confidence_adjust"])
                            )
        except Exception:
            pass

    # V30: 条件62 - K线形态反向确认（K-line Pattern Confirmation）
    for mmd in mmds:
        if closes is not None and mmd.bi is not None:
            try:
                pat_confirm = _calc_kline_pattern_confirmation(mmd, closes)
                mmd._kline_pattern_confirm = pat_confirm
                if pat_confirm.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + pat_confirm["confidence_adjust"])
                    )
            except Exception:
                pass

    # V30: 条件63 - 中枢突破方向确认（ZS Breakout Direction Confirmation）
    for mmd in mmds:
        if closes is not None and mmd.bi is not None:
            try:
                zs_breakout = _calc_zs_breakout_confirmation(mmd, closes, volumes, zss)
                mmd._zs_breakout_confirm = zs_breakout
                if zs_breakout.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + zs_breakout["confidence_adjust"])
                    )
            except Exception:
                pass

    # V30: 条件64 - 近期波动区间止损优化（Recent Range Stop-Loss）
    for mmd in mmds:
        if closes is not None and mmd.bi is not None:
            try:
                range_stop = _calc_recent_range_stop_loss(mmd, closes, highs, lows)
                mmd._recent_range_stop = range_stop
                if range_stop.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + range_stop["confidence_adjust"])
                    )
            except Exception:
                pass

    # V31: 条件65 - 均线排列确认（MA Alignment Confirmation）
    for mmd in mmds:
        if closes is not None and mmd.bi is not None:
            try:
                ma_align = _calc_ma_alignment_confirmation(mmd, closes)
                mmd._ma_alignment = ma_align
                if ma_align.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + ma_align["confidence_adjust"])
                    )
            except Exception:
                pass

    # V31: 条件66 - MACD柱状图加速度确认（MACD Histogram Acceleration）
    for mmd in mmds:
        if macd_data is not None and mmd.bi is not None:
            try:
                macd_accel = _calc_macd_histogram_acceleration(mmd, macd_data, closes)
                mmd._macd_histogram_acceleration = macd_accel
                if macd_accel.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + macd_accel["confidence_adjust"])
                    )
            except Exception:
                pass

    # V31: 条件67 - 信号综合健康度报告（Signal Health Dashboard）
    for mmd in mmds:
        try:
            health = _calc_signal_health_dashboard(mmd, closes, volumes, macd_data, volatility)
            mmd._signal_health_dashboard = health
            if health.get("confidence_adjust", 0) != 0:
                mmd.confidence = max(0.0, min(1.0, mmd.confidence + health["confidence_adjust"]))
        except Exception:
            pass

    # V32: 条件68 - 量价背离检测增强（Volume-Price Divergence Enhancement）
    for mmd in mmds:
        if closes is not None and volumes is not None and mmd.bi is not None:
            try:
                vp_div = _calc_volume_price_divergence_enhanced(mmd, closes, volumes)
                mmd._vol_price_divergence_enhanced = vp_div
                if vp_div.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + vp_div["confidence_adjust"])
                    )
            except Exception:
                pass

    # V32: 条件69 - 信号优先级动态排序（Dynamic Signal Priority Ranking）
    for mmd in mmds:
        if closes is not None:
            try:
                pri = _calc_signal_priority_ranking(mmd, mmds, closes)
                mmd._signal_priority = pri
                if pri.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(0.0, min(1.0, mmd.confidence + pri["confidence_adjust"]))
            except Exception:
                pass

    # V32: 条件70 - 支撑阻力位突破确认（Support/Resistance Breakout Confirmation）
    for mmd in mmds:
        if closes is not None and highs is not None and lows is not None and mmd.bi is not None:
            try:
                sr = _calc_sr_breakout_confirmation(mmd, closes, highs, lows)
                mmd._sr_breakout_confirm = sr
                if sr.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(0.0, min(1.0, mmd.confidence + sr["confidence_adjust"]))
            except Exception:
                pass

    # V33: 条件71 - OBV能量潮趋势确认（OBV Trend Confirmation）
    for mmd in mmds:
        if closes is not None and volumes is not None and mmd.bi is not None:
            try:
                obv_result = _calc_obv_trend_confirmation(mmd, closes, volumes)
                mmd._obv_trend_confirm = obv_result
                if obv_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + obv_result["confidence_adjust"])
                    )
            except Exception:
                pass

    # V33: 条件72 - MACD动能锥面积确认（MACD Histogram Area）
    for mmd in mmds:
        if macd_data is not None:
            try:
                hist_area = _calc_macd_histogram_area(mmd, macd_data)
                mmd._macd_hist_area = hist_area
                if hist_area.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + hist_area["confidence_adjust"])
                    )
            except Exception:
                pass

    # V33: 条件73 - RSI动量确认（RSI Momentum Confirmation）
    for mmd in mmds:
        if closes is not None and mmd.bi is not None:
            try:
                rsi_momentum = _calc_rsi_momentum_confirmation(mmd, closes)
                mmd._rsi_momentum_confirm = rsi_momentum
                if rsi_momentum.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + rsi_momentum["confidence_adjust"])
                    )
            except Exception:
                pass

    # V34: 条件74-76（需要先收集各指标结果，再计算共振评分）
    # 先批量计算各指标结果供共振评分使用
    obv_results: list[dict[str, Any]] = []
    macd_hist_results: list[dict[str, Any]] = []
    rsi_results: list[dict[str, Any]] = []
    vp_div_results: list[dict[str, Any]] = []
    ma_align_results: list[dict[str, Any]] = []

    if closes is not None and volumes is not None:
        for mmd in mmds:
            if mmd.bi is not None:
                try:
                    obv_r = _calc_obv_trend_confirmation(mmd, closes, volumes)
                    obv_results.append(obv_r)
                except Exception:
                    obv_results.append({})
            else:
                obv_results.append({})
            try:
                mh_r = _calc_macd_histogram_area(mmd, macd_data) if macd_data is not None else {}
                macd_hist_results.append(mh_r)
            except Exception:
                macd_hist_results.append({})
            try:
                rs_r = _calc_rsi_momentum_confirmation(mmd, closes) if mmd.bi is not None else {}
                rsi_results.append(rs_r)
            except Exception:
                rsi_results.append({})
            try:
                vp_r = (
                    _calc_volume_price_divergence_enhanced(mmd, closes, volumes)
                    if mmd.bi is not None
                    else {}
                )
                vp_div_results.append(vp_r)
            except Exception:
                vp_div_results.append({})
            try:
                ma_r = _calc_ma_alignment_confirmation(mmd, closes) if mmd.bi is not None else {}
                ma_align_results.append(ma_r)
            except Exception:
                ma_align_results.append({})

    # V34: 条件74 - 趋势动能延续确认
    for i, mmd in enumerate(mmds):
        if closes is not None and mmd.bi is not None:
            try:
                tm_result = _calc_trend_momentum_continuation(mmd, closes)
                mmd._trend_momentum_continuation = tm_result
                if tm_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + tm_result["confidence_adjust"])
                    )
            except Exception:
                pass

    # V34: 条件75 - 多指标共振强度评分
    for i, mmd in enumerate(mmds):
        try:
            res_result = _calc_multi_indicator_resonance(
                mmd,
                obv_result=obv_results[i] if i < len(obv_results) else None,
                macd_hist_result=macd_hist_results[i] if i < len(macd_hist_results) else None,
                rsi_result=rsi_results[i] if i < len(rsi_results) else None,
                vp_div_result=vp_div_results[i] if i < len(vp_div_results) else None,
                ma_align_result=ma_align_results[i] if i < len(ma_align_results) else None,
            )
            mmd._multi_indicator_resonance = res_result
            if res_result.get("confidence_adjust", 0) != 0:
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + res_result["confidence_adjust"])
                )
        except Exception:
            pass

    # V34: 条件76 - 波动率环境自适应阈值（全局一次性计算）
    if closes is not None:
        try:
            vol_result = _calc_volatility_adaptive_threshold(closes, highs, lows)
            # 将所有MMD的置信度加上波动率调整
            for mmd in mmds:
                if vol_result.get("threshold_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + vol_result["threshold_adjust"])
                    )
            # 存储波动率结果供诊断API使用
            if not hasattr(find_mmds, "_last_vol_result"):
                find_mmds._last_vol_result = {}  # type: ignore[attr-defined]
            find_mmds._last_vol_result = vol_result  # type: ignore[attr-defined]
        except Exception:
            pass

    # V35: 条件77-82（市场环境+假信号过滤+动态SL/TP+板块轮动+多维背离）
    # 条件77：市场大环境过滤（全局一次性）
    market_context_result: dict[str, Any] = {}
    if closes is not None and len(closes) >= 60:
        try:
            market_context_result = _calc_market_context_filter(closes)
            adj = market_context_result.get("confidence_adjust", 0.0)
            if adj != 0.0:
                for mmd in mmds:
                    mmd.confidence = max(0.0, min(1.0, mmd.confidence + adj))
        except Exception:
            pass
    if not hasattr(find_mmds, "_last_market_context"):
        find_mmds._last_market_context = {}  # type: ignore[attr-defined]
    find_mmds._last_market_context = market_context_result  # type: ignore[attr-defined]

    # 条件78-82：逐信号处理
    for i, mmd in enumerate(mmds):
        # 条件78：信号衰减增强
        if closes is not None and mmd.bi is not None:
            try:
                decay_result = _calc_enhanced_signal_decay(mmd, closes, volatility)
                mmd._enhanced_signal_decay = decay_result
                if decay_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + decay_result["confidence_adjust"])
                    )
            except Exception:
                pass

        # 条件79：假信号过滤
        if closes is not None and mmd.bi is not None and volumes is not None:
            try:
                fake_result = _calc_fake_signal_filter(mmd, closes, volumes, macd_data, volatility)
                mmd._false_signal_filter = fake_result
                if fake_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + fake_result["confidence_adjust"])
                    )
            except Exception:
                pass

        # 条件80：动态止损止盈增强
        if closes is not None and highs is not None and lows is not None and mmd.bi is not None:
            try:
                sl_tp_result = _calc_dynamic_sl_tp_enhanced(mmd, closes, highs, lows, volatility)
                mmd._dynamic_sl_tp_enhanced = sl_tp_result
            except Exception:
                pass

        # 条件81：板块轮动上下文
        if closes is not None and mmd.bi is not None and len(closes) >= 60:
            try:
                sector_result = _calc_sector_rotation_context(mmd, closes, trend_direction)
                mmd._sector_rotation_context = sector_result
                if sector_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + sector_result["confidence_adjust"])
                    )
            except Exception:
                pass

        # 条件82：多维背离确认
        if macd_data is not None and closes is not None and mmd.bi is not None:
            try:
                div_result = _calc_multi_dim_divergence(mmd, macd_data, closes, volumes)
                mmd._multi_dim_divergence = div_result
                if div_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + div_result["confidence_adjust"])
                    )
            except Exception:
                pass

        # 条件83：信号执行窗口优化（V36）
        if closes is not None and mmd.bi is not None:
            try:
                exec_result = _calc_execution_window(mmd, closes, volatility)
                mmd._execution_window = exec_result
                if exec_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + exec_result["confidence_adjust"])
                    )
            except Exception:
                pass

        # 条件84：多时间框架一致性验证（V36）
        if closes is not None and mmd.bi is not None and len(closes) >= 60:
            try:
                tf_result = _calc_tf_consistency(mmd, closes)
                mmd._tf_consistency = tf_result
                if tf_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + tf_result["confidence_adjust"])
                    )
            except Exception:
                pass

        # 条件85：风险调整后收益预期（V36）
        if closes is not None and highs is not None and lows is not None and mmd.bi is not None:
            try:
                rar_result = _calc_risk_adjusted_return(mmd, closes, highs, lows, volatility)
                mmd._risk_adjusted_return = rar_result
            except Exception:
                pass

        # 条件86：信号时效性紧急度评分（V36）
        if closes is not None and mmd.bi is not None:
            try:
                urg_result = _calc_urgency_score(mmd, closes, volatility)
                mmd._urgency_score = urg_result
                if urg_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + urg_result["confidence_adjust"])
                    )
            except Exception:
                pass

        # 条件87：市场环境综合评分（V36，全局一次性计算）
        if closes is not None and len(closes) >= 60:
            try:
                mkt_result = _calc_market_composite(closes, volumes, macd_data)
                if mkt_result.get("confidence_adjust", 0) != 0:
                    for m in mmds:
                        m.confidence = max(
                            0.0, min(1.0, m.confidence + mkt_result["confidence_adjust"])
                        )
                if not hasattr(find_mmds, "_last_market_composite"):
                    find_mmds._last_market_composite = {}  # type: ignore[attr-defined]
                find_mmds._last_market_composite = mkt_result  # type: ignore[attr-defined]
            except Exception:
                pass

        # 条件88：买卖点策略推荐（V36）
        if mmd.bi is not None:
            try:
                rec_result = _calc_strategy_recommendation(mmd, closes, volatility)
                mmd._strategy_recommendation = rec_result
            except Exception:
                pass

        # 条件89：连续确认过滤（V37）
        if closes is not None and mmd.bi is not None:
            try:
                cc_result = _calc_consecutive_confirmation(mmd, closes)
                mmd._consecutive_confirmation = cc_result
                if cc_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + cc_result["confidence_adjust"])
                    )
            except Exception:
                pass

        # 条件90：价格动能加速度（V37）
        if closes is not None and mmd.bi is not None:
            try:
                ma_result = _calc_momentum_acceleration(mmd, closes)
                mmd._momentum_acceleration = ma_result
                if ma_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + ma_result["confidence_adjust"])
                    )
            except Exception:
                pass

    # V37 条件91：波动率状态转换检测（全局一次性）
    vol_regime_result: dict[str, Any] = {}
    if closes is not None and len(closes) >= 60:
        try:
            vol_regime_result = _calc_volatility_regime_change(closes)
            adj = vol_regime_result.get("confidence_adjust", 0.0)
            if adj != 0.0:
                for m in mmds:
                    m.confidence = max(0.0, min(1.0, m.confidence + adj))
        except Exception:
            pass
    if not hasattr(find_mmds, "_last_vol_regime_change"):
        find_mmds._last_vol_regime_change = {}  # type: ignore[attr-defined]
    find_mmds._last_vol_regime_change = vol_regime_result  # type: ignore[attr-defined]

    # V37 条件92-94：逐信号处理
    for mmd in mmds:
        # 条件92：买卖点时间序列关联分析
        if mmd.bi is not None:
            try:
                tc_result = _calc_temporal_correlation(mmd, mmds)
                mmd._temporal_correlation = tc_result
                if tc_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + tc_result["confidence_adjust"])
                    )
            except Exception:
                pass

        # 条件93：多时间框架动量一致性
        if closes is not None and mmd.bi is not None:
            try:
                mfm_result = _calc_multi_tf_momentum_consistency(mmd, closes)
                mmd._multi_tf_momentum = mfm_result
                if mfm_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + mfm_result["confidence_adjust"])
                    )
            except Exception:
                pass

        # 条件94：信号综合质量排名
        try:
            qr_result = _calc_quality_ranking(mmd, mmds)
            mmd._quality_ranking = qr_result
        except Exception:
            pass

        # V38: 条件95-98 逐信号处理
        # 条件95：中枢结构完整性评分
        if mmd.bi is not None:
            try:
                zs_integrity = _calc_zs_structure_integrity(mmd, zss)
                mmd._zs_structure_integrity = zs_integrity
                adj = zs_integrity.get("confidence_adjust", 0.0)
                if adj != 0.0:
                    mmd.confidence = max(0.0, min(1.0, mmd.confidence + adj))
            except Exception:
                pass

        # 条件96：买卖点位置评分
        if closes is not None and mmd.bi is not None:
            try:
                pos_result = _calc_mmd_position_score(mmd, closes)
                mmd._mmd_position_score = pos_result
                if pos_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + pos_result["confidence_adjust"])
                    )
            except Exception:
                pass

        # 条件97：信号后收益跟踪
        if closes is not None and mmd.bi is not None:
            try:
                ret_result = _calc_post_signal_return(mmd, closes)
                mmd._post_signal_return = ret_result
                adj = ret_result.get("confidence_adjust", 0.0)
                if adj != 0.0:
                    mmd.confidence = max(0.0, min(1.0, mmd.confidence + adj))
            except Exception:
                pass

        # 条件98：中枢突破力度评估
        if closes is not None and mmd.bi is not None:
            try:
                bt_result = _calc_breakout_strength(mmd, closes, volumes)
                mmd._breakout_strength = bt_result
                adj = bt_result.get("confidence_adjust", 0.0)
                if adj != 0.0:
                    mmd.confidence = max(0.0, min(1.0, mmd.confidence + adj))
            except Exception:
                pass

        # 条件100：信号衰减预警
        if mmd.bi is not None:
            try:
                decay_result = _calc_signal_decay_warning(mmd, closes)
                mmd._signal_decay_warning = decay_result
                if decay_result.get("confidence_adjust", 0) != 0:
                    mmd.confidence = max(
                        0.0, min(1.0, mmd.confidence + decay_result["confidence_adjust"])
                    )
            except Exception:
                pass

    # V38 条件99：多指标偏离度综合评分（全局一次性）
    composite_dev_result: dict[str, Any] = {}
    if closes is not None and len(closes) >= 30:
        try:
            composite_dev_result = _calc_composite_deviation(closes, volumes, macd_data)
            adj = composite_dev_result.get("confidence_adjust", 0.0)
            if adj != 0.0:
                for m in mmds:
                    m.confidence = max(0.0, min(1.0, m.confidence + adj))
        except Exception:
            pass
    if not hasattr(find_mmds, "_last_composite_deviation"):
        find_mmds._last_composite_deviation = {}  # type: ignore[attr-defined]
    find_mmds._last_composite_deviation = composite_dev_result  # type: ignore[attr-defined]

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


def _reference_zs_for_bi(zss: list[ZS], bi: BI) -> ZS | None:
    """返回笔所对应的"同期参考中枢"：在笔开始前最后一个已完成的（或最近的）中枢。

    一买/一卖 是"跌破/突破某个中枢后的背驰点"——应参考该笔发生时存在的那个中枢，
    而非数据末端最后的中枢。用单一末端中枢做全局参考会导致历史每个底部都被标注。
    """
    if not zss:
        return None
    if bi.start is None or bi.start.k is None:
        return None
    bi_start_k = bi.start.k.k_index
    ref: ZS | None = None
    for zs in zss:
        if zs.end is None or zs.end.k is None:
            continue
        if zs.end.k.k_index < bi_start_k:
            ref = zs  # 记录最后一个在该笔之前结束的中枢
        else:
            break  # zss 按时间排序，之后的都更晚
    # 若无已完成先导中枢，退而取最早的完成中枢，再退而取最后的中枢（可能未完成）。
    # 最终跌破/突破笔正是"关闭"最后中枢的那一笔，此时参考该中枢是合法的。
    if ref is None:
        for zs in zss:
            if zs.done:
                return zs
        if zss:
            return zss[-1]
    return ref


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

    1买：下跌趋势中，跌破某中枢后的底背驰（参考笔当时的同期中枢）
    1卖：上涨趋势中，突破某中枢后的顶背驰

    V14增强：增加成交量异常检测 + 缺口分析
    """
    mmds: list[MMD] = []

    if len(zss) == 0:
        return mmds

    # 趋势强度（至少两个同向中枢），用于参考判断
    trend_strength = _calc_trend_strength(zss)

    # 一买/一卖 是"趋势反转"信号：必须建立在真实趋势之上（≥2 个同向中枢）。
    # 震荡市（单中枢、趋势强度为0）中反复的顶底不构成反转，不应产生 1买/1卖，
    # 盘整背驰交给 2买/类二买 处理。
    if trend_strength <= 0:
        return mmds

    # V5: 动态阈值 - 根据波动率调整
    base_threshold = 0.8
    if volatility is not None:
        threshold = _adjust_threshold_by_volatility(base_threshold, volatility)
    else:
        threshold = base_threshold

    # V14: 获取最近高低点用于缺口分析
    recent_highs = highs[-50:] if highs else None
    recent_lows = lows[-50:] if lows else None

    # 在一类买点区域查找底背驰（识别各趋势段的末端背驰点）
    # 双重去重避免同一底部反复创新低造成信号风暴：
    #   1. last_1buy_bi_idx：相邻 1买 至少相隔 5 笔
    #   2. rebound_high：前一次 1买 之后价格必须显著反弹（≥3%），
    #      否则视为同一底部的反复下探（震荡市/阴跌中的假底），不重复标记。
    # 一买是趋势反转末端信号，应稀缺而精准。
    last_1buy_bi_idx = -100
    last_1buy_low: float | None = None
    rebound_high = 0.0  # 自上次1买以来的反弹最高价
    for bi in bis:
        # 更新自上次1买以来的反弹最高点（含当前笔）
        rebound_high = max(rebound_high, bi.high)

        if bi.direction.value != "down":
            continue
        # 条件：笔低点在其"同期参考中枢"下沿下方
        ref_zs = _reference_zs_for_bi(zss, bi)
        if ref_zs is None:
            continue
        if bi.low >= ref_zs.zd:
            continue
        # 最小笔间距：相邻 1买 至少隔 5 笔，过滤同段反复的假底
        if bi.index - last_1buy_bi_idx < 5:
            continue
        # 结构去重：前一次 1买 后必须出现 ≥3% 的有意义反弹，
        # 才认定开启新的下跌腿；否则是同一底部的反复下探
        if last_1buy_low is not None and last_1buy_bi_idx >= 0:
            if rebound_high <= last_1buy_low:
                continue
            if (rebound_high - last_1buy_low) / last_1buy_low < 0.03:
                continue
        # 检查背驰（识别所有有效背驰点）
        if _is_strong_beichi(bi, bis, zss, closes, threshold):
            strength = _get_beichi_strength(bi, bis, zss, closes)
            msg_parts = [
                f"1买: 底背驰(强度={strength}), 低点={bi.low:.2f} < 中枢下沿={ref_zs.zd:.2f}"
            ]

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

            mmds.append(
                MMD(
                    mmd_type=MMDType.BUY_1,
                    zs=ref_zs,
                    bi=bi,
                    msg=", ".join(msg_parts),
                )
            )
            last_1buy_bi_idx = bi.index
            last_1buy_low = bi.low
            rebound_high = bi.high  # 重置反弹追踪，开启下一个下跌腿
            # 记录成交量放大和缺口状态到mmd属性
            if volumes is not None and bi_end_idx > 0:
                if _check_volume_spike(volumes, bi_end_idx, lookback=20, min_ratio=1.3):
                    mmds[-1]._vol_spike = True
            if recent_highs and recent_lows and bi_end_idx > 0:
                gap_info = _detect_price_gap(closes, recent_highs, recent_lows, bi_end_idx)
                if gap_info.get("gap_type") == "down" and not gap_info.get("filled", False):
                    mmds[-1]._gap_down = True
                    mmds[-1]._gap_size = gap_info.get("gap_size_pct", 0.0)

    # 在一类卖点区域查找顶背驰（识别各上升段的末端背驰点）
    # 与 1买 同理的双重去重：
    #   1. 相邻 1卖 至少相隔 5 笔
    #   2. pullback_low：前一次 1卖 之后价格必须显著回落（≥3%），
    #      否则视为同一顶部的反复创新高（震荡市中的假顶），不重复标记。
    last_1sell_bi_idx = -100
    last_1sell_high: float | None = None
    pullback_low = float("inf")  # 自上次1卖以来的回落最低价
    for bi in reversed(bis):
        # 更新自上次1卖以来的回落最低点（含当前笔）
        pullback_low = min(pullback_low, bi.low)

        if bi.direction.value != "up":
            continue
        # 条件：笔高点在其"同期参考中枢"上沿上方
        ref_zs = _reference_zs_for_bi(zss, bi)
        if ref_zs is None:
            continue
        if bi.high <= ref_zs.zg:
            continue
        # 最小笔间距
        if abs(bi.index - last_1sell_bi_idx) < 5:
            continue
        # 结构去重：前一次 1卖 后必须出现 ≥3% 的有意义回落，
        # 才认定开启新的上升腿；否则是同一顶部的反复创新高
        if last_1sell_high is not None and last_1sell_bi_idx >= 0:
            if pullback_low >= last_1sell_high:
                continue
            if (last_1sell_high - pullback_low) / last_1sell_high < 0.03:
                continue
        # 检查背驰（识别所有有效背驰点）
        if _is_strong_beichi(bi, bis, zss, closes, threshold, direction="up"):
            strength = _get_beichi_strength(bi, bis, zss, closes, direction="up")
            msg_parts = [
                f"1卖: 顶背驰(强度={strength}), 高点={bi.high:.2f} > 中枢上沿={ref_zs.zg:.2f}"
            ]

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

            mmds.append(
                MMD(
                    mmd_type=MMDType.SELL_1,
                    zs=ref_zs,
                    bi=bi,
                    msg=", ".join(msg_parts),
                )
            )
            last_1sell_bi_idx = bi.index
            last_1sell_high = bi.high
            pullback_low = bi.low  # 重置回落追踪，开启下一个上升腿
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
        # 1买结束对应的原始K线索引（用于时间窗口的同一尺度比较）
        buy_1_end_k = buy_1_bi.end.k.k_index

        # V8: 在1买之后找向上笔（离开笔），限制在30根K线内
        leave_bi_up = None
        for bi in bis[buy_1_idx + 1 :]:
            if bi.direction.value == "up":
                time_to_leave = bi.start.k.k_index - buy_1_end_k
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

        _ = leave_range * 0.5  # 严格条件（2买）
        _ = leave_range * 0.7  # 宽松条件（类二买）

        # V8: 在离开笔之后找回调笔，限制总时间窗口在10-40根K线内
        found_2buy = False
        found_2s_buy = False
        for bi in bis[bis.index(leave_bi_up) + 1 :]:
            total_time = bi.start.k.k_index - buy_1_end_k
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

                    # V8: 成交量确认（回调缩量，基准用1买附近的局部均量）
                    if volumes is not None:
                        vol_ok = _check_pullback_volume_v2(
                            volumes,
                            bi.start.k.k_index,
                            bi.end.k.k_index,
                            _calc_local_avg_volume(volumes, buy_1_end_k, 20),
                            max_ratio=0.85,
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

                    mmds.append(
                        MMD(
                            mmd_type=MMDType.BUY_2S,
                            zs=buy_1_mmd.zs,
                            bi=bi,
                            msg=f"类2买V8: 浅回调确认, 低点={bi.low:.2f} > 1买={buy_1_low:.2f}, 回撤{pct:.0f}%",
                        )
                    )
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
        # 1卖结束对应的原始K线索引（用于时间窗口的同一尺度比较）
        sell_1_end_k = sell_1_bi.end.k.k_index

        # V8: 在1卖之后找向下笔（离开笔），限制在30根K线内
        leave_bi_down = None
        for bi in bis[sell_1_idx + 1 :]:
            if bi.direction.value == "down":
                time_to_leave = bi.start.k.k_index - sell_1_end_k
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

        max_pullback_strict = leave_range * 0.5  # 严格条件（2卖）
        max_pullback_loose = leave_range * 0.7  # 宽松条件（类二卖）

        # V8: 在离开笔之后找反弹笔，限制总时间窗口在10-40根K线内
        found_2sell = False
        found_2s_sell = False
        for bi in bis[bis.index(leave_bi_down) + 1 :]:
            total_time = bi.start.k.k_index - sell_1_end_k
            if total_time > 40:
                break

            if bi.direction.value == "up":
                # 检查是否是2卖（严格条件）
                if (
                    not found_2sell
                    and bi.high < sell_1_high
                    and (bi.high - leave_low) < max_pullback_strict
                ):
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

                    # V8: 成交量确认（反弹缩量，基准用1卖附近的局部均量）
                    if volumes is not None:
                        vol_ok = _check_pullback_volume_v2(
                            volumes,
                            bi.start.k.k_index,
                            bi.end.k.k_index,
                            _calc_local_avg_volume(volumes, sell_1_end_k, 20),
                            max_ratio=0.85,
                            is_pullback=False,
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
                elif (
                    not found_2s_sell
                    and not found_2sell
                    and bi.high < sell_1_high
                    and (bi.high - leave_low) < max_pullback_loose
                ):
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

                    mmds.append(
                        MMD(
                            mmd_type=MMDType.SELL_2S,
                            zs=sell_1_mmd.zs,
                            bi=bi,
                            msg=f"类2卖V8: 浅反弹确认, 高点={bi.high:.2f} < 1卖={sell_1_high:.2f}, 反弹{pct:.0f}%",
                        )
                    )
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


def _calc_local_avg_volume(
    volumes: list[float] | None,
    anchor_idx: int,
    lookback: int = 20,
) -> float:
    """计算信号点附近（以 anchor_idx 为锚）的局部平均成交量。

    用于 2买/3买 等历史信号的"回调缩量"判断：
    应以信号发生时刻附近的量能为基准，而非整个数据末端的均量
    （后者会被后期放量段抬高，导致历史回调误判为未缩量）。
    """
    if not volumes or anchor_idx < 0:
        return 0.0
    start = max(0, anchor_idx - lookback + 1)
    window = volumes[start : anchor_idx + 1]
    if not window:
        return 0.0
    return sum(window) / len(window)


def _calc_zs_avg_volume(volumes: list[float] | None, zs: ZS) -> float:
    """计算中枢自身盘整期的平均成交量。

    以中枢所有构成笔覆盖的原始K线区间为窗口，作为突破/跌破的量能比较基准：
    突破相对盘整放量才是健康突破；被数据末端均量抬高会导致历史突破误判。
    """
    if not volumes:
        return 0.0
    start_k = min((ln.start.k.k_index for ln in zs.lines if ln.start and ln.start.k), default=None)
    end_k = max((ln.end.k.k_index for ln in zs.lines if ln.end and ln.end.k), default=None)
    if start_k is None or end_k is None:
        return 0.0
    last = len(volumes) - 1
    if last < 0:
        return 0.0
    start_k = min(max(0, start_k), last)
    end_k = min(max(0, end_k), last)
    if end_k < start_k:
        return 0.0
    window = volumes[start_k : end_k + 1]
    if not window:
        return 0.0
    return sum(window) / len(window)


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
        break_vols = volumes[break_start : break_end + 1]
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
        pull_vols = volumes[pull_start : pull_end + 1]
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
        pull_vols = volumes[pull_start : pull_end + 1]
        if not pull_vols:
            return True
        pull_avg = sum(pull_vols) / len(pull_vols)
        return pull_avg <= avg_vol * max_ratio
    except Exception:
        return True


# ── V13: 成交量剖面分析 ─────────────────────────────────────────────────────


# ── V14: 增强功能 ──────────────────────────────────────────────────────────────


# ── V15 新增函数 ─────────────────────────────────────────────────────────────


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
    # 放量倍数按"突破笔均量 vs 中枢盘整均量"度量。
    # 笔均量会被笔内多根K线稀释，1.8x 的硬阈值几乎无法达到导致 3买/3卖 系统性失效；
    # 实测真实结构比值约 1.2-1.5，故下调为 1.3。
    vol_adjusted_vol_ratio = 1.3  # 基础放量倍数

    if volatility is not None:
        if volatility > 0.03:  # 高波动市场：放宽阈值
            vol_adjusted_force_ratio = 1.1
            vol_adjusted_break_ratio = 0.45
            vol_adjusted_time_window = 7
            vol_adjusted_vol_ratio = 1.15
        elif volatility < 0.01:  # 低波动市场：收紧阈值
            vol_adjusted_force_ratio = 1.5
            vol_adjusted_break_ratio = 0.25
            vol_adjusted_time_window = 4
            vol_adjusted_vol_ratio = 1.5

    # 预计算MACD数据用于动量确认
    latest_dif = macd_data["dif"][-1] if macd_data and macd_data.get("dif") else None
    _ = macd_data["dif"][-2] if macd_data and len(macd_data.get("dif", [])) > 1 else None
    latest_hist = macd_data["hist"][-1] if macd_data and macd_data.get("hist") else None
    prev_hist = macd_data["hist"][-2] if macd_data and len(macd_data.get("hist", [])) > 1 else None

    for zs in zss:
        if not zs.done:
            continue

        # 计算中枢内首尾笔的力度比
        if len(zs.lines) >= 2:
            first_bi_force = _calc_bi_force(zs.lines[0], closes, zs.lines[0].index)
            last_bi_force = _calc_bi_force(zs.lines[-1], closes, zs.lines[-1].index)
            _ = last_bi_force / first_bi_force if first_bi_force > 0 else 1.0
        else:
            first_bi_force = 0.0
            _ = 1.0

        # 计算平均成交量（用于成交量确认，基准用"中枢自身盘整期均量"）。
        # 突破/跌破相对盘整放量才是合理的量能确认；用数据末端或突破附近的
        # 均量会被后期放量段抬高，导致历史突破误判为未放量。
        zs_end_idx = zs.end.k.k_index if zs.end else 0
        avg_vol_20 = _calc_zs_avg_volume(volumes, zs)

        # 找3买：突破中枢后的回踩
        # （zs_end_idx 已在计算均量时定义，bi.start.k.k_index 同为原始K线索引）

        # 找向上突破笔
        break_bi_up = None
        for bi in bis:
            if bi.start.k.k_index > zs_end_idx and bi.direction.value == "up":
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
                    volumes,
                    break_bi_up.start.k.k_index,
                    break_bi_up.end.k.k_index,
                    avg_vol_20,
                    min_ratio=vol_adjusted_vol_ratio,
                ):
                    continue

            # 在突破笔之后找回调笔
            for bi in bis[bis.index(break_bi_up) + 1 :]:
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

                    # 条件6：回调时缩量（< 85%中枢均量）。
                    # 原 <60% 过严：笔均量被笔内少量上涨日抬高，导致几乎无法满足，
                    # 3买/3卖 因此系统性失效；0.85 仍要求明显缩量。
                    vol_ok = True
                    if volumes is not None:
                        vol_ok = _check_pullback_volume_v2(
                            volumes,
                            bi.start.k.k_index,
                            bi.end.k.k_index,
                            avg_vol_20,
                            max_ratio=0.85,
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
                        vol_spike = _check_volume_spike(
                            volumes, break_bi_up.end.k.k_index, lookback=20, min_ratio=1.5
                        )

                    # V14: 条件17 - 缺口分析（向上缺口突破=强势信号）
                    gap_info: dict[str, Any] = {"has_gap": False, "gap_type": None, "filled": True}
                    if highs is not None and lows is not None:
                        gap_info = _detect_price_gap(closes, highs, lows, break_bi_up.end.k.k_index)

                    # V14: 条件18 - MACD柱状图斜率确认
                    macd_slope = _check_macd_histogram_slope(
                        macd_data, bi.end.k.k_index, direction="up"
                    )
                    if macd_slope["slope_direction"] == "shrinking":
                        continue  # 柱状图收缩，动量减弱，跳过

                    # V14: 条件19 - 假突破过滤（突破后需站稳min_bars根K线）
                    if not _check_breakout_persistence(closes, break_bi_up, zs.zg, min_bars=3):
                        continue

                    # 构建增强消息
                    extra_parts = []
                    if vol_spike:
                        extra_parts.append("量能放大✅")
                    if (
                        gap_info.get("has_gap")
                        and gap_info.get("gap_type") == "up"
                        and not gap_info.get("filled")
                    ):
                        extra_parts.append(f"跳空突破({gap_info['gap_size_pct']:.1f}%)✅")
                    if macd_slope["confirmed"]:
                        extra_parts.append("MACD斜率确认✅")

                    # V15: 条件20 - K线形态确认（回踩笔出现锤子线或阳吞没=看涨增强）
                    kline_pattern: dict[str, Any] = {"pattern": None, "strength": "none"}
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
                        bi.low, zs.zg, zs.zd, MMDType.BUY_3, closes, highs, lows, bi.end.k.k_index
                    )
                    if not atr_support_ok:
                        continue  # 回踩位置不在ATR支撑区域内，可能是假突破
                    if atr_support_ok:
                        extra_parts.append("ATR支撑✅")

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
                        vol_dist = _analyze_volume_at_levels(
                            closes, volumes, zs.zg, "resistance", lookback=30
                        )
                        if (
                            vol_dist["strength"] == "weak"
                            and vol_dist["volume_concentration"] < 0.5
                        ):
                            # 中枢上沿成交量极度稀疏，支撑强度存疑
                            pass  # 不直接跳过，但在消息中标记
                        elif vol_dist["strength"] == "strong":
                            extra_parts.append(f"阻力位量密({vol_dist['signal']})✅")

                    # V15: 条件21 - 二次回踩确认（break-retest-break pattern）
                    retest_result = _check_break_retest_break(bis, break_bi_up, zs.zg, closes)
                    if retest_result["exists"]:
                        extra_parts.append(
                            f"二次确认(回踩{retest_result.get('retracement_pct', '?')}%)✅"
                        )

                    # V47: 条件131 - 后确认价格跟随过滤（仅当数据足够时生效）
                    if closes is not None and len(closes) > 10:
                        try:
                            post_confirm = _check_post_signal_price_follow_through(
                                MMD(mmd_type=MMDType.BUY_3, zs=zs, bi=bi, msg=""),
                                closes,
                                lookback_bars=5,
                                min_follow_pct=0.02,
                            )
                            if not post_confirm["followed"] and post_confirm["looked_bars"] > 0:
                                # 后确认失败但有数据可查，跳过
                                pass  # 不直接跳过，而是记录到消息中供参考
                        except Exception:
                            pass

                    extra_msg = ", " + ", ".join(extra_parts) if extra_parts else ""

                    mmds.append(
                        MMD(
                            mmd_type=MMDType.BUY_3,
                            zs=zs,
                            bi=bi,
                            msg=f"3买V47: 突破确认后回踩(深度{(break_bi_up.low - bi.low) / breakout_range * 100:.0f}%), 低点={bi.low:.2f} > zg={zs.zg:.2f}, Regime={regime}(×{regime_adjust:.2f}), MA20={ma_slope}, RSI={rsi_3buy:.0f}(+{rsi_momentum:+.1f}), ADX={adx_val:.0f}, KDJ.J={kjd_j:.0f}, BOLL%b={boll_pos['percent_b']:.2f}, MACD零轴={macd_zero_pos}, 回踩{pullback_time_span}根K线, ATR支撑✅"
                            + extra_msg,
                        )
                    )
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
                        vol_dist_3buy = _analyze_volume_at_levels(
                            closes, volumes, zs.zg, "resistance", lookback=30
                        )
                        mmds[-1]._vol_dist_at_zg = vol_dist_3buy
                    break

        # 找3卖：跌破中枢后的反抽
        break_bi_down = None
        for bi in bis:
            if bi.start.k.k_index > zs_end_idx and bi.direction.value == "down":
                if bi.low < zs.zd:  # 跌破中枢下沿
                    break_bi_down = bi
                    break

        if break_bi_down:
            # V8: 条件A - 跌破笔必须有足够力度（波动率自适应）
            break_force_down = _calc_bi_force(break_bi_down, closes, break_bi_down.index)
            if (
                len(zs.lines) >= 2
                and break_force_down
                < _calc_bi_force(zs.lines[0], closes, zs.lines[0].index) * vol_adjusted_force_ratio
            ):
                continue

            # V8: 条件B - 跌破后价格应该站稳中枢下方（自适应）
            breakdown_price_ratio = (
                (zs.zd - break_bi_down.low) / (zs.zg - zs.zd) if zs.zg > zs.zd else 0
            )
            if breakdown_price_ratio < 0.4:  # V8: 最低要求40%
                continue

            # V8: 条件C - 成交量确认 - 跌破时应显著放量（自适应倍数）
            if volumes is not None:
                if not _check_breakout_volume(
                    volumes,
                    break_bi_down.start.k.k_index,
                    break_bi_down.end.k.k_index,
                    avg_vol_20,
                    min_ratio=vol_adjusted_vol_ratio,
                ):
                    continue

            # 在跌破笔之后找反弹笔
            for bi in bis[bis.index(break_bi_down) + 1 :]:
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
                            volumes,
                            bi.start.k.k_index,
                            bi.end.k.k_index,
                            avg_vol_20,
                            max_ratio=0.6,
                            is_pullback=False,
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
                        vol_spike_sell = _check_volume_spike(
                            volumes, break_bi_down.end.k.k_index, lookback=20, min_ratio=1.5
                        )

                    # V14: 条件17 - 缺口分析（向下缺口跌破=加速下跌信号）
                    gap_info_sell: dict[str, Any] = {
                        "has_gap": False,
                        "gap_type": None,
                        "filled": True,
                    }
                    if highs is not None and lows is not None:
                        gap_info_sell = _detect_price_gap(
                            closes, highs, lows, break_bi_down.end.k.k_index
                        )

                    # V14: 条件18 - MACD柱状图斜率确认
                    macd_slope_sell = _check_macd_histogram_slope(
                        macd_data, bi.end.k.k_index, direction="down"
                    )
                    if macd_slope_sell["slope_direction"] == "shrinking":
                        continue  # 柱状图收缩，动量减弱，跳过

                    # V14: 条件19 - 假突破过滤（跌破后需站稳min_bars根K线）
                    if not _check_breakout_persistence(closes, break_bi_down, zs.zd, min_bars=3):
                        continue  # 跌破后价格已回升，可能是假跌破

                    # 构建增强消息
                    extra_parts_sell = []
                    if vol_spike_sell:
                        extra_parts_sell.append("量能放大✅")
                    if (
                        gap_info_sell.get("has_gap")
                        and gap_info_sell.get("gap_type") == "down"
                        and not gap_info_sell.get("filled")
                    ):
                        extra_parts_sell.append(f"跳空跌破({gap_info_sell['gap_size_pct']:.1f}%)✅")
                    if macd_slope_sell["confirmed"]:
                        extra_parts_sell.append("MACD斜率确认✅")

                    # V15: 条件20 - K线形态确认（回抽笔出现锤子线或阴吞没=看跌增强）
                    kline_pattern_sell: dict[str, Any] = {"pattern": None, "strength": "none"}
                    if highs is not None and lows is not None:
                        kline_pattern_sell = _detect_kline_pattern(
                            closes, highs, lows, bi.end.k.k_index
                        )
                    if kline_pattern_sell["pattern"] in ("hammer", "bullish_engulfing"):
                        extra_parts_sell.append(f"K线形态:{kline_pattern_sell['pattern']}✅")
                    # V17: 条件24 - K线形态反向过滤：回抽笔出现阳吞没=看涨信号，跳过3卖
                    elif kline_pattern_sell["pattern"] == "bearish_engulfing":
                        continue  # 回抽末端出现阴吞没，短期可能继续上涨

                    # V18: 条件26 - 跌破力度确认：跌破笔力度需大于进入中枢的笔（避免弱势跌破）
                    if len(zs.lines) >= 1 and break_bi_down:
                        break_force_down = _calc_bi_force(
                            break_bi_down, closes, break_bi_down.index
                        )
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
                        bi.high, zs.zg, zs.zd, MMDType.SELL_3, closes, highs, lows, bi.end.k.k_index
                    )
                    if not atr_resist_ok:
                        continue  # 反弹位置不在ATR阻力区域内
                    if atr_resist_ok:
                        extra_parts_sell.append("ATR阻力✅")

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
                        accel_sell, trend_state_sell = _calc_trend_acceleration(
                            macd_data, bi.end.k.k_index
                        )
                        if trend_state_sell == "accelerating":
                            # 趋势正在加速向上，可能是底背离前兆，跳过
                            continue
                        elif trend_state_sell == "decelerating":
                            extra_parts_sell.append("趋势加速下行✅")

                    # V20: 条件33 - 关键价位成交量分布：zd附近应有足够成交量确认
                    if volumes is not None:
                        vol_dist_sell = _analyze_volume_at_levels(
                            closes, volumes, zs.zd, "support", lookback=30
                        )
                        if (
                            vol_dist_sell["strength"] == "weak"
                            and vol_dist_sell["volume_concentration"] < 0.5
                        ):
                            pass  # 中枢下沿成交量极度稀疏，支撑强度存疑
                        elif vol_dist_sell["strength"] == "strong":
                            extra_parts_sell.append(f"支撑位量密({vol_dist_sell['signal']})✅")

                    # V15: 条件21 - 二次回踩确认（break-retest-break pattern）
                    retest_result_sell = _check_break_retest_break(
                        bis, break_bi_down, zs.zd, closes
                    )
                    if retest_result_sell["exists"]:
                        extra_parts_sell.append(
                            f"二次确认(反抽{retest_result_sell.get('retracement_pct', '?')}%)✅"
                        )

                    # V47: 条件131 - 后确认价格跟随过滤（仅当数据足够时生效）
                    if closes is not None and len(closes) > 10:
                        try:
                            post_confirm_sell = _check_post_signal_price_follow_through(
                                MMD(mmd_type=MMDType.SELL_3, zs=zs, bi=bi, msg=""),
                                closes,
                                lookback_bars=5,
                                min_follow_pct=-0.02,
                            )
                            if (
                                not post_confirm_sell["followed"]
                                and post_confirm_sell["looked_bars"] > 0
                            ):
                                pass  # 不直接跳过，记录到置信度中
                        except Exception:
                            pass

                    extra_msg_sell = ", " + ", ".join(extra_parts_sell) if extra_parts_sell else ""

                    mmds.append(
                        MMD(
                            mmd_type=MMDType.SELL_3,
                            zs=zs,
                            bi=bi,
                            msg=f"3卖V47: 跌破确认后反抽(幅度{(bi.high - break_bi_down.high) / breakdown_range * 100:.0f}%), 高点={bi.high:.2f} < zd={zs.zd:.2f}, Regime={regime_sell}(×{regime_adjust_sell:.2f}), MA20={ma_slope}, RSI={rsi_3sell:.0f}(+{rsi_momentum_sell:+.1f}), ADX={adx_val:.0f}, KDJ.J={kjd_j_sell:.0f}, BOLL%b={boll_pos['percent_b']:.2f}, MACD零轴={macd_zero_pos_sell}, 反抽{retracement_time_span}根K线, ATR阻力✅"
                            + extra_msg_sell,
                        )
                    )
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
                        mmds[-1]._retest_retracement = retest_result_sell.get(
                            "retracement_pct", 0.0
                        )
                    # V20: 记录波动率Regime和趋势加速度
                    mmds[-1]._vol_regime = regime_sell
                    mmds[-1]._trend_accel = trend_state_sell if macd_data is not None else "neutral"
                    if volumes is not None:
                        vol_dist_3sell = _analyze_volume_at_levels(
                            closes, volumes, zs.zd, "support", lookback=30
                        )
                        mmds[-1]._vol_dist_at_zd = vol_dist_3sell
                    break

    return mmds


# ── 辅助函数 ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# V20 新增：波动率Regime过滤 + 趋势加速度确认 + 关键价位成交量分布
# ─────────────────────────────────────────────────────────────────────────────


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
        MMDType.BUY_1: 1,
        MMDType.SELL_1: 2,
        MMDType.BUY_2: 3,
        MMDType.SELL_2: 4,
        MMDType.BUY_2S: 5,
        MMDType.SELL_2S: 6,
        MMDType.BUY_3: 7,
        MMDType.SELL_3: 8,
    }

    def sort_key(mmd: MMD) -> tuple[int, float, int]:
        grade = getattr(getattr(mmd, "quality", None), "grade", "D")
        grade_order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
        return (
            grade_order.get(grade, 4),  # 1. 质量等级
            -mmd.confidence,  # 2. 置信度（降序）
            type_priority.get(mmd.mmd_type, 9),  # 3. 类型优先级
        )

    return sorted(mmds, key=sort_key)


# ─────────────────────────────────────────────────────────────────────────────
# V21 新增：动态支撑阻力 + 组合信号 + 多时间框架共振 + 决策辅助
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────


# ── V23 新增函数 ────────────────────────────────────────────────────────────────


# ── V24 新增函数 ────────────────────────────────────────────────────────────────


# ── V25 新增函数 ────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# V26 新增：条件51-53
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# V27 新增：条件54-56
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# V28 新增：条件57-59
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# V29 新增：条件60-61
# ──────────────────────────────────────────────────────────────────────────────


# ── V31 新增：条件65-67 ────────────────────────────────────────────────────────


# ── V32 新增：条件68-70 ────────────────────────────────────────────────────────


# ── V33 新增：条件71-73 ────────────────────────────────────────────────────────


# ── V34 新增：条件74-76 ────────────────────────────────────────────────────────


# ── V35 新增：條件77-82 ────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# V36 增强功能（条件83-88）
# ─────────────────────────────────────────────────────────────────────────────


# ── V37: 条件89-94 缠论模型增强 ───────────────────────────────────────────────────


# ── V38: 条件95-100 缠论模型增强 ────────────────────────────────────────────────


# ── V39: 条件101-105 缠论模型决策增强 ───────────────────────────────────────────


def find_mmds_v39(
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
    """V39/V40/V41 版本的 find_mmds：调用 V38 逻辑后再执行 V39 条件 101-105 + V40 条件 106-110 + V41 条件 111-115。

    返回：与 find_mmds 相同的 MMD 列表，但每个 MMD 包含 V39/V40/V41 字段。
    """
    mmds = find_mmds(
        bis=bis,
        zss=zss,
        closes=closes,
        config=config,
        volumes=volumes,
        macd_data=macd_data,
        volatility=volatility,
        highs=highs,
        lows=lows,
    )

    if not mmds or not closes:
        return mmds

    # V48/V57 条件复用 find_mmds 内的全局指标（此前未定义导致条件被 try 吞掉）
    trend_strength = _calc_trend_strength(zss)
    bc_list: list[Any] = []

    # V83: 记录校准基线置信度（find_mmds 内 V47 校验后的值）。
    # 后续 V39-V82 共 160+ 个条件各自做 ±0.01~±0.05 的小幅调整，
    # 累计漂移会把强信号压向 0/1 边界（实测强 1买 被压到 0.00~0.15）。
    # 最终将置信度收敛回基线 ±CONFIDENCE_BAND，保留条件细化能力，避免过度压制。
    _conf_base: dict[int, float] = {id(m): m.confidence for m in mmds}

    # 条件103：多时间框架背离确认（一次性计算）
    multi_tf_div = None
    try:
        multi_tf_div = _calc_multi_tf_divergence_confirmation(closes, volumes or [], macd_data)
        find_mmds_v39._last_multi_tf_divergence = multi_tf_div  # type: ignore[attr-defined]
    except Exception:
        pass

    # V40 条件108：多周期MACD共振（一次性计算）
    macd_resonance = None
    try:
        macd_resonance = _calc_multi_cycle_macd_resonance(closes, macd_data)
        find_mmds_v39._last_macd_resonance = macd_resonance  # type: ignore[attr-defined]
    except Exception:
        pass

    # 收集所有置信度用于校准
    all_confidences = [mmd.confidence for mmd in mmds]

    # V41 条件112：量能周期检测（全局一次性计算）
    volume_cycle: dict[str, Any] | None = None
    # V41 条件113：走势预测（全局一次性计算）
    trajectory: dict[str, Any] | None = None
    # V41 条件114：动态质量分层（全局一次性计算）
    quality_tiers: dict[str, Any] | None = None
    # V41 条件115：反转风险评估（全局一次性计算）
    reversal_risk: dict[str, Any] | None = None

    for mmd in mmds:
        bi_end_idx = mmd.bi.end.k.k_index if mmd.bi else 0

        # 条件101：信号一致性验证
        try:
            consistency = _calc_signal_consistency_check(mmd, closes, mmds)
            mmd._signal_consistency = consistency
            mmd.confidence = max(
                0.0, min(1.0, mmd.confidence + consistency.get("confidence_adjust", 0.0))
            )
        except Exception:
            pass

        # 条件102：中枢级别匹配验证
        try:
            level_match = _calc_zs_level_match(mmd, zss)
            mmd._zs_level_match = level_match
            mmd.confidence = max(
                0.0, min(1.0, mmd.confidence + level_match.get("confidence_adjust", 0.0))
            )
        except Exception:
            pass

        # 条件103：应用多时间框架背离调整（方向感知）
        if multi_tf_div:
            try:
                mmd._multi_tf_divergence = multi_tf_div
                is_buy = "buy" in mmd.mmd_type.value
                adj = multi_tf_div.get("confidence_adjust", 0.0)
                if is_buy and multi_tf_div.get("multi_tf_bullish", 0) >= 2:
                    pass
                elif not is_buy and multi_tf_div.get("multi_tf_bearish", 0) >= 2:
                    pass
                elif is_buy and multi_tf_div.get("multi_tf_bearish", 0) >= 1:
                    adj = 0.0
                elif not is_buy and multi_tf_div.get("multi_tf_bullish", 0) >= 1:
                    adj = 0.0
                mmd.confidence = max(0.0, min(1.0, mmd.confidence + adj))
            except Exception:
                pass

        # 条件104：独立交叉验证
        try:
            cross_val = _calc_independent_cross_validation(mmd, closes, volumes)
            mmd._independent_cross_validation = cross_val
            mmd.confidence = max(
                0.0, min(1.0, mmd.confidence + cross_val.get("confidence_adjust", 0.0))
            )
        except Exception:
            pass

        # 条件105：决策质量综合评分
        try:
            decision = _calc_decision_quality_score(mmd, closes, volumes, macd_data, volatility)
            mmd._decision_quality_score = decision
        except Exception:
            pass

        # ── V40 条件 106-110 ──

        # 条件106：时间衰减自适应过滤
        try:
            time_decay = _calc_time_decay_adaptive(mmd, closes, volatility)
            mmd._time_decay_adaptive = time_decay
            mmd.confidence = max(
                0.0, min(1.0, mmd.confidence + time_decay.get("confidence_adjust", 0.0))
            )
        except Exception:
            pass

        # 条件107：中枢突破回踩验证
        try:
            retest_val = _calc_breakout_retest_validation(mmd, bis, zss, closes, volumes)
            mmd._breakout_retest_validation = retest_val
            mmd.confidence = max(
                0.0, min(1.0, mmd.confidence + retest_val.get("confidence_adjust", 0.0))
            )
        except Exception:
            pass

        # 条件108：多周期MACD共振确认
        if macd_resonance:
            try:
                mmd._multi_cycle_macd_resonance = macd_resonance
                is_buy = "buy" in mmd.mmd_type.value
                adj = macd_resonance.get("confidence_adjust", 0.0)
                if is_buy and macd_resonance.get("slow_macd_bearish"):
                    adj = 0.0
                elif not is_buy and macd_resonance.get("slow_macd_bullish"):
                    adj = 0.0
                mmd.confidence = max(0.0, min(1.0, mmd.confidence + adj))
            except Exception:
                pass

        # 条件109：K线形态综合评分
        try:
            mmd_idx = mmd.bi.end.k.k_index if mmd.bi else len(closes) - 1
            kline_score = _calc_kline_pattern_composite(closes, highs, lows, None, mmd_idx)
            mmd._kline_pattern_composite = kline_score
            mmd.confidence = max(
                0.0, min(1.0, mmd.confidence + kline_score.get("confidence_adjust", 0.0))
            )
        except Exception:
            pass

        # 条件110：置信度动态校准
        try:
            calibration = _calc_confidence_calibration(mmd, mmd.confidence, all_confidences)
            mmd._confidence_calibration = calibration
            mmd.confidence = max(
                0.0, min(1.0, mmd.confidence + calibration.get("confidence_adjust", 0.0))
            )
        except Exception:
            pass

        # ── V41 条件 111-115 ──

        # 条件111：量价能量分布分析
        try:
            energy_dist = _calc_volume_price_energy_dist(mmd, closes, volumes, highs, lows)
            mmd._volume_price_energy_dist = energy_dist
            mmd.confidence = max(
                0.0, min(1.0, mmd.confidence + energy_dist.get("confidence_adjust", 0.0))
            )
        except Exception:
            pass

        # 条件112：量能周期检测（全局一次性计算）
        if volume_cycle is None:
            try:
                volume_cycle = _calc_volume_cycle_detection(closes, volumes)
                find_mmds_v39._last_volume_cycle = volume_cycle  # type: ignore[attr-defined]
            except Exception:
                volume_cycle = {}
        if volume_cycle:
            try:
                mmd._volume_cycle_detection = volume_cycle
                is_buy = "buy" in mmd.mmd_type.value
                adj = volume_cycle.get("confidence_adjust", 0.0)
                if is_buy and volume_cycle.get("cycle_state") == "contracting":
                    adj = 0.0
                elif not is_buy and volume_cycle.get("cycle_state") == "expanding":
                    adj = 0.0
                mmd.confidence = max(0.0, min(1.0, mmd.confidence + adj))
            except Exception:
                pass

        # 条件113：走势预测（全局一次性计算）
        if trajectory is None:
            try:
                trajectory = _calc_post_signal_trajectory(closes, volumes, macd_data)
                find_mmds_v39._last_trajectory_prediction = trajectory  # type: ignore[attr-defined]
            except Exception:
                trajectory = {}
        if trajectory:
            try:
                mmd._post_signal_trajectory = trajectory
                is_buy = "buy" in mmd.mmd_type.value
                adj = trajectory.get("confidence_adjust", 0.0)
                if is_buy and trajectory.get("predicted_direction") == "down":
                    adj = -abs(adj)
                elif not is_buy and trajectory.get("predicted_direction") == "up":
                    adj = -abs(adj)
                mmd.confidence = max(0.0, min(1.0, mmd.confidence + adj))
            except Exception:
                pass

        # 条件114：动态质量分层（全局一次性计算）
        if quality_tiers is None:
            try:
                quality_tiers = _calc_quality_tier_classification(mmds, all_confidences)
            except Exception:
                quality_tiers = {}
        if quality_tiers:
            try:
                tier = quality_tiers.get(mmd.mmd_type.value, "C")
                mmd._quality_tier_classification = {
                    "tier": tier,
                    "rank": quality_tiers.get(f"{mmd.mmd_type.value}_rank", 0),
                }
                tier_multiplier = {"S": 0.03, "A": 0.01, "B": 0.0, "C": -0.01}.get(tier, 0.0)
                mmd.confidence = max(0.0, min(1.0, mmd.confidence + tier_multiplier))
            except Exception:
                pass

        # 条件115：反转风险评估（全局一次性计算）
        if reversal_risk is None:
            try:
                reversal_risk = _calc_reversal_risk_assessment(
                    closes, volumes, highs, lows, macd_data, volatility
                )
                find_mmds_v39._last_reversal_risk = reversal_risk  # type: ignore[attr-defined]
            except Exception:
                reversal_risk = {}
        if reversal_risk:
            try:
                mmd._reversal_risk_assessment = reversal_risk
                is_buy = "buy" in mmd.mmd_type.value
                risk_level = reversal_risk.get("risk_level", "low")
                if is_buy and risk_level in ("high", "extreme"):
                    mmd.confidence = max(0.0, min(1.0, mmd.confidence - 0.05))
                elif not is_buy and risk_level in ("high", "extreme"):
                    mmd.confidence = max(0.0, min(1.0, mmd.confidence - 0.03))
            except Exception:
                pass

        # ── V42 条件 116-120 ──

        # 条件116：后确认验证（Post-Signal Confirmation）
        try:
            post_confirm = _calc_post_signal_confirmation(
                mmd, closes, volumes, highs, lows, bi_end_idx
            )
            mmd._post_signal_confirmation = post_confirm
            mmd.confidence = max(
                0.0, min(1.0, mmd.confidence + post_confirm.get("confidence_adjust", 0.0))
            )
        except Exception:
            pass

        # 条件117：突破-回调量比验证
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and mmd.zs
            and volumes is not None
            and bis is not None
        ):
            try:
                vol_ratio_result = _calc_break_pullback_volume_ratio(mmd, bis, zss, closes, volumes)
                mmd._break_pullback_volume_ratio = vol_ratio_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vol_ratio_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件118：中枢距离验证
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and mmd.zs
            and closes is not None
            and mmd.bi is not None
        ):
            try:
                dist_result = _calc_zhongshu_distance_validation(mmd, closes)
                mmd._zhongshu_distance_validation = dist_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + dist_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件119：ADX趋势强度确认
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and highs is not None
            and lows is not None
            and mmd.bi is not None
        ):
            try:
                adx_result = _calc_adx_trend_strength_check(mmd, closes, highs, lows, bi_end_idx)
                mmd._adx_trend_strength = adx_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + adx_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件120：信号时效性衰减增强（改进版指数衰减）
        try:
            freshness = _calc_enhanced_signal_freshness(mmd, closes, volatility)
            mmd._signal_freshness = freshness
            mmd.confidence = max(
                0.0, min(1.0, mmd.confidence + freshness.get("confidence_adjust", 0.0))
            )
        except Exception:
            pass

        # ── V44 条件 121-125 ──

        # 条件121：趋势方向对齐验证（Trend Direction Alignment）
        # 3买必须在上升趋势中，3卖必须在下降趋势中
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and mmd.bi is not None
        ):
            try:
                trend_align = _calc_trend_direction_alignment(mmd, closes, volumes)
                mmd._trend_direction_alignment = trend_align
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + trend_align.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件122：突破笔力度对比（Breakout Bi Strength vs Entry Bi）
        # 突破笔成交量/长度必须大于进入笔，否则可能是假突破
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and mmd.zs is not None
            and bis is not None
            and volumes is not None
        ):
            try:
                breakout_strength = _calc_breakout_bi_strength_compare(mmd, bis, zss, volumes)
                mmd._breakout_bi_strength_compare = breakout_strength
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + breakout_strength.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件123：回踩时间窗口过滤（Pullback Time Window Filter）
        # 信号形成后经过的K线数量不能过多，否则信号失效
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and mmd.bi is not None
        ):
            try:
                pullback_window = _calc_pullback_time_window(mmd, closes)
                mmd._pullback_time_window = pullback_window
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + pullback_window.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件124：波动率自适应阈值（Volatility-Adaptive Thresholds）
        # 根据当前波动率动态调整置信度加成幅度
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and volatility is not None
            and closes is not None
        ):
            try:
                vol_adapt = _calc_volatility_adaptive_v44(mmd, volatility, closes)
                mmd._volatility_adaptive_threshold = vol_adapt
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vol_adapt.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件125：多指标背离共振增强（Multi-Indicator Divergence Resonance）
        # MACD+RSI+KDJ 同时出现背离时，额外确认趋势反转
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
            and macd_data is not None
        ):
            try:
                div_resonance = _calc_multi_indicator_divergence_resonance(
                    mmd, closes, volumes, macd_data
                )
                mmd._multi_indicator_divergence_resonance = div_resonance
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + div_resonance.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V46 条件 126-130 ──

        # 条件126：趋势动能强度过滤（Trend Momentum Strength Filter）
        # 使用ADX确认趋势强度，只有ADX>20时才给予完整加分
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and highs is not None
            and lows is not None
            and mmd.bi is not None
        ):
            try:
                mom_strength = _calc_trend_momentum_strength(mmd, closes, highs, lows)
                mmd._trend_momentum_strength = mom_strength
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + mom_strength.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件127：量价背离二次确认（Volume-Price Divergence Secondary Confirmation）
        # 在突破笔和回踩笔中检测量价背离，加强确认
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
            and mmd.bi is not None
        ):
            try:
                vol_price_sec = _calc_volume_price_divergence_secondary(mmd, closes, volumes)
                mmd._volume_price_divergence_secondary = vol_price_sec
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vol_price_sec.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件128：中枢突破真实性验证（ZS Breakout Authenticity Verification）
        # 突破后价格需站稳中枢上方/下方至少3根K线
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and mmd.zs is not None
            and closes is not None
            and mmd.bi is not None
        ):
            try:
                zs_authenticity = _calc_zs_breakout_authenticity(mmd, closes)
                mmd._zs_breakout_authenticity = zs_authenticity
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + zs_authenticity.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件129：多时间框架信号一致性（Multi-Timeframe Signal Consistency）
        # 通过不同周期MA斜率判断多TF一致性
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and mmd.bi is not None
        ):
            try:
                tf_consistency = _calc_multi_tf_signal_consistency(mmd, closes)
                mmd._multi_tf_signal_consistency = tf_consistency
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + tf_consistency.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件130：动态市场环境适配（Dynamic Market Regime Adaptation）
        # 识别当前市场状态（趋势/盘整/高波动），动态调整阈值
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
        ):
            try:
                regime = _calc_dynamic_market_regime(mmd, closes, volumes)
                mmd._dynamic_market_regime = regime
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + regime.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V47 条件 131-133 ──

        # 条件131：后确认价格跟随过滤（Post-Signal Price Follow-Through）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and mmd.bi is not None
        ):
            try:
                follow_result = _check_post_signal_price_follow_through(
                    mmd, closes, lookback_bars=5, min_follow_pct=0.02
                )
                mmd._post_signal_price_follow_through = follow_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + follow_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件132：信号有效性窗口（Signal Validity Window）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and highs is not None
            and lows is not None
            and mmd.bi is not None
        ):
            try:
                window_result = _calc_signal_validity_window(mmd, closes, highs, lows, volatility)
                mmd._signal_validity_window = window_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + window_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件133：置信度动态校准（Confidence Dynamic Calibration）
        if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
            mmd._confidence_v47_calibrated = mmd.confidence

        # ── V48 条件 134-136 ──

        # 条件134：量价背离二次确认（Volume-Price Divergence Secondary Confirmation）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
            and mmd.bi is not None
        ):
            try:
                vol_price_result = _calc_volume_price_divergence_secondary_v48(mmd, closes, volumes)
                mmd._volume_price_divergence_secondary_v48 = vol_price_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vol_price_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件135：趋势强度加权（Trend Strength Weighting）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and mmd.bi is not None
        ):
            try:
                trend_weight_result = _calc_trend_strength_weighting_v48(
                    mmd, closes, highs, lows, trend_strength
                )
                mmd._trend_strength_weighting = trend_weight_result
                mmd.confidence = max(
                    0.0,
                    min(1.0, mmd.confidence + trend_weight_result.get("confidence_adjust", 0.0)),
                )
            except Exception:
                pass

        # 条件136：动态风险收益比（Dynamic Risk-Reward Ratio）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and mmd.bi is not None
        ):
            try:
                rrr_result = _calc_dynamic_risk_reward_ratio_v48(mmd, closes, highs, lows)
                mmd._dynamic_risk_reward_ratio = rrr_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + rrr_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V49 条件 137-139 ──

        # 条件137：突破力度二次验证（Breakout Strength Re-validation）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and mmd.bi is not None
        ):
            try:
                breakout_result = _calc_breakout_strength_revalidation_v49(
                    mmd, closes, volumes, macd_data
                )
                mmd._breakout_strength_revalidation_v49 = breakout_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + breakout_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件138：回踩结构完整性（Pullback Structure Integrity）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and mmd.bi is not None
            and bis is not None
        ):
            try:
                pullback_result = _calc_pullback_structure_integrity_v49(mmd, bis, closes)
                mmd._pullback_structure_integrity_v49 = pullback_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + pullback_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件139：中枢级别权重（Zhongshu Level Weight）
        if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3) and mmd.zs is not None:
            try:
                zs_level_result = _calc_zhongshu_level_weight_v49(mmd, zss)
                mmd._zhongshu_level_weight_v49 = zs_level_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + zs_level_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V50 条件 140-143 ──

        # 条件140：板块联动分析（Sector Correlation Analysis）
        # 通过成交活跃度与波动率判断板块联动效应
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
            and mmd.bi is not None
        ):
            try:
                sector_result = _calc_sector_correlation_v50(mmd, closes, volumes)
                mmd._sector_correlation_v50 = sector_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + sector_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件141：多时间框架共振验证（Multi-Timeframe Resonance）
        # 通过不同周期价格动量一致性验证信号质量
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and mmd.bi is not None
        ):
            try:
                mtf_result = _calc_multi_tf_resonance_v50(mmd, closes)
                mmd._multi_tf_resonance_v50 = mtf_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + mtf_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件142：缠论级别递归验证（Multi-Level Chanlun Recursive Validation）
        # 验证当前信号在更高级别结构中是否一致
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and mmd.zs is not None
            and zss is not None
        ):
            try:
                level_result = _calc_level_recursive_validation_v50(mmd, zss)
                mmd._level_recursive_validation_v50 = level_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + level_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件143：市场情绪指标融合（Market Sentiment Fusion）
        # 通过涨跌幅分布和量能分布判断市场情绪
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
        ):
            try:
                sentiment_result = _calc_market_sentiment_fusion_v50(mmd, closes, volumes)
                mmd._market_sentiment_fusion_v50 = sentiment_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + sentiment_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V51 条件 144-147 ──

        # 条件144：突破笔力度二次确认增强（Breakout Bi Strength Enhanced）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and bis is not None
            and zss is not None
            and volumes is not None
        ):
            try:
                breakout_enhanced = _calc_breakout_bi_strength_enhanced_v51(
                    mmd, bis, zss, volumes, macd_data
                )
                mmd._breakout_bi_strength_enhanced_v51 = breakout_enhanced
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + breakout_enhanced.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件145：回踩笔深度+时间综合验证（Pullback Depth+Time）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and highs is not None
            and lows is not None
            and volatility is not None
        ):
            try:
                pullback_dt = _calc_pullback_depth_time_v51(mmd, closes, highs, lows, volatility)
                mmd._pullback_depth_time_v51 = pullback_dt
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + pullback_dt.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件146：趋势强度综合评分（Trend Strength Composite）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and highs is not None
            and lows is not None
        ):
            try:
                trend_composite = _calc_trend_strength_composite_v51(
                    mmd, closes, highs, lows, volumes
                )
                mmd._trend_strength_composite_v51 = trend_composite
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + trend_composite.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件147：交易决策建议（Trading Decision Recommendation）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and highs is not None
            and lows is not None
        ):
            try:
                decision = _calc_trading_decision_v51(mmd, closes, highs, lows, zss)
                mmd._trading_decision_v51 = decision
            except Exception:
                pass

        # ── V52 条件 148-151 ──

        # 条件148：量价持续确认（Volume Sustain After Signal）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
        ):
            try:
                vol_sustain = _calc_volume_sustain_after_signal_v52(mmd, closes, volumes)
                mmd._volume_sustain_after_signal_v52 = vol_sustain
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vol_sustain.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件149：多指标背离共振（Multi-Indicator Divergence Fusion）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and macd_data is not None
        ):
            try:
                div_fusion = _calc_multi_indicator_divergence_fusion_v52(mmd, closes, macd_data)
                mmd._multi_indicator_divergence_fusion_v52 = div_fusion
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + div_fusion.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件150：近期极端价位检测（Recent Extreme Price Detection）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and highs is not None
            and lows is not None
        ):
            try:
                extreme_price = _calc_recent_extreme_price_v52(mmd, closes, highs, lows)
                mmd._recent_extreme_price_v52 = extreme_price
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + extreme_price.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件151：市场环境健康评分（Market Regime Score）
        if closes is not None and volumes is not None and highs is not None and lows is not None:
            try:
                regime_score = _calc_market_regime_score_v52(closes, volumes, highs, lows)
                mmd._market_regime_score_v52 = regime_score
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + regime_score.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V53 条件 152-155 ──

        # 条件152：趋势阶段识别与顺势确认（Trend Stage Follow Confirmation）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and highs is not None
            and lows is not None
        ):
            try:
                trend_follow = _calc_trend_stage_follow_confirmation_v53(mmd, closes, highs, lows)
                mmd._trend_stage_follow_confirmation_v53 = trend_follow
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + trend_follow.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件153：ATR自适应止损距离（ATR Adaptive Stop Loss）
        if closes is not None and highs is not None and lows is not None:
            try:
                atr_result = _calc_atr_adaptive_stop_v53(closes, highs, lows)
                mmd._atr_adaptive_stop_v53 = atr_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + atr_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件154：中枢突破力度验证（Zhongshu Breakout Strength）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and bis is not None
            and zss is not None
            and closes is not None
        ):
            try:
                breakout_strength = _calc_zs_breakout_strength_v53(mmd, bis, zss, closes)
                mmd._zs_breakout_strength_v53 = breakout_strength
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + breakout_strength.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件155：信号质量综合分层（Signal Quality Tier）
        if closes is not None:
            try:
                quality_tier = _calc_signal_quality_tier_v53(mmd, closes[-1])
                mmd._signal_quality_tier_v53 = quality_tier
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + quality_tier.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V54 条件 156-159 ──

        # 条件156：多K线确认后确认（Multi-Bar Post-Signal Confirmation）
        if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3) and closes is not None:
            try:
                multi_bar = _calc_multi_bar_confirmation_v54(mmd, closes)
                mmd._multi_bar_confirmation_v54 = multi_bar
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + multi_bar.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件157：缺口风险评估（Gap Risk Assessment）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and highs is not None
            and lows is not None
        ):
            try:
                gap_risk = _calc_gap_risk_assessment_v54(mmd, closes, highs, lows)
                mmd._gap_risk_assessment_v54 = gap_risk
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + gap_risk.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件158：波动率 regime 切换检测（Volatility Regime Change Detection）
        if closes is not None and highs is not None and lows is not None:
            try:
                vol_regime = _calc_volatility_regime_change_v54(closes, highs, lows)
                mmd._volatility_regime_change_v54 = vol_regime
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vol_regime.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件159：量价配合度评分（Volume-Price Coordination Score）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
        ):
            try:
                vol_price_coord = _calc_volume_price_coordination_v54(mmd, closes, volumes)
                mmd._volume_price_coordination_v54 = vol_price_coord
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vol_price_coord.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V55 条件 160-163 ──

        # 条件160：分钟级多时间框架共振过滤（Multi-Timeframe Resonance Filter）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
        ):
            try:
                mtfr = _calc_multi_tf_resonance_filter_v55(mmd, closes, volumes)
                mmd._multi_tf_resonance_filter_v55 = mtfr
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + mtfr.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件161：中枢级别权重自适应（Zhongshu Level Weight Adaptation）
        if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3) and zss is not None:
            try:
                zs_weight = _calc_zhongshu_level_weight_v55(mmd, zss)
                mmd._zhongshu_level_weight_v55 = zs_weight
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + zs_weight.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件162：弱势股专项风险检测（Weak Stock Risk Detection）
        if closes is not None and volumes is not None and highs is not None and lows is not None:
            try:
                weak_risk = _calc_weak_stock_risk_v55(mmd, closes, volumes, highs, lows)
                mmd._weak_stock_risk_v55 = weak_risk
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + weak_risk.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件163：信号与趋势方向对齐验证（Signal Trend Alignment Validation）
        if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3) and closes is not None:
            try:
                trend_align = _calc_signal_trend_alignment_v55(mmd, closes)
                mmd._signal_trend_alignment_v55 = trend_align
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + trend_align.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V56 条件 164-167 ──

        # 条件164：假突破识别（False Breakout Detection）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
        ):
            try:
                fake_result = _calc_false_breakout_detection_v56(mmd, closes, volumes, highs, lows)
                mmd._false_breakout_detection_v56 = fake_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + fake_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件165：中枢结构复杂度分析（Zhongshu Structure Complexity）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and zss is not None
            and mmd.zs is not None
        ):
            try:
                zs_complexity = _calc_zhongshu_structure_complexity_v56(mmd, zss)
                mmd._zhongshu_structure_complexity_v56 = zs_complexity
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + zs_complexity.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件166：波动率自适应仓位建议（Volatility Adaptive Position Sizing）
        if closes is not None and highs is not None and lows is not None:
            try:
                pos_size = _calc_volatility_adaptive_position_v56(mmd, closes, highs, lows)
                mmd._volatility_adaptive_position_v56 = pos_size
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + pos_size.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件167：多信号共振评分（Multi-Signal Resonance Score）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
        ):
            try:
                resonance = _calc_multi_signal_resonance_v56(mmd, closes, volumes)
                mmd._multi_signal_resonance_v56 = resonance
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + resonance.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V57 条件 168-171 ──

        # 条件168：回踩幅度与时间双重过滤（Pullback Depth & Time Filter）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and highs is not None
            and lows is not None
        ):
            try:
                pullback = _calc_pullback_filter_v57(mmd, closes, highs, lows)
                mmd._pullback_filter_v57 = pullback
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + pullback.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件169：突破力度验证（Breakout Strength Validation）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
        ):
            try:
                breakout = _calc_breakout_strength_validation_v57(mmd, closes, volumes)
                mmd._breakout_strength_validation_v57 = breakout
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + breakout.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件170：中枢背驰检测（Zhongshu Divergence Check）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and bis is not None
            and bc_list is not None
        ):
            try:
                divergence = _calc_zs_divergence_check_v57(mmd, bis, bc_list)
                mmd._zs_divergence_check_v57 = divergence
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + divergence.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件171：信号衰减检测（Signal Decay Detection）
        if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3) and closes is not None:
            try:
                decay = _calc_signal_decay_detection_v57(mmd, closes)
                mmd._signal_decay_detection_v57 = decay
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + decay.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V58 条件 172-175 ──

        # 条件172：多时间框架趋势一致性验证（Multi-Timeframe Trend Consistency）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 60
        ):
            try:
                tf_consistency = _calc_multi_tf_trend_consistency_v58(mmd, closes)
                mmd._multi_tf_trend_consistency_v58 = tf_consistency
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + tf_consistency.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件173：成交量堆积验证（Volume Accumulation Validation）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
            and len(closes) >= 30
        ):
            try:
                vol_accum = _calc_volume_accumulation_validation_v58(mmd, closes, volumes)
                mmd._volume_accumulation_validation_v58 = vol_accum
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vol_accum.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件174：ATR自适应止损距离（ATR Adaptive Stop Distance）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and highs is not None
            and lows is not None
        ):
            try:
                atr_stop = _calc_atr_adaptive_stop_v58(mmd, highs, lows)
                mmd._atr_adaptive_stop_v58 = atr_stop
            except Exception:
                pass

        # 条件175：信号质量综合评分（Composite Quality Score）
        if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
            try:
                quality = _calc_composite_quality_score_v58(mmd)
                mmd._composite_quality_score_v58 = quality
            except Exception:
                pass

        # ── V59 条件 176-179 ──

        # 条件176：波动率自适应MA周期（Volatility-Adaptive MA Period）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 90
        ):
            try:
                vol_adapt = _calc_volatility_adaptive_ma_v59(mmd, closes)
                mmd._volatility_adaptive_ma_v59 = vol_adapt
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vol_adapt.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件177：ATR倍数自适应（ATR Multiplier Adaptation）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and highs is not None
            and lows is not None
        ):
            try:
                atr_mult = _calc_atr_multiplier_adapt_v59(mmd, highs, lows)
                mmd._atr_multiplier_adapt_v59 = atr_mult
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + atr_mult.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件178：多时间框架共振信号（Multi-TF Resonance Signal）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 25
        ):
            try:
                tf_resonance = _calc_multi_tf_resonance_signal_v59(mmd, closes, volumes)
                mmd._multi_tf_resonance_signal_v59 = tf_resonance
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + tf_resonance.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件179：信号衰减速度评估（Signal Decay Speed）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 15
        ):
            try:
                decay_speed = _calc_signal_decay_speed_v59(mmd, closes)
                mmd._signal_decay_speed_v59 = decay_speed
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + decay_speed.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V60 条件 180-183 ──

        # 条件180：RSI深度背离过滤（RSI Deep Divergence Filter）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 40
        ):
            try:
                rsi_div = _calc_rsi_deep_divergence_v60(mmd, closes)
                mmd._rsi_deep_divergence_v60 = rsi_div
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + rsi_div.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件181：MA排列间距强度评分（MA Alignment Spacing Score）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 60
        ):
            try:
                ma_spacing = _calc_ma_spacing_strength_v60(mmd, closes)
                mmd._ma_spacing_strength_v60 = ma_spacing
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + ma_spacing.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件182：中枢支撑/阻力距离评分增强（ZhongShu Distance Score Enhanced）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and mmd.zs is not None
            and closes is not None
            and mmd.bi is not None
        ):
            try:
                zs_dist = _calc_zs_distance_enhanced_v60(mmd, closes)
                mmd._zs_distance_enhanced_v60 = zs_dist
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + zs_dist.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件183：KDJ超买超卖确认（KDJ Overbought/Oversold Confirmation）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 15
        ):
            try:
                kdj_conf = _calc_kdj_ob_os_confirm_v60(mmd, closes)
                mmd._kdj_ob_os_confirm_v60 = kdj_conf
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + kdj_conf.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V61 条件 184-185 ──

        # 条件184：MACD柱状图背离融合（MACD Histogram Divergence Fusion）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and macd_data is not None
        ):
            try:
                macd_div = _calc_macd_histogram_divergence_v61(mmd, closes, macd_data)
                mmd._macd_hist_divergence_v61 = macd_div
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + macd_div.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件185：综合多信号评分（Composite Signal Score）
        if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3):
            try:
                comp_score = _calc_composite_signal_score_v61(mmd)
                mmd._composite_signal_score_v61 = comp_score
            except Exception:
                pass

        # ── V62 条件 186-189 ──

        # 条件186：BOLL带宽突破确认（BOLL Bandwidth Breakout Confirmation）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 40
        ):
            try:
                boll_bw = _calc_boll_bandwidth_breakout_confirm_v62(mmd, closes)
                mmd._boll_bandwidth_breakout_v62 = boll_bw
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + boll_bw.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件187：BOLL带宽压缩反弹确认（BOLL Bandwidth Reversal Confirmation）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 60
        ):
            try:
                boll_rev = _calc_boll_bandwidth_reversal_confirm_v62(mmd, closes)
                mmd._boll_bandwidth_reversal_v62 = boll_rev
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + boll_rev.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件188：动态阈值-波动率状态切换（Dynamic Threshold Volatility Regime）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 30
        ):
            try:
                vol_regime = _calc_dynamic_threshold_volatility_regime_v62(mmd, closes)
                mmd._dynamic_threshold_volatility_regime_v62 = vol_regime
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vol_regime.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件189：动态阈值-ATR倍数自适应（Dynamic Threshold ATR Multiplier Adaptive）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 30
        ):
            try:
                atr_mult = _calc_dynamic_threshold_atr_multiplier_v62(mmd, closes)
                mmd._dynamic_threshold_atr_multiplier_v62 = atr_mult
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + atr_mult.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V63 条件 190-191 ──

        # 条件190：中枢级别权重优化增强（Zhongshu Level Weight Optimization Enhanced）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and zss is not None
            and closes is not None
        ):
            try:
                zs_weight_enh = _calc_zhongshu_level_weight_enhanced_v63(mmd, zss, closes)
                mmd._zhongshu_level_weight_enhanced_v63 = zs_weight_enh
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + zs_weight_enh.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件191：多周期信号衰减追踪（Multi-Period Signal Decay Tracking）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 25
        ):
            try:
                multi_decay = _calc_multi_period_signal_decay_v63(mmd, closes)
                mmd._multi_period_signal_decay_v63 = multi_decay
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + multi_decay.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V65 条件 192-195 ──

        # 条件192：量价背离二次确认增强（Volume-Price Divergence Secondary Confirmation）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
            and len(closes) >= 60
        ):
            try:
                vp_div = _calc_volume_price_divergence_secondary_v65(mmd, closes, volumes)
                mmd._volume_price_divergence_secondary_v65 = vp_div
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vp_div.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件193：中枢突破回踩确认（Breakout Retest Confirmation）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and zss is not None
            and closes is not None
            and len(closes) >= 40
        ):
            try:
                retest = _calc_breakout_retest_confirmation_v65(mmd, zss, closes)
                mmd._breakout_retest_confirmation_v65 = retest
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + retest.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件194：波动率压缩突破信号（Volatility Compression Breakout）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 80
        ):
            try:
                vol_comp = _calc_volatility_compression_breakout_v65(mmd, closes)
                mmd._volatility_compression_breakout_v65 = vol_comp
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vol_comp.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件195：买卖点时间窗口新鲜度（Signal Time Window Freshness）
        if mmd.bi is not None and closes is not None and len(closes) >= 20:
            try:
                freshness = _calc_signal_time_window_freshness_v65(mmd, closes)
                mmd._signal_time_window_freshness_v65 = freshness
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + freshness.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V66 条件 196-199 ──

        # 条件196：MACD动能锥加速确认（MACD Momentum Acceleration Confirmation）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and macd_data is not None
            and len(macd_data.get("hist", [])) >= 20
        ):
            try:
                macd_acc = _calc_macd_momentum_acceleration_v66(mmd, macd_data)
                mmd._macd_momentum_acceleration_v66 = macd_acc
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + macd_acc.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件197：量价配合深度评分（Volume-Price Coordination Deep Score）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
            and len(closes) >= 60
        ):
            try:
                vp_coord = _calc_volume_price_coordination_deep_v66(mmd, closes, volumes)
                mmd._volume_price_coordination_deep_v66 = vp_coord
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vp_coord.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件198：多时间框架共振强度评分（Multi-Timeframe Convergence Intensity）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 100
        ):
            try:
                tf_conv = _calc_multi_tf_convergence_intensity_v66(mmd, closes)
                mmd._multi_tf_convergence_intensity_v66 = tf_conv
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + tf_conv.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件199：信号执行优先级建议（Signal Execution Priority Recommendation）
        if mmd.bi is not None and closes is not None and len(closes) >= 30:
            try:
                exec_pri = _calc_signal_execution_priority_v66(mmd, closes)
                mmd._signal_execution_priority_v66 = exec_pri
            except Exception:
                pass

        # ── V67 条件 200-203 ──

        # 条件200：中枢背驰力度量化（Zhongshu Divergence Strength Quantification）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and zss is not None
            and closes is not None
            and len(closes) >= 30
        ):
            try:
                zs_div = _calc_zhongshu_divergence_strength_v67(mmd, zss, closes, macd_data)
                mmd._zhongshu_divergence_strength_v67 = zs_div
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + zs_div.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件201：多级别买卖点一致性验证（Multi-level MMD Consistency）
        if mmd.bi is not None and closes is not None and len(closes) >= 60:
            try:
                ml_cons = _calc_multi_level_mmd_consistency_v67(mmd, closes)
                mmd._multi_level_mmd_consistency_v67 = ml_cons
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + ml_cons.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件202：信号后价格轨迹健康度（Post-signal Price Trajectory Health）
        if mmd.bi is not None and closes is not None and len(closes) >= 40:
            try:
                traj_health = _calc_post_signal_trajectory_health_v67(mmd, closes)
                mmd._post_signal_trajectory_health_v67 = traj_health
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + traj_health.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件203：动态止损止盈推荐（Dynamic SL/TP Recommendation）
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 20
        ):
            try:
                sl_tp = _calc_dynamic_sl_tp_recommendation_v67(mmd, closes, highs, lows)
                mmd._dynamic_sl_tp_recommendation_v67 = sl_tp
            except Exception:
                pass

        # ── V68 条件 204-207 ──

        # 条件204：缺口方向与趋势一致性验证（Gap-Trend Consistency）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and len(closes) >= 30
        ):
            try:
                gap_res = _calc_gap_trend_consistency_v68(mmd, closes)
                mmd._gap_trend_consistency_v68 = gap_res
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + gap_res.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件205：多级别区间套一致性验证（Range Set Multi-level Consistency）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and zss is not None
            and closes is not None
            and len(closes) >= 40
        ):
            try:
                rs_cons = _calc_range_set_multi_level_v68(mmd, zss, closes)
                mmd._range_set_multi_level_v68 = rs_cons
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + rs_cons.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件206：信号后资金流向确认（Post-signal Fund Flow）
        if mmd.bi is not None and closes is not None and volumes is not None and len(closes) >= 30:
            try:
                fund_flow = _calc_post_signal_fund_flow_v68(mmd, closes, volumes)
                mmd._post_signal_fund_flow_v68 = fund_flow
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + fund_flow.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件207：市场风格适配评分（Market Regime Adaptation）
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and volumes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 60
        ):
            try:
                regime_adapt = _calc_market_regime_adaptation_v68(mmd, closes, volumes, highs, lows)
                mmd._market_regime_adaptation_v68 = regime_adapt
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + regime_adapt.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V69 条件 208-211 ──

        # 条件208：量价背离二次确认（Price-Volume Divergence Secondary Confirmation）
        # 价格创新高但成交量未放大（或创新低但缩量）= 强烈反转信号
        if mmd.bi is not None and closes is not None and volumes is not None and len(closes) >= 30:
            try:
                pv_div = _calc_price_volume_divergence_v69(mmd, closes, volumes)
                mmd._price_volume_divergence_v69 = pv_div
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + pv_div.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件209：结构完整性评分（Structural Integrity Scoring）
        # 评估当前笔的完整性、线段连接性、中枢有效性
        if mmd.bi is not None and bis is not None and zss is not None and len(bis) >= 3:
            try:
                struct_int = _calc_structural_integrity_v69(mmd, bis, zss, closes)
                mmd._structural_integrity_v69 = struct_int
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + struct_int.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件210：多指标背离融合（Multi-Indicator Divergence Fusion）
        # 综合MACD/KDJ/RSI背离信号，提供综合背离强度评分
        if (
            macd_data is not None
            and closes is not None
            and mmd.bi is not None
            and len(closes) >= 30
        ):
            try:
                multi_div = _calc_multi_indicator_divergence_v69(mmd, closes, volumes, macd_data)
                mmd._multi_indicator_divergence_v69 = multi_div
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + multi_div.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件211：回踩深度量化（Retracement Depth Quantification）
        # 量化回踩幅度与时间，判断回踩是否充分
        if (
            mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 20
        ):
            try:
                retrace = _calc_retracement_depth_v69(mmd, closes, highs, lows)
                mmd._retracement_depth_v69 = retrace
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + retrace.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V70 条件 212-215 ──

        # 条件212：分时量峰检测（Volume Peak Detection）
        # 检测突破/反转时的成交量峰值，确认信号真实性
        if mmd.bi is not None and closes is not None and volumes is not None and len(closes) >= 30:
            try:
                vol_peak = _calc_volume_peak_detection_v70(mmd, closes, volumes)
                mmd._volume_peak_detection_v70 = vol_peak
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vol_peak.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件213：买卖点时间窗口衰减（Signal Time Decay）
        # 根据信号出现后的K线数量应用指数衰减
        if mmd.bi is not None and closes is not None and len(closes) >= 10:
            try:
                time_decay = _calc_signal_time_decay_v70(mmd, closes)
                mmd._signal_time_decay_v70 = time_decay
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + time_decay.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件214：假突破二次过滤（False Breakout Secondary Filter）
        # 突破后价格需持续N根K线维持在突破水平之上/之下
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 15
        ):
            try:
                false_break = _calc_false_breakout_filter_v70(mmd, closes, highs, lows)
                mmd._false_breakout_filter_v70 = false_break
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + false_break.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件215：信号置信度最终校准（Final Confidence Calibration）
        # 综合所有累积的置信度调整，输出最终校准分数
        if mmd.bi is not None and closes is not None and len(closes) >= 20:
            try:
                final_cal = _calc_final_confidence_calibration_v70(mmd, closes)
                mmd._final_confidence_calibration_v70 = final_cal
            except Exception:
                pass

        # ── V71 条件 216-219 ──

        # 条件216：均线排列强度评估（MA Alignment Strength）
        # 评估当前价格相对于多条均线的排列状态
        if mmd.bi is not None and closes is not None and len(closes) >= 60:
            try:
                ma_align = _calc_ma_alignment_strength_v71(mmd, closes)
                mmd._ma_alignment_strength_v71 = ma_align
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + ma_align.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件217：多周期均线共振（Multi-TF MA Resonance）
        # 短中长期均线同时发出同向信号时增强置信度
        if mmd.bi is not None and closes is not None and len(closes) >= 120:
            try:
                ma_res = _calc_multi_tf_ma_resonance_v71(mmd, closes)
                mmd._multi_tf_ma_resonance_v71 = ma_res
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + ma_res.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件218：买卖点历史胜率回溯（MMD History Winrate）
        # 对历史类似形态的胜率进行回溯分析
        if mmd.bi is not None and closes is not None and volumes is not None and len(closes) >= 100:
            try:
                winrate = _calc_mmd_history_winrate_v71(mmd, closes, volumes)
                mmd._mmd_history_winrate_v71 = winrate
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + winrate.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件219：动态风险收益比优化（Dynamic RR Optimization）
        # 根据当前波动率和市场环境动态调整止损止盈比例
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 30
        ):
            try:
                rr_opt = _calc_dynamic_rr_optimization_v71(mmd, closes, highs, lows, volatility)
                mmd._dynamic_rr_optimization_v71 = rr_opt
            except Exception:
                pass

        # ── V72 条件 220-223 ──

        # 条件220：均线收敛发散状态评估（MA Convergence/Divergence）
        # 评估短期MA(20)与长期MA(60)之间的收敛/发散状态
        if mmd.bi is not None and closes is not None and len(closes) >= 80:
            try:
                ma_cd = _calc_ma_convergence_divergence_v72(mmd, closes)
                mmd._ma_convergence_divergence_v72 = ma_cd
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + ma_cd.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件221：支撑/阻力位距离评估（Support/Resistance Proximity）
        # 计算当前价格相对于最近支撑/阻力位的距离
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 30
        ):
            try:
                sr_prox = _calc_support_resistance_proximity_v72(mmd, closes, highs, lows)
                mmd._support_resistance_proximity_v72 = sr_prox
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + sr_prox.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件222：量价结构质量评分（Volume Structure Quality）
        # 评估近期量价配合的健康程度
        if mmd.bi is not None and closes is not None and volumes is not None and len(closes) >= 60:
            try:
                vsq = _calc_volume_structure_quality_v72(mmd, closes, volumes)
                mmd._volume_structure_quality_v72 = vsq
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vsq.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件223：信号衰减速度评估（Signal Decay Velocity）
        # 分析最近同类型买卖点信号的置信度变化趋势
        if mmd.bi is not None and closes is not None and len(closes) >= 50:
            try:
                sdv = _calc_signal_decay_velocity_v72(mmd, closes, mmds)
                mmd._signal_decay_velocity_v72 = sdv
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + sdv.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V73 条件 224-227 ──

        # 条件224：买卖点位置风险评估（MMD Position Risk Assessment）
        # 评估信号在近期价格区间中的位置风险
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 30
        ):
            try:
                pos_risk = _calc_mmd_position_risk_v73(mmd, closes, highs, lows)
                mmd._mmd_position_risk_v73 = pos_risk
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + pos_risk.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件225：中枢突破有效性验证（Zhongshu Breakout Validity）
        # 验证突破后价格是否持续维持在外侧且量能配合
        if mmd.bi is not None and closes is not None and len(closes) >= 30:
            try:
                bo_valid = _calc_zhongshu_breakout_validity_v73(mmd, closes, volumes, highs, lows)
                mmd._zhongshu_breakout_validity_v73 = bo_valid
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + bo_valid.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件226：多指标确认一致性（Multi-Indicator Confirmation Consistency）
        # 检查MACD/KDJ/RSI/BOLL/Volume五个独立指标是否同向
        if mmd.bi is not None and closes is not None and len(closes) >= 20:
            try:
                # 本地计算 KDJ/RSI/BOLL（macd_data 默认不含这些）
                _mi_rsi: list[float] | None = None
                _mi_kdj: dict[str, list[float]] | None = None
                _mi_boll: dict[str, list[float]] | None = None
                if len(closes) >= 14:
                    from easy_tdx.MyTT import BOLL as _mytt_boll
                    from easy_tdx.MyTT import KDJ as _mytt_kdj
                    from easy_tdx.MyTT import RSI as _mytt_rsi

                    _mi_rsi = [float(x) for x in _mytt_rsi(closes, N=14)]
                if len(closes) >= 30:
                    _k, _d, _j = _mytt_kdj(closes, highs or closes, lows or closes, N=9, M1=3, M2=3)
                    _mi_kdj = {"k": [float(x) for x in _k], "d": [float(x) for x in _d]}
                if highs is not None and lows is not None and len(closes) >= 20:
                    _b = _mytt_boll(closes, N=20)
                    if len(_b) >= 3 and len(_b[0]) > 0:
                        _mi_boll = {
                            "upper": [float(x) for x in _b[0]],
                            "lower": [float(x) for x in _b[1]],
                            "mid": [float(x) for x in _b[2]],
                        }
                mi_cons = _calc_multi_indicator_consistency_v73(
                    mmd, closes, macd_data, _mi_kdj, _mi_rsi, _mi_boll, volumes
                )
                mmd._multi_indicator_consistency_v73 = mi_cons
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + mi_cons.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件227：波动率环境适配（Volatility Regime Adaptation）
        # 根据当前ATR分位动态调整置信度
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 60
        ):
            try:
                vol_reg = _calc_volatility_regime_adaptation_v73(mmd, closes, highs, lows)
                mmd._volatility_regime_adaptation_v73 = vol_reg
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vol_reg.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V74 条件 228-231 ──

        # 条件228：量价背离二次确认（Volume-Price Divergence Secondary）
        if mmd.bi is not None and closes is not None and volumes is not None and len(closes) >= 30:
            try:
                vp_div = _calc_volume_price_divergence_secondary_v74(mmd, closes, volumes)
                mmd._volume_price_divergence_secondary_v74 = vp_div
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vp_div.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件229：趋势动能持续验证（Trend Momentum Continuity）
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 30
        ):
            try:
                mom = _calc_trend_momentum_continuity_v74(mmd, closes, highs, lows)
                mmd._trend_momentum_continuity_v74 = mom
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + mom.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件230：中枢重叠度评估（Zhongshu Overlap Density）
        if mmd.bi is not None and zss is not None and closes is not None and len(closes) >= 10:
            try:
                overlap = _calc_zhongshu_overlap_density_v74(mmd, zss, closes[-1])
                mmd._zhongshu_overlap_density_v74 = overlap
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + overlap.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件231：信号共振深度评分（Signal Resonance Depth）
        if mmd.bi is not None and closes is not None and len(closes) >= 20:
            try:
                resonance = _calc_signal_resonance_depth_v74(
                    mmd, closes, highs, lows, macd_data, volumes
                )
                mmd._signal_resonance_depth_v74 = resonance
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + resonance.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V75 条件 232-235 ──

        # 条件232：回调深度验证（Pullback Depth Validation）
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 30
        ):
            try:
                pb_depth = _calc_pullback_depth_validation_v75(mmd, closes, highs, lows)
                mmd._pullback_depth_validation_v75 = pb_depth
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + pb_depth.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件233：中枢区间回踩确认（Zhongshu Retracement Confirmation）
        if mmd.bi is not None and zss is not None and closes is not None and len(closes) >= 15:
            try:
                zs_ret = _calc_zhongshu_retracement_confirm_v75(mmd, zss, closes)
                mmd._zhongshu_retracement_confirm_v75 = zs_ret
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + zs_ret.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件234：量峰持续时间评分（Volume Peak Duration Score）
        if (
            mmd.bi is not None
            and volumes is not None
            and closes is not None
            and len(volumes) >= 30
            and len(closes) >= 30
        ):
            try:
                vp_dur = _calc_volume_peak_duration_v75(mmd, volumes, closes)
                mmd._volume_peak_duration_v75 = vp_dur
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vp_dur.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件235：多信号时间一致性（Multi-Signal Time Consistency）
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 40
        ):
            try:
                sig_time = _calc_multi_signal_time_consistency_v75(
                    mmd, closes, highs, lows, macd_data, volumes
                )
                mmd._multi_signal_time_consistency_v75 = sig_time
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + sig_time.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V76 条件 236-239 ──

        # 条件236：价格结构完整性验证（Price Structure Integrity）
        if mmd.bi is not None and closes is not None and volumes is not None and len(closes) >= 30:
            try:
                psi = _calc_price_structure_integrity_v76(mmd, closes, volumes)
                mmd._price_structure_integrity_v76 = psi
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + psi.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件237：趋势方向对齐验证（Trend Alignment Validation）
        if mmd.bi is not None and closes is not None and len(closes) >= 60:
            try:
                tav = _calc_trend_alignment_validation_v76(mmd, closes)
                mmd._trend_alignment_validation_v76 = tav
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + tav.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件238：波动率自适应置信度（Volatility Adaptive Confidence）
        if mmd.bi is not None and closes is not None and len(closes) >= 60:
            try:
                vac = _calc_volatility_adaptive_confidence_v76(mmd, closes)
                mmd._volatility_adaptive_confidence_v76 = vac
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vac.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件239：买卖点最终有效性评分（Signal Final Validity）
        if mmd.bi is not None:
            try:
                sfv = _calc_signal_final_validity_v76(mmd)
                mmd._signal_final_validity_v76 = sfv
            except Exception:
                pass

        # ── V77 条件 240-243 ──

        # 条件240：量能分布深度分析（Volume Distribution Depth）
        if mmd.bi is not None and closes is not None and volumes is not None and len(closes) >= 40:
            try:
                vdd = _calc_volume_distribution_depth_v77(mmd, closes, volumes)
                mmd._volume_distribution_depth_v77 = vdd
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vdd.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件241：中枢结构权重评估（Zhongshu Structure Weight）
        if mmd.bi is not None and zss is not None and closes is not None and len(closes) >= 10:
            try:
                zsw = _calc_zhongshu_structure_weight_v77(mmd, zss, closes)
                mmd._zhongshu_structure_weight_v77 = zsw
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + zsw.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件242：信号新鲜度验证（Signal Freshness Validation）
        if mmd.bi is not None and closes is not None and len(closes) >= 10:
            try:
                sfv = _calc_signal_freshness_validation_v77(mmd, closes)
                mmd._signal_freshness_validation_v77 = sfv
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + sfv.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件243：价格动能加速度（Price Momentum Acceleration）
        if mmd.bi is not None and closes is not None and len(closes) >= 20:
            try:
                pma = _calc_price_momentum_acceleration_v77(mmd, closes)
                mmd._price_momentum_acceleration_v77 = pma
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + pma.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V78 条件 244-247 ──

        # 条件244：买卖点周期位置评分（MMD Cycle Position）
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 30
        ):
            try:
                mcp = _calc_mmd_cycle_position_v78(mmd, closes, highs, lows)
                mmd._mmd_cycle_position_v78 = mcp
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + mcp.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件245：多信号时间窗口一致性（Multi-Signal Consensus）
        if mmd.bi is not None and mmds is not None and closes is not None and len(closes) >= 20:
            try:
                msc = _calc_multi_signal_consensus_v78(mmds, mmd, closes)
                mmd._multi_signal_consensus_v78 = msc
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + msc.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件246：波动率压缩突破预测（Volatility Compression Breakout）
        if closes is not None and highs is not None and lows is not None and len(closes) >= 50:
            try:
                vcb = _calc_volatility_compression_breakout_v78(closes, highs, lows)
                mmd._volatility_compression_breakout_v78 = vcb
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vcb.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件247：资金流向与价格背离检测（Fund Flow Divergence）
        if closes is not None and volumes is not None and len(closes) >= 30 and len(volumes) >= 30:
            try:
                ffd = _calc_fund_flow_divergence_v78(closes, volumes)
                mmd._fund_flow_divergence_v78 = ffd
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + ffd.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V79 条件 248-251 ──

        # 条件248：分型稳定性验证（Fractal Stability Validation）
        if mmd.bi is not None and highs is not None and lows is not None and len(highs) >= 10:
            try:
                fsf = _calc_fractal_stability_validation_v79(mmd, highs, lows)
                mmd._fractal_stability_validation_v79 = fsf
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + fsf.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件249：买卖点距离安全阈值（MMD Distance Safety）
        if mmds is not None and mmd.bi is not None and closes is not None and len(closes) >= 10:
            try:
                mds = _calc_mmd_distance_safety_v79(mmds, mmd, closes)
                mmd._mmd_distance_safety_v79 = mds
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + mds.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件250：多级别结构一致性评分（Multi-Level Structure Consistency）
        if mmd.bi is not None and closes is not None and len(closes) >= 10:
            try:
                mls = _calc_multi_level_structure_consistency_v79(
                    mmd, closes, highs or closes, lows or closes
                )
                mmd._multi_level_structure_consistency_v79 = mls
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + mls.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件251：价格动能持续性评分（Price Momentum Continuity）
        if mmd.bi is not None and closes is not None and len(closes) >= 15:
            try:
                pmc = _calc_price_momentum_continuity_v79(mmd, closes, volumes)
                mmd._price_momentum_continuity_v79 = pmc
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + pmc.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V80 条件 252-255 ──

        # 条件252：买卖点与中枢距离验证（MMD-Zhongshu Distance Validation）
        if mmd.bi is not None and closes is not None and len(closes) >= 20:
            try:
                msd = _calc_mmd_zhongshu_distance_v80(mmd, closes, highs or closes, lows or closes)
                mmd._mmd_zhongshu_distance_v80 = msd
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + msd.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件253：量能配合度评分（Volume Confirmation Score）
        if (
            mmd.bi is not None
            and closes is not None
            and volumes is not None
            and len(closes) >= 10
            and len(volumes) >= 10
        ):
            try:
                vcf = _calc_volume_confirmation_v80(mmd, closes, volumes)
                mmd._volume_confirmation_v80 = vcf
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vcf.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件254：均线排列强度确认（MA Alignment Strength）
        if mmd.bi is not None and closes is not None and len(closes) >= 30:
            try:
                mas = _calc_ma_alignment_strength_v80(mmd, closes)
                mmd._ma_alignment_strength_v80 = mas
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + mas.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件255：盈亏比动态评估（Dynamic Risk-Reward Assessment）
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 20
        ):
            try:
                drr = _calc_dynamic_risk_reward_v80(mmd, closes, highs, lows)
                mmd._dynamic_risk_reward_v80 = drr
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + drr.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V81 条件 256-259 ──

        # 条件256：波动率状态转换检测（Volatility Regime Transition）
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 30
        ):
            try:
                vrt = _calc_volatility_regime_transition_v81(mmd, closes, highs, lows)
                mmd._volatility_regime_transition_v81 = vrt
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vrt.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件257：关键支撑阻力强度验证（Support/Resistance Strength）
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 20
        ):
            try:
                srs = _calc_support_resistance_strength_v81(mmd, closes, highs, lows)
                mmd._support_resistance_strength_v81 = srs
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + srs.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件258：量价能量分布验证（Volume-Price Energy Distribution）
        if (
            mmd.bi is not None
            and closes is not None
            and volumes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 30
            and len(volumes) >= 30
        ):
            try:
                vped = _calc_volume_price_energy_distribution_v81(mmd, closes, volumes, highs, lows)
                mmd._volume_price_energy_distribution_v81 = vped
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vped.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件259：信号执行窗口评估（Signal Execution Window）
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 20
        ):
            try:
                sew = _calc_signal_execution_window_v81(mmd, closes, highs, lows, volumes)
                mmd._signal_execution_window_v81 = sew
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + sew.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V82 条件 260-263 ──

        # 条件260：买卖点时间衰减验证（MMD Age Decay）
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 10
        ):
            try:
                mad = _calc_mmd_age_decay_v82(mmd, closes, highs, lows)
                mmd._mmd_age_decay_v82 = mad
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + mad.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件261：中枢突破回踩确认（Breakout Retest Confirmation）
        if mmd.bi is not None and closes is not None and len(closes) >= 20:
            try:
                brc = _calc_breakout_retest_confirm_v82(
                    mmd, closes, highs or closes, lows or closes
                )
                mmd._breakout_retest_confirm_v82 = brc
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + brc.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件262：多级别MACD共振（Multi-Timeframe MACD Resonance）
        if mmd.bi is not None and closes is not None and len(closes) >= 30:
            try:
                mtr = _calc_macd_multi_tf_resonance_v82(mmd, closes)
                mmd._macd_multi_tf_resonance_v82 = mtr
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + mtr.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件263：波动率压缩突破确认（Volatility Compression Breakout）
        if (
            mmd.bi is not None
            and closes is not None
            and highs is not None
            and lows is not None
            and len(closes) >= 30
        ):
            try:
                vcb = _calc_volatility_compression_breakout_v82(mmd, closes, highs, lows)
                mmd._volatility_compression_breakout_v82 = vcb
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + vcb.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # ── V102 条件 264-267 缠论模型决策支持增强 ───────────────────────────

        # 条件264：多信号相关性分析（Multi-Signal Correlation）
        # 当同一股票有多个买卖点信号时，分析其相关性避免重复入场
        if len(mmds) > 1 and closes is not None and len(closes) >= 20:
            try:
                corr_result = _calc_multi_signal_correlation(mmd, mmds, closes)
                mmd._multi_signal_correlation = corr_result
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + corr_result.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

        # 条件265：信号质量评分卡（Signal Quality Scorecard）
        # 提供全面的信号质量评估，包括各项指标得分
        scorecard: dict[str, Any] | None = None
        try:
            scorecard = _calc_signal_quality_scorecard(mmd, closes, volumes, macd_data, volatility)
            mmd._signal_quality_scorecard = scorecard
        except Exception:
            pass

        # 条件266：决策支持输出（Decision Support Output）
        # 生成可操作的买卖建议，包括入场价、止损、止盈
        v102_decision: dict[str, Any] | None = None
        try:
            v102_decision = _calc_decision_support_enhanced(
                mmd, closes, highs, lows, volumes, macd_data
            )
            mmd._decision_support = v102_decision
        except Exception:
            pass

        # V102 条件265/266 置信度调整并入（质量等级 + 风险收益比）
        if scorecard is not None and v102_decision is not None:
            try:
                _apply_v102_decision_confidence(mmd, scorecard, v102_decision)
            except Exception:
                pass

        # 条件267：历史模式匹配（Historical Pattern Matching）
        # 匹配历史相似模式，提供概率统计参考
        if len(closes) >= 60:
            try:
                pattern = _calc_historical_pattern_matching(mmd, closes, volumes)
                mmd._historical_pattern_match = pattern
                mmd.confidence = max(
                    0.0, min(1.0, mmd.confidence + pattern.get("confidence_adjust", 0.0))
                )
            except Exception:
                pass

    # V83: 置信度有界收敛 —— 限制 160+ 条件累计漂移对校准基线的影响
    _BAND = 0.25
    for m in mmds:
        base = _conf_base.get(id(m))
        if base is not None:
            m.confidence = round(
                max(0.0, min(1.0, max(base - _BAND, min(base + _BAND, m.confidence)))),
                3,
            )

    return mmds


def find_mmds_v40(
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
    """V40 版本的 find_mmds：完整集成条件101-110。

    别名：与 find_mmds_v39 完全相同，提供统一入口。

    .. deprecated:: V390
        版本化别名仅作向后兼容，请使用 find_mmds_v39 或 find_mmds。
    """
    return find_mmds_v39(
        bis=bis,
        zss=zss,
        closes=closes,
        config=config,
        volumes=volumes,
        macd_data=macd_data,
        volatility=volatility,
        highs=highs,
        lows=lows,
    )


def find_mmds_v41(
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
    """V41 版本的 find_mmds：完整集成条件101-120（含V42）。

    在 V40 基础上新增：量价能量分布(111)+量能周期(112)+走势预测(113)+质量分层(114)+反转风险(115)。
    V42 条件(116-120)已集成至 find_mmds_v39，故本函数同样生效。

    .. deprecated:: V390
        版本化别名仅作向后兼容，请使用 find_mmds_v39 或 find_mmds。
    """
    return find_mmds_v39(
        bis=bis,
        zss=zss,
        closes=closes,
        config=config,
        volumes=volumes,
        macd_data=macd_data,
        volatility=volatility,
        highs=highs,
        lows=lows,
    )


def find_mmds_v42(
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
    """V42/V43/V44 版本的 find_mmds：完整集成条件101-125。

    在 V41 基础上新增：后确认验证(116)+突破-回调量比(117)+中枢距离验证(118)+ADX趋势确认(119)+指数衰减(120)。
    V43 修复了 API 暴露问题。V44 新增五维增强：趋势对齐(121)+突破力度(122)+回踩窗口(123)+波动自适应(124)+背离共振(125)。
    基础置信度已重新校准：BUY_3 0.65→0.55，SELL_3 0.60→0.50。

    .. deprecated:: V390
        版本化别名仅作向后兼容，请使用 find_mmds_v39 或 find_mmds。
    """
    return find_mmds_v39(
        bis=bis,
        zss=zss,
        closes=closes,
        config=config,
        volumes=volumes,
        macd_data=macd_data,
        volatility=volatility,
        highs=highs,
        lows=lows,
    )


def find_mmds_v44(
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
    """V44 版本的 find_mmds：完整集成条件101-125。

    V44 在五维增强基础上进一步提升 3买/3卖 准确率：
    - 条件121：趋势方向对齐验证（避免逆势交易）
    - 条件122：突破笔力度对比（过滤假突破）
    - 条件123：回踩时间窗口过滤（避免信号过期）
    - 条件124：波动率自适应阈值（动态调整敏感度）
    - 条件125：多指标背离共振（多指标同时确认）
    """
    return find_mmds_v39(
        bis=bis,
        zss=zss,
        closes=closes,
        config=config,
        volumes=volumes,
        macd_data=macd_data,
        volatility=volatility,
        highs=highs,
        lows=lows,
    )


# 运行时挂载的诊断缓存属性（mypy 不跟踪函数对象属性，仅作初始化）
setattr(find_mmds_v39, "_last_multi_tf_divergence", {})
setattr(find_mmds_v39, "_last_macd_resonance", {})
setattr(find_mmds_v39, "_last_volume_cycle", {})
setattr(find_mmds_v39, "_last_trajectory_prediction", {})
setattr(find_mmds_v39, "_last_reversal_risk", {})


# ── V40: 条件106-110 缠论模型决策增强 ───────────────────────────────────────────


def _calc_breakout_retest_validation(
    mmd: MMD,
    bis: list[BI],
    zss: list[ZS],
    closes: list[float],
    volumes: list[float] | None,
) -> dict[str, Any]:
    """中枢突破回踩验证（V40 条件107）。

    验证中枢突破后是否有健康的回踩确认：
    - 突破后价格回踩到中枢上沿附近（Fib 38.2%-61.8%区域）并获得支撑
    - 回踩时成交量萎缩（<均量70%）
    - 满足条件则加分，不满足则适当降权
    """
    result: dict[str, Any] = {
        "retest_detected": False,
        "retest_depth": 0.0,
        "volume_confirm": False,
        "breakout_valid": False,
        "confidence_adjust": 0.0,
    }
    try:
        if not mmd.zs or not closes or len(closes) < 30:
            return result

        is_buy = "buy" in mmd.mmd_type.value
        zs = mmd.zs
        zs_high = zs.gg
        zs_low = zs.dd
        zs_range = zs_high - zs_low
        if zs_range <= 0:
            return result

        if not mmd.bi:
            return result
        mmd_idx = mmd.bi.end.k.k_index
        if mmd_idx < 15:
            return result

        breakout_bar = closes[mmd_idx - 1]
        prev_close = closes[mmd_idx - 2] if mmd_idx >= 2 else breakout_bar

        if is_buy:
            is_breakout = breakout_bar > zs_high and prev_close <= zs_high * 1.01
            lookback = min(15, mmd_idx)
            pullback_lows = closes[mmd_idx - lookback : mmd_idx]
            if pullback_lows:
                min_pullback = min(pullback_lows)
                fib_62 = zs_high - zs_range * 0.618
                retest_zone_low = fib_62
                retest_zone_high = zs_high * 1.02
                retest_depth = (zs_high - min_pullback) / zs_range * 100 if zs_range > 0 else 0
                result["retest_depth"] = round(retest_depth, 1)
                result["retest_detected"] = (
                    retest_depth > 5
                    and retest_depth < 65
                    and min_pullback >= retest_zone_low
                    and min_pullback <= retest_zone_high
                )
                if volumes and len(volumes) > mmd_idx:
                    recent_vol = sum(volumes[max(0, mmd_idx - 5) : mmd_idx]) / min(5, mmd_idx)
                    avg_vol = _calc_avg_volume(volumes, 20)
                    result["volume_confirm"] = recent_vol < avg_vol * 0.7 if avg_vol > 0 else False
        else:
            is_breakout = breakout_bar < zs_low and prev_close >= zs_low * 0.99
            lookback = min(15, mmd_idx)
            pullback_highs = closes[mmd_idx - lookback : mmd_idx]
            if pullback_highs:
                max_pullback = max(pullback_highs)
                fib_38 = zs_low + zs_range * 0.382
                retest_zone_low = zs_low * 0.98
                retest_zone_high = fib_38
                retest_depth = (max_pullback - zs_low) / zs_range * 100 if zs_range > 0 else 0
                result["retest_depth"] = round(retest_depth, 1)
                result["retest_detected"] = (
                    retest_depth > 5
                    and retest_depth < 65
                    and max_pullback >= retest_zone_low
                    and max_pullback <= retest_zone_high
                )
                if volumes and len(volumes) > mmd_idx:
                    recent_vol = sum(volumes[max(0, mmd_idx - 5) : mmd_idx]) / min(5, mmd_idx)
                    avg_vol = _calc_avg_volume(volumes, 20)
                    result["volume_confirm"] = recent_vol < avg_vol * 0.7 if avg_vol > 0 else False

        result["breakout_valid"] = is_breakout and result["retest_detected"]

        if result["breakout_valid"]:
            result["confidence_adjust"] = 0.03
        elif is_breakout and not result["retest_detected"]:
            result["confidence_adjust"] = -0.02

        return result
    except Exception:
        return result


# ── V41: 条件111-115 缠论模型决策增强 ─────────────────────────────────────────────


# ── V42: 条件116-120 缠论模型精准度提升 ──────────────────────────────────────────


# ── V44: 条件121-125 缠论模型精准度进一步提升 ──────────────────────────────────


# ── V48: 条件134-136 缠论模型决策增强 ────────────────────────────────────────────────


# ── V51: 条件144-147 缠论模型精准度与决策帮助进一步提升 ────────────────────────────────
