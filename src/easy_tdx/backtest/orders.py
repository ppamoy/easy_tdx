"""订单撮合模拟器。

将策略信号转换为成交记录，支持多种执行模式、仓位管理和拒绝策略。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from easy_tdx.backtest.types import Signal, Trade

if TYPE_CHECKING:
    from easy_tdx.backtest.slippage import SlippageModel


@dataclass
class OrderSimulator:
    """订单撮合模拟器。

    将策略信号（Signal）转换为成交记录（Trade），支持多种执行模式、
    仓位管理和拒绝策略。

    Attributes:
        df: K线数据 DataFrame
        execution: 成交价规则 (next_open/next_close)
        position_mode: 仓位模式 (full/fixed/percent)
        reject_policy: 拒绝策略 (reduce/skip)
        commission: 佣金费率
        min_commission: 最低佣金
        stamp_tax: 印花税率（仅卖出）
        slippage: 滑点（每股）
        respect_price_limit: 是否启用涨跌停约束（V-AUDIT，默认开启）。
            涨停（成交价 ≥ 前收×(1+limit_pct)）禁止买入、跌停禁止卖出，
            拒绝的成交记 rejected=True。无前收（首根）不约束。
        limit_pct: 涨跌停幅度（默认 0.10 = 10%；主板口径，不含 ST/创业板差异）
    """

    df: pd.DataFrame
    execution: str = "next_open"
    position_mode: str = "full"
    reject_policy: str = "reduce"
    commission: float = 0.0003
    min_commission: float = 5.0
    stamp_tax: float = 0.001
    slippage: float = 0.0
    slippage_model: SlippageModel | None = None
    respect_price_limit: bool = True
    limit_pct: float = 0.10

    def simulate(
        self,
        signals: list[Signal],
        cash: float,
        position: float,
        position_mode: str | None = None,
    ) -> list[Trade]:
        """模拟订单撮合过程。

        Args:
            signals: 交易信号列表
            cash: 初始现金
            position: 初始持仓（股数）
            position_mode: 仓位模式（覆盖初始化参数）

        Returns:
            成交记录列表
        """
        if position_mode is None:
            position_mode = self.position_mode

        trades: list[Trade] = []
        current_cash = cash
        current_position = position

        for signal in signals:
            # 找到信号对应的 K 线
            bar_idx = self._find_bar_index(signal.datetime)
            if bar_idx is None:
                continue

            # 信号成交时点分三类：
            #  - source="stop"（止损/止盈触发）：延迟到下一根开盘成交，消除"用当根
            #    intrabar 触发价精确成交"的前视偏差；若下一根跳空，取对持仓者更不利的价。
            #  - price is not None 且非 stop（限价单）：在信号 bar 当根以信号价成交。
            #  - 其他（市价策略信号）：按 execution 配置（默认 next_open）在下一根成交。
            if signal.source == "stop":
                exec_idx_raw = self._resolve_exec_index(bar_idx)
                # 下一根不可用时（信号在最后一根 bar 触发），回退到当根收盘成交，
                # 避免止损信号被静默丢弃（审计 #4：不能因延迟成交而漏平仓）。
                next_price: float
                if exec_idx_raw is None or exec_idx_raw >= len(self.df):
                    exec_idx = bar_idx
                    row = self.df.iloc[bar_idx] if bar_idx < len(self.df) else None
                    if row is None:
                        continue
                    next_price = float(row["close"])
                else:
                    exec_idx = exec_idx_raw
                    price_raw = self._get_price(exec_idx, signal.direction)
                    if price_raw is None:
                        continue
                    next_price = price_raw
                # 跳空保护：对 SELL（平仓），若下一根开盘比触发价更不利（更低），
                # 取实际开盘价；否则按触发价（止损已生效）。
                trigger = signal.price if signal.price is not None else next_price
                if signal.direction == "SELL":
                    price: float = min(next_price, trigger)
                else:
                    price = max(next_price, trigger)
            elif signal.price is not None:
                # 限价单：在信号所在 bar 以信号价格成交
                exec_idx = bar_idx
                price = signal.price
            else:
                # 确定成交的 K 线索引
                exec_idx_raw = self._resolve_exec_index(bar_idx)
                if exec_idx_raw is None or exec_idx_raw >= len(self.df):
                    continue
                exec_idx = exec_idx_raw

                # 获取成交价
                price_raw = self._get_price(exec_idx, signal.direction)
                if price_raw is None:
                    continue
                price = price_raw

            # V-AUDIT: 涨跌停约束。A 股涨停当日无法买入、跌停当日无法卖出。
            # 以成交 bar 的前一根收盘为基准判定；基准缺失（首根）不约束。
            if self.respect_price_limit and self._is_limit_bar(exec_idx, price, signal.direction):
                # 生成拒绝成交记录（与资金不足拒绝同形态），保留信号轨迹可审计
                row = self.df.iloc[exec_idx] if exec_idx < len(self.df) else None
                trades.append(
                    Trade(
                        datetime=row["datetime"] if row is not None else signal.datetime,
                        direction=signal.direction,
                        size=0.0,
                        price=price,
                        commission=0.0,
                        slippage=0.0,
                        pnl=0.0,
                        rejected=True,
                        tag=signal.tag,
                    )
                )
                continue

            # 执行交易
            if signal.direction == "BUY":
                trade = self._execute_buy(
                    signal=signal,
                    bar_idx=bar_idx,
                    exec_idx=exec_idx,
                    price=price,
                    cash=current_cash,
                    position=current_position,
                    position_mode=position_mode,
                )
                if trade is not None:
                    trades.append(trade)
                    if not trade.rejected:
                        current_cash -= trade.size * trade.price + trade.commission + trade.slippage
                        current_position += trade.size

            elif signal.direction == "SELL":
                trade = self._execute_sell(
                    signal=signal,
                    bar_idx=bar_idx,
                    exec_idx=exec_idx,
                    price=price,
                    cash=current_cash,
                    position=current_position,
                    position_mode=position_mode,
                )
                if trade is not None:
                    trades.append(trade)
                    if not trade.rejected:
                        current_cash += trade.size * trade.price - trade.commission - trade.slippage
                        current_position -= trade.size

        return trades

    def _find_bar_index(self, datetime_val: int) -> int | None:
        """查找 datetime 对应的 K 线索引。

        Args:
            datetime_val: 信号时间（int 格式 YYYYMMDD）

        Returns:
            K 线索引，未找到返回 None
        """
        # 检查 df 中的 datetime 列类型
        dt_col = self.df["datetime"]

        # 尝试直接比较（如果是 int 类型）
        # 注意：用 to_numpy().argmax() 取位置索引，而非 idxmax()（返回 label），
        # 因为后续 self.df.iloc[...] 按位置取行；若 df.index 非默认 RangeIndex，
        # label != position 会导致撮合取错 bar。
        try:
            mask = (dt_col == datetime_val).to_numpy()
            if mask.any():
                return int(mask.argmax())
        except (TypeError, ValueError):
            pass

        # 如果是 datetime 对象，转为 int 比较
        if pd.api.types.is_datetime64_any_dtype(dt_col):
            dt_ints = dt_col.dt.strftime("%Y%m%d").astype(int)
            mask_arr = (dt_ints == datetime_val).to_numpy()
            if mask_arr.any():
                return int(mask_arr.argmax())
            return None

        return None

    def _is_limit_bar(self, exec_idx: int, price: float, direction: str) -> bool:
        """判定成交 bar 是否处于涨跌停状态（V-AUDIT）。

        以**前一根收盘**为基准（撮合时刻可知的口径）：成交价 ≥ 前收×(1+pct)
        视为涨停（禁买），≤ 前收×(1-pct) 视为跌停（禁卖）。基准无效或
        价格非正时不约束。买入看涨停、卖出看跌停，另一侧不限制。
        """
        if exec_idx <= 0 or exec_idx >= len(self.df):
            return False
        prev_close = float(self.df.iloc[exec_idx - 1]["close"])
        if prev_close <= 0 or price <= 0:
            return False
        limit_up = prev_close * (1 + self.limit_pct)
        limit_down = prev_close * (1 - self.limit_pct)
        if direction == "BUY":
            return price >= limit_up - 1e-9
        return price <= limit_down + 1e-9

    def _resolve_exec_index(self, bar_idx: int) -> int | None:
        """根据执行模式确定成交的 K 线索引。

        开盘价 / 收盘价模式均在信号后一根 K 线成交（next_open 取次根开盘价，
        next_close 取次根收盘价），避免使用信号当根的未完成/未来数据。

        Args:
            bar_idx: 信号对应的 K 线索引

        Returns:
            成交 K 线索引
        """
        return bar_idx + 1

    def _get_price(self, exec_idx: int, direction: str) -> float | None:
        """根据执行模式获取成交价。

        Args:
            exec_idx: 成交 K 线索引
            direction: 交易方向（仅作保留，当前两种模式均不依赖方向）

        Returns:
            成交价格
        """
        if exec_idx >= len(self.df):
            return None

        row = self.df.iloc[exec_idx]

        if self.execution == "next_open":
            return float(row["open"])
        elif self.execution == "next_close":
            return float(row["close"])
        else:
            return None

    def _calculate_buy_size(
        self,
        signal_size: float,
        price: float,
        cash: float,
        position_mode: str,
    ) -> float:
        """计算买入数量。

        Args:
            signal_size: 信号指定的数量
            price: 成交价格
            cash: 可用现金
            position_mode: 仓位模式

        Returns:
            买入数量（股）
        """
        # V733 修复：策略**显式指定**的仓位必须被尊重。
        #
        # ⚠️ 原实现：`if position_mode == "full" or signal_size == 0:`
        # 引擎默认 position_mode='full' ⇒ 任何非零 signal_size 都被**丢弃**，
        # 一律按现金满仓买入。而 ChanlunStrategy._do_buy 会按 `position_pct`
        # 算出成比例的股数（如 50% → 4600 股），却在这里被改回 99900 股。
        # 后果：策略文档承诺的"四季建议仓位 30%~50% 可直接设该参数"
        # **完全不起作用**，用户按建议设仓位却仍被满仓 —— 会误导真实决策。
        #
        # 修复：'full' 的语义是"**未指定仓位时**满仓"，而非"忽略指定仓位"。
        # 因此只有 signal_size == 0 才走满仓计算。
        if signal_size and signal_size > 0:
            # 策略显式指定了股数（已按整手取整），不再被仓位模式覆盖
            if position_mode == "percent":
                total_value = cash  # 简化：假设现金=总资产
                max_shares = int(total_value * signal_size / price / 100) * 100
                return float(max_shares)
            if position_mode == "fixed":
                return signal_size
            # full / long_only 等：尊重策略指定的股数
            return signal_size
        if position_mode == "full" or signal_size == 0:
            # 全仓：计算可用现金能买多少（100股整手）
            # 先计算最大股数，然后向下取整到100的倍数
            max_cost_per_share = price * (1 + self.commission) + self.slippage
            max_shares_raw = cash / max_cost_per_share
            max_shares = int(max_shares_raw / 100) * 100
            return float(max_shares)
        elif position_mode == "fixed":
            # 固定股数
            return signal_size
        elif position_mode == "percent":
            # 总资产的百分比
            total_value = cash  # 简化：假设现金=总资产
            target_value = total_value * signal_size
            max_shares = int(target_value / price / 100) * 100
            return float(max_shares)
        else:
            return signal_size

    def _calculate_sell_size(
        self,
        signal_size: float,
        position: float,
        position_mode: str,
    ) -> float:
        """计算卖出数量。

        Args:
            signal_size: 信号指定的数量
            position: 当前持仓
            position_mode: 仓位模式

        Returns:
            卖出数量（股）
        """
        # V733 修复：与买入侧对称 —— 策略显式指定的卖出数量必须被尊重。
        # 原来 `position_mode == "full"` 会把所有非零 signal_size 也当成"全卖"，
        # 导致策略想"减半仓"时仍然一次清空。
        if signal_size and signal_size > 0:
            if position_mode == "percent":
                return position * signal_size
            return signal_size
        if position_mode == "full" or signal_size == 0:
            # 全部卖出
            return position
        elif position_mode == "fixed":
            # 固定股数
            return signal_size
        elif position_mode == "percent":
            # 持仓的百分比
            return position * signal_size
        else:
            return signal_size

    def _calculate_commission(self, size: float, price: float, is_sell: bool = False) -> float:
        """计算手续费。

        Args:
            size: 成交数量
            price: 成交价格
            is_sell: 是否为卖出

        Returns:
            手续费总额
        """
        # 佣金
        commission = max(size * price * self.commission, self.min_commission)

        # 印花税（仅卖出）
        if is_sell:
            stamp = size * price * self.stamp_tax
            commission += stamp

        return commission

    def _compute_slippage(self, size: float, price: float, is_sell: bool) -> float:
        """计算滑点成本。"""
        if self.slippage_model is not None:
            volume = self._get_current_volume()
            volatility = self._estimate_volatility()
            return self.slippage_model.compute(
                price=price,
                size=size,
                volume=volume,
                volatility=volatility,
                direction="SELL" if is_sell else "BUY",
            )
        return size * self.slippage

    def _get_current_volume(self) -> float:
        """获取最后一根K线的成交量，兼容 vol/volume 列名。"""
        if len(self.df) == 0:
            return 0.0
        for col in ("vol", "volume"):
            if col in self.df.columns:
                return float(self.df[col].iloc[-1])
        return 0.0

    def _estimate_volatility(self) -> float:
        """从收盘价估计年化波动率。"""
        if "close" not in self.df.columns or len(self.df) < 2:
            return 0.0
        close = self.df["close"].to_numpy()
        returns = np.diff(close) / close[:-1]
        if len(returns) < 2:
            return 0.0
        daily_vol = float(np.std(returns))
        return float(daily_vol * np.sqrt(252))

    def _execute_buy(
        self,
        signal: Signal,
        bar_idx: int,
        exec_idx: int,
        price: float,
        cash: float,
        position: float,
        position_mode: str,
    ) -> Trade | None:
        """执行买入。

        Args:
            signal: 交易信号
            bar_idx: 信号 K 线索引
            exec_idx: 成交 K 线索引
            price: 成交价格
            cash: 可用现金
            position: 当前持仓
            position_mode: 仓位模式

        Returns:
            成交记录
        """
        # 保存原始信号数量
        original_size = signal.size

        # 计算买入数量
        size = self._calculate_buy_size(signal.size, price, cash, position_mode)

        if size <= 0:
            # 资金不足或计算结果为0
            if self.reject_policy == "skip":
                # 对于 percent 模式，original_size 是百分比（如 0.5），不是股数
                # 对于 fixed/full 模式，original_size 就是股数
                display_size = original_size if position_mode == "fixed" else 100
                return Trade(
                    datetime=self.df.iloc[exec_idx]["datetime"],
                    direction="BUY",
                    size=display_size,
                    price=price,
                    commission=0.0,
                    slippage=0.0,
                    pnl=0.0,
                    rejected=True,
                    tag=signal.tag,
                )
            return None

        # 计算费用
        commission = self._calculate_commission(size, price, is_sell=False)
        slippage = self._compute_slippage(size, price, is_sell=False)

        # 检查资金是否足够
        total_cost = size * price + commission + slippage
        if total_cost > cash:
            if self.reject_policy == "skip":
                return Trade(
                    datetime=self.df.iloc[exec_idx]["datetime"],
                    direction="BUY",
                    size=original_size,
                    price=price,
                    commission=commission,
                    slippage=slippage,
                    pnl=0.0,
                    rejected=True,
                    tag=signal.tag,
                )
            elif self.reject_policy == "reduce":
                # reduce 模式：重新计算可买数量
                available_cash = cash - self.min_commission - slippage
                if available_cash > price:
                    reduced_size = int(available_cash / price / 100) * 100
                    if reduced_size > 0:
                        commission = self._calculate_commission(reduced_size, price, is_sell=False)
                        slippage = self._compute_slippage(reduced_size, price, is_sell=False)
                        return Trade(
                            datetime=self.df.iloc[exec_idx]["datetime"],
                            direction="BUY",
                            size=reduced_size,
                            price=price,
                            commission=commission,
                            slippage=slippage,
                            pnl=0.0,
                            rejected=False,
                            tag=signal.tag,
                        )
                # 无法买任何数量
                return None

        return Trade(
            datetime=self.df.iloc[exec_idx]["datetime"],
            direction="BUY",
            size=size,
            price=price,
            commission=commission,
            slippage=slippage,
            pnl=0.0,
            rejected=False,
            tag=signal.tag,
        )

    def _execute_sell(
        self,
        signal: Signal,
        bar_idx: int,
        exec_idx: int,
        price: float,
        cash: float,
        position: float,
        position_mode: str,
    ) -> Trade | None:
        """执行卖出。

        Args:
            signal: 交易信号
            bar_idx: 信号 K 线索引
            exec_idx: 成交 K 线索引
            price: 成交价格
            cash: 可用现金
            position: 当前持仓
            position_mode: 仓位模式

        Returns:
            成交记录
        """
        # 计算卖出数量
        size = self._calculate_sell_size(signal.size, position, position_mode)

        if size <= 0:
            # 无持仓
            if self.reject_policy == "skip":
                return Trade(
                    datetime=self.df.iloc[exec_idx]["datetime"],
                    direction="SELL",
                    size=0,
                    price=price,
                    commission=0.0,
                    slippage=0.0,
                    pnl=0.0,
                    rejected=True,
                    tag=signal.tag,
                )
            return None

        # 检查持仓是否足够
        if size > position:
            if self.reject_policy == "skip":
                return Trade(
                    datetime=self.df.iloc[exec_idx]["datetime"],
                    direction="SELL",
                    size=size,
                    price=price,
                    commission=0.0,
                    slippage=0.0,
                    pnl=0.0,
                    rejected=True,
                    tag=signal.tag,
                )
            # reduce 模式：减少到实际持仓
            size = position

        # 计算费用
        commission = self._calculate_commission(size, price, is_sell=True)
        slippage = self._compute_slippage(size, price, is_sell=True)

        return Trade(
            datetime=self.df.iloc[exec_idx]["datetime"],
            direction="SELL",
            size=size,
            price=price,
            commission=commission,
            slippage=slippage,
            pnl=0.0,
            rejected=False,
            tag=signal.tag,
        )
