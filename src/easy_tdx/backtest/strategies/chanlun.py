"""缠论买卖点策略（v9 - 精确日期映射版 + 置信度过滤 + 信号类型追踪）。

基于 easy_tdx.chanlun 模块，预计算全量缠论结构后按时间顺序执行信号。

策略逻辑：
- 1buy/2buy/2buy_s → 买入（空仓时，按置信度过滤）
- 3buy → 加仓/首次买入（持仓时，可选）
- 1sell/2sell/2sell_s → 卖出（持仓时，按置信度过滤）
- 3sell → 清仓（持仓时，可选）

核心改进：
- 精确日期映射：将笔结束日期映射到 DataFrame 确切 bar index
- 预计算一次性完成，运行时零开销
- 支持置信度阈值过滤（只交易高置信度信号）
- 支持类二买/类二卖信号
- v9 新增：信号类型追踪（记录每种买卖点的进场/出场价格用于后续回测验证）
- v9 新增：high_conf_only 参数（仅交易置信度 >= 70% 的信号）
"""

from __future__ import annotations

from typing import Any

from easy_tdx.backtest.strategies.registry import (
    Param,
    ParametrizedStrategy,
    register_strategy,
)


@register_strategy(
    name="chanlun",
    label="缠论买卖点",
    description="基于缠论笔、中枢、买卖点的预计算回测策略。精确日期映射，支持置信度过滤，可选递归级别信号（0=笔级别/1=线段级别/2+=更高级别）。",
)
class ChanlunStrategy(ParametrizedStrategy):
    """缠论买卖点策略（精确日期映射版 + 置信度过滤 + 信号追踪）。

    `analysis_level` 选择买卖点信号来源：
    - 0（默认）= 笔级别（基础级别 result.mmds，历史行为不变）；
    - N>=1 = 多级别递归第 N 级信号（result.recursive_levels[N-1].mmds，
      即把更高级别线段当作「笔」识别出的买卖点），级别不存在时无信号。
    """

    params = [
        Param("bi_type", str, default="new", choices=("new", "old", "simple"), label="笔类型"),
        Param("zs_min_lines", int, default=3, min_value=3, max_value=5, label="中枢最少笔数"),
        Param("macd_fast", int, default=12, min_value=6, max_value=20, label="MACD 快线"),
        Param("macd_slow", int, default=26, min_value=12, max_value=50, label="MACD 慢线"),
        Param("macd_signal", int, default=9, min_value=5, max_value=15, label="MACD 信号线"),
        Param(
            "analysis_level",
            int,
            default=0,
            min_value=0,
            max_value=8,
            label="信号分析级别 0=笔/1=线段/2+=递归更高级",
        ),
        Param(
            "position_pct",
            float,
            default=1.0,
            min_value=0.05,
            max_value=1.0,
            label="仓位比例(1=全仓,可按四季建议设 0.3~0.5)",
        ),
        Param("use_3buy", bool, default=True, label="启用三类买点"),
        Param("use_3sell", bool, default=True, label="启用三类卖点"),
        Param("use_2s_signals", bool, default=False, label="启用类二买/类二卖"),
        Param(
            "min_confidence",
            float,
            default=0.0,
            min_value=0.0,
            max_value=1.0,
            label="最低置信度(0=不过滤)",
        ),
        Param("stop_loss_pct", float, default=0.08, min_value=0.0, max_value=0.3, label="止损比例"),
        Param(
            "take_profit_pct", float, default=0.25, min_value=0.0, max_value=0.5, label="止盈比例"
        ),
        Param(
            "high_conf_only",
            bool,
            default=False,
            label="仅交易高置信度(>=70%)",
        ),
        Param(
            "use_v102_advice",
            bool,
            default=False,
            label="3买按V102建议止损止盈",
        ),
    ]

    def init(self) -> None:
        """初始化：预计算缠论并构建精确信号队列。"""
        import pandas as pd

        from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

        # 构建 DataFrame（保留原始 datetime 用于日期匹配）
        # vol/amount 列可能缺失（如纯 OHLC 数据），缺省回退 0，避免初始化崩溃
        n = len(self.data.open.raw)
        try:
            _vol_arr = [float(v) if v else 0.0 for v in self.data.vol.raw]
        except (KeyError, AttributeError):
            _vol_arr = [0.0] * n
        try:
            _amount_arr = [float(a) if a else 0.0 for a in self.data.amount.raw]
        except (KeyError, AttributeError):
            _amount_arr = [0.0] * n
        df = pd.DataFrame(
            {
                "open": self.data.open.raw.tolist(),
                "close": self.data.close.raw.tolist(),
                "high": self.data.high.raw.tolist(),
                "low": self.data.low.raw.tolist(),
                "vol": _vol_arr,
                "amount": _amount_arr,
            }
        )
        if self._datetime_array is not None:
            df["datetime"] = pd.to_datetime([int(d) for d in self._datetime_array], format="%Y%m%d")
        else:
            df["datetime"] = pd.date_range("2000-01-01", periods=n, freq="D")

        # 构建日期→bar index 映射
        self._date_to_bar: dict[str, int] = {}
        for i, row in df.iterrows():
            dt_str = str(row["datetime"])[:10]
            self._date_to_bar[dt_str] = i

        # 预计算缠论
        analysis_level = max(0, int(self.p.get("analysis_level") or 0))
        config = ChanlunConfig(
            bi_type=self.p["bi_type"],
            zs_min_lines=self.p["zs_min_lines"],
            macd_fast=self.p["macd_fast"],
            macd_slow=self.p["macd_slow"],
            macd_signal=self.p["macd_signal"],
            # 请求 N 级递归信号时，需保证多级别递归深度 >= N。
            recursion_depth=max(1, analysis_level),
        )
        analyser = ChanlunAnalyser(code="TEST", frequency="daily", config=config)
        result = analyser.process_klines(df)

        # 选定买卖点信号来源：
        #  analysis_level=0 → 笔级别（基础 result.mmds，历史行为）；
        #  analysis_level=N>=1 → 多级别递归第 N 级信号（不存在则该级无信号）。
        if analysis_level <= 0:
            src_mmds = result.mmds
            done_bis: list[Any] = [b for b in result.bis if b.is_done()]
        else:
            rec_idx = analysis_level - 1
            if rec_idx >= len(result.recursive_levels):
                # 请求的递归级别尚未被计算（数据/深度不足）→ 该级无信号。
                src_mmds = []
                done_bis = []
            else:
                src_mmds = result.recursive_levels[rec_idx].mmds
                # 该级别的「笔」= 计算该级递归所用到的线段，用作已完结信号过滤。
                level_lines = (
                    result.xds
                    if rec_idx == 0
                    else result.recursive_levels[rec_idx - 1].xds
                )
                done_bis = [ln for ln in level_lines if ln.is_done()]

        # 已完成的笔（用于判断信号是否可见）
        self._done_bis = done_bis

        # 构建信号队列：(bar_idx, mmd_type_str, confidence, v102_advice|None)
        self._chanlun_signals: list[tuple[int, str, float, dict[str, Any] | None]] = []
        seen_bi: set[int] = set()
        min_conf = self.p["min_confidence"]
        use_2s = self.p["use_2s_signals"]
        high_conf_only = self.p["high_conf_only"]

        for mmd in sorted(src_mmds, key=lambda m: m.bi.index if m.bi else 0):
            if mmd.bi is None:
                continue
            bi_idx = mmd.bi.index
            if bi_idx in seen_bi:
                continue
            seen_bi.add(bi_idx)

            # 只处理已完成笔的买卖点
            if bi_idx >= len(self._done_bis):
                continue

            # 置信度过滤
            conf = mmd.confidence
            if conf < min_conf:
                continue
            if high_conf_only and conf < 0.7:
                continue

            # 类二买/类二卖过滤
            if not use_2s and mmd.mmd_type.name in ("BUY_2S", "SELL_2S"):
                continue

            # 精确映射：笔结束日期 → bar index
            bar_idx = self._bi_end_bar_idx(mmd.bi)
            if bar_idx < 0:
                continue

            # V324: 3买 信号附带 V102 决策支持建议（入场/止损/止盈），供按建议执行
            advice = getattr(mmd, "_decision_support", None) or None
            self._chanlun_signals.append((bar_idx, mmd.mmd_type.value, conf, advice))

        # v9: 信号类型追踪（供回测准确度分析使用）
        self._signal_traces: dict[str, list[dict[str, Any]]] = {}
        for mmd in src_mmds:
            if mmd.bi is None:
                continue
            bar_idx = self._bi_end_bar_idx(mmd.bi)
            if bar_idx >= 0:
                key = mmd.mmd_type.value
                self._signal_traces.setdefault(key, []).append(
                    {"bar_index": bar_idx, "confidence": mmd.confidence}
                )

        # 状态
        self._signal_ptr = 0
        self._entry_price: float = 0.0
        self._position_count: int = 0
        self._last_signal_conf: float = 0.0
        self._last_signal_type: str = ""
        self._trade_log: list[dict[str, Any]] = []
        # V324: 当前仓位是否按 V102 建议止损止盈（3买 建议的 stop/take_profit_1）
        self._v102_active: bool = False
        self._v102_sl: float = 0.0
        self._v102_tp: float = 0.0

    def _do_buy(self) -> None:
        """按 position_pct 生成买入信号（1=全仓走引擎全仓估算；<1 按现金比例
        折算 100 股整数手）。四季建议仓位（春播 30%~50% 等）可直接设该参数。"""
        pct = float(self.p.get("position_pct", 1.0) or 1.0)
        if pct >= 1.0:
            self.buy()
            return
        price = float(self.data.close[0])
        if price <= 0 or self._cash <= 0:
            self.buy()
            return
        # 100 股整数手 + 少量余量吸收手续费（引擎实际执行价由 OrderSimulator 定）
        size = int(self._cash * pct / (price * 1.0005) / 100) * 100
        if size > 0:
            self.buy(size=size)
        else:
            # 现金不足一手：回退全仓信号（引擎按现金计算能买多少是多少）
            self.buy()

    def _bi_end_bar_idx(self, bi: Any) -> int:
        """获取笔结束分型的日期对应的 bar index。"""
        if bi.end is None:
            return -1
        end_date_str = str(bi.end.k.date)[:10]
        return self._date_to_bar.get(end_date_str, -1)

    def next(self) -> None:
        """每根 bar 调用：消费到达的信号。"""
        current_price = float(self.data.close[0])

        # V324: V102 建议止损/止盈优先（用盘中 high/low 判断触发）
        if self._v102_active and self._position_count > 0:
            if self._v102_sl > 0 and float(self.data.low[0]) <= self._v102_sl:
                self._record_trade("SELL", self._v102_sl, "v102_stop_loss", 0.0)
                self._close_position()
                return
            if self._v102_tp > 0 and float(self.data.high[0]) >= self._v102_tp:
                self._record_trade("SELL", self._v102_tp, "v102_take_profit", 0.0)
                self._close_position()
                return

        # 止损/止盈（百分比，V102 建议未激活时生效）
        if self._position_count > 0 and (
            self.p["stop_loss_pct"] > 0 or self.p["take_profit_pct"] > 0
        ):
            if self.p["stop_loss_pct"] > 0 and current_price <= self._entry_price * (
                1 - self.p["stop_loss_pct"]
            ):
                self._record_trade("SELL", current_price, "stop_loss", 0.0)
                self._close_position()
                return
            if self.p["take_profit_pct"] > 0 and current_price >= self._entry_price * (
                1 + self.p["take_profit_pct"]
            ):
                self._record_trade("SELL", current_price, "take_profit", 0.0)
                self._close_position()
                return

        # 消费信号队列
        while self._signal_ptr < len(self._chanlun_signals):
            bar_idx, mmd_type, confidence, advice = self._chanlun_signals[self._signal_ptr]
            if bar_idx > self._bar_index:
                break
            self._signal_ptr += 1
            self._last_signal_conf = confidence
            self._last_signal_type = mmd_type

            if mmd_type in ("1buy", "2buy"):
                if self._position_count == 0:
                    self._position_count = 1
                    self._entry_price = current_price
                    self._record_trade("BUY", current_price, mmd_type, confidence)
                    self._do_buy()

            elif mmd_type in ("2buy_s",) and self.p["use_2s_signals"]:
                if self._position_count == 0:
                    self._position_count = 1
                    self._entry_price = current_price
                    self._record_trade("BUY", current_price, mmd_type, confidence)
                    self._do_buy()

            elif mmd_type == "3buy" and self.p["use_3buy"]:
                if self._position_count >= 1:
                    self._position_count += 1
                    self._record_trade("BUY", current_price, mmd_type, confidence)
                    self._do_buy()
                elif self._position_count == 0:
                    self._position_count = 1
                    self._entry_price = current_price
                    # V324: 首仓按 V102 建议设定动态止损/止盈位
                    if self.p["use_v102_advice"] and advice:
                        self._v102_active = True
                        self._v102_sl = float(advice.get("stop_loss") or 0.0)
                        self._v102_tp = float(advice.get("take_profit_1") or 0.0)
                    else:
                        self._v102_active = False
                    self._record_trade("BUY", current_price, mmd_type, confidence)
                    self._do_buy()

            elif mmd_type in ("1sell", "2sell"):
                if self._position_count > 0:
                    self._record_trade("SELL", current_price, mmd_type, confidence)
                    self._close_position()

            elif mmd_type in ("2sell_s",) and self.p["use_2s_signals"]:
                if self._position_count > 0:
                    self._record_trade("SELL", current_price, mmd_type, confidence)
                    self._close_position()

            elif mmd_type == "3sell" and self.p["use_3sell"]:
                if self._position_count > 0:
                    self._record_trade("SELL", current_price, mmd_type, confidence)
                    self._close_position()

    def _record_trade(
        self,
        direction: str,
        price: float,
        signal_type: str,
        confidence: float,
    ) -> None:
        """记录交易（含信号类型和置信度）。"""
        self._trade_log.append(
            {
                "bar_index": self._bar_index,
                "direction": direction,
                "price": round(price, 4),
                "signal_type": signal_type,
                "confidence": round(confidence, 4),
            }
        )

    def _close_position(self) -> None:
        """平仓。"""
        self._position_count = 0
        self._entry_price = 0.0
        self._v102_active = False
        self._v102_sl = 0.0
        self._v102_tp = 0.0
        self.sell()

    @property
    def trade_log(self) -> list[dict[str, Any]]:
        """返回交易记录（供外部分析信号类型准确率）。"""
        return self._trade_log

    @property
    def signal_traces(self) -> dict[str, list[dict[str, Any]]]:
        """返回预计算的信号类型追踪（供外部分析）。"""
        return self._signal_traces
