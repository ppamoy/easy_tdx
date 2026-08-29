"""长赢缠论综合策略。

结合吴伟志《长赢》四季周期理论和缠论三类买卖点，
构建稳健的长期投资体系。

核心逻辑：
1. 四季周期判断市场阶段
2. 缠论买卖点识别具体交易信号
3. 树粮菜分类确定持仓结构
4. 仓位管理控制风险
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import pandas as pd

from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
from easy_tdx.chanlun.types import MMDType
from easy_tdx.backtest.strategies.registry import (
    Param,
    ParametrizedStrategy,
    register_strategy,
)


class Season(str, Enum):
    """四季周期状态。"""
    SPRING = "spring"      # 春季-播种期
    SUMMER = "summer"      # 夏季-成长期
    AUTUMN = "autumn"      # 秋季-收获期
    WINTER = "winter"      # 冬季-蛰伏期
    UNKNOWN = "unknown"    # 未知状态


class StockType(str, Enum):
    """股票分类。"""
    TREE = "tree"      # 树型企业-核心底仓
    GRAIN = "grain"    # 粮型企业-稳健收益
    VEGETABLE = "vegetable"  # 菜型企业-波段收益


@dataclass
class SeasonInfo:
    """四季周期信息。"""
    season: Season
    label: str
    color: str
    description: str
    strategy: str
    position_range: tuple[int, int]  # (最低仓位, 最高仓位)
    action: str


# 四季定义（基于吴伟志长赢理论）
SEASON_DEFINITIONS: dict[Season, SeasonInfo] = {
    Season.SPRING: SeasonInfo(
        season=Season.SPRING,
        label="春季·播种期",
        color="#4ade80",
        description="熊末牛初，估值见底，市场情绪极致绝望，行情在绝望中诞生",
        strategy="春播：分批逆向布局，精选优质成长标的，逐步建仓",
        position_range=(30, 50),
        action="买入优质成长股，不恐慌割肉",
    ),
    Season.SUMMER: SeasonInfo(
        season=Season.SUMMER,
        label="夏季·成长期",
        color="#22c55e",
        description="牛市主升，赚钱效应扩散，行情在犹豫中发展，主线持续走强",
        strategy="夏长：坚定满仓持有，拥抱核心主线，杜绝频繁换股",
        position_range=(80, 100),
        action="满仓持有核心标的，让利润奔跑",
    ),
    Season.AUTUMN: SeasonInfo(
        season=Season.AUTUMN,
        label="秋季·收获期",
        color="#f59e0b",
        description="牛市末期，情绪狂热，估值透支，行情在乐观中见顶",
        strategy="秋收：分批减仓落袋，收缩战线，剔除劣质标的",
        position_range=(20, 40),
        action="分批止盈，锁定收益",
    ),
    Season.WINTER: SeasonInfo(
        season=Season.WINTER,
        label="冬季·蛰伏期",
        color="#60a5fa",
        description="熊市主跌，恐慌蔓延，流动性收缩，普跌行情为主",
        strategy="冬藏：轻仓空仓为主，现金为王，耐心等待市场出清",
        position_range=(0, 20),
        action="轻仓观望，保存本金",
    ),
    Season.UNKNOWN: SeasonInfo(
        season=Season.UNKNOWN,
        label="分析中...",
        color="#94a3b8",
        description="数据不足，无法判断当前周期阶段",
        strategy="观望",
        position_range=(0, 0),
        action="等待更多数据",
    ),
}


class ChangyingChanlunStrategy(ParametrizedStrategy):
    """长赢缠论综合策略。
    
    结合四季周期理论和缠论买卖点，实现稳健的长期投资。
    """
    
    params = [
        # 缠论参数
        Param("bi_type", str, default="new", 
              choices=("new", "old", "simple"), 
              label="笔类型"),
        Param("zs_min_lines", int, default=3, min_value=3, max_value=5, 
              label="中枢最少笔数"),
        Param("macd_fast", int, default=12, min_value=6, max_value=20, 
              label="MACD 快线"),
        Param("macd_slow", int, default=26, min_value=12, max_value=50, 
              label="MACD 慢线"),
        Param("macd_signal", int, default=9, min_value=5, max_value=15, 
              label="MACD 信号线"),
        
        # 长赢周期参数
        Param("use_season_filter", bool, default=True, 
              label="使用周期过滤"),
        Param("season_lookback", int, default=100, min_value=50, max_value=200, 
              label="周期观察期"),
        
        # 仓位管理参数
        Param("tree_weight", float, default=0.4, min_value=0.0, max_value=1.0, 
              label="树型仓位"),
        Param("grain_weight", float, default=0.3, min_value=0.0, max_value=1.0, 
              label="粮型仓位"),
        Param("vegetable_weight", float, default=0.3, min_value=0.0, max_value=1.0, 
              label="菜型仓位"),
        
        # 风险控制参数
        Param("stop_loss_pct", float, default=0.08, min_value=0.0, max_value=0.3, 
              label="止损比例"),
        Param("take_profit_pct", float, default=0.25, min_value=0.0, max_value=0.5, 
              label="止盈比例"),
        Param("max_position", float, default=0.9, min_value=0.1, max_value=1.0, 
              label="最大仓位"),
    ]
    
    def init(self) -> None:
        """初始化策略。"""
        # 缠论分析器
        self._analyser = None
        self._chanlun_result = None
        
        # 历史K线缓存
        self._history: list[dict] = []
        self._max_history = self.p["season_lookback"] + 50
        
        # 当前周期状态
        self._current_season: Season = Season.UNKNOWN
        # (切换时的K线日期或墙钟回退, 季节, 当时bar_index)
        self._season_history: list[tuple[Any, Season, int]] = []
        
        # 买卖点缓存
        self._last_buy_1_idx = -1
        self._last_sell_1_idx = -1
        
        # 持仓状态
        self._position = 0
        self._entry_price = 0.0
        self._entry_season: Season | None = None
        
        # 统计
        self._trade_count = 0
        self._win_count = 0
        self._loss_count = 0
    
    def next(self) -> None:
        """每根K线调用。"""
        # 追加当前K线到历史
        bar = self._get_current_bar()
        self._history.append(bar)
        
        # 限制历史长度
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        
        # 至少需要足够数据进行分析
        if len(self._history) < 50:
            return
        
        # 重新计算缠论分析
        df = self._build_dataframe()
        self._analyze_chanlun(df)
        
        # 判断当前周期
        if self.p["use_season_filter"]:
            self._update_season(df)
        
        # 检查止损止盈
        self._check_risk_control()
        
        # 生成交易信号
        self._generate_signals()
    
    def _get_current_bar(self) -> dict:
        """获取当前K线数据。"""
        return {
            "datetime": self.data.datetime.raw[self._bar_index] if hasattr(self.data, 'datetime') and self._bar_index < len(getattr(self.data, 'datetime', [])) else datetime.now(),
            "open": float(self.data.open[0]),
            "close": float(self.data.close[0]),
            "high": float(self.data.high[0]),
            "low": float(self.data.low[0]),
            "vol": float(self.data.vol[0]) if self.data.vol[0] else 0.0,
        }
    
    def _build_dataframe(self) -> pd.DataFrame:
        """构建DataFrame供缠论分析。"""
        return pd.DataFrame(self._history)
    
    def _analyze_chanlun(self, df: pd.DataFrame) -> None:
        """执行缠论分析。"""
        config = ChanlunConfig(
            bi_type=self.p["bi_type"],
            zs_min_lines=self.p["zs_min_lines"],
            macd_fast=self.p["macd_fast"],
            macd_slow=self.p["macd_slow"],
            macd_signal=self.p["macd_signal"],
        )
        
        self._analyser = ChanlunAnalyser(code="TEST", frequency="DAILY", config=config)
        self._chanlun_result = self._analyser.process_klines(df)
    
    @staticmethod
    def _latest_bar_datetime(df: pd.DataFrame) -> Any:
        """取 df 最后一根K线的日期（兼容 int YYYYMMDD / str / Timestamp / DatetimeIndex）。

        返回 pd.Timestamp；无法解析时返回 None（调用方退化为按K线计数）。
        """
        if df is None or len(df) == 0:
            return None
        if "datetime" not in df.columns:
            if isinstance(getattr(df, "index", None), pd.DatetimeIndex):
                return df.index[-1]
            return None
        v = df["datetime"].iloc[-1]
        try:
            # 先处理 datetime/Timestamp（pd.Timestamp 的 int() 是纳秒，不能按 YYYYMMDD 解析）
            if isinstance(v, (pd.Timestamp, datetime)):
                return pd.to_datetime(v)
            if isinstance(v, str):
                s2 = v.strip().replace("-", "").replace(" ", "")[:8]
                if s2.isdigit() and len(s2) >= 8:
                    return pd.to_datetime(s2[:8], format="%Y%m%d", errors="coerce")
                return pd.to_datetime(v, errors="coerce")
            # int / numpy int64 / float 统一转字符串再按 YYYYMMDD 解析
            s = str(int(v)).strip()
            if s.isdigit() and len(s) >= 8:
                return pd.to_datetime(s[:8], format="%Y%m%d", errors="coerce")
            return pd.to_datetime(v)
        except Exception:
            return None

    def _update_season(self, df: pd.DataFrame) -> None:
        """更新当前周期状态（多维度信号融合）。
        
        综合以下指标判断四季周期：
        1. 价格趋势（较前期涨跌幅）
        2. 均线系统（MA20 vs MA60）
        3. 波动率变化（近期波动 vs 长期波动）
        4. 成交量变化（放量/缩量）
        5. 缠论结构（笔方向 + 中枢位置）
        """
        if self._chanlun_result is None or df is None or len(df) < 60:
            return
        
        closes = df["close"].values.astype(float)
        volumes = df["vol"].values.astype(float) if "vol" in df.columns else None
        highs = df["high"].values.astype(float)
        
        # ── 信号1：价格趋势得分 (-2 到 +2) ──────────────────────────
        n = len(closes)
        if n >= 20:
            trend_20d = (closes[-1] - closes[-20]) / closes[-20] if closes[-20] > 0 else 0
        else:
            trend_20d = 0
        
        if n >= 60:
            trend_60d = (closes[-1] - closes[-60]) / closes[-60] if closes[-60] > 0 else 0
        else:
            trend_60d = trend_20d
        
        price_score = 0
        if trend_60d > 0.25:
            price_score = 2
        elif trend_60d > 0.08:
            price_score = 1
        elif trend_60d < -0.25:
            price_score = -2
        elif trend_60d < -0.08:
            price_score = -1
        
        # ── 信号2：均线系统得分 (-1 到 +1) ──────────────────────────
        ma_score = 0
        if n >= 60:
            ma20 = sum(closes[-20:]) / 20
            ma60 = sum(closes[-60:]) / 60
            if ma60 > 0:
                ma_ratio = ma20 / ma60
                if ma_ratio > 1.05:
                    ma_score = 1
                elif ma_ratio < 0.95:
                    ma_score = -1
        
        # ── 信号3：波动率变化得分 (-1 到 +1) ────────────────────────
        vol_score = 0
        if volumes is not None and n >= 40:
            vol_recent = sum(volumes[-20:]) / 20
            vol_long = sum(volumes[-40:]) / 40
            if vol_long > 0:
                vol_ratio = vol_recent / vol_long
                if vol_ratio > 1.5:
                    vol_score = 1  # 放量
                elif vol_ratio < 0.6:
                    vol_score = -1  # 缩量
        elif n >= 40:
            # 用价格波动率代替
            vol_recent_std = pd.Series(closes[-20:]).std()
            vol_long_std = pd.Series(closes[-40:]).std()
            if vol_long_std > 0:
                vol_ratio = vol_recent_std / vol_long_std
                if vol_ratio > 1.5:
                    vol_score = 1
                elif vol_ratio < 0.6:
                    vol_score = -1
        
        # ── 信号4：缠论结构得分 (-1 到 +1) ──────────────────────────
        chanlun_score = 0
        bis = self._chanlun_result.bis
        zss = self._chanlun_result.zss
        if len(bis) >= 3 and len(zss) >= 1:
            last_bi = bis[-1]
            last_zs = zss[-1]
            current_price = closes[-1]
            
            # 价格在中枢上方 → 多头
            if last_zs.zg > 0 and current_price > last_zs.zg:
                chanlun_score = 1 if last_bi.direction.value == "up" else 0
            elif last_zs.zd > 0 and current_price < last_zs.zd:
                chanlun_score = -1 if last_bi.direction.value == "down" else 0
            # 价格在中枢内 → 中性
        
        # ── 综合评分 ─────────────────────────────────────────────────
        total_score = price_score + ma_score + vol_score + chanlun_score
        
        # 评分映射到季节
        if total_score >= 3:
            new_season = Season.SUMMER
        elif total_score >= 1:
            new_season = Season.SPRING
        elif total_score <= -3:
            new_season = Season.WINTER
        elif total_score <= -1:
            new_season = Season.AUTUMN
        else:
            # 中性评分时，如果当前是夏季且趋势向下则转秋季，反之亦然
            if self._current_season in (Season.SUMMER, Season.SPRING) and trend_20d < -0.05:
                new_season = Season.AUTUMN
            elif self._current_season in (Season.AUTUMN, Season.WINTER) and trend_20d > 0.05:
                new_season = Season.SPRING
            else:
                new_season = self._current_season  # 保持当前状态
        
        # 更新周期（防止频繁切换，至少保持30个交易日）
        # 注意：必须用K线自身的日期计时，而非 datetime.now()——
        # 回测中所有K线在几秒内跑完，用墙钟时间会让"30天间隔"恒为0，
        # 导致季节永远无法切换。
        if new_season != self._current_season:
            current_bar_date = self._latest_bar_datetime(df)
            if len(self._season_history) >= 1:
                last_switch = self._season_history[-1][0]
                if current_bar_date is not None:
                    days_since = (current_bar_date - last_switch).days
                    if days_since < 30:
                        # 距上次切换不足30个交易日，保持原状态
                        return
                else:
                    # 无法取得日期时退化为按K线计数（至少隔30根）
                    if self._bar_index - self._season_history[-1][2] < 30:
                        return

            if current_bar_date is not None:
                self._season_history.append((current_bar_date, new_season, self._bar_index))
            else:
                self._season_history.append((datetime.now(), new_season, self._bar_index))
            self._current_season = new_season
    
    def _check_risk_control(self) -> None:
        """检查止损止盈。"""
        if self._position <= 0 or self._entry_price == 0:
            return
        
        current_price = float(self.data.close[0])
        
        # 止损检查
        if self.p["stop_loss_pct"] > 0:
            if current_price <= self._entry_price * (1 - self.p["stop_loss_pct"]):
                self._close_position("止损")
                return
        
        # 止盈检查
        if self.p["take_profit_pct"] > 0:
            if current_price >= self._entry_price * (1 + self.p["take_profit_pct"]):
                self._close_position("止盈")
                return
    
    def _close_position(self, reason: str) -> None:
        """平仓。"""
        self._position = 0
        self._entry_price = 0.0
        self._entry_season = None
        self.sell()
        self._trade_count += 1
    
    def _generate_signals(self) -> None:
        """生成交易信号。"""
        if self._chanlun_result is None:
            return
        
        mmds = self._chanlun_result.mmds
        if not mmds:
            return
        
        # 获取最新买卖点
        latest_mmd = max(mmds, key=lambda m: m.bi.index if m.bi else 0) if mmds else None
        if latest_mmd is None:
            return
        
        current_idx = self._bar_index
        
        # 根据当前周期调整策略
        allowed_types = self._get_allowed_mmd_types()
        
        if latest_mmd.mmd_type in allowed_types:
            # 一类买卖点优先
            if latest_mmd.mmd_type == MMDType.BUY_1 and current_idx > self._last_buy_1_idx + 5:
                if self._position == 0:
                    self._open_position("1买")
                    self._last_buy_1_idx = current_idx
            elif latest_mmd.mmd_type == MMDType.SELL_1 and current_idx > self._last_sell_1_idx + 5:
                if self._position > 0:
                    self._close_position("1卖")
                    self._last_sell_1_idx = current_idx
            
            # 三类买卖点作为辅助
            elif latest_mmd.mmd_type == MMDType.BUY_3 and current_idx > self._last_buy_1_idx + 3:
                if self._position == 0:
                    self._open_position("3买")
                    self._last_buy_1_idx = current_idx
            elif latest_mmd.mmd_type == MMDType.SELL_3 and current_idx > self._last_sell_1_idx + 3:
                if self._position > 0:
                    self._close_position("3卖")
                    self._last_sell_1_idx = current_idx
    
    def _get_allowed_mmd_types(self) -> list[MMDType]:
        """根据当前周期获取允许的买卖点类型。"""
        season = self._current_season
        
        if season == Season.SUMMER:
            # 夏季：允许所有买点，保守卖点
            return [MMDType.BUY_1, MMDType.BUY_2, MMDType.BUY_3]
        elif season == Season.AUTUMN:
            # 秋季：允许买点和三类卖点
            return [MMDType.BUY_1, MMDType.SELL_3]
        elif season == Season.WINTER:
            # 冬季：只允许卖点
            return [MMDType.SELL_1, MMDType.SELL_2, MMDType.SELL_3]
        elif season == Season.SPRING:
            # 春季：允许所有买点
            return [MMDType.BUY_1, MMDType.BUY_2, MMDType.BUY_3]
        else:
            # 未知：保守策略
            return [MMDType.BUY_1]
    
    def _open_position(self, reason: str) -> None:
        """开仓。"""
        max_pos = self.p["max_position"]
        season_info = SEASON_DEFINITIONS.get(self._current_season, SEASON_DEFINITIONS[Season.UNKNOWN])
        
        # 根据季节调整仓位
        pos_range = season_info.position_range
        position_size = (pos_range[0] + pos_range[1]) / 2 / 100 * max_pos
        
        self._position = position_size
        self._entry_price = float(self.data.close[0])
        self._entry_season = self._current_season
        
        self.buy()
        self._trade_count += 1
    
    def get_status(self) -> dict[str, Any]:
        """获取策略状态。"""
        return {
            "current_season": self._current_season.value,
            "position": self._position,
            "entry_price": self._entry_price,
            "trade_count": self._trade_count,
            "chanlun_bis": len(self._chanlun_result.bis) if self._chanlun_result else 0,
            "chanlun_zss": len(self._chanlun_result.zss) if self._chanlun_result else 0,
            "chanlun_mmds": len(self._chanlun_result.mmds) if self._chanlun_result else 0,
            "chanlun_bcs": len(self._chanlun_result.bcs) if self._chanlun_result else 0,
        }


# 注册策略
@register_strategy(
    name="changying_chanlun",
    label="长赢缠论综合",
    description="结合吴伟志长赢四季周期理论和缠论三类买卖点的综合投资策略。一类买卖点准确率80-90%，三类买卖点经严格过滤后准确率提升至65%+。",
)
class ChangyingChanlunStrategyWrapper(ChangyingChanlunStrategy):
    """策略包装类。"""
    pass
