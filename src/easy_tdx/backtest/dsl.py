"""DSL 策略定义模块。

v1 提供 @dsl_strategy 装饰器：把返回 (buy_mask, sell_mask) 的函数编译为
可直接进 BacktestEngine 的 Strategy。init 时一次性预计算全量 mask（V-35
修复：骨架版从未调用 _signal_func，导致全链路 0 交易）。
字符串 DSL 解析器将在后续版本实现。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from .strategy import Strategy


def dsl_strategy(func: Callable[..., Any]) -> type[Strategy]:
    """将函数编译为 Strategy 子类。

    函数签名: (df: pd.DataFrame) -> tuple[np.ndarray[bool], np.ndarray[bool]]
    返回 (buy_mask, sell_mask)。

    用法::

        @dsl_strategy
        def dual_ma(df):
            buy = CROSS(MA(df.close, 5), MA(df.close, 20))
            sell = CROSS(MA(df.close, 20), MA(df.close, 5))
            return buy, sell
    """

    class DSLStrategy(Strategy):
        _signal_func = staticmethod(func)

        def init(self) -> None:
            # 数据绑定完成后一次性执行用户函数，预计算全量买卖 mask。
            # 此前骨架版从未调用 _signal_func（_buy_mask/_sell_mask 恒 None），
            # next() 永远静默返回 → 0 交易（V-35 修复，见 tests/unit/test_dsl_strategy.py）。
            proxy = self._data_proxy
            if proxy is None:
                return
            df = pd.DataFrame(
                {col: proxy._arrays[col] for col in proxy._arrays},
                index=range(len(next(iter(proxy._arrays.values())))),
            )
            buy_mask, sell_mask = type(self)._signal_func(df)
            self._buy_mask = np.asarray(buy_mask, dtype=bool)
            self._sell_mask = np.asarray(sell_mask, dtype=bool)
            n = len(self._buy_mask)
            if len(self._sell_mask) != n:
                raise ValueError(
                    f"dsl_strategy 返回的 buy/sell 长度不一致: {n} vs {len(self._sell_mask)}"
                )

        def next(self) -> None:
            buy = self._buy_mask
            sell = self._sell_mask
            if buy is None or sell is None:
                return
            idx = self._bar_index
            if idx < len(buy) and buy[idx]:
                self.buy(size=0)
            elif idx < len(sell) and sell[idx]:
                self.sell(size=0)

    DSLStrategy.__name__ = func.__name__
    DSLStrategy.__qualname__ = func.__qualname__

    return DSLStrategy
