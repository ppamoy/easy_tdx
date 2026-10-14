"""吴伟志+缠论融合引擎 — 核心决策模块。

三层架构（PRD §1.3）：
  第一层（方向过滤）：树粮草分类 + 春夏秋冬季节 → 决定标的池 + 仓位上限
  第二层（时机执行）：缠论买卖点（30min/60min）→ 决定具体买卖时机
  第三层（制度适配）：T+1约束 + 风控 → 决定仓位规划

融合决策流程（PRD §6.1）：
  缠论信号 → 方向过滤（一票否决）→ 多级别确认 → 技术评分 → 最终信号
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# ── 分类映射（现有 screener 用"菜"，PRD 用"草"，语义一致）──
GRASS = "vegetable"  # 菜 ↔ 草
GRAIN = "grain"      # 粮
TREE = "tree"        # 树

CATEGORY_CN = {
    TREE: "树",
    GRAIN: "粮",
    GRASS: "草",
}

# ── 季节 → 仓位上限（PRD §4.2.2）──
SEASON_POSITION = {
    "spring": 0.70,
    "summer": 0.50,
    "autumn": 0.30,
    "winter": 0.10,
    "unknown": 0.30,
}

SEASON_DAILY_OPEN_LIMIT = {
    "spring": 5,
    "summer": 2,
    "autumn": 1,
    "winter": 0,
    "unknown": 1,
}


@dataclass
class ChanlunSignal:
    """一条缠论买卖点信号。"""
    signal_type: str        # buy_1/buy_2/buy_3/sell_1/sell_2/sell_3
    level: str              # 30min/60min/daily
    price: float
    bar_index: int = 0
    confidence: float = 0.0
    beichi_force: float = 0.0     # 背驰力度（0-1）
    zhongshu_range: list[float] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def is_buy(self) -> bool:
        return "buy" in self.signal_type

    @property
    def is_sell(self) -> bool:
        return "sell" in self.signal_type


@dataclass
class FilterResult:
    """方向过滤结果。"""
    passed: bool
    reason: str
    category: str = ""        # tree/grain/grass
    season: str = ""          # spring/summer/autumn/winter
    position_limit: float = 0.0
    daily_open_limit: int = 0


@dataclass
class ScoreResult:
    """技术面评分结果。"""
    total: int = 0
    items: dict[str, int] = field(default_factory=dict)
    recommendation: str = "observe"   # execute/observe/reject
    suggested_position: float = 0.0


@dataclass
class HybridResult:
    """融合分析最终结果。"""
    code: str
    market: str
    # 方向过滤层
    category: str = ""           # tree/grain/grass
    category_label: str = ""
    season: str = ""
    season_label: str = ""
    position_limit: float = 0.0
    # 时机执行层
    signals: list[ChanlunSignal] = field(default_factory=list)
    latest_signal: ChanlunSignal | None = None
    # 融合结果
    filter_result: FilterResult | None = None
    score_result: ScoreResult | None = None
    final_signal: str = "reject"     # execute/observe/reject
    final_reason: str = ""
    # 树类提醒（树类不再禁止交易，而是提醒大周期买点买入持有）
    reminder: str = ""
    is_long_term: bool = False       # 树类=长期持有策略
    # 多级别确认
    daily_trend: str = "unknown"     # up/down/sideways
    lower_level_signal: str = "none"
    # 原始数据
    indicators: dict[str, Any] = field(default_factory=dict)
    season_detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "market": self.market,
            "category": self.category,
            "category_label": self.category_label,
            "season": self.season,
            "season_label": self.season_label,
            "position_limit": self.position_limit,
            "signals": [
                {
                    "signal_type": s.signal_type,
                    "level": s.level,
                    "price": s.price,
                    "confidence": round(s.confidence, 3),
                    "beichi_force": round(s.beichi_force, 3),
                    "is_buy": s.is_buy,
                    "is_sell": s.is_sell,
                    "detail": s.detail,
                }
                for s in self.signals
            ],
            "latest_signal": {
                "signal_type": self.latest_signal.signal_type,
                "level": self.latest_signal.level,
                "price": self.latest_signal.price,
                "is_buy": self.latest_signal.is_buy,
                "confidence": round(self.latest_signal.confidence, 3),
                "beichi_force": round(self.latest_signal.beichi_force, 3),
            } if self.latest_signal else None,
            "filter": {
                "passed": self.filter_result.passed if self.filter_result else False,
                "reason": self.filter_result.reason if self.filter_result else "",
            } if self.filter_result else None,
            "score": {
                "total": self.score_result.total if self.score_result else 0,
                "items": self.score_result.items if self.score_result else {},
                "recommendation": self.score_result.recommendation if self.score_result else "observe",
                "suggested_position": round(self.score_result.suggested_position, 3) if self.score_result else 0,
            } if self.score_result else None,
            "final_signal": self.final_signal,
            "final_reason": self.final_reason,
            "reminder": self.reminder,
            "is_long_term": self.is_long_term,
            "daily_trend": self.daily_trend,
            "lower_level_signal": self.lower_level_signal,
            "indicators": self.indicators,
            "season_detail": self.season_detail,
        }


class HybridEngine:
    """吴伟志+缠论融合引擎。

    用法：
        engine = HybridEngine()
        result = engine.analyze(
            code="600000", market="SH", period="MIN_30",
            klines_df=df_30min, daily_df=df_daily,
            screen_result=screen_res, season_result=season_res,
        )
    """

    def analyze(
        self,
        *,
        code: str,
        market: str,
        klines_df: pd.DataFrame,
        signals: list[ChanlunSignal],
        screen_result: Any | None = None,
        season_result: Any | None = None,
        daily_df: pd.DataFrame | None = None,
        daily_signals: list[ChanlunSignal] | None = None,
        indicators: dict[str, Any] | None = None,
    ) -> HybridResult:
        """执行融合分析。

        Args:
            code: 股票代码
            market: 市场 SH/SZ
            klines_df: 操作级别K线（30min/60min）
            signals: 操作级别缠论信号列表
            screen_result: 树粮草分类结果（ScreenResult 或 dict）
            season_result: 四季判断结果（SeasonResult 或 dict）
            daily_df: 日线K线（用于趋势确认）
            daily_signals: 日线级别信号
            indicators: 财务指标字典
        """
        result = HybridResult(code=code, market=market)
        result.indicators = indicators or {}

        # ── 第一层：方向过滤 ──
        # 辅助：安全取属性值（如果是方法就调用，如果是 dict 就用 get）
        def _safe_get(obj: Any, key: str, default: Any = "") -> Any:
            if obj is None:
                return default
            if isinstance(obj, dict):
                return obj.get(key, default)
            val = getattr(obj, key, default)
            if callable(val):
                try:
                    val = val()
                except Exception:
                    val = default
            return val if val is not None else default

        category = ""
        season = "unknown"
        season_label = ""
        season_detail = {}

        if screen_result is not None:
            category = _safe_get(screen_result, "category", "")
            ind = _safe_get(screen_result, "indicators", {})
            if isinstance(ind, dict) and ind:
                result.indicators = ind
            # 优先用 as_dict() 获取完整信息
            if hasattr(screen_result, "as_dict"):
                try:
                    sd = screen_result.as_dict()
                    if not category:
                        category = sd.get("category", "")
                    if not result.indicators:
                        result.indicators = sd.get("indicators", {})
                except Exception:
                    pass

        if season_result is not None:
            season = _safe_get(season_result, "season", "unknown")
            season_label = _safe_get(season_result, "label", "")
            season_detail = _safe_get(season_result, "signals", {})
            # 优先用 as_dict()
            if hasattr(season_result, "as_dict"):
                try:
                    sd = season_result.as_dict()
                    if not season or season == "unknown":
                        season = sd.get("season", season)
                    if not season_label:
                        season_label = sd.get("label", "")
                    if not season_detail:
                        season_detail = sd.get("signals", {})
                except Exception:
                    pass

        result.category = category
        result.category_label = CATEGORY_CN.get(category, category)
        result.season = season
        result.season_label = season_label
        result.season_detail = season_detail
        result.position_limit = SEASON_POSITION.get(season, 0.30)

        # ── 第二层：缠论信号 ──
        result.signals = signals
        result.latest_signal = signals[-1] if signals else None

        # 多级别确认：日线趋势
        if daily_df is not None and len(daily_df) > 20:
            ma20 = daily_df["close"].rolling(20).mean().iloc[-1]
            close = daily_df["close"].iloc[-1]
            if close > ma20 * 1.02:
                result.daily_trend = "up"
            elif close < ma20 * 0.98:
                result.daily_trend = "down"
            else:
                result.daily_trend = "sideways"

        if daily_signals:
            latest_daily = daily_signals[-1]
            result.lower_level_signal = latest_daily.signal_type if latest_daily else "none"

        # ── 方向过滤（一票否决制）──
        result.filter_result = self._direction_filter(
            category=category,
            season=season,
            latest_signal=result.latest_signal,
        )

        # 树类提醒（不再否决，而是提醒大周期买入持有）
        if category == TREE and result.latest_signal and result.latest_signal.is_buy:
            result.is_long_term = True
            result.reminder = (
                "🌳 树类股票，适合长期持有。"
                "建议在日线/周线大周期买点出现时买入并持有，"
                "不要因为短期波动频繁交易。"
            )

        # ── 技术面评分 ──
        if result.latest_signal and result.filter_result.passed:
            result.score_result = self._technical_score(
                signal=result.latest_signal,
                klines_df=klines_df,
                daily_trend=result.daily_trend,
                is_tree=category == TREE,
            )
        else:
            result.score_result = ScoreResult(recommendation="reject")

        # ── 最终决策 ──
        result.final_signal, result.final_reason = self._decide(
            filter_result=result.filter_result,
            score_result=result.score_result,
            latest_signal=result.latest_signal,
            daily_trend=result.daily_trend,
            is_tree=category == TREE,
            reminder=result.reminder,
        )

        return result

    def _direction_filter(
        self,
        *,
        category: str,
        season: str,
        latest_signal: ChanlunSignal | None,
    ) -> FilterResult:
        """方向过滤层 — 一票否决制（PRD §4.2.3）。"""
        pos_limit = SEASON_POSITION.get(season, 0.30)
        daily_limit = SEASON_DAILY_OPEN_LIMIT.get(season, 1)

        # 规则1：树类——不否决，改为提醒大周期买入持有
        if category == TREE:
            if latest_signal and latest_signal.is_buy:
                return FilterResult(
                    passed=True, reason="树类：大周期买点出现，建议买入并长期持有",
                    category=category, season=season,
                    position_limit=pos_limit, daily_open_limit=1,
                )
            elif latest_signal and latest_signal.is_sell:
                return FilterResult(
                    passed=True, reason="树类：卖出信号出现，但建议仅在大周期卖点减仓",
                    category=category, season=season,
                    position_limit=pos_limit, daily_open_limit=1,
                )
            # 无信号也通过（等待大周期买点）
            return FilterResult(
                passed=True, reason="树类：等待大周期买点出现时买入并持有",
                category=category, season=season,
                position_limit=pos_limit, daily_open_limit=1,
            )

        # 规则2：冬季禁止开新仓
        if season == "winter" and latest_signal and latest_signal.is_buy:
            return FilterResult(
                passed=False, reason="冬季禁止新开仓（市场温度过低）",
                category=category, season=season,
                position_limit=pos_limit, daily_open_limit=0,
            )

        # 规则3：秋季不参与草类买入
        if season == "autumn" and category == GRASS and latest_signal and latest_signal.is_buy:
            return FilterResult(
                passed=False, reason="秋季不参与草类交易（趋势反转风险高）",
                category=category, season=season,
                position_limit=pos_limit, daily_open_limit=daily_limit,
            )

        # 规则4：无信号
        if latest_signal is None:
            return FilterResult(
                passed=False, reason="无缠论买卖点信号",
                category=category, season=season,
                position_limit=pos_limit, daily_open_limit=daily_limit,
            )

        # 规则5：卖出信号始终通过（用于管理已有仓位）
        if latest_signal.is_sell:
            return FilterResult(
                passed=True, reason="卖出信号通过方向过滤",
                category=category, season=season,
                position_limit=pos_limit, daily_open_limit=daily_limit,
            )

        # 通过
        return FilterResult(
            passed=True,
            reason=f"{CATEGORY_CN.get(category, category)}类股票，{season}季节，方向过滤通过",
            category=category, season=season,
            position_limit=pos_limit, daily_open_limit=daily_limit,
        )

    def _technical_score(
        self,
        *,
        signal: ChanlunSignal,
        klines_df: pd.DataFrame,
        daily_trend: str,
        is_tree: bool = False,
    ) -> ScoreResult:
        """技术面辅助评分（PRD §6.2）。

        树类：门槛降低（≥30 execute），因为长期持有不需要太严格的技术确认。
        非树类：≥60 execute（原逻辑）。
        """
        score = ScoreResult()
        items = {}

        # 成交量评分（买入信号时量 > 5日均量）
        if len(klines_df) >= 5 and signal.is_buy:
            vol_now = klines_df["vol"].iloc[-1] if "vol" in klines_df.columns else 0
            vol_ma5 = klines_df["vol"].rolling(5).mean().iloc[-1] if "vol" in klines_df.columns else 0
            if vol_ma5 > 0 and vol_now > vol_ma5:
                items["成交量放大"] = 15
                score.total += 15

        # RSI评分
        if len(klines_df) >= 14:
            try:
                delta = klines_df["close"].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss.replace(0, 1e-10)
                rsi = (100 - 100 / (1 + rs)).iloc[-1]
                if signal.is_buy and 30 <= rsi <= 60:
                    items["RSI适中"] = 10
                    score.total += 10
                elif signal.is_sell and rsi > 70:
                    items["RSI超买"] = 10
                    score.total += 10
            except Exception:
                pass

        # 换手率评分
        if "vol" in klines_df.columns and "turnover" in klines_df.columns:
            turnover = klines_df["turnover"].iloc[-1] if len(klines_df) > 0 else 0
            if 1 <= turnover <= 15:
                items["换手率正常"] = 10
                score.total += 10

        # 日线趋势评分
        if daily_trend == "up" and signal.is_buy:
            items["日线趋势向上"] = 10
            score.total += 10

        # 背驰力度评分
        if signal.beichi_force > 0.3:
            items["背驰力度强"] = 20
            score.total += 20
        elif signal.beichi_force > 0.15:
            items["背驰力度中等"] = 10
            score.total += 10

        # 3买中枢位置评分
        if signal.signal_type == "buy_3" and signal.zhongshu_range:
            items["3买突破中枢"] = 20
            score.total += 20

        score.items = items

        # 推荐等级（树类门槛降低：≥30 execute，因为长期持有不需要严格技术确认）
        exec_threshold = 30 if is_tree else 60
        observe_threshold = 20 if is_tree else 40
        base_pos = 0.15 if is_tree else 0.10  # 树类基准仓位更高（长期持有）
        if score.total >= exec_threshold:
            score.recommendation = "execute"
            score.suggested_position = base_pos * (score.total / 100)
        elif score.total >= observe_threshold:
            score.recommendation = "observe"
            score.suggested_position = 0
        else:
            score.recommendation = "reject"
            score.suggested_position = 0

        return score

    def _decide(
        self,
        *,
        filter_result: FilterResult,
        score_result: ScoreResult,
        latest_signal: ChanlunSignal | None,
        daily_trend: str,
        is_tree: bool = False,
        reminder: str = "",
    ) -> tuple[str, str]:
        """融合决策（PRD §6.1）。"""
        if not filter_result.passed:
            return "reject", filter_result.reason

        if latest_signal is None:
            if is_tree:
                return "observe", "树类：等待大周期买点出现"
            return "reject", "无信号"

        # 卖出信号
        if latest_signal.is_sell:
            if is_tree:
                return "observe", f"树类卖出信号：{latest_signal.signal_type}，建议仅在大周期卖点减仓"
            return "execute", f"卖出信号：{latest_signal.signal_type}，建议执行卖出"

        # 买入信号
        if score_result.recommendation == "execute":
            prefix = f"🌳 {reminder} " if reminder and is_tree else ""
            if daily_trend == "down" and not is_tree:
                return "observe", f"评分{score_result.total}通过，但日线趋势向下，观察"
            return "execute", f"{prefix}评分{score_result.total}，建议买入并持有，仓位{score_result.suggested_position:.0%}"
        elif score_result.recommendation == "observe":
            return "observe", f"评分{score_result.total}，观察不执行"
        else:
            return "reject", f"评分{score_result.total}过低，忽略信号"
