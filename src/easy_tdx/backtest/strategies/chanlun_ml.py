"""缠论**多级别联立**策略：本级别买点进 → 次级别卖点出。

## 为什么必须有这个策略
此前所有缠论回测都是**同级别配对**（本级别买点进、本级别卖点出）。
而缠论操作法的核心是**级别配合**（区间套思想的落地）：

    本级别（日线）定方向、找买点 → 次级别（30min）找**精确**卖点

典型如用户所问的「本级别 3买 买入，次级别 一卖 卖出」：
日线 3买 说明中枢突破回踩成立、趋势启动；但**何时离场**要下钻到 30min，
用次级别的 1卖（背驰）抓住那个更精确的转折点，而不是等日线卖点（往往已回吐大半）。

这类组合**此前一分钟都没测过**（仓库只有日线数据，且所有策略都是单周期）。

## 设计
- 主周期 df（日线）：产生**入场**信号（`entry_types` 过滤）
- 次周期 df（30min）：产生**出场**信号（`exit_types` 过滤）
- 时间对齐：日线第 i 根 → 次级别中 datetime 落在 (day[i-1], day[i]] 的所有 bar
- 兜底：次级别卖点迟迟不出现时，用本级别卖点或 `max_hold_bars` 强制离场，
  避免"永远不出场"（这类 bug 会让回测结果虚高，必须防）

## ⚠️ 防未来函数
次级别信号必须**只用截至当前日线 bar 时刻**的数据。
实现上：次级别信号预先算好（全量算一次会用到未来 —— 见下方说明），
        ...
        实际上本策略对次级别也走 ChanlunAnalyser 全量分析，但**消费时**只取
        「信号 bar 的 datetime <= 当前日线 bar 的 datetime」的信号，
        因此不会有未来函数。预计算只是提前算出来，消费仍按时间推进。
        这一点与 ChanlunPairStrategy 的 `_signal_ptr` 推进逻辑同构。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from easy_tdx.backtest.strategies.registry import (
    Param,
    ParametrizedStrategy,
    register_strategy,
)
from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig

_BUY = ("1buy", "2buy", "2buy_s", "3buy")
_SELL = ("1sell", "2sell", "2sell_s", "3sell")


@register_strategy(
    name="chanlun_ml",
    label="缠论多级别联立",
    description="本级别（日线）买点入场，次级别（30min）卖点出场，实现缠论级别配合操作法。",
)
class ChanlunMLStrategy(ParametrizedStrategy):
    """多级别联立：本级别买点进 → 次级别卖点出。"""

    params = (
        Param("entry_types", "csv", "1buy,2buy,3buy",
              "本级别入场买点类型（逗号分隔）"),
        Param("exit_types", "csv", "1sell,2sell,3sell",
              "次级别出场卖点类型（逗号分隔）"),
        Param("fallback_exit_types", "csv", "1sell",
              "兜底：本级别出现这些卖点时强制离场（防次级别迟迟不出信号）"),
        Param("max_hold_bars", "int", 60,
              "本级别最多持有多少根后强制离场（0=不限）"),
        Param("min_confidence", "float", 0.0, "信号最低置信度"),
        Param("use_3buy", "bool", True, "是否使用 3buy 入场"),
        Param("use_3sell", "bool", True, "是否使用 3sell 出场"),
        Param("exit_stop_loss_pct", "float", 0.0, "熔断止损（0=关闭）"),
        Param("bi_type", "csv", "new", "笔口径"),
        Param("sub_entry_scope", "csv", "none",
              "次级别入场过滤：none=不过滤；nested=要求本级别买点被次级别区间套确认"),
        Param("sub_exit_mode", "csv", "first",
              "次级别出场口径：first=任一卖点即出；nested=仅区间套确认的卖点"),
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # 主/次级别数据由外部注入（引擎只喂主周期，次级别必须显式给）
        self.main_df: pd.DataFrame | None = None
        self.sub_df: pd.DataFrame | None = None
        self._dt_arr: list[pd.Timestamp] = []
        self._sub_signals: list[tuple[pd.Timestamp, str, float]] = []
        self._main_signals: list[tuple[int, str, float]] = []
        self._sub_ptr = 0
        self._main_ptr = 0
        self._in_position = False
        # 区间套确认表：signal 序号 → 是否被低级别确认（见 set_precomputed）
        self._sub_nested: dict[int, bool] = {}
        self._main_nested: dict[int, bool] = {}
        self._precomputed = False
        self._entry_price = 0.0
        self._entry_bar = 0
        self._entry_type = ""
        self._trade_log: list[dict[str, Any]] = []
        self._pair_log: list[dict[str, Any]] = []
        self._bar_index = 0

    # ── 注入次级别数据 ──────────────────────────────────────────────
    def set_data(self, main_df: pd.DataFrame, sub_df: pd.DataFrame | None) -> None:
        """注入主周期（日线）与次级别（30min）K 线。须在引擎 run 之前调用。"""
        self.main_df = main_df
        self.sub_df = sub_df
        if main_df is not None:
            d = pd.to_datetime(pd.Series(main_df["datetime"]).reset_index(drop=True))
            # ⚠️ 关键：日线时间戳是当日 **00:00**，而次级别 30min 是当日 10:00~15:00。
            #    若直接用日线时间戳做 `sub_dt > now` 比较，当日所有次级别 bar 都
            #    "晚于"日线 bar ⇒ 当日收盘前出现的次级别卖点**要等到下一根日线**
            #    才被消费 ⇒ 出场**系统性延迟一根日线**。
            #
            #    ⚠️ 更正（2026-10-10 实测，原注释写错了）：
            #    原注释称"次级别卖点**永远无法触发**，全部退化成 max_hold 兜底"
            #    —— **已证伪**。30 只实测：坏版本出场分布 {1sell:104, max_hold:10}
            #    与好版本**完全一致**，104 笔差异全部是 exit_bar **恰好延迟 1 根**，
            #    没有任何一笔退化成 max_hold。真实影响是**晚一天卖出**
            #    （配对差 −2.37%，t=−2.15），不是"功能失效"。
            #    当时之所以看到满屏 max_hold，是**另一个**（更早期的）bug 造成的，
            #    不是这一处对齐。改注释不能只凭印象，见 scripts/verify_ml_sub_exit_fires.py。
            #
            #    修正：把日线 bar 对齐到当日 **收盘时刻**（23:59），
            #    表示"该根日线走完"后才消费其间的次级别信号 —— 这样同一交易日内
            #    出现的次级别卖点能在当日收盘就被消费，不拖延到次日。
            self._dt_arr = list(d + pd.Timedelta(hours=23, minutes=59))

    # ── 预计算结构注入（性能：次级别分析很贵，跨方案复用）─────────────
    def set_precomputed(
        self,
        main_signals: list[tuple[int, str, float]] | None = None,
        sub_signals: list[tuple[pd.Timestamp, str, float]] | None = None,
        sub_nested: dict[int, bool] | None = None,
        main_nested: dict[int, bool] | None = None,
    ) -> None:
        """注入**预先算好**的缠论信号，跳过 ``init()`` 里的全量分析。

        为什么需要：30min 序列每只约 4000 根，``ChanlunAnalyser`` 单只要 20s
        （实测 O(n²)）。一个方案矩阵有 6~10 个方案，若每个方案各算一次，
        285 只 × 20s × 10 = 16 小时，全量根本跑不动。而所有方案共用**同一份**
        次级别分析结果 —— 差别只在"消费哪些信号"，故只需算一次。

        ⚠️ 语义不变：注入的信号与 ``init()`` 自算的**逐位一致**（由
        ``scripts/audit_chanlun_full_theory.py --check-cache`` 断言）。
        """
        if main_signals is not None:
            self._main_signals = sorted(main_signals, key=lambda x: x[0])
        if sub_signals is not None:
            self._sub_signals = sorted(sub_signals, key=lambda x: x[0])
        if sub_nested is not None:
            self._sub_nested = dict(sub_nested)
        if main_nested is not None:
            self._main_nested = dict(main_nested)
        self._precomputed = True

    def _parse_types(self, raw: Any) -> tuple[str, ...]:
        if isinstance(raw, (list, tuple)):
            return tuple(str(x) for x in raw)
        s = str(raw or "")
        return tuple(x.strip() for x in s.split(",") if x.strip())

    def init(self) -> None:
        if self._precomputed and (self._main_signals or self._sub_signals):
            return  # 已注入预计算结果，跳过昂贵的全量分析
        df = self.main_df if self.main_df is not None else None
        if df is None:
            return
        cfg = ChanlunConfig(bi_type=(self._parse_types(self.p["bi_type"]) or ["new"])[0])

        # 主周期信号（入场 + 兜底出场）
        res = ChanlunAnalyser(code="ML", frequency="daily", config=cfg).process_klines(df)
        for m in res.mmds:
            t = str(m.mmd_type.value)
            if t in _BUY or t in _SELL:
                bar = int(m.bi.end.bar_index) if m.bi else -1
                if bar >= 0:
                    self._main_signals.append((bar, t, float(getattr(m, "confidence", 0.0))))
        self._main_signals.sort(key=lambda x: x[0])

        # 次级别信号（出场）
        if self.sub_df is not None and not self.sub_df.empty:
            sub = self.sub_df.copy()
            sub["datetime"] = pd.to_datetime(sub["datetime"])
            sres = ChanlunAnalyser(code="ML-SUB", frequency="30min", config=cfg).process_klines(sub)
            dts = sub["datetime"].reset_index(drop=True)
            for m in sres.mmds:
                t = str(m.mmd_type.value)
                if t in _SELL:
                    bar = int(m.bi.end.bar_index) if m.bi else -1
                    if 0 <= bar < len(dts):
                        self._sub_signals.append((dts.iloc[bar], t,
                                                  float(getattr(m, "confidence", 0.0))))
            self._sub_signals.sort(key=lambda x: x[0])

    def _current_dt(self) -> pd.Timestamp:
        """当前主周期 bar 的时间（用于次级别信号的时间对齐）。"""
        if self._bar_index < len(self._dt_arr):
            return self._dt_arr[self._bar_index]
        return self._dt_arr[-1] if self._dt_arr else pd.Timestamp.min

    def _enter(self, price: float, sig: str, conf: float) -> None:
        self._in_position = True
        self._entry_price = price
        self._entry_bar = self._bar_index
        self._entry_type = sig
        self.buy(size=0, tag=sig)
        self._trade_log.append({"bar_index": self._bar_index, "direction": "BUY",
                                "price": price, "signal_type": sig, "confidence": conf})

    def _exit(self, price: float, sig: str) -> None:
        pnl = (price / self._entry_price - 1) if self._entry_price else 0.0
        self._pair_log.append({
            "entry_type": self._entry_type, "exit_type": sig,
            "entry_bar": self._entry_bar, "exit_bar": self._bar_index,
            "holding_bars": self._bar_index - self._entry_bar,
            "entry_price": self._entry_price, "exit_price": price,
            "pnl_pct": pnl * 100,
        })
        self._trade_log.append({"bar_index": self._bar_index, "direction": "SELL",
                                "price": price, "signal_type": sig})
        self.sell(size=0, tag=sig)
        self._in_position = False

    def next(self) -> None:
        price = float(self.data.close[0])
        now = self._current_dt()
        minconf = float(self.p.get("min_confidence", 0.0) or 0.0)
        entry_types = self._parse_types(self.p["entry_types"])
        exit_types = self._parse_types(self.p["exit_types"])
        fb_types = self._parse_types(self.p["fallback_exit_types"])
        max_hold = int(self.p.get("max_hold_bars", 0) or 0)
        # 区间套口径（默认 none/first = 与旧行为逐位一致，见 PIT 回归）
        sub_entry_scope = (self._parse_types(self.p.get("sub_entry_scope", "none"))
                           or ["none"])[0]
        sub_exit_mode = (self._parse_types(self.p.get("sub_exit_mode", "first"))
                         or ["first"])[0]

        # 熔断止损
        sl = float(self.p.get("exit_stop_loss_pct", 0.0) or 0.0)
        if self._in_position and sl > 0 and self._entry_price > 0:
            if price <= self._entry_price * (1 - sl):
                self._exit(price, "fuse_stop_loss")
                return

        # 1) 次级别卖点出场（只消费 datetime <= 当前日线时间的信号）
        while self._sub_ptr < len(self._sub_signals):
            dt, t, conf = self._sub_signals[self._sub_ptr]
            if dt > now:
                break
            sidx = self._sub_ptr
            self._sub_ptr += 1
            if t not in exit_types or conf < minconf:
                continue
            if t == "3sell" and not self.p["use_3sell"]:
                continue
            if sub_exit_mode == "nested" and not self._sub_nested.get(sidx, False):
                continue
            if self._in_position:
                self._exit(price, t)
                return

        # 2) 主周期信号：入场 + 兜底出场
        while self._main_ptr < len(self._main_signals):
            bar, t, conf = self._main_signals[self._main_ptr]
            if bar > self._bar_index:
                break
            midx = self._main_ptr
            self._main_ptr += 1
            if conf < minconf:
                continue
            if t in _BUY:
                if t == "3buy" and not self.p["use_3buy"]:
                    continue
                if t in entry_types and not self._in_position:
                    if sub_entry_scope == "nested" and not self._main_nested.get(midx, False):
                        continue
                    self._enter(price, t, conf)
            elif t in fb_types and self._in_position:
                self._exit(price, f"main_{t}")
                return

        # 3) 超时兜底（防"次级别永远不出信号"导致虚高）
        if self._in_position and max_hold > 0:
            if self._bar_index - self._entry_bar >= max_hold:
                self._exit(price, "max_hold")

        self._bar_index += 1

    @property
    def trade_log(self) -> list[dict[str, Any]]:
        return self._trade_log

    @property
    def pair_log(self) -> list[dict[str, Any]]:
        return self._pair_log
