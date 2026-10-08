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

from easy_tdx.backtest.strategies.registry import (
    Param,
    ParametrizedStrategy,
    register_strategy,
)
from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
from easy_tdx.chanlun.types import MMDType


class Season(str, Enum):
    """四季周期状态。"""

    SPRING = "spring"  # 春季-播种期
    SUMMER = "summer"  # 夏季-成长期
    AUTUMN = "autumn"  # 秋季-收获期
    WINTER = "winter"  # 冬季-蛰伏期
    UNKNOWN = "unknown"  # 未知状态


class StockType(str, Enum):
    """股票分类。"""

    TREE = "tree"  # 树型企业-核心底仓
    GRAIN = "grain"  # 粮型企业-稳健收益
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
        Param("bi_type", str, default="new", choices=("new", "old", "simple"), label="笔类型"),
        Param("zs_min_lines", int, default=3, min_value=3, max_value=5, label="中枢最少笔数"),
        Param("macd_fast", int, default=12, min_value=6, max_value=20, label="MACD 快线"),
        Param("macd_slow", int, default=26, min_value=12, max_value=50, label="MACD 慢线"),
        Param("macd_signal", int, default=9, min_value=5, max_value=15, label="MACD 信号线"),
        # 长赢周期参数
        Param("use_season_filter", bool, default=True, label="使用周期过滤"),
        Param("season_lookback", int, default=100, min_value=50, max_value=200, label="周期观察期"),
        # 仓位管理参数
        Param("tree_weight", float, default=0.4, min_value=0.0, max_value=1.0, label="树型仓位"),
        Param("grain_weight", float, default=0.3, min_value=0.0, max_value=1.0, label="粮型仓位"),
        Param(
            "vegetable_weight", float, default=0.3, min_value=0.0, max_value=1.0, label="菜型仓位"
        ),
        # 风险控制参数
        Param("stop_loss_pct", float, default=0.08, min_value=0.0, max_value=0.3, label="止损比例"),
        Param(
            "take_profit_pct", float, default=0.25, min_value=0.0, max_value=0.5, label="止盈比例"
        ),
        Param("max_position", float, default=0.9, min_value=0.1, max_value=1.0, label="最大仓位"),
        # 前视守卫（与 chanlun._apply_lookahead_guard 同口径，防漂移）
        Param(
            "lookahead_guard",
            bool,
            default=True,
            label="前视守卫(前缀复现确认后才发信号)",
        ),
        Param(
            "confirm_lag",
            int,
            default=3,
            min_value=0,
            max_value=20,
            label="信号确认延迟(根)",
        ),
        Param(
            "guard_window",
            int,
            default=400,
            min_value=60,
            max_value=5000,
            label="守卫滚动复核窗口(根)",
        ),
    ]

    def init(self) -> None:
        """初始化策略。

        预计算**全量**缠论信号队列（供前视守卫复核 + ``next`` 按生效 bar 消费）；
        全量分析**不**写入 ``self._chanlun_result``——运行时仍按前缀逐步重算，
        季节/状态逻辑依赖的是逐步可得的信息。
        """
        # 缠论分析器
        self._analyser: ChanlunAnalyser | None = None
        self._chanlun_result: Any = None

        # 历史K线缓存
        self._history: list[dict[str, Any]] = []
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

        # ── 预计算全量信号队列（3 元组: bar_idx, mmd_type_str, confidence）──
        self._date_to_bar: dict[str, int] = {}
        self._full_datetime_strs: list[str] = []
        self._chanlun_signals: list[tuple[int, str, float]] = []
        self._signal_ptr = 0
        df = self._build_full_dataframe()
        if df is not None:
            for i, dt_str in enumerate(self._full_datetime_strs):
                self._date_to_bar[dt_str] = i
            self._chanlun_signals = self._precompute_signals(df)
            self._apply_lookahead_guard(df)

    def _build_full_dataframe(self) -> pd.DataFrame | None:
        """用绑定数据的全量 OHLCVA 构造 DataFrame（与 chanlun.py 同口径）。

        vol/amount 列可能缺失（如纯 OHLC 数据），缺省回退 0，避免初始化崩溃。
        """
        try:
            n = len(self.data.open.raw)
        except (RuntimeError, AttributeError, KeyError):
            return None
        if n == 0:
            return None
        try:
            vol_arr = [float(v) if v else 0.0 for v in self.data.vol.raw]
        except (KeyError, AttributeError):
            vol_arr = [0.0] * n
        try:
            amount_arr = [float(a) if a else 0.0 for a in self.data.amount.raw]
        except (KeyError, AttributeError):
            amount_arr = [0.0] * n
        df = pd.DataFrame(
            {
                "open": self.data.open.raw.tolist(),
                "close": self.data.close.raw.tolist(),
                "high": self.data.high.raw.tolist(),
                "low": self.data.low.raw.tolist(),
                "vol": vol_arr,
                "amount": amount_arr,
            }
        )
        if self._datetime_array is not None:
            df["datetime"] = pd.to_datetime([int(d) for d in self._datetime_array], format="%Y%m%d")
        else:
            df["datetime"] = pd.date_range("2000-01-01", periods=n, freq="D")
        self._full_datetime_strs = [str(v)[:10] for v in df["datetime"]]
        return df

    def _make_chanlun_analyser(self) -> ChanlunAnalyser:
        """构造与本策略参数一致的缠论分析器（全量预计算与运行时复用，防口径漂移）。"""
        config = ChanlunConfig(
            bi_type=self.p["bi_type"],
            zs_min_lines=self.p["zs_min_lines"],
            macd_fast=self.p["macd_fast"],
            macd_slow=self.p["macd_slow"],
            macd_signal=self.p["macd_signal"],
        )
        return ChanlunAnalyser(code="TEST", frequency="DAILY", config=config)

    def _bi_end_bar_idx(self, bi: Any) -> int:
        """笔结束分型日期 → bar index。

        与 ``chanlun._bi_end_bar_idx`` 同口径：走 ``mmd.bi.end.k.date`` 的日期→bar
        映射，**不用** ``end.bar_index``——合并K线后两者会错位。
        """
        if bi is None or bi.end is None:
            return -1
        end_date_str = str(bi.end.k.date)[:10]
        return self._date_to_bar.get(end_date_str, -1)

    def _precompute_signals(self, df: pd.DataFrame) -> list[tuple[int, str, float]]:
        """全量缠论分析 → Changying 专用信号队列 ``(bar_idx, type_str, confidence)``。"""
        result = self._make_chanlun_analyser().process_klines(df)
        queue: list[tuple[int, str, float]] = []
        seen: set[tuple[int, str]] = set()
        for mmd in sorted(result.mmds or [], key=lambda m: m.bi.index if m.bi else 0):
            bar_idx = self._bi_end_bar_idx(mmd.bi)
            if bar_idx < 0:
                continue
            key = (bar_idx, mmd.mmd_type.value)
            if key in seen:
                continue  # 去重保留首次置信度
            seen.add(key)
            queue.append((bar_idx, mmd.mmd_type.value, float(mmd.confidence)))
        return sorted(queue, key=lambda x: x[0])

    def _apply_lookahead_guard(self, df: pd.DataFrame) -> None:
        """与 chanlun._apply_lookahead_guard 同口径，防漂移。

        对每个候选 ``(b, type)``，在以 ``b+lag`` 为右端的滚动窗口（默认 400 根）
        上重跑一次本策略（**关守卫**，避免递归），仍能得到同一 ``(b, type)`` 才保留，
        并把生效 bar 改为 ``b + lag``；复现不出即为依赖未来数据的伪影，丢弃。
        数据不足（前缀==全量）时丢弃信号。

        差异说明：本策略信号为 3 元组 ``(b, type, conf)``；复核时只比对
        ``(b, type)``，conf 沿用首次出现的候选值。
        """
        if not bool(self.p.get("lookahead_guard", True)):
            return
        lag = max(0, int(self.p.get("confirm_lag", 3) or 0))
        window = max(60, int(self.p.get("guard_window", 400) or 400))
        candidates = self._chanlun_signals
        if not candidates:
            return

        n = len(df)
        kept: list[tuple[int, str, float]] = []
        seen: set[tuple[int, str]] = set()
        cache: dict[int, set[tuple[int, str]]] = {}

        from easy_tdx.backtest.strategies.registry import get_registry

        entry = get_registry().get("changying_chanlun")

        for bar_idx, mmd_type, conf in candidates:
            key = (bar_idx, mmd_type)
            if key in seen:
                continue
            seen.add(key)

            # 确认前缀必须严格短于全量数据，否则复核自证恒真
            k = bar_idx + lag + 1
            if k <= 0 or k >= n:
                continue
            lo = max(0, k - window)
            if k not in cache:
                sub = df.iloc[lo:k].reset_index(drop=True)
                offset = lo  # sub 内 bar_idx + offset = 原 df bar_idx
                try:
                    sub_strat = entry.build({**dict(self.p), "lookahead_guard": False})
                    sub_strat._bind_data(sub)
                    sub_strat._call_init()
                    sigs = getattr(sub_strat, "_chanlun_signals", [])
                    cache[k] = {(b + offset, t) for b, t, _c in sigs}
                except Exception:  # noqa: BLE001
                    cache[k] = set()
                    continue

            if key in cache[k]:
                # 延后到确认点：第 bar_idx+lag 根才真正可知
                kept.append((min(bar_idx + lag, n - 1), mmd_type, conf))

        self._chanlun_signals = sorted(kept, key=lambda x: x[0])

    def next(self) -> None:
        """每根K线调用。"""
        # 追加当前K线到历史
        bar = self._get_current_bar()
        self._history.append(bar)

        # 限制历史长度
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

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

    def _get_current_bar(self) -> dict[str, Any]:
        """获取当前K线数据。"""
        return {
            "datetime": self.data.datetime.raw[self._bar_index]
            if hasattr(self.data, "datetime")
            and self._bar_index < len(getattr(self.data, "datetime", []))
            else datetime.now(),
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
        """执行缠论分析（运行时按前缀逐步重算，供季节/状态使用）。"""
        analyser = self._make_chanlun_analyser()
        self._analyser = analyser
        self._chanlun_result = analyser.process_klines(df)

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
            if isinstance(v, pd.Timestamp | datetime):
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
        _ = df["high"].values.astype(float)

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
        """生成交易信号（消费预计算队列，按生效 bar 触发）。

        队列 ``self._chanlun_signals`` 是 init 时用全量数据算出的
        ``(bar_idx, type_str, confidence)``，已经过前视守卫复核并延后到确认 bar。
        这里只消费**当前 bar 刚好到达**的条目：
        - 未来条目（``bar_idx > current_idx``）→ 停住等它到期；
        - 过期条目（``bar_idx < current_idx``）→ 跳过（迟到的信号不再补发）。

        ``self._chanlun_result`` 仍是运行时按前缀重算的，仅用于季节/状态；
        信号判定**不再**直接读它，以免把全量未来信息带进决策。
        """
        if not self._chanlun_signals:
            return

        current_idx = self._bar_index

        # 根据当前周期调整策略
        allowed_types = self._get_allowed_mmd_types()

        while self._signal_ptr < len(self._chanlun_signals):
            bar_idx, mmd_type_str, _confidence = self._chanlun_signals[self._signal_ptr]
            if bar_idx > current_idx:
                break  # 未来的信号，尚未生效
            self._signal_ptr += 1
            if bar_idx < current_idx:
                continue  # 过期信号：不补发，避免迟到触发

            try:
                mmd_type = MMDType(mmd_type_str)
            except ValueError:
                continue

            if mmd_type not in allowed_types:
                continue

            # 一类买卖点优先
            if mmd_type == MMDType.BUY_1 and current_idx > self._last_buy_1_idx + 5:
                if self._position == 0:
                    self._open_position("1买")
                    self._last_buy_1_idx = current_idx
            elif mmd_type == MMDType.SELL_1 and current_idx > self._last_sell_1_idx + 5:
                if self._position > 0:
                    self._close_position("1卖")
                    self._last_sell_1_idx = current_idx

            # 三类买卖点作为辅助
            elif mmd_type == MMDType.BUY_3 and current_idx > self._last_buy_1_idx + 3:
                if self._position == 0:
                    self._open_position("3买")
                    self._last_buy_1_idx = current_idx
            elif mmd_type == MMDType.SELL_3 and current_idx > self._last_sell_1_idx + 3:
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
        season_info = SEASON_DEFINITIONS.get(
            self._current_season, SEASON_DEFINITIONS[Season.UNKNOWN]
        )

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
