"""缠论买卖点策略（v8 - 精确日期映射版 + 置信度过滤）。

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
"""

from __future__ import annotations

from easy_tdx.backtest.strategies.registry import (
    Param,
    ParametrizedStrategy,
    register_strategy,
)


@register_strategy(
    name="chanlun",
    label="缠论买卖点",
    description="基于缠论笔、中枢、买卖点的预计算回测策略。精确日期映射，支持置信度过滤。",
)
class ChanlunStrategy(ParametrizedStrategy):
    """缠论买卖点策略（精确日期映射版 + 置信度过滤）。"""

    params = [
        Param("bi_type", str, default="new", choices=("new", "old", "simple"), label="笔类型"),
        Param("zs_min_lines", int, default=3, min_value=3, max_value=5, label="中枢最少笔数"),
        Param("macd_fast", int, default=12, min_value=6, max_value=20, label="MACD 快线"),
        Param("macd_slow", int, default=26, min_value=12, max_value=50, label="MACD 慢线"),
        Param("macd_signal", int, default=9, min_value=5, max_value=15, label="MACD 信号线"),
        Param("use_3buy", bool, default=True, label="启用三类买点"),
        Param("use_3sell", bool, default=True, label="启用三类卖点"),
        Param("use_2s_signals", bool, default=False, label="启用类二买/类二卖"),
        Param("min_confidence", float, default=0.0, min_value=0.0, max_value=1.0, label="最低置信度(0=不过滤)"),
        Param("stop_loss_pct", float, default=0.08, min_value=0.0, max_value=0.3, label="止损比例"),
        Param("take_profit_pct", float, default=0.25, min_value=0.0, max_value=0.5, label="止盈比例"),
    ]

    def init(self) -> None:
        """初始化：预计算缠论并构建精确信号队列。"""
        import pandas as pd
        from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

        # 构建 DataFrame（保留原始 datetime 用于日期匹配）
        n = len(self.data.open.raw)
        df = pd.DataFrame({
            "open": self.data.open.raw.tolist(),
            "close": self.data.close.raw.tolist(),
            "high": self.data.high.raw.tolist(),
            "low": self.data.low.raw.tolist(),
            "vol": [float(v) if v else 0.0 for v in self.data.vol.raw],
            "amount": [float(a) if a else 0.0 for a in self.data.amount.raw],
        })
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
        config = ChanlunConfig(
            bi_type=self.p["bi_type"],
            zs_min_lines=self.p["zs_min_lines"],
            macd_fast=self.p["macd_fast"],
            macd_slow=self.p["macd_slow"],
            macd_signal=self.p["macd_signal"],
        )
        analyser = ChanlunAnalyser(code="TEST", frequency="daily", config=config)
        result = analyser.process_klines(df)

        # 已完成的笔（用于判断信号是否可见）
        self._done_bis = [b for b in result.bis if b.is_done()]

        # 构建信号队列：(bar_idx, mmd_type_str, confidence)
        self._chanlun_signals: list[tuple[int, str, float]] = []
        seen_bi: set[int] = set()
        min_conf = self.p["min_confidence"]
        use_2s = self.p["use_2s_signals"]

        for mmd in sorted(result.mmds, key=lambda m: m.bi.index if m.bi else 0):
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
            if mmd.confidence < min_conf:
                continue

            # 类二买/类二卖过滤
            if not use_2s and mmd.mmd_type.name in ("BUY_2S", "SELL_2S"):
                continue

            # 精确映射：笔结束日期 → bar index
            bar_idx = self._bi_end_bar_idx(mmd.bi)
            if bar_idx < 0:
                continue

            self._chanlun_signals.append((bar_idx, mmd.mmd_type.value, mmd.confidence))

        # 状态
        self._signal_ptr = 0
        self._entry_price: float = 0.0
        self._position_count: int = 0
        self._last_signal_conf: float = 0.0

    def _bi_end_bar_idx(self, bi) -> int:
        """获取笔结束分型的日期对应的 bar index。"""
        if bi.end is None:
            return -1
        end_date_str = str(bi.end.k.date)[:10]
        return self._date_to_bar.get(end_date_str, -1)

    def next(self) -> None:
        """每根 bar 调用：消费到达的信号。"""
        current_price = float(self.data.close[0])

        # 止损/止盈
        if self._position_count > 0 and (self.p["stop_loss_pct"] > 0 or self.p["take_profit_pct"] > 0):
            if self.p["stop_loss_pct"] > 0 and current_price <= self._entry_price * (1 - self.p["stop_loss_pct"]):
                self._close_position()
                return
            if self.p["take_profit_pct"] > 0 and current_price >= self._entry_price * (1 + self.p["take_profit_pct"]):
                self._close_position()
                return

        # 消费信号队列
        while self._signal_ptr < len(self._chanlun_signals):
            bar_idx, mmd_type, confidence = self._chanlun_signals[self._signal_ptr]
            if bar_idx > self._bar_index:
                break
            self._signal_ptr += 1
            self._last_signal_conf = confidence

            if mmd_type in ("1buy", "2buy"):
                if self._position_count == 0:
                    self._position_count = 1
                    self._entry_price = current_price
                    self.buy()

            elif mmd_type in ("2buy_s",) and self.p["use_2s_signals"]:
                if self._position_count == 0:
                    self._position_count = 1
                    self._entry_price = current_price
                    self.buy()

            elif mmd_type == "3buy" and self.p["use_3buy"]:
                if self._position_count >= 1:
                    self._position_count += 1
                    self.buy()
                elif self._position_count == 0:
                    self._position_count = 1
                    self._entry_price = current_price
                    self.buy()

            elif mmd_type in ("1sell", "2sell"):
                if self._position_count > 0:
                    self._close_position()

            elif mmd_type in ("2sell_s",) and self.p["use_2s_signals"]:
                if self._position_count > 0:
                    self._close_position()

            elif mmd_type == "3sell" and self.p["use_3sell"]:
                if self._position_count > 0:
                    self._close_position()

    def _close_position(self) -> None:
        """平仓。"""
        self._position_count = 0
        self._entry_price = 0.0
        self.sell()
