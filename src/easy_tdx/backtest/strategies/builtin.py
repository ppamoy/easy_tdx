"""内置策略集合。

每个策略通过 :func:`~easy_tdx.backtest.strategies.registry.register_strategy`
登记到全局注册表，并声明参数 schema 供 Web API 表单动态渲染。

导入本模块即触发所有策略的注册。Web API / CLI 通过 ``get_registry()```
发现策略，无需手动枚举。
"""

from __future__ import annotations

import numpy as np

from easy_tdx.backtest.strategies.registry import (
    Param,
    ParametrizedStrategy,
    register_strategy,
)
from easy_tdx.MyTT import (
    ATR,
    BBI,
    BIAS,
    BOLL,
    CCI,
    COUNT,
    CROSS,
    DMI,
    DPO,
    EMA,
    EMV,
    FSL,
    HHV,
    KDJ,
    KTN,
    LLV,
    MA,
    MACD,
    OBV,
    RSI,
    TAQ,
    TRIX,
    WR,
)

__all__: list[str] = []  # 注册副作用即可，无需导出符号


# ── 双均线交叉 ─────────────────────────────────────────────────────────────────


@register_strategy(
    name="ma_cross",
    label="双均线交叉",
    description="快线上穿慢线买入，快线下穿慢线卖出。最经典的趋势跟随策略。",
)
class MaCrossStrategy(ParametrizedStrategy):
    """快慢均线金叉买入、死叉卖出。"""

    params = [
        Param("fast", int, default=5, min_value=1, max_value=60, label="快线周期"),
        Param("slow", int, default=20, min_value=5, max_value=250, label="慢线周期"),
    ]

    def init(self) -> None:
        self.ma_fast = self.I(MA, self.data.close, self.p["fast"])
        self.ma_slow = self.I(MA, self.data.close, self.p["slow"])
        self.gold = self.I(CROSS, self.ma_fast, self.ma_slow)
        self.dead = self.I(CROSS, self.ma_slow, self.ma_fast)

    def next(self) -> None:
        i = self._bar_index
        if self.gold[i]:
            self.buy()
        elif self.dead[i] and self.position["size"] > 0:
            self.sell()


# ── MACD 金叉 ──────────────────────────────────────────────────────────────────


@register_strategy(
    name="macd",
    label="MACD 金叉",
    description="DIF 上穿 DEA 买入（金叉），DIF 下穿 DEA 卖出（死叉）。",
)
class MacdStrategy(ParametrizedStrategy):
    """MACD 金叉/死叉。"""

    params = [
        Param("short", int, default=12, min_value=2, max_value=50, label="短期EMA"),
        Param("long", int, default=26, min_value=5, max_value=100, label="长期EMA"),
        Param("signal", int, default=9, min_value=2, max_value=50, label="信号周期"),
    ]

    def init(self) -> None:
        self.dif, self.dea, self._hist = self.I(
            MACD,
            self.data.close,
            self.p["short"],
            self.p["long"],
            self.p["signal"],
        )
        self.gold = self.I(CROSS, self.dif, self.dea)
        self.dead = self.I(CROSS, self.dea, self.dif)

    def next(self) -> None:
        i = self._bar_index
        if self.gold[i]:
            self.buy()
        elif self.dead[i] and self.position["size"] > 0:
            self.sell()


# ── 布林带突破 ─────────────────────────────────────────────────────────────────


@register_strategy(
    name="boll_breakout",
    label="布林带突破",
    description="收盘价突破下轨买入，突破上轨卖出（均值回归思路）。",
)
class BollBreakoutStrategy(ParametrizedStrategy):
    """价格触及下轨买入、触及上轨卖出。"""

    params = [
        Param("n", int, default=20, min_value=5, max_value=100, label="周期"),
        Param("p", float, default=2.0, min_value=0.5, max_value=4.0, label="标准差倍数"),
    ]

    def init(self) -> None:
        self.upper, self.mid, self.lower = self.I(BOLL, self.data.close, self.p["n"], self.p["p"])

    def next(self) -> None:
        i = self._bar_index
        close = self.data.close[0]
        # 触及下轨买入（均值回归）；触及上轨获利了结
        if close <= self.lower[i] and self.position["size"] == 0:
            self.buy()
        elif close >= self.upper[i] and self.position["size"] > 0:
            self.sell()


# ── RSI 超买超卖 ───────────────────────────────────────────────────────────────


@register_strategy(
    name="rsi_reversal",
    label="RSI 超卖反弹",
    description="RSI 低于超卖线买入，RSI 高于超买线卖出。",
)
class RsiReversalStrategy(ParametrizedStrategy):
    """RSI 超卖买入、超买卖出。"""

    params = [
        Param("n", int, default=14, min_value=2, max_value=50, label="RSI周期"),
        Param("oversold", int, default=30, min_value=5, max_value=45, label="超卖线"),
        Param("overbought", int, default=70, min_value=55, max_value=95, label="超买线"),
    ]

    def init(self) -> None:
        self.rsi = self.I(RSI, self.data.close, self.p["n"])

    def next(self) -> None:
        i = self._bar_index
        rsi = self.rsi[i]
        if rsi <= self.p["oversold"] and self.position["size"] == 0:
            self.buy()
        elif rsi >= self.p["overbought"] and self.position["size"] > 0:
            self.sell()


# ── KDJ 金叉 ───────────────────────────────────────────────────────────────────


@register_strategy(
    name="kdj_cross",
    label="KDJ 金叉",
    description="K 线上穿 D 线买入（金叉），K 线下穿 D 线卖出（死叉）。",
)
class KdjCrossStrategy(ParametrizedStrategy):
    """KDJ K/D 金叉死叉。"""

    params = [
        Param("n", int, default=9, min_value=2, max_value=30, label="RSV周期"),
    ]

    def init(self) -> None:
        self.k, self.d, self._j = self.I(
            KDJ,
            self.data.close,
            self.data.high,
            self.data.low,
            self.p["n"],
        )
        self.gold = self.I(CROSS, self.k, self.d)
        self.dead = self.I(CROSS, self.d, self.k)

    def next(self) -> None:
        i = self._bar_index
        if self.gold[i]:
            self.buy()
        elif self.dead[i] and self.position["size"] > 0:
            self.sell()


# ── EMA 双线交叉 ──────────────────────────────────────────────────────────────


@register_strategy(
    name="ema_cross",
    label="EMA 双线交叉",
    description="指数均线金叉买入、死叉卖出。比简单均线反应更灵敏。",
)
class EmaCrossStrategy(ParametrizedStrategy):
    params = [
        Param("fast", int, default=12, min_value=2, max_value=60, label="快线周期"),
        Param("slow", int, default=26, min_value=5, max_value=120, label="慢线周期"),
    ]

    def init(self) -> None:
        self.ema_fast = self.I(EMA, self.data.close, self.p["fast"])
        self.ema_slow = self.I(EMA, self.data.close, self.p["slow"])
        self.gold = self.I(CROSS, self.ema_fast, self.ema_slow)
        self.dead = self.I(CROSS, self.ema_slow, self.ema_fast)

    def next(self) -> None:
        i = self._bar_index
        if self.gold[i]:
            self.buy()
        elif self.dead[i] and self.position["size"] > 0:
            self.sell()


# ── 三均线系统 ────────────────────────────────────────────────────────────────


@register_strategy(
    name="triple_ma",
    label="三均线系统",
    description="短中长期均线多头排列买入、空头排列卖出。",
)
class TripleMaStrategy(ParametrizedStrategy):
    params = [
        Param("short", int, default=5, min_value=1, max_value=30, label="短期"),
        Param("mid", int, default=20, min_value=5, max_value=60, label="中期"),
        Param("long", int, default=60, min_value=20, max_value=250, label="长期"),
    ]

    def init(self) -> None:
        self.ma_s = self.I(MA, self.data.close, self.p["short"])
        self.ma_m = self.I(MA, self.data.close, self.p["mid"])
        self.ma_l = self.I(MA, self.data.close, self.p["long"])

    def next(self) -> None:
        i = self._bar_index
        if self.ma_s[i] > self.ma_m[i] > self.ma_l[i] and self.position["size"] == 0:
            self.buy()
        elif self.ma_s[i] < self.ma_m[i] < self.ma_l[i] and self.position["size"] > 0:
            self.sell()


# ── 唐安奇通道（海龟）────────────────────────────────────────────────────────


@register_strategy(
    name="donchian",
    label="唐安奇通道突破",
    description="突破N日最高价买入，跌破N日最低价卖出。海龟交易法核心。",
)
class DonchianStrategy(ParametrizedStrategy):
    params = [
        Param("n", int, default=20, min_value=5, max_value=100, label="通道周期"),
    ]

    def init(self) -> None:
        self.upper, self._mid, self.lower = self.I(TAQ, self.data.high, self.data.low, self.p["n"])

    def next(self) -> None:
        i = self._bar_index
        close = self.data.close[0]
        if close >= self.upper[i] and self.position["size"] == 0:
            self.buy()
        elif close <= self.lower[i] and self.position["size"] > 0:
            self.sell()


# ── 肯特纳通道 ────────────────────────────────────────────────────────────────


@register_strategy(
    name="keltner",
    label="肯特纳通道",
    description="收盘价突破上轨买入，跌破下轨卖出。ATR-based 通道。",
)
class KeltnerStrategy(ParametrizedStrategy):
    params = [
        Param("n", int, default=20, min_value=5, max_value=100, label="均线周期"),
        Param("m", int, default=10, min_value=2, max_value=50, label="ATR周期"),
    ]

    def init(self) -> None:
        self.upper, self._mid, self.lower = self.I(
            KTN, self.data.close, self.data.high, self.data.low, self.p["n"], self.p["m"]
        )

    def next(self) -> None:
        i = self._bar_index
        close = self.data.close[0]
        if close >= self.upper[i] and self.position["size"] == 0:
            self.buy()
        elif close <= self.lower[i] and self.position["size"] > 0:
            self.sell()


# ── BBI 多空指标 ──────────────────────────────────────────────────────────────


@register_strategy(
    name="bbi",
    label="BBI 多空指标",
    description="收盘价上穿BBI买入，下穿BBI卖出。多空综合指标。",
)
class BbiStrategy(ParametrizedStrategy):
    params = [
        Param("m1", int, default=3, min_value=1, max_value=20, label="均线1"),
        Param("m2", int, default=6, min_value=2, max_value=30, label="均线2"),
        Param("m3", int, default=12, min_value=5, max_value=60, label="均线3"),
        Param("m4", int, default=20, min_value=10, max_value=120, label="均线4"),
    ]

    def init(self) -> None:
        self.bbi = self.I(
            BBI, self.data.close, self.p["m1"], self.p["m2"], self.p["m3"], self.p["m4"]
        )

    def next(self) -> None:
        i = self._bar_index
        close = self.data.close[0]
        if close > self.bbi[i] and self.position["size"] == 0:
            self.buy()
        elif close < self.bbi[i] and self.position["size"] > 0:
            self.sell()


# ── CCI 顺势指标 ──────────────────────────────────────────────────────────────


@register_strategy(
    name="cci",
    label="CCI 超卖反弹",
    description="CCI 跌破-100后回升买入，涨破+100卖出。",
)
class CciStrategy(ParametrizedStrategy):
    params = [
        Param("n", int, default=14, min_value=2, max_value=50, label="CCI周期"),
        Param("oversold", int, default=-100, min_value=-200, max_value=0, label="超卖线"),
        Param("overbought", int, default=100, min_value=0, max_value=200, label="超买线"),
    ]

    def init(self) -> None:
        self.cci = self.I(CCI, self.data.close, self.data.high, self.data.low, self.p["n"])

    def next(self) -> None:
        i = self._bar_index
        cci = self.cci[i]
        if cci <= self.p["oversold"] and self.position["size"] == 0:
            self.buy()
        elif cci >= self.p["overbought"] and self.position["size"] > 0:
            self.sell()


# ── WR 威廉指标 ───────────────────────────────────────────────────────────────


@register_strategy(
    name="wr_reversal",
    label="WR 威廉超卖",
    description="WR 进入超卖区（<-80）买入，进入超买区（>-20）卖出。",
)
class WrReversalStrategy(ParametrizedStrategy):
    params = [
        Param("n", int, default=14, min_value=2, max_value=50, label="WR周期"),
        Param("oversold", int, default=-80, min_value=-100, max_value=-40, label="超卖线"),
        Param("overbought", int, default=-20, min_value=-60, max_value=0, label="超买线"),
    ]

    def init(self) -> None:
        self.wr, self._wr1 = self.I(WR, self.data.close, self.data.high, self.data.low, self.p["n"])

    def next(self) -> None:
        i = self._bar_index
        wr = self.wr[i]
        if wr <= self.p["oversold"] and self.position["size"] == 0:
            self.buy()
        elif wr >= self.p["overbought"] and self.position["size"] > 0:
            self.sell()


# ── BIAS 乖离率 ───────────────────────────────────────────────────────────────


@register_strategy(
    name="bias_reversal",
    label="BIAS 乖离反弹",
    description="乖离率低于负阈值（超跌）买入，高于正阈值（超涨）卖出。",
)
class BiasReversalStrategy(ParametrizedStrategy):
    params = [
        Param("n", int, default=6, min_value=2, max_value=30, label="均线周期"),
        Param("threshold", float, default=5.0, min_value=1.0, max_value=20.0, label="乖离阈值%"),
    ]

    def init(self) -> None:
        self.bias, self._b2, self._b3 = self.I(BIAS, self.data.close, self.p["n"], 12, 24)

    def next(self) -> None:
        i = self._bar_index
        bias_pct = self.bias[i] * 100
        threshold = self.p["threshold"]
        if bias_pct <= -threshold and self.position["size"] == 0:
            self.buy()
        elif bias_pct >= threshold and self.position["size"] > 0:
            self.sell()


# ── DMI 趋向指标 ──────────────────────────────────────────────────────────────


@register_strategy(
    name="dmi",
    label="DMI 趋向指标",
    description="+DI 上穿-DI 买入（多头趋强），+DI 下穿-DI 卖出。",
)
class DmiStrategy(ParametrizedStrategy):
    params = [
        Param("m1", int, default=14, min_value=2, max_value=30, label="DI周期"),
        Param("m2", int, default=6, min_value=2, max_value=20, label="ADX周期"),
    ]

    def init(self) -> None:
        self.pdi, self.mdi, self._adx, self._adxr = self.I(
            DMI, self.data.close, self.data.high, self.data.low, self.p["m1"], self.p["m2"]
        )
        self.gold = self.I(CROSS, self.pdi, self.mdi)
        self.dead = self.I(CROSS, self.mdi, self.pdi)

    def next(self) -> None:
        i = self._bar_index
        if self.gold[i]:
            self.buy()
        elif self.dead[i] and self.position["size"] > 0:
            self.sell()


# ── TRIX 三重平滑 ─────────────────────────────────────────────────────────────


@register_strategy(
    name="trix",
    label="TRIX 三重平滑",
    description="TRIX 上穿信号线买入，下穿卖出。过滤短期波动的趋势指标。",
)
class TrixStrategy(ParametrizedStrategy):
    params = [
        Param("m1", int, default=12, min_value=2, max_value=30, label="TRIX周期"),
        Param("m2", int, default=20, min_value=5, max_value=60, label="信号周期"),
    ]

    def init(self) -> None:
        self.trix, self.trma = self.I(TRIX, self.data.close, self.p["m1"], self.p["m2"])
        self.gold = self.I(CROSS, self.trix, self.trma)
        self.dead = self.I(CROSS, self.trma, self.trix)

    def next(self) -> None:
        i = self._bar_index
        if self.gold[i]:
            self.buy()
        elif self.dead[i] and self.position["size"] > 0:
            self.sell()


# ── EMV 简易波动 ──────────────────────────────────────────────────────────────


@register_strategy(
    name="emv",
    label="EMV 简易波动",
    description="EMV 上穿0轴买入，下穿0轴卖出。量价结合指标。",
)
class EmvStrategy(ParametrizedStrategy):
    params = [
        Param("n", int, default=14, min_value=2, max_value=30, label="EMV周期"),
    ]

    def init(self) -> None:
        self.emv, self._maemv = self.I(
            EMV, self.data.high, self.data.low, self.data.vol, self.p["n"]
        )

    def next(self) -> None:
        i = self._bar_index
        if self.emv[i] > 0 and self.position["size"] == 0:
            self.buy()
        elif self.emv[i] < 0 and self.position["size"] > 0:
            self.sell()


# ── DPO 区间震荡 ──────────────────────────────────────────────────────────────


@register_strategy(
    name="dpo",
    label="DPO 区间震荡",
    description="DPO 上穿信号线买入，下穿卖出。去除趋势的震荡指标。",
)
class DpoStrategy(ParametrizedStrategy):
    params = [
        Param("m1", int, default=20, min_value=5, max_value=60, label="DPO周期"),
    ]

    def init(self) -> None:
        self.dpo, self.madpo = self.I(DPO, self.data.close, self.p["m1"])
        self.gold = self.I(CROSS, self.dpo, self.madpo)
        self.dead = self.I(CROSS, self.madpo, self.dpo)

    def next(self) -> None:
        i = self._bar_index
        if self.gold[i]:
            self.buy()
        elif self.dead[i] and self.position["size"] > 0:
            self.sell()


# ── ATR 通道突破 ──────────────────────────────────────────────────────────────


@register_strategy(
    name="atr_breakout",
    label="ATR 通道突破",
    description="收盘价突破 均线+K×ATR 买入，跌破 均线-K×ATR 卖出。",
)
class AtrBreakoutStrategy(ParametrizedStrategy):
    params = [
        Param("n_ma", int, default=20, min_value=5, max_value=100, label="均线周期"),
        Param("n_atr", int, default=20, min_value=5, max_value=50, label="ATR周期"),
        Param("k", float, default=2.0, min_value=0.5, max_value=5.0, label="ATR倍数"),
    ]

    def init(self) -> None:
        self.ma = self.I(MA, self.data.close, self.p["n_ma"])
        self.atr = self.I(ATR, self.data.close, self.data.high, self.data.low, self.p["n_atr"])

    def next(self) -> None:
        i = self._bar_index
        close = self.data.close[0]
        upper = self.ma[i] + self.p["k"] * self.atr[i]
        lower = self.ma[i] - self.p["k"] * self.atr[i]
        if close >= upper and self.position["size"] == 0:
            self.buy()
        elif close <= lower and self.position["size"] > 0:
            self.sell()


# ── FSL 分水岭指标 ────────────────────────────────────────────────────────────


@register_strategy(
    name="fsl",
    label="FSL 分水岭",
    description="SWL 上穿 SWS 买入（多头占优），SWL 下穿 SWS 卖出（空头占优）。",
)
class FslStrategy(ParametrizedStrategy):
    """FSL 分水岭 SWL/SWS 金叉死叉。"""

    params = [
        Param(
            "capital",
            float,
            default=1e8,
            min_value=1e6,
            max_value=1e12,
            label="流通股本(股)",
        ),
    ]

    def init(self) -> None:
        self.swl, self.sws = self.I(FSL, self.data.close, self.data.vol, self.p["capital"])
        self.gold = self.I(CROSS, self.swl, self.sws)
        self.dead = self.I(CROSS, self.sws, self.swl)

    def next(self) -> None:
        i = self._bar_index
        if self.gold[i]:
            self.buy()
        elif self.dead[i] and self.position["size"] > 0:
            self.sell()


# ── RSI 背离策略 ──────────────────────────────────────────────────────────────


@register_strategy(
    name="rsi_divergence",
    label="RSI 背离",
    description="价格创新低但 RSI 未创新低（底背离）买入；价格创新高但 RSI 未创新高（顶背离）卖出。",
)
class RsiDivergenceStrategy(ParametrizedStrategy):
    """RSI 背离：底背离买入，顶背离卖出。"""

    params = [
        Param("n", int, default=14, min_value=5, max_value=30, label="RSI周期"),
        Param("lookback", int, default=20, min_value=10, max_value=60, label="回溯窗口"),
        Param("threshold", float, default=5.0, min_value=1.0, max_value=20.0, label="背离强度%"),
    ]

    def init(self) -> None:
        self.rsi = self.I(RSI, self.data.close, self.p["n"])

    def next(self) -> None:
        i = self._bar_index
        lb = self.p["lookback"]
        if i < lb + 1:
            return

        close_arr = self.data.close.raw
        rsi_arr = self.rsi

        # 找最近 lookback 内的局部极值点
        min_idx = int(np.argmin(close_arr[i - lb : i])) + (i - lb)
        max_idx = int(np.argmax(close_arr[i - lb : i])) + (i - lb)

        # 再往前看一个窗口
        prev_start = max(0, i - lb * 2)
        prev_window = close_arr[prev_start : i - lb]
        prev_rsi_window = rsi_arr[prev_start : i - lb]

        if len(prev_window) < 5:
            return

        prev_min_idx = int(np.argmin(prev_window)) + prev_start
        prev_max_idx = int(np.argmax(prev_window)) + prev_start

        # 底背离：当前低点 < 前低点，且当前 RSI 低点 > 前 RSI 低点
        buy_signal = False
        if (
            close_arr[min_idx] < close_arr[prev_min_idx]
            and rsi_arr[min_idx] > rsi_arr[prev_min_idx]
            and self.position["size"] == 0
        ):
            diff_pct = (
                abs(rsi_arr[min_idx] - rsi_arr[prev_min_idx])
                / max(abs(rsi_arr[prev_min_idx]), 1)
                * 100
            )
            if diff_pct >= self.p["threshold"]:
                buy_signal = True

        # 顶背离：当前高点 > 前高点，且当前 RSI 高点 < 前 RSI 高点
        sell_signal = False
        if (
            close_arr[max_idx] > close_arr[prev_max_idx]
            and rsi_arr[max_idx] < rsi_arr[prev_max_idx]
            and self.position["size"] > 0
        ):
            diff_pct = (
                abs(rsi_arr[max_idx] - rsi_arr[prev_max_idx])
                / max(abs(rsi_arr[prev_max_idx]), 1)
                * 100
            )
            if diff_pct >= self.p["threshold"]:
                sell_signal = True

        if buy_signal:
            self.buy()
        elif sell_signal:
            self.sell()


# ── SuperTrend 策略 ────────────────────────────────────────────────────────────


@register_strategy(
    name="supertrend",
    label="SuperTrend",
    description="基于 ATR 的动态趋势跟踪：价格跌破 SuperTrend 线买入，突破卖出（趋势反转信号）。",
)
class SuperTrendStrategy(ParametrizedStrategy):
    """SuperTrend 趋势跟踪：上轨跌破买入，下轨突破卖出。"""

    params = [
        Param("atr_period", int, default=10, min_value=5, max_value=30, label="ATR周期"),
        Param("multiplier", float, default=3.0, min_value=1.0, max_value=6.0, label="ATR倍数"),
        Param("trend_period", int, default=7, min_value=3, max_value=20, label="趋势平滑周期"),
    ]

    def init(self) -> None:
        close_arr = self.data.close.raw
        high_arr = self.data.high.raw
        low_arr = self.data.low.raw

        atr = self.I(ATR, close_arr, high_arr, low_arr, self.p["atr_period"])
        basic_upper = ((high_arr + low_arr) / 2) + self.p["multiplier"] * atr
        basic_lower = ((high_arr + low_arr) / 2) - self.p["multiplier"] * atr

        # SuperTrend 上轨/下轨平滑
        st_upper = np.full(len(close_arr), np.nan)
        st_lower = np.full(len(close_arr), np.nan)
        direction = np.ones(len(close_arr))

        warmup = max(self.p["trend_period"] * 2, 20)
        for idx in range(warmup, len(close_arr)):
            if idx == warmup:
                st_upper[idx] = basic_upper[idx]
                st_lower[idx] = basic_lower[idx]
                direction[idx] = 1
            else:
                st_upper[idx] = (
                    basic_upper[idx]
                    if basic_upper[idx] < st_upper[idx - 1]
                    else st_upper[idx - 1]
                )
                st_lower[idx] = (
                    basic_lower[idx]
                    if basic_lower[idx] > st_lower[idx - 1]
                    else st_lower[idx - 1]
                )
                if close_arr[idx] <= st_upper[idx - 1]:
                    direction[idx] = -1
                else:
                    direction[idx] = 1

        self._st_upper = st_upper
        self._st_lower = st_lower
        self._direction = direction

    def next(self) -> None:
        i = self._bar_index
        if i < 30 or np.isnan(self._st_upper[i]):
            return

        close = self.data.close[0]
        prev_dir = int(self._direction[i - 1]) if i > 0 else 1

        # 趋势由空转正（价格站上 SuperTrend 上轨）→ 买入
        if close > self._st_upper[i] and prev_dir <= 0 and self.position["size"] == 0:
            self.buy()
        # 趋势由正转空（价格跌破 SuperTrend 下轨）→ 卖出
        elif close < self._st_lower[i] and prev_dir >= 0 and self.position["size"] > 0:
            self.sell()


# ── OBV 趋势突破策略 ──────────────────────────────────────────────────────────


@register_strategy(
    name="obv_breakout",
    label="OBV 趋势突破",
    description="OBV 均线突破买入，跌破卖出；配合价格确认，过滤假信号。",
)
class ObvBreakoutStrategy(ParametrizedStrategy):
    """OBV 趋势突破：EMA(OBV) 上穿价格均线买入，下穿卖出。"""

    params = [
        Param("n_obv", int, default=14, min_value=5, max_value=50, label="OBV周期"),
        Param("n_price", int, default=20, min_value=5, max_value=60, label="价格均线周期"),
        Param("n_signal", int, default=10, min_value=5, max_value=30, label="信号确认周期"),
    ]

    def init(self) -> None:
        self.obv = self.I(OBV, self.data.close, self.data.vol)
        obv_ma = self.I(EMA, self.obv, self.p["n_obv"])
        price_ma = self.I(MA, self.data.close, self.p["n_price"])
        self.obv_gold = self.I(CROSS, obv_ma, price_ma)
        self.obv_dead = self.I(CROSS, price_ma, obv_ma)
        self.price_above_ma = self.data.close.raw > price_ma

    def next(self) -> None:
        i = self._bar_index
        if i < self.p["n_signal"]:
            return

        # OBV 金叉 + 价格在均线上方 → 买入
        if self.obv_gold[i] and self.price_above_ma[i] and self.position["size"] == 0:
            self.buy()
        # OBV 死叉 + 价格在均线下方 → 卖出
        elif self.obv_dead[i] and not self.price_above_ma[i] and self.position["size"] > 0:
            self.sell()
        # 价格跌破均线（紧急止损）
        elif not self.price_above_ma[i] and self.position["size"] > 0:
            price_below = self.data.close.raw < MA(self.data.close.raw, self.p["n_price"])
            if COUNT(price_below, self.p["n_signal"]) >= self.p["n_signal"]:
                self.sell()


# ── ADX 趋势确认策略 ────────────────────────────────────────────────────────────


@register_strategy(
    name="adx_trend",
    label="ADX 趋势确认",
    description="ADX > 阈值确认趋势强度，PDI>MDI 做多，PDI<MDI 做空。适合趋势明显的股票。",
)
class AdxTrendStrategy(ParametrizedStrategy):
    """ADX 趋势确认：强趋势时交易，避免震荡市亏损。"""

    params = [
        Param("adx_period", int, default=14, min_value=5, max_value=30, label="ADX周期"),
        Param("adx_threshold", float, default=25.0, min_value=15.0, max_value=50.0, label="ADX阈值"),
        Param("pdi_period", int, default=14, min_value=5, max_value=30, label="PDI周期"),
    ]

    def init(self) -> None:
        close = self.data.close.raw
        high = self.data.high.raw
        low = self.data.low.raw

        self.pdi, self.mdi, self.adx, self.adxr = self.I(
            DMI, close, high, low, self.p["pdi_period"], self.p["adx_period"]
        )
        self.trend_up = self.pdi > self.mdi
        self.strong_trend = self.adx > self.p["adx_threshold"]

    def next(self) -> None:
        i = self._bar_index
        if i < 30:
            return

        # 强趋势 + PDI > MDI → 买入
        if (
            self.strong_trend[i]
            and self.trend_up[i]
            and self.position["size"] == 0
        ):
            self.buy()
        # 强趋势 + PDI < MDI → 卖出
        elif (
            self.strong_trend[i]
            and not self.trend_up[i]
            and self.position["size"] > 0
        ):
            self.sell()


# ── 成交量突破策略 ──────────────────────────────────────────────────────────────


@register_strategy(
    name="volume_breakout",
    label="成交量突破",
    description="价格突破N日高点且成交量放大时买入，跌破N日低点且放量时卖出。",
)
class VolumeBreakoutStrategy(ParametrizedStrategy):
    """成交量突破：价涨量增买入，价跌量增卖出。"""

    params = [
        Param("lookback", int, default=20, min_value=5, max_value=60, label="突破窗口"),
        Param("vol_multiplier", float, default=1.5, min_value=1.0, max_value=3.0, label="放量倍数"),
    ]

    def init(self) -> None:
        self.high_n = self.I(HHV, self.data.high, self.p["lookback"])
        self.low_n = self.I(LLV, self.data.low, self.p["lookback"])
        self.vol_ma = self.I(MA, self.data.vol, self.p["lookback"])
        self.vol_ratio = self.data.vol / self.vol_ma

    def next(self) -> None:
        i = self._bar_index
        if i < self.p["lookback"]:
            return

        close = self.data.close[0]
        high_n = self.high_n[i]
        low_n = self.low_n[i]
        vol_ratio = self.vol_ratio[i]

        # 突破高点 + 放量 → 买入
        if close >= high_n and vol_ratio >= self.p["vol_multiplier"] and self.position["size"] == 0:
            self.buy()
        # 跌破低点 + 放量 → 卖出
        elif close <= low_n and vol_ratio >= self.p["vol_multiplier"] and self.position["size"] > 0:
            self.sell()


# ── RSI + MACD 共振策略 ────────────────────────────────────────────────────────


@register_strategy(
    name="rsi_macd_combo",
    label="RSI+MACD 共振",
    description="RSI 超卖 + MACD 金叉共振买入；RSI 超买 + MACD 死叉共振卖出。",
)
class RsiMacdComboStrategy(ParametrizedStrategy):
    """RSI+MACD 共振：两个指标同时确认才交易，减少假信号。"""

    params = [
        Param("rsi_period", int, default=14, min_value=5, max_value=30, label="RSI周期"),
        Param("rsi_oversold", float, default=30.0, min_value=10.0, max_value=40.0, label="RSI超卖线"),
        Param("rsi_overbought", float, default=70.0, min_value=60.0, max_value=90.0, label="RSI超买线"),
        Param("macd_fast", int, default=12, min_value=6, max_value=20, label="MACD快线"),
        Param("macd_slow", int, default=26, min_value=12, max_value=50, label="MACD慢线"),
        Param("macd_signal", int, default=9, min_value=5, max_value=15, label="MACD信号线"),
    ]

    def init(self) -> None:
        close = self.data.close
        self.rsi = self.I(RSI, close, self.p["rsi_period"])
        self.dif, self.dea, self.hist = self.I(
            MACD, close, self.p["macd_fast"], self.p["macd_slow"], self.p["macd_signal"]
        )
        self.macd_gold = CROSS(self.dif, self.dea)
        self.macd_dead = CROSS(self.dea, self.dif)
        self.rsi_oversold = self.rsi < self.p["rsi_oversold"]
        self.rsi_overbought = self.rsi > self.p["rsi_overbought"]

    def next(self) -> None:
        i = self._bar_index
        if i < 50:
            return

        # RSI 超卖 + MACD 金叉 → 买入（双重确认）
        if (
            self.rsi_oversold[i]
            and self.macd_gold[i]
            and self.position["size"] == 0
        ):
            self.buy()
        # RSI 超买 + MACD 死叉 → 卖出（双重确认）
        elif (
            self.rsi_overbought[i]
            and self.macd_dead[i]
            and self.position["size"] > 0
        ):
            self.sell()
