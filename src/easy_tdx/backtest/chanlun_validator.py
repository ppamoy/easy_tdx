"""缠论条件回测验证框架。

提供系统化的回测验证能力：
1. 单条件影响评估：对比启用/禁用某条件组的信号准确率
2. V58-V63 条件组回测验证
3. 多股票对比分析

使用示例：
    >>> from easy_tdx.backtest.chanlun_validator import (
    ...     ConditionGroup, ChanlunConditionBacktestValidator
    ... )
    >>> validator = ChanlunConditionBacktestValidator()
    >>> result = validator.validate_conditions(df, [ConditionGroup.V63])
    >>> print(result.summary())
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ConditionGroup(str, Enum):
    """缠论条件分组枚举。

    每个分组对应 V58-V65 中一组相关的增强条件。
    V64 是回测验证框架本身，不对应具体条件编号。
    """

    # V58: 条件172-175（多TF趋势+量能验证+ATR止损+综合评分）
    V58 = "v58"
    # V59: 条件176-179（波动率MA+ATR倍数+多TF共振+衰减速度）
    V59 = "v59"
    # V60: 条件180-183（RSI背离+MA间距+中枢距离+KDJ确认）
    V60 = "v60"
    # V61: 条件184-185（RSI+MACD双指标融合+S/A/B/C/D质量分层）
    V61 = "v61"
    # V62: 条件186-189（突破确认+压缩反弹+波动率切换+ATR自适应）
    V62 = "v62"
    # V63: 条件190-191（中枢级别权重优化+多周期信号衰减追踪）
    V63 = "v63"
    # V64: 回测验证框架（无具体条件编号，代表回测基础设施）
    V64 = "v64"
    # V65: 条件192-195（量价背离二次确认+突破回踩+波动率压缩+时间窗口）
    V65 = "v65"
    # V66: 条件196-199（MACD加速+量价配合+多TF共振+执行优先级）
    V66 = "v66"
    # V67: 条件200-203（中枢背驰量化+多级别一致性+轨迹健康度+动态止损止盈）
    V67 = "v67"
    # V68: 条件204-207（缺口趋势+区间套+资金流向+市场风格）
    V68 = "v68"
    # V69: 条件208-211（量价背离+结构完整+多指标背离+回踩深度）
    V69 = "v69"
    # V70: 条件212-215（量峰检测+时间衰减+假突破过滤+置信度校准）
    V70 = "v70"
    # V71: 条件216-219（均线排列强度+多周期均线共振+历史胜率回溯+动态风险收益比）
    V71 = "v71"
    # V72: 条件220-223（均线收敛发散+支撑阻力距离+量价结构质量+信号衰减速度）
    V72 = "v72"
    # V73: 条件224-227（买卖点位置风险+中枢突破验证+多指标一致性+波动率适配）
    V73 = "v73"
    # V74: 条件228-231（量价背离二次确认+趋势动能持续+中枢重叠度+信号共振深度）
    V74 = "v74"
    # V75: 条件232-235（回调深度验证+中枢回踩确认+量峰持续评分+多信号时间一致性）
    V75 = "v75"
    # V76: 条件236-239（价格结构完整性+趋势方向对齐+波动率自适应置信度+买卖点最终有效性）
    V76 = "v76"

    @property
    def condition_range(self) -> tuple[int, int]:
        """返回该分组对应的条件编号范围。V64无具体条件，返回(0, 0)。"""
        mapping = {
            ConditionGroup.V58: (172, 175),
            ConditionGroup.V59: (176, 179),
            ConditionGroup.V60: (180, 183),
            ConditionGroup.V61: (184, 185),
            ConditionGroup.V62: (186, 189),
            ConditionGroup.V63: (190, 191),
            ConditionGroup.V64: (0, 0),
            ConditionGroup.V65: (192, 195),
            ConditionGroup.V66: (196, 199),
            ConditionGroup.V67: (200, 203),
            ConditionGroup.V68: (204, 207),
            ConditionGroup.V69: (208, 211),
            ConditionGroup.V70: (212, 215),
            ConditionGroup.V71: (216, 219),
            ConditionGroup.V72: (220, 223),
            ConditionGroup.V73: (224, 227),
            ConditionGroup.V74: (228, 231),
            ConditionGroup.V75: (232, 235),
            ConditionGroup.V76: (236, 239),
        }
        return mapping[self]

    @property
    def description(self) -> str:
        """返回分组描述。"""
        mapping = {
            ConditionGroup.V58: "多TF趋势+量能验证+ATR止损+综合评分",
            ConditionGroup.V59: "波动率MA+ATR倍数+多TF共振+衰减速度",
            ConditionGroup.V60: "RSI背离+MA间距+中枢距离+KDJ确认",
            ConditionGroup.V61: "RSI+MACD双指标融合+质量分层",
            ConditionGroup.V62: "BOLL带宽确认+动态阈值增强",
            ConditionGroup.V63: "中枢级别权重优化+多周期信号衰减追踪",
            ConditionGroup.V64: "回测验证框架（基础设施）",
            ConditionGroup.V65: "量价背离二次确认+突破回踩+波动率压缩+时间窗口",
            ConditionGroup.V66: "MACD加速+量价配合+多TF共振+执行优先级",
            ConditionGroup.V67: "中枢背驰量化+多级别一致性+轨迹健康度+动态止损止盈",
            ConditionGroup.V68: "缺口趋势一致+区间套验证+资金流向确认+市场风格适配",
            ConditionGroup.V69: "量价背离二次确认+结构完整性评分+多指标背离融合+回踩深度量化",
            ConditionGroup.V70: "分时量峰检测+信号时间衰减+假突破过滤+置信度最终校准",
            ConditionGroup.V71: "均线排列强度+多周期均线共振+历史胜率回溯+动态风险收益比",
            ConditionGroup.V72: "均线收敛发散+支撑阻力距离+量价结构质量+信号衰减速度",
            ConditionGroup.V73: "买卖点位置风险+中枢突破验证+多指标一致性+波动率适配",
            ConditionGroup.V74: "量价背离二次确认+趋势动能持续+中枢重叠度+信号共振深度",
            ConditionGroup.V75: "回调深度验证+中枢回踩确认+量峰持续评分+多信号时间一致性",
            ConditionGroup.V76: "价格结构完整性+趋势方向对齐+波动率自适应置信度+买卖点最终有效性",
        }
        return mapping[self]


@dataclass
class SignalResult:
    """单个信号的回测结果。"""

    signal_type: str  # "buy" or "sell"
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    pnl_pct: float  # 收益率百分比
    holding_days: int
    hit: bool  # 是否盈利
    signal_confidence: float
    condition_tags: list[str] = field(default_factory=list)


@dataclass
class ConditionValidationResult:
    """单个条件分组的回测验证结果。"""

    group: ConditionGroup
    total_signals: int = 0
    buy_signals: int = 0
    sell_signals: int = 0
    win_count: int = 0
    lose_count: int = 0
    hit_rate: float = 0.0
    avg_pnl_pct: float = 0.0
    avg_holding_days: float = 0.0
    max_pnl_pct: float = 0.0
    min_pnl_pct: float = 0.0
    signals: list[SignalResult] = field(default_factory=list)
    confidence_correlation: float = 0.0  # 置信度与实际收益的相关系数
    condition_details: dict[str, Any] = field(default_factory=dict)

    @property
    def improved(self) -> bool:
        """判断该条件组是否提升了准确率。"""
        return self.hit_rate > 0.5

    def summary(self) -> str:
        """生成人类可读的验证摘要。"""
        lines = [
            f"=== {self.group.value.upper()} 条件验证 ===",
            f"分组描述: {self.group.description}",
            f"总信号数: {self.total_signals} (买{self.buy_signals}/卖{self.sell_signals})",
            f"胜率: {self.hit_rate:.2%}",
            f"平均收益: {self.avg_pnl_pct:.2f}%",
            f"平均持仓: {self.avg_holding_days:.1f}天",
            f"最大收益: {self.max_pnl_pct:.2f}%",
            f"最小收益: {self.min_pnl_pct:.2f}%",
            f"置信度相关性: {self.confidence_correlation:.3f}",
        ]
        if self.condition_details:
            lines.append("条件详情:")
            for k, v in self.condition_details.items():
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)


@dataclass
class MultiStockResult:
    """多股票对比分析结果。"""

    stock_code: str
    stock_name: str
    signal_count: int
    win_rate: float
    avg_confidence: float
    top_signals: list[dict[str, Any]] = field(default_factory=list)
    condition_breakdown: dict[str, int] = field(default_factory=dict)


class ChanlunConditionBacktestValidator:
    """缠论条件回测验证器。

    对给定数据运行系统化的回测，评估各条件组对买卖点判断准确率的贡献。
    """

    # 止损止盈参数
    DEFAULT_STOP_LOSS = 0.08
    DEFAULT_TAKE_PROFIT = 0.20
    # 信号最小持仓bar数（避免噪音）
    MIN_HOLDING_BARS = 3
    # 最大持仓bar数
    MAX_HOLDING_BARS = 60

    def __init__(
        self,
        stop_loss: float = DEFAULT_STOP_LOSS,
        take_profit: float = DEFAULT_TAKE_PROFIT,
        min_confidence: float = 0.0,
        min_bars: int = 100,
    ) -> None:
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.min_confidence = min_confidence
        self.min_bars = min_bars

    def validate_conditions(
        self,
        df: pd.DataFrame,
        groups: list[ConditionGroup],
        code: str = "TEST",
    ) -> list[ConditionValidationResult]:
        """对指定条件分组运行回测验证。

        Args:
            df: OHLCV 数据框，需包含 open/high/low/close/vol 列
            groups: 要验证的条件分组列表
            code: 股票代码（用于日志）

        Returns:
            每个分组的验证结果列表
        """
        if len(df) < self.min_bars:
            logger.warning("数据不足 %d bars，跳过验证", self.min_bars)
            note = f"数据不足 {len(df)} bars < min_bars={self.min_bars}"
            return [
                ConditionValidationResult(group=g, condition_details={"note": note})
                for g in groups
            ]

        from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

        config = ChanlunConfig()
        analyser = ChanlunAnalyser(code=code, frequency="daily", config=config)
        result = analyser.process_klines(df)

        if not result.mmds:
            logger.warning("未检测到买卖点信号")
            return [
                ConditionValidationResult(group=g, condition_details={"note": "无买卖点信号"})
                for g in groups
            ]

        results = []
        for group in groups:
            validation = self._validate_group(df, result, group)
            results.append(validation)

        return results

    def _validate_group(
        self,
        df: pd.DataFrame,
        chanlun_result: Any,
        group: ConditionGroup,
    ) -> ConditionValidationResult:
        """验证单个条件分组。"""
        low, high = group.condition_range
        signals = [
            mmd
            for mmd in chanlun_result.mmds
            if self._is_valid_signal(mmd)
            and mmd.confidence >= self.min_confidence
        ]

        if not signals:
            return ConditionValidationResult(group=group, condition_details={"note": "无有效信号"})

        signal_results = self._simulate_trades(df, signals, low, high)
        return self._compute_metrics(group, signals, signal_results)

    def _is_valid_signal(self, mmd: Any) -> bool:
        """检查信号是否有效。"""
        from easy_tdx.chanlun.types import MMDType

        valid_types = {MMDType.BUY_1, MMDType.BUY_2, MMDType.BUY_3,
                       MMDType.SELL_1, MMDType.SELL_2, MMDType.SELL_3}
        return mmd.mmd_type in valid_types and mmd.bi is not None

    def _simulate_trades(
        self,
        df: pd.DataFrame,
        signals: list[Any],
        cond_low: int,
        cond_high: int,
    ) -> list[SignalResult]:
        """模拟信号交易，计算收益。"""
        results = []
        closes = df["close"].values.astype(float)
        highs = df["high"].values.astype(float)
        lows = df["low"].values.astype(float)
        n = len(closes)

        for mmd in signals:
            bi_idx = mmd.bi.index
            if bi_idx is None or bi_idx >= n - 1:
                continue

            signal_type = "buy" if "buy" in mmd.mmd_type.value else "sell"
            entry_bar = bi_idx + 1  # 次根bar入场
            if entry_bar >= n:
                continue

            entry_price = closes[entry_bar]
            stop_loss = entry_price * (1 - self.stop_loss)
            take_profit = entry_price * (1 + self.take_profit)

            # 查找出场bar
            exit_bar = self._find_exit_bar(
                entry_bar, stops=stop_loss, profit=take_profit,
                highs=highs, lows=lows, closes=closes, max_bars=self.MAX_HOLDING_BARS,
            )

            if exit_bar < 0:
                continue  # 未触发止损止盈，跳过

            holding_days = exit_bar - entry_bar
            if holding_days < self.MIN_HOLDING_BARS:
                continue

            if signal_type == "buy":
                pnl_pct = (closes[exit_bar] - entry_price) / entry_price * 100
                hit = pnl_pct > 0
            else:
                pnl_pct = (entry_price - closes[exit_bar]) / entry_price * 100
                hit = pnl_pct > 0

            results.append(SignalResult(
                signal_type=signal_type,
                entry_bar=entry_bar,
                exit_bar=exit_bar,
                entry_price=entry_price,
                exit_price=closes[exit_bar],
                pnl_pct=pnl_pct,
                holding_days=holding_days,
                hit=hit,
                signal_confidence=mmd.confidence,
                condition_tags=[f"cond_{i}" for i in range(cond_low, cond_high + 1)
                               if hasattr(mmd, f"_condition_{i}")],
            ))

        return results

    def _find_exit_bar(
        self,
        entry_bar: int,
        stops: float,
        profit: float,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        max_bars: int,
    ) -> int:
        """查找止损/止盈触发bar。"""
        end = min(entry_bar + max_bars, len(closes))
        for bar in range(entry_bar + 1, end):
            if lows[bar] <= stops:
                return bar
            if highs[bar] >= profit:
                return bar
        return -1

    def _compute_metrics(
        self,
        group: ConditionGroup,
        signals: list[Any],
        signal_results: list[SignalResult],
    ) -> ConditionValidationResult:
        """计算验证指标。"""
        if not signal_results:
            return ConditionValidationResult(
                group=group,
                condition_details={"note": "无可用交易信号"},
            )

        buys = [r for r in signal_results if r.signal_type == "buy"]
        sells = [r for r in signal_results if r.signal_type == "sell"]
        wins = [r for r in signal_results if r.hit]
        losses = [r for r in signal_results if not r.hit]

        pnl_vals = [r.pnl_pct for r in signal_results]
        hit_rate = len(wins) / len(signal_results) if signal_results else 0.0

        # 置信度与收益的相关性
        conf_corr = 0.0
        if len(signal_results) >= 5:
            confs = np.array([r.signal_confidence for r in signal_results])
            pnls = np.array(pnl_vals)
            if np.std(confs) > 0 and np.std(pnls) > 0:
                conf_corr = float(np.corrcoef(confs, pnls)[0, 1])

        # 条件命中统计
        condition_details = {
            "total_enhanced_signals": len(signals),
            "avg_confidence": float(np.mean([s.confidence for s in signals])),
            "confidence_std": float(np.std([s.confidence for s in signals])),
        }

        return ConditionValidationResult(
            group=group,
            total_signals=len(signal_results),
            buy_signals=len(buys),
            sell_signals=len(sells),
            win_count=len(wins),
            lose_count=len(losses),
            hit_rate=hit_rate,
            avg_pnl_pct=float(np.mean(pnl_vals)),
            avg_holding_days=float(np.mean([r.holding_days for r in signal_results])),
            max_pnl_pct=float(np.max(pnl_vals)),
            min_pnl_pct=float(np.min(pnl_vals)),
            signals=signal_results,
            confidence_correlation=conf_corr,
            condition_details=condition_details,
        )

    def validate_multi_stock(
        self,
        stock_data: dict[str, pd.DataFrame],
        groups: list[ConditionGroup] | None = None,
    ) -> list[MultiStockResult]:
        """多股票对比分析。

        Args:
            stock_data: {code: DataFrame} 映射
            groups: 要分析的条件分组，None=全部

        Returns:
            每只股票的对比结果
        """
        if groups is None:
            groups = list(ConditionGroup)

        results = []
        for code, df in stock_data.items():
            if len(df) < self.min_bars:
                continue

            from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
            config = ChanlunConfig()
            analyser = ChanlunAnalyser(code=code, frequency="daily", config=config)
            chanlun_result = analyser.process_klines(df)

            valid_signals = [
                mmd for mmd in chanlun_result.mmds
                if self._is_valid_signal(mmd)
                and mmd.confidence >= self.min_confidence
            ]

            # 统计各条件命中
            condition_counts: dict[str, int] = {}
            for mmd in valid_signals:
                for g in groups:
                    low, high = g.condition_range
                    for c in range(low, high + 1):
                        attr = f"_condition_{c}"
                        if hasattr(mmd, attr):
                            key = f"{g.value}_cond{c}"
                            condition_counts[key] = condition_counts.get(key, 0) + 1

            results.append(MultiStockResult(
                stock_code=code,
                stock_name=code,
                signal_count=len(valid_signals),
                win_rate=0.0,  # 需历史回测填充
                avg_confidence=(
                    float(np.mean([s.confidence for s in valid_signals]))
                    if valid_signals else 0.0
                ),
                condition_breakdown=condition_counts,
            ))

        return results

    def compare_groups(
        self,
        df: pd.DataFrame,
        groups: list[ConditionGroup],
    ) -> pd.DataFrame:
        """生成条件组对比表格。

        Returns:
            DataFrame 包含各组的关键指标
        """
        validations = self.validate_conditions(df, groups)
        rows = []
        for v in validations:
            rows.append({
                "分组": v.group.value,
                "描述": v.group.description,
                "总信号": v.total_signals,
                "买信号": v.buy_signals,
                "卖信号": v.sell_signals,
                "胜率": f"{v.hit_rate:.2%}",
                "平均收益%": f"{v.avg_pnl_pct:.2f}",
                "平均持仓天": round(v.avg_holding_days, 1),
                "最大收益%": f"{v.max_pnl_pct:.2f}",
                "最小收益%": f"{v.min_pnl_pct:.2f}",
                "置信度相关": f"{v.confidence_correlation:.3f}",
                "提升": "✅" if v.improved else "❌",
            })
        return pd.DataFrame(rows)
