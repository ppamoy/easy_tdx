"""缠论买卖点配对策略（同一级别买卖点配对出场）。

与 :mod:`easy_tdx.backtest.strategies.chanlun` 的区别：出场**只认同级别卖点**。

背景
----
``ChanlunStrategy`` 虽然也是信号驱动（只有 1sell/2sell/3sell 才平仓），但它默认
开启百分比止损/止盈（``stop_loss_pct=0.08`` / ``take_profit_pct=0.25``），且这两个
检查在消费信号队列**之前**执行并 ``return``——于是仓位经常在同级别卖点出现之前
就被截断，"日线买入、日线卖点卖出"这条缠论最基本的交易规则并没有真正跑出来。

本策略把出场口径改回缠论原文：

- 入场：同级别买点（1buy / 2buy / 类2buy / 3buy，按置信度与开关过滤）
- 出场：同级别卖点（1sell / 2sell / 类2sell / 3sell，**任一出现即平仓**）
- 不设百分比止损/止盈：``exit_stop_loss_pct`` 默认 0.0（关闭），仅在显式配置时
  作为极端熔断使用，且会记录在交易原因里与「卖点出场」区分开

这样"日线买入 → 日线出现卖点（不管是 1/2/3 卖还是类 2 卖）→ 卖出"这一次完整的
级别内交易才会作为一笔被统计出来，回测结论才对得上缠论的操作定义。

配对记账
--------
每笔交易记录 ``entry_type`` / ``exit_type``，供「哪种卖点出场最赚」的分组统计：

- ``trade_log`` 每条含 ``bar_index/direction/price/entry_type/exit_type/confidence``
- ``pair_log`` 逐笔配对：买入与卖出的信号类型、价格、持有 bar 数、收益

参数与 ``ChanlunStrategy`` 保持一致的命名（``analysis_level`` / ``min_confidence`` /
``use_2s_signals`` 等），便于两个策略直接对比。
"""

from __future__ import annotations

from typing import Any

import pandas as pd  # noqa: F401  # 类型注解引用（"pd.DataFrame"）

from easy_tdx.backtest.strategies.registry import (
    Param,
    ParametrizedStrategy,
    register_strategy,
)

# 买点 → 入场；卖点 → 出场（同一级别，任一出现即执行）
_BUY_TYPES = ("1buy", "2buy", "2buy_s", "3buy")
_SELL_TYPES = ("1sell", "2sell", "2sell_s", "3sell")


@register_strategy(
    name="chanlun_pair",
    label="缠论买卖点配对",
    description="同级别买卖点配对：买点入场、同级别任一卖点（1/2/3卖、类2卖）出场，不带百分比止损止盈。用于验证「日线买、日线卖点卖」的级别内交易表现。",
)
class ChanlunPairStrategy(ParametrizedStrategy):
    """缠论买卖点配对策略（同级别卖点出场）。

    `analysis_level` 选择买卖点信号来源，语义与 :class:`ChanlunStrategy` 一致：
    - 0（默认）= 笔级别（``result.mmds``）；
    - N>=1 = 多级别递归第 N 级信号（``result.recursive_levels[N-1].mmds``）。

    关键差异：**出场只认同级别卖点**，且默认没有任何百分比止损/止盈。
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
            label="仓位比例(1=全仓)",
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
        Param(
            "exit_stop_loss_pct",
            float,
            default=0.0,
            min_value=0.0,
            max_value=0.5,
            label="熔断止损(0=关闭,仅极端保护)",
        ),
        Param(
            "exit_trailing_stop_pct",
            float,
            default=0.0,
            min_value=0.0,
            max_value=0.5,
            label="移动止盈(0=关闭,从最高点回撤X%出场)",
        ),
        Param(
            "allow_pyramid",
            bool,
            default=False,
            label="持仓中遇买点加仓(默认否)",
        ),
        Param(
            "require_qujiantao",
            bool,
            default=False,
            label="仅交易区间套确认信号",
        ),
        Param(
            "qujiantao_low_level",
            str,
            default="MIN_30",
            label="区间套低级别周期",
        ),
        Param(
            "qujiantao_strict",
            bool,
            default=False,
            label="区间套严格模式(算不出则过滤)",
        ),
        Param(
            "qujiantao_seed",
            int,
            default=20240101,
            label="低级别合成随机种子(保证可复现)",
        ),
        Param(
            "lookahead_guard",
            bool,
            default=True,
            label="前视守卫(信号需经确认期复核)",
        ),
        Param(
            "confirm_lag",
            int,
            default=3,
            label="信号确认延迟根数",
        ),
        Param(
            "guard_window",
            int,
            default=400,
            label="守卫复核滚动窗口(根)",
        ),
        Param(
            "hold_in_higher_uptrend",
            bool,
            default=False,
            label="线段趋势向上时持有过2卖3卖(级别联用)",
        ),
        Param(
            "zs_from_xd",
            bool,
            default=False,
            label="中枢由线段构成(True=原文第91课,False=笔构中枢)",
        ),
        Param(
            "use_seg_mmd",
            bool,
            default=False,
            label="线段级别买卖点(参考chan.py,在线段末端检测)",
        ),
        Param(
            "seg_mmd_hybrid",
            bool,
            default=False,
            label="混合模式(T1线段级别+T2T3笔级别)",
        ),
        Param(
            "seg_divergence_rate",
            float,
            default=1.5,
            label="线段级别背驰率阈值",
        ),
        Param(
            "bs1_peak",
            bool,
            default=False,
            label="一类买卖点要求创新极值",
        ),
        Param(
            "bsp2_follow_1",
            bool,
            default=False,
            label="二类买卖点必须跟随一类",
        ),
        Param(
            "bsp3_follow_1",
            bool,
            default=False,
            label="三类买卖点必须跟随一类",
        ),
        Param(
            "max_bs2_rate",
            float,
            default=1.0,
            label="二类买卖点最大回踩率",
        ),
    ]

    def init(self) -> None:
        """初始化：预计算缠论并构建精确信号队列。"""
        import pandas as pd

        from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

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

        # 日期→bar index 映射（笔结束日期 → 精确 bar）
        self._date_to_bar: dict[str, int] = {}
        for i, row in df.iterrows():
            dt_str = str(row["datetime"])[:10]
            self._date_to_bar[dt_str] = i

        analysis_level = max(0, int(self.p.get("analysis_level") or 0))
        config = ChanlunConfig(
            bi_type=self.p["bi_type"],
            zs_min_lines=self.p["zs_min_lines"],
            macd_fast=self.p["macd_fast"],
            macd_slow=self.p["macd_slow"],
            macd_signal=self.p["macd_signal"],
            recursion_depth=max(1, analysis_level),
            zs_from_xd=bool(self.p.get("zs_from_xd", False)),
            use_seg_mmd=bool(self.p.get("use_seg_mmd", False)),
            seg_mmd_hybrid=bool(self.p.get("seg_mmd_hybrid", False)),
            seg_divergence_rate=float(self.p.get("seg_divergence_rate", 1.5)),
            bs1_peak=bool(self.p.get("bs1_peak", False)),
            bsp2_follow_1=bool(self.p.get("bsp2_follow_1", False)),
            bsp3_follow_1=bool(self.p.get("bsp3_follow_1", False)),
            max_bs2_rate=float(self.p.get("max_bs2_rate", 1.0)),
        )
        analyser = ChanlunAnalyser(code="TEST", frequency="daily", config=config)
        result = analyser.process_klines(df)

        if analysis_level <= 0:
            src_mmds = result.mmds
            done_bis: list[Any] = [b for b in result.bis if b.is_done()]
        else:
            rec_idx = analysis_level - 1
            if rec_idx >= len(result.recursive_levels):
                src_mmds = []
                done_bis = []
            else:
                src_mmds = result.recursive_levels[rec_idx].mmds
                level_lines = (
                    result.xds if rec_idx == 0 else result.recursive_levels[rec_idx - 1].xds
                )
                done_bis = [ln for ln in level_lines if ln.is_done()]

        self._done_bis = done_bis

        # ── 级别联用：线段级趋势方向 ──────────────────────────────────
        # 策略在笔级买卖点交易，用线段(更高一级)的趋势方向做"是否该持有了结"
        # 的过滤。当线段趋势仍向上时，2卖/3卖只是回调，不立即了结，只对
        # 1卖（背驰卖点=趋势反转）无条件离场。趋势反转后(线段向下)则任何卖点
        # 都离场。
        self._higher_trend_lookup = self._build_trend_lookup(result)

        # ── 真跨周期区间套 ──────────────────────────────────────────────
        # 原文含义：大级别的背驰段，在小级别上也被确认为背驰。
        # 策略只拿到单一周期 df，因此用 level_synth 合成近似低级别数据，
        # 再走 compute_qujiantao_cross_period（真区间套语义）逐 MMD 打标签。
        # 仅在需要时合成（否则白白跑一遍低级别缠论，极慢）。
        if bool(self.p.get("require_qujiantao", False)):
            self._attach_cross_period_qujiantao(df, src_mmds)
        else:
            for mmd in src_mmds:
                try:
                    mmd._qujiantao = None
                except Exception:  # noqa: BLE001
                    pass

        # 信号队列：(bar_idx, mmd_type, confidence, nested)
        self._chanlun_signals: list[tuple[int, str, float, bool | None]] = []
        seen_bi: set[int] = set()
        min_conf = self.p["min_confidence"]
        use_2s = self.p["use_2s_signals"]
        require_nested = self.p["require_qujiantao"]
        strict_nested = bool(self.p.get("qujiantao_strict", False))

        for mmd in sorted(src_mmds, key=lambda m: m.bi.index if m.bi else 0):
            if mmd.bi is None:
                continue
            bi_idx = mmd.bi.index
            if bi_idx in seen_bi:
                continue
            seen_bi.add(bi_idx)
            if bi_idx >= len(self._done_bis):
                continue

            conf = mmd.confidence
            if conf < min_conf:
                continue
            if not use_2s and mmd.mmd_type.name in ("BUY_2S", "SELL_2S"):
                continue

            bar_idx = self._bi_end_bar_idx(mmd.bi)
            if bar_idx < 0:
                continue

            # 区间套确认标签（真跨周期区间套；None = 无法计算/无低级别数据）
            nested = self._qujiantao_nested(mmd)
            if require_nested and not self._nested_pass(nested, strict_nested):
                continue

            self._chanlun_signals.append((bar_idx, mmd.mmd_type.value, conf, nested))

        # ── 前视守卫 ────────────────────────────────────────────────────
        # 缠论的笔/分型/中枢天然需要后续 K 线确认，一次性全量分析会让"第 b 根的
        # 信号"实际用到了 b 之后的数据（实测：同一根 bar 的信号类型会随后续数据
        # 变化，早期信号甚至在任何前缀上都复现不出来）。
        # 守卫做法：候选信号 (b, type) 必须能在 df[:b+lag+1] 上被复现，
        # 且**延后到第 b+lag 根才发出**——那时它才是真正可知的信息。
        # 复现不出来的（全量分析的伪影）直接丢弃。
        self._apply_lookahead_guard(df)

        # 信号追踪（供引擎 signal_accuracy 的 chanlun_by_type 分组）
        self._signal_traces: dict[str, list[dict[str, Any]]] = {}
        for mmd in src_mmds:
            if mmd.bi is None:
                continue
            bar_idx = self._bi_end_bar_idx(mmd.bi)
            if bar_idx >= 0:
                self._signal_traces.setdefault(mmd.mmd_type.value, []).append(
                    {"bar_index": bar_idx, "confidence": mmd.confidence}
                )

        # 状态
        self._signal_ptr = 0
        self._entry_price: float = 0.0
        self._entry_type: str = ""
        self._entry_bar: int = 0
        self._entry_conf: float = 0.0
        self._entry_nested: bool | None = None
        self._in_position = False
        self._highest_since_entry: float = 0.0
        self._trade_log: list[dict[str, Any]] = []
        self._pair_log: list[dict[str, Any]] = []

    @staticmethod
    def _build_trend_lookup(result: Any) -> list[tuple[int, str]]:
        """从线段构建"每根 bar 的趋势方向"查找表。

        返回 [(bar_index, 'up'/'down')]，按 bar_index 排序。
        对于线段之间的空隙，沿用上一段的方向。

        注意：线段方向有轻微前视（线段终点需后续K线确认），但趋势方向比
        信号时间点稳定得多，作为"是否持有"的粗粒度过滤是可以接受的。
        """
        xds = getattr(result, "xds", None) or []
        if not xds:
            return []

        def _bar_idx(fx: Any) -> int:
            for attr in ("bar_index", "k_index"):
                v = getattr(fx, attr, None)
                if v is not None:
                    return int(v)
            k = getattr(fx, "k", None)
            if k is not None:
                return int(getattr(k, "k_index", getattr(k, "index", 0)))
            return 0

        segments: list[tuple[int, int, str]] = []
        for xd in xds:
            try:
                s = _bar_idx(getattr(xd, "start", None))
                e = _bar_idx(getattr(xd, "end", None))
                d = getattr(
                    getattr(xd, "direction", None), "value", str(getattr(xd, "direction", ""))
                )
                segments.append((s, e, str(d).lower()))
            except Exception:  # noqa: BLE001
                continue
        if not segments:
            return []

        segments.sort(key=lambda x: x[0])
        out: list[tuple[int, str]] = []
        cur_dir = segments[0][2]
        for s, e, d in segments:
            cur_dir = d  # 进入该线段后方向更新
            out.append((s, cur_dir))
        return out

    def _higher_trend_at(self, bar_idx: int) -> str | None:
        """返回 bar_idx 处的线段级趋势方向 ('up'/'down')，无数据返回 None。"""
        lk = self._higher_trend_lookup
        if not lk:
            return None
        dir_ = None
        for b, d in lk:
            if b > bar_idx:
                break
            dir_ = d
        return dir_

    def _apply_lookahead_guard(self, df: pd.DataFrame) -> None:
        """把候选信号逐个用"只含历史的前缀"复核，并延后到确认点发出。

        对每个候选 ``(b, type)``：在 ``df[: b + lag + 1]`` 上重新跑一遍缠论，
        若仍能得到同一个 ``(b, type)``，说明它不依赖 b 之后的数据，予以保留并把
        生效 bar 改为 ``b + lag``；否则判为全量分析的伪影，丢弃。

        性能优化：不用全长前缀（O(n) 每次），而是用以 b+lag 为右端的**滚动窗口**
        （默认 400 根）。笔/中枢/背驰在 bar b 附近只需要局部上下文即可确定，
        400 根足以覆盖。窗口内的 bar 序号需映射回原 df 序号。
        """
        if not bool(self.p.get("lookahead_guard", True)):
            return
        lag = max(0, int(self.p.get("confirm_lag", 3) or 0))
        window = max(60, int(self.p.get("guard_window", 400) or 400))
        candidates = self._chanlun_signals
        if not candidates:
            return

        n = len(df)
        kept: list[tuple[int, str, float, bool | None]] = []
        seen: set[tuple[int, str]] = set()
        cache: dict[int, set[tuple[int, str]]] = {}

        from easy_tdx.backtest.strategies.registry import get_registry

        entry = get_registry().get("chanlun_pair")

        for bar_idx, mmd_type, conf, nested in candidates:
            key = (bar_idx, mmd_type)
            if key in seen:
                continue
            seen.add(key)

            # 确认前缀必须严格短于全量数据——否则 prefix==full，复核变成
            # 自证（恒真），无法排除前视。数据不足时丢弃该信号。
            k = bar_idx + lag + 1
            if k <= 0 or k >= n:
                continue
            # 滚动窗口：左端 = max(0, k - window)，右端 = k
            lo = max(0, k - window)
            if k not in cache:
                sub = df.iloc[lo:k].reset_index(drop=True)
                offset = lo  # sub 内 bar_idx + offset = 原 df bar_idx
                try:
                    # 子分析必须关闭守卫，否则递归；也关闭区间套合成以省时间
                    sub_strat = entry.build(
                        {
                            **dict(self.p),
                            "lookahead_guard": False,
                            "require_qujiantao": False,
                        }
                    )
                    sub_strat._bind_data(sub)
                    sub_strat._call_init()
                    sigs = getattr(sub_strat, "_chanlun_signals", [])
                    cache[k] = {(b + offset, t) for b, t, _c, _n in sigs}
                except Exception:  # noqa: BLE001
                    cache[k] = set()
                    continue

            if key in cache[k]:
                # 延后到确认点：第 bar_idx+lag 根才真正可知
                kept.append((min(bar_idx + lag, n - 1), mmd_type, conf, nested))

        self._chanlun_signals = sorted(kept, key=lambda x: x[0])

    def _attach_cross_period_qujiantao(self, df: pd.DataFrame, src_mmds: list[Any]) -> None:
        """给每个高级别 MMD 打上区间套标签（写入 mmd._qujiantao）。

        **V731 口径更正**：此前这里自称打「**真**跨周期区间套」标签，但实际
        建立在合成数据上——两者矛盾。准确表述是：**合成低级别区间套（近似）**。

        策略只被喂进单一周期 df，拿不到真实低级别行情，因此用
        :mod:`easy_tdx.chanlun.level_synth` 合成近似低级别 K 线（默认日线→30分钟），
        再跑一遍缠论得到笔/中枢/背驰/买卖点，交给
        :func:`compute_qujiantao_cross_period` 按原文语义确认。

        注意 :mod:`easy_tdx.chanlun.level_synth` 自述「这只是**近似**，不是真实
        Tick……不能当成精确的小级别买卖点」；而
        :func:`compute_qujiantao_cross_period` 的契约要求「另一份**真实行情**」。
        因此本路径产出的 ``nested`` **不等于**原文意义的真区间套，调用方以
        ``synthetic=True`` 显式声明来源。开启 ``require_qujiantao`` 过滤真实
        交易时，请务必知道它过滤的是「合成数据上的确认」。

        任何一步失败都**静默降级**为 ``_qujiantao = None``：
        此时 ``require_qujiantao=True`` 会因为 ``nested is not True`` 过滤掉全部信号，
        与修复前"0 交易"的行为一致——为避免这种情况，失败时我们把标签设为
        ``{"nested": None}`` 并在 ``require_qujiantao`` 下**放行**（见信号构建处）。
        """
        if not src_mmds:
            return
        try:
            from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
            from easy_tdx.chanlun.level_synth import synthesize_lower_level
            from easy_tdx.chanlun.qujiantao import compute_qujiantao_cross_period
        except Exception:  # noqa: BLE001
            return

        low_level = str(self.p.get("qujiantao_low_level") or "MIN_30")
        try:
            low_df = synthesize_lower_level(
                df,
                high_level="DAY",
                low_level=low_level,
                seed=int(self.p.get("qujiantao_seed") or 20240101),
            )
            if low_df is None or len(low_df) < 30:
                raise ValueError("合成低级别数据不足")
            cfg = ChanlunConfig(
                bi_type=self.p["bi_type"],
                zs_min_lines=self.p["zs_min_lines"],
                macd_fast=self.p["macd_fast"],
                macd_slow=self.p["macd_slow"],
                macd_signal=self.p["macd_signal"],
            zs_from_xd=bool(self.p.get("zs_from_xd", False)),
            use_seg_mmd=bool(self.p.get("use_seg_mmd", False)),
            seg_mmd_hybrid=bool(self.p.get("seg_mmd_hybrid", False)),
            seg_divergence_rate=float(self.p.get("seg_divergence_rate", 1.5)),
            bs1_peak=bool(self.p.get("bs1_peak", False)),
            bsp2_follow_1=bool(self.p.get("bsp2_follow_1", False)),
            bsp3_follow_1=bool(self.p.get("bsp3_follow_1", False)),
            )
            low_result = ChanlunAnalyser(code="LOW", frequency="low", config=cfg).process_klines(
                low_df
            )
            results = compute_qujiantao_cross_period(
                src_mmds,
                bis_low=getattr(low_result, "bis", None),
                zss_low=getattr(low_result, "zss", None),
                bcs_low=getattr(low_result, "bcs", None),
                mmds_low=getattr(low_result, "mmds", None),
                # V731：这里的低级别数据是 level_synth **合成**的近似值
                # （该模块自述「不能当成精确的小级别买卖点」），不是真实
                # 行情。必须声明来源，否则 nested 会被误当作原文意义的
                # 真区间套。开启 require_qujiantao 时请先读这个前提。
                synthetic=True,
            )
        except Exception:  # noqa: BLE001
            results = [None] * len(src_mmds)

        for mmd, qt in zip(src_mmds, results):
            try:
                mmd._qujiantao = qt
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _nested_pass(nested: bool | None, strict: bool) -> bool:
        """区间套过滤判定。

        - ``strict=True``（严格）：只放行**明确确认**（True）的信号；
          未确认(False)或算不出来(None)都过滤。这是"只做区间套确认过的点"。
        - ``strict=False``（默认，宽松）：过滤**明确未确认**(False) 的信号，
          但**放行算不出来(None)** 的——避免因为合成低级别数据失败而把交易
          清零，制造"0 交易"的假象。
        """
        if nested is True:
            return True
        if nested is False:
            return False
        return not strict

    @staticmethod
    def _qujiantao_nested(mmd: Any) -> bool | None:
        """取信号的真区间套确认标签（None = 未计算/无跨级别数据）。"""
        qt = getattr(mmd, "_qujiantao", None)
        if not isinstance(qt, dict):
            return None
        v = qt.get("nested")
        return bool(v) if isinstance(v, bool) else None

    def _do_buy(self) -> None:
        """按 position_pct 生成买入信号。"""
        pct = float(self.p.get("position_pct", 1.0) or 1.0)
        if pct >= 1.0:
            self.buy()
            return
        price = float(self.data.close[0])
        if price <= 0 or self._cash <= 0:
            self.buy()
            return
        size = int(self._cash * pct / (price * 1.0005) / 100) * 100
        if size > 0:
            self.buy(size=size)
        else:
            self.buy()

    def _bi_end_bar_idx(self, bi: Any) -> int:
        """笔结束分型日期 → bar index。"""
        if bi.end is None:
            return -1
        end_date_str = str(bi.end.k.date)[:10]
        return self._date_to_bar.get(end_date_str, -1)

    def _enter(self, price: float, mmd_type: str, conf: float, nested: bool | None) -> None:
        """建仓并记账。"""
        self._in_position = True
        self._entry_price = price
        self._entry_type = mmd_type
        self._entry_bar = self._bar_index
        self._entry_conf = conf
        self._entry_nested = nested
        self._highest_since_entry = price  # 移动止盈跟踪
        self._trade_log.append(
            {
                "bar_index": self._bar_index,
                "direction": "BUY",
                "price": round(price, 4),
                "signal_type": mmd_type,
                "confidence": round(conf, 4),
                "nested": nested,
            }
        )
        self._do_buy()

    def _exit(self, price: float, exit_type: str, conf: float = 0.0) -> None:
        """平仓并记账（配对一条完整交易）。"""
        entry_type = self._entry_type
        pnl_pct = (
            (price - self._entry_price) / self._entry_price * 100.0
            if self._entry_price > 0
            else 0.0
        )
        self._trade_log.append(
            {
                "bar_index": self._bar_index,
                "direction": "SELL",
                "price": round(price, 4),
                "signal_type": exit_type,
                "confidence": round(conf, 4),
                "nested": self._entry_nested,
            }
        )
        self._pair_log.append(
            {
                "entry_bar": self._entry_bar,
                "exit_bar": self._bar_index,
                "holding_bars": self._bar_index - self._entry_bar,
                "entry_type": entry_type,
                "exit_type": exit_type,
                "entry_price": round(self._entry_price, 4),
                "exit_price": round(price, 4),
                "pnl_pct": round(pnl_pct, 4),
                "entry_confidence": round(self._entry_conf, 4),
                "nested": self._entry_nested,
            }
        )
        self._in_position = False
        self._entry_price = 0.0
        self._entry_type = ""
        self._entry_conf = 0.0
        self._entry_nested = None
        self._highest_since_entry = 0.0
        self.sell()

    def next(self) -> None:
        """每根 bar 调用：先消费卖点（出场优先），再消费买点。"""
        current_price = float(self.data.close[0])

        # 熔断止损（默认 0=关闭）。不是同级别卖点，仅极端保护，单独记因。
        sl = float(self.p.get("exit_stop_loss_pct", 0.0) or 0.0)
        if self._in_position and sl > 0 and self._entry_price > 0:
            if current_price <= self._entry_price * (1 - sl):
                self._exit(current_price, "fuse_stop_loss")
                return

        # 移动止盈（默认 0=关闭）。从持仓最高点回撤 X% 时出场，锁定利润。
        tsp = float(self.p.get("exit_trailing_stop_pct", 0.0) or 0.0)
        if self._in_position and tsp > 0:
            hi = getattr(self, "_highest_since_entry", current_price)
            if current_price > hi:
                self._highest_since_entry = current_price
                hi = current_price
            if hi > 0 and current_price <= hi * (1 - tsp):
                self._exit(current_price, "trailing_stop")
                return

        while self._signal_ptr < len(self._chanlun_signals):
            bar_idx, mmd_type, confidence, nested = self._chanlun_signals[self._signal_ptr]
            if bar_idx > self._bar_index:
                break
            self._signal_ptr += 1

            if mmd_type in _SELL_TYPES:
                # 3sell / 类2卖 受各自开关控制；1sell/2sell 始终生效
                if mmd_type == "3sell" and not self.p["use_3sell"]:
                    continue
                if mmd_type == "2sell_s" and not self.p["use_2s_signals"]:
                    continue
                if self._in_position:
                    # 级别联用：线段趋势仍向上时，2卖/3卖只是回调，持有；
                    # 只有 1卖（背驰卖点=趋势反转）无条件离场。
                    if self.p.get("hold_in_higher_uptrend", False) and mmd_type != "1sell":
                        trend = self._higher_trend_at(self._bar_index)
                        if trend == "up":
                            continue  # 持有，不在此卖点了结
                    self._exit(current_price, mmd_type, confidence)
                    # 出场后本根 bar 不再处理后续信号（避免同根又买又卖）
                    break

            elif mmd_type in _BUY_TYPES:
                if mmd_type == "3buy" and not self.p["use_3buy"]:
                    continue
                if mmd_type == "2buy_s" and not self.p["use_2s_signals"]:
                    continue
                if not self._in_position:
                    self._enter(current_price, mmd_type, confidence, nested)
                elif self.p["allow_pyramid"]:
                    # 加仓不改首仓配对（entry_* 保留首仓，出场时仍算一笔）
                    self._trade_log.append(
                        {
                            "bar_index": self._bar_index,
                            "direction": "BUY",
                            "price": round(current_price, 4),
                            "signal_type": mmd_type,
                            "confidence": round(confidence, 4),
                            "nested": nested,
                        }
                    )
                    self._do_buy()

    @property
    def trade_log(self) -> list[dict[str, Any]]:
        """交易记录（含 entry/exit 信号类型，供分组统计）。"""
        return self._trade_log

    @property
    def pair_log(self) -> list[dict[str, Any]]:
        """逐笔配对记录：一次「买点进 → 卖点出」一条。"""
        return self._pair_log

    @property
    def signal_traces(self) -> dict[str, list[dict[str, Any]]]:
        """预计算的信号类型追踪（供引擎 signal_accuracy 分组）。"""
        return self._signal_traces
