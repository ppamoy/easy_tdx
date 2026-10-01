"""缠论分析器主入口。

ChanlunAnalyser 接收 easy_tdx 的 K 线 DataFrame，
内部执行完整的缠论计算管道：
K线合并 → 分型识别 → 笔计算 → 中枢计算 → 线段 → 买卖点 → 背驰。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from easy_tdx.chanlun.beichi import check_bi_beichi  # noqa: F401
from easy_tdx.chanlun.bi import find_bis
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.fractal import find_fractals
from easy_tdx.chanlun.kline_merge import merge_klines
from easy_tdx.chanlun.macd import calc_macd  # noqa: F401
from easy_tdx.chanlun.mmd import find_mmds_v44  # noqa: F401
from easy_tdx.chanlun.recursive import (
    RecursiveLevelResult,
    compute_recursive_levels,
)
from easy_tdx.chanlun.types import BC, BI, FX, MMD, XD, ZS, CLKline, Kline, Line
from easy_tdx.chanlun.xd import find_xds  # noqa: F401
from easy_tdx.chanlun.zs import find_zss
from easy_tdx.chanlun.zsd import find_qsds, find_zsds
from easy_tdx.MyTT import BOLL


def _df_to_klines(df: pd.DataFrame) -> list[Kline]:
    """将 easy_tdx K 线 DataFrame 转为缠论 Kline 列表。

    期望 DataFrame 包含列：datetime, open, close, high, low, vol
    """
    klines: list[Kline] = []
    for i, row in enumerate(df.itertuples()):
        dt = getattr(row, "datetime", None) or getattr(row, "date", None)
        if dt is None:
            continue
        # V623: 字符串日期（如 JSON 载入的 DataFrame）归一化为时间对象，
        # 否则后续 _fmt_dt 调 strftime 会因 str 无该方法而崩溃。
        if isinstance(dt, str):
            dt = pd.to_datetime(dt)
        row_any: Any = row  # avoid pandas-stubs vs bare pandas type mismatch
        vol = getattr(row, "vol", 0.0) or 0.0
        klines.append(
            Kline(
                index=i,
                date=dt,
                open=float(row_any.open),
                close=float(row_any.close),
                high=float(row_any.high),
                low=float(row_any.low),
                amount=float(vol),
            )
        )
    return klines


def _enforce_fx_independence(fxs: list[FX], config: ChanlunConfig) -> list[FX]:
    """按缠论原文保证剩余分型「顶底严格交替 + 相邻不共用 K 线」。

    为什么需要单独这一步：``valid_fractals`` 是笔端点分型，其性质原本由
    ``find_bis`` 间接保证，但该保证依赖 ``bi_type``——legacy 的 ``simple``
    口径只要顶底交替就成笔，甚至允许一笔起止点同类（实测 ``ding@2 → ding@2``）。
    分型的交替性与独立性是缠论原文的硬性要求，不应取决于用户选了哪种笔口径，
    故在序列化前显式收紧一次。

    输入可能已经病态（含同类相邻、同值重复），因此这里不能假定入参干净：
      1. 先按 (bar_index, 类型) 去重；
      2. 顺序扫描，候选必须满足：与前一分型异类 + 间距达标，才纳入；
      3. 同类或间距不足的候选，若为更强的极值则替换前一分型
         （顶取更高、底取更低），否则丢弃。替换后仍要与再前一分型保持交替，
         不满足则直接丢弃。

    Args:
        fxs: 候选分型（按时间排序，可能已含违反者）
        config: 缠论配置，决定最小间距（口径同 bi.py::_check_bi_gap）

    Returns:
        满足「严格交替 + 相邻独立」的分型列表
    """
    if len(fxs) <= 1:
        return list(fxs)

    min_gap = 5 if config.bi_type == "old" else 3

    def _gap_ok(a: FX, b: FX) -> bool:
        """a 在前、b 在后：两者之间是否至少隔 min_gap 根缠论K线。"""
        if not a.klines or not b.klines:
            return False
        try:
            gap = b.klines[0].index - a.klines[-1].index + 1
        except (AttributeError, IndexError):
            return False
        return gap >= min_gap

    def _is_stronger(cand: FX, cur: FX) -> bool:
        """同为顶/底时，cand 是否比 cur 更符合「该位置的极值」。"""
        return cand.val < cur.val if cand.fx_type.value == "di" else cand.val > cur.val

    unique: list[FX] = []
    seen: set[tuple[int, str]] = set()
    for fx in fxs:
        key = (fx.bar_index, fx.fx_type.value)
        if key in seen:
            continue
        seen.add(key)
        unique.append(fx)

    kept: list[FX] = []
    for fx in unique:
        if not kept:
            kept.append(fx)
            continue
        prev = kept[-1]
        if prev.fx_type != fx.fx_type and _gap_ok(prev, fx):
            kept.append(fx)
            continue
        # 走到这里：同类相邻，或间距不足，或间距无法判定。
        # 「留极值更强者」只有在确知两者冲突（同类/间距不足）时才成立；
        # 若仅仅是 klines 缺失导致无法判定，绝不能用它去替换已保留的合法分型
        # ——数据损坏时宁可保守地丢弃候选，也不能把好数据换掉。
        known_conflict = fx.fx_type == prev.fx_type or (
            prev.klines and fx.klines and not _gap_ok(prev, fx)
        )
        if known_conflict and _is_stronger(fx, prev):
            # 替换后仍须与「前前项」保持交替与间距
            if len(kept) < 2 or (kept[-2].fx_type != fx.fx_type and _gap_ok(kept[-2], fx)):
                kept[-1] = fx
        continue
        kept.append(fx)
    return kept


@dataclass
class ChanlunResult:
    """缠论分析结果。"""

    code: str = ""
    frequency: str = ""
    klines: list[Kline] = field(default_factory=list)
    cklines: list[CLKline] = field(default_factory=list)
    fractals: list[FX] = field(default_factory=list)
    # 缠论意义上的「有效分型」：构成笔端点的分型，并经独立性收紧后，保证顶底严格
    # 交替且相邻不共用K线。原始 fractals 由逐三根滑动窗口扫出，含大量共用K线的
    # 重叠分型（如 底-顶-底 挤在连续K线），不能直接作为独立分型渲染。
    #
    # ⚠️ 已证伪并修正：旧注释称笔端点分型「天然交替且不重叠」，此说法**不成立**。
    # 该性质实际依赖 bi_type——legacy 的 simple 口径只要顶底交替就成笔，甚至允许
    # 一笔起止点同类（实测 ding@2 → ding@2），此时笔端点集合会退化成几乎全部原始
    # 分型（000001 日线：266 个原始分型 → valid 退化到 45 个且仍有 15 对同类相邻）。
    # 现由 _enforce_fx_independence 显式施加「交替 + 间距」约束，与 bi_type 无关。
    # 展示层应使用它而非原始 fractals。
    valid_fractals: list[FX] = field(default_factory=list)
    bis: list[BI] = field(default_factory=list)
    zss: list[ZS] = field(default_factory=list)
    xds: list[XD] = field(default_factory=list)
    mmds: list[MMD] = field(default_factory=list)
    bcs: list[BC] = field(default_factory=list)
    macd: dict[str, list[float]] = field(default_factory=dict)
    boll: Any = None  # BOLLResult or None
    # 多级别递归：Level 1 = 以线段为「高级别笔」的线段中枢/线段/买卖点/背驰
    xds_l1: list[XD] = field(default_factory=list)
    zss_l1: list[ZS] = field(default_factory=list)
    mmds_l1: list[MMD] = field(default_factory=list)
    bcs_l1: list[BC] = field(default_factory=list)
    # 递归级别的走势段/趋势段（以线段级别的「线段」再合并）。
    zsds_l1: list[XD] = field(default_factory=list)
    qsds_l1: list[XD] = field(default_factory=list)
    # 多级别递归链：recursive_levels[i] = 第 i+1 级递归结果（i=0 即 *_l1）。
    # 每级把上一级的线段当作更高级别「笔」逐级递归，直到 recursion_depth 或
    # 该级线段不足 3 根为止。*_l1 字段保留作向后兼容的 Level-1 快捷入口。
    recursive_levels: list[RecursiveLevelResult] = field(default_factory=list)
    # 走势段/趋势段：由线段（XD）合并得到，供更高级别画图与择时参考。
    zsds: list[XD] = field(default_factory=list)
    qsds: list[XD] = field(default_factory=list)

    def _fmt_dt(self, dt: datetime) -> str:
        """按 frequency 自适应格式化日期。

        分钟级别（1/5/15/30/60min）输出完整时分 YYYY-MM-DD HH:MM，
        日/周/月/年级别只输出日期 YYYY-MM-DD（无多余 00:00）。
        frequency 来自 CLI 原始值（如 5MIN/30MIN）或 Web 映射值（5min/30min），
        统一转小写后判断是否含 'min'。
        """
        fmt = "%Y-%m-%d %H:%M" if "min" in self.frequency.lower() else "%Y-%m-%d"
        return dt.strftime(fmt)

    def _fx_anchor_datetime(self, fx: FX) -> datetime:
        """分型极值锚定的原始K线时间。

        分型极值对应的原始K线是 fx.bar_index 那根（可能不是合并组最后一根，
        例如向上取高高时高点来自较早一根K线）。返回该K线的 date，
        保证序列化的 start_date/end_date 与 start_index/end_index 指向同一根K线，
        前端按索引或按日期都能锚定到同一个点。
        """
        for k in fx.k.klines:
            if k.index == fx.bar_index:
                return k.date
        return fx.k.date

    def _line_dict(self, line: Line) -> dict[str, Any]:
        """序列化笔/线段（两者同为 Line 子类，字段一致）。"""
        return {
            "index": line.index,
            "direction": line.direction.value,
            "start_date": self._fmt_dt(self._fx_anchor_datetime(line.start)),
            "end_date": self._fmt_dt(self._fx_anchor_datetime(line.end)),
            "high": round(line.high, 2),
            "low": round(line.low, 2),
            "start_val": round(line.start.val, 2),
            "end_val": round(line.end.val, 2),
            "start_index": line.start.bar_index,
            "end_index": line.end.bar_index,
        }

    def _zs_dict(self, zs: ZS) -> dict[str, Any]:
        return {
            "index": zs.index,
            "zg": round(zs.zg, 2),
            "zd": round(zs.zd, 2),
            "gg": round(zs.gg, 2),
            "dd": round(zs.dd, 2),
            "line_count": zs.line_count,
            "start_date": (self._fmt_dt(self._fx_anchor_datetime(zs.start)) if zs.start else None),
            "end_date": self._fmt_dt(self._fx_anchor_datetime(zs.end)) if zs.end else None,
            "start_index": zs.start.bar_index if zs.start else None,
            "end_index": zs.end.bar_index if zs.end else None,
            "done": zs.done,
            "enter_bi_index": zs.enter_bi.index if zs.enter_bi else None,
            "exit_bi_index": zs.exit_bi.index if zs.exit_bi else None,
        }

    def _mmd_dict_core(self, mmd: MMD) -> dict[str, Any]:
        return {
            "type": mmd.mmd_type.value,
            "date": self._fmt_dt(self._fx_anchor_datetime(mmd.bi.end)) if mmd.bi else None,
            "bar_index": mmd.bi.end.bar_index if mmd.bi else None,
            "anchor_val": round(mmd.bi.end.val, 2) if mmd.bi else None,
            "msg": mmd.msg,
            "confidence": round(mmd.confidence, 2),
        }

    def _bc_dict_core(self, bc: BC) -> dict[str, Any]:
        return {
            "type": bc.bc_type.value,
            "bc": bc.bc,
            "date": (
                self._fmt_dt(self._fx_anchor_datetime(bc.curr.end))
                if bc.curr
                else self._fmt_dt(self._fx_anchor_datetime(bc.prev.end))
                if bc.prev
                else None
            ),
            "anchor_val": (
                round(bc.curr.end.val, 2)
                if bc.curr
                else round(bc.prev.end.val, 2)
                if bc.prev
                else None
            ),
            "anchor_bar_index": (
                bc.curr.end.bar_index if bc.curr else bc.prev.end.bar_index if bc.prev else None
            ),
            "msg": bc.msg,
        }

    def _level_payload(
        self,
        name: str,
        lines: Sequence[Line],
        xds: list[XD],
        zss: list[ZS],
        mmds: list[MMD],
        bcs: list[BC],
        zsds: list[XD],
        qsds: list[XD],
    ) -> dict[str, Any]:
        """序列化一个分析级别：笔/线段、中枢、买卖点、背驰、走势段/趋势段。"""
        return {
            "name": name,
            "bi_count": len(lines),
            "xd_count": len(xds),
            "zs_count": len(zss),
            "mmd_count": len(mmds),
            "bc_count": len(bcs),
            "zsd_count": len(zsds),
            "qsd_count": len(qsds),
            # 本级「笔」序列；线段级别中这些笔是低级别线段（xd 复用 line 字段）。
            "bis": [self._line_dict(line) for line in lines],
            "xds": [self._line_dict(xd) for xd in xds],
            "zss": [self._zs_dict(zs) for zs in zss],
            "mmds": [self._mmd_dict_core(m) for m in mmds],
            "bcs": [self._bc_dict_core(bc) for bc in bcs],
            "zsds": [self._line_dict(zsd) for zsd in zsds],
            "qsds": [self._line_dict(qsd) for qsd in qsds],
        }

    def _recursive_levels_payload(self) -> dict[str, dict[str, Any]]:
        """序列化多级别递归链：第 1 级为 levels.xd，更高级别为 levels.xd_lN。

        每级的「笔」= 上一级线段（Level 1 的「笔」= 基础线段 self.xds），
        本级的线段 = 该级递归得到的 XD。Level 1（xd）始终输出；更高级别仅
        在递归链有结果时输出。
        """
        out: dict[str, dict[str, Any]] = {}
        empty_xds: list[XD] = []
        empty_zss: list[ZS] = []
        empty_mmds: list[MMD] = []
        empty_bcs: list[BC] = []
        if not self.recursive_levels:
            out["xd"] = self._level_payload(
                "线段级别",
                self.xds,
                empty_xds,
                empty_zss,
                empty_mmds,
                empty_bcs,
                empty_xds,
                empty_xds,
            )
            return out

        prev_lines: list[XD] = self.xds
        for lvl, rl in enumerate(self.recursive_levels):
            level_no = lvl + 1
            key = "xd" if level_no == 1 else f"xd_l{level_no}"
            name = "线段级别" if level_no == 1 else f"递归{level_no}级"
            out[key] = self._level_payload(
                name,
                prev_lines,
                rl.xds,
                rl.zss,
                rl.mmds,
                rl.bcs,
                rl.zsds,
                rl.qsds,
            )
            prev_lines = rl.xds
        return out

    def to_dict(self) -> dict[str, Any]:
        """将结果转为可序列化的字典（用于 JSON 输出）。"""
        macd = getattr(self, "macd", None) or {}
        return {
            "code": self.code,
            "frequency": self.frequency,
            "kline_count": len(self.klines),
            "ckline_count": len(self.cklines),
            "fractal_count": len(self.fractals),
            "valid_fractal_count": len(self.valid_fractals),
            "bi_count": len(self.bis),
            "zs_count": len(self.zss),
            "xd_count": len(self.xds),
            "zsd_count": len(self.zsds),
            "qsd_count": len(self.qsds),
            "mmd_count": len(self.mmds),
            "bc_count": len(self.bcs),
            # MACD 序列（dif/dea/hist 与 K 线一一对应）。
            # 背驰判断基于笔内 MACD 红绿柱面积（calc_macd_force），
            # 返回完整序列供前端副图展示，用户可直观核对背驰依据。
            "macd": {
                "dif": [round(x, 6) for x in (macd.get("dif") or [])],
                "dea": [round(x, 6) for x in (macd.get("dea") or [])],
                "hist": [round(x, 6) for x in (macd.get("hist") or [])],
            },
            "bis": [
                {
                    "index": bi.index,
                    "direction": bi.direction.value,
                    "start_date": self._fmt_dt(self._fx_anchor_datetime(bi.start)),
                    "end_date": self._fmt_dt(self._fx_anchor_datetime(bi.end)),
                    "high": round(bi.high, 2),
                    "low": round(bi.low, 2),
                    "start_val": round(bi.start.val, 2),
                    "end_val": round(bi.end.val, 2),
                    # 端点锚定的原始K线索引（极值来源），前端据此精确描点，
                    # 避免按日期字符串模糊匹配在分钟线上错位。
                    "start_index": bi.start.bar_index,
                    "end_index": bi.end.bar_index,
                    "done": bi.is_done(),
                }
                for bi in self.bis
            ],
            "zss": [
                {
                    "index": zs.index,
                    "zg": round(zs.zg, 2),
                    "zd": round(zs.zd, 2),
                    "gg": round(zs.gg, 2),
                    "dd": round(zs.dd, 2),
                    "line_count": zs.line_count,
                    "start_date": (
                        self._fmt_dt(self._fx_anchor_datetime(zs.start)) if zs.start else None
                    ),
                    "end_date": (
                        self._fmt_dt(self._fx_anchor_datetime(zs.end)) if zs.end else None
                    ),
                    "start_index": zs.start.bar_index if zs.start else None,
                    "end_index": zs.end.bar_index if zs.end else None,
                    "done": zs.done,
                    # 缠论原文：中枢的进入段/离开段（用于背驰与画图标注）
                    "enter_bi_index": zs.enter_bi.index if zs.enter_bi else None,
                    "exit_bi_index": zs.exit_bi.index if zs.exit_bi else None,
                    # v89: 中枢质量评分
                    "quality_score": (
                        round(zs.quality_score, 2) if hasattr(zs, "quality_score") else None
                    ),
                    "grade": zs.grade if hasattr(zs, "grade") else None,
                    "width_pct": round(zs.width_pct, 2) if hasattr(zs, "width_pct") else None,
                }
                for zs in self.zss
            ],
            "xds": [
                {
                    "index": xd.index,
                    "direction": xd.direction.value,
                    "start_date": self._fmt_dt(self._fx_anchor_datetime(xd.start)),
                    "end_date": self._fmt_dt(self._fx_anchor_datetime(xd.end)),
                    "high": round(xd.high, 2),
                    "low": round(xd.low, 2),
                    "start_val": round(xd.start.val, 2),
                    "end_val": round(xd.end.val, 2),
                    "start_index": xd.start.bar_index,
                    "end_index": xd.end.bar_index,
                }
                for xd in self.xds
            ],
            "zsds": [self._line_dict(zsd) for zsd in self.zsds],
            "qsds": [self._line_dict(qsd) for qsd in self.qsds],
            "mmds": [
                {
                    "type": mmd.mmd_type.value,
                    "date": self._fmt_dt(self._fx_anchor_datetime(mmd.bi.end)) if mmd.bi else None,
                    # 买卖点锚定的原始K线索引（触发笔终点极值来源）
                    "bar_index": mmd.bi.end.bar_index if mmd.bi else None,
                    # 买卖点锚定价格（触发笔终点分型极值）：买点=底分型低点，
                    # 卖点=顶分型高点。前端标注必须用该值，不能用 bars 的
                    # low/high 乘偏移，否则标注不会精确落在触发笔端点极值上。
                    "anchor_val": round(mmd.bi.end.val, 2) if mmd.bi else None,
                    "msg": mmd.msg,
                    "confidence": round(mmd.confidence, 2),
                    "quality": {
                        "grade": getattr(mmd.quality, "grade", None) if mmd.quality else None,
                        "score": getattr(mmd.quality, "score", None) if mmd.quality else None,
                        "reasons": getattr(mmd.quality, "reasons", None) if mmd.quality else None,
                    }
                    if mmd.quality
                    else None,
                    # V79 缠论增强条件（条件248-251）
                    "v79_fractal_stability": getattr(
                        mmd, "_fractal_stability_validation_v79", None
                    ),
                    "v79_distance_safety": getattr(mmd, "_mmd_distance_safety_v79", None),
                    "v79_multi_level_consistency": getattr(
                        mmd, "_multi_level_structure_consistency_v79", None
                    ),
                    "v79_momentum_continuity": getattr(mmd, "_price_momentum_continuity_v79", None),
                    # V80 缠论增强条件（条件252-255）
                    "v80_zhongshu_distance": getattr(mmd, "_mmd_zhongshu_distance_v80", None),
                    "v80_volume_confirmation": getattr(mmd, "_volume_confirmation_v80", None),
                    "v80_ma_alignment": getattr(mmd, "_ma_alignment_strength_v80", None),
                    "v80_risk_reward": getattr(mmd, "_dynamic_risk_reward_v80", None),
                    # V81 缠论增强条件（条件256-259）
                    "v81_volatility_regime": getattr(
                        mmd, "_volatility_regime_transition_v81", None
                    ),
                    "v81_support_resistance": getattr(
                        mmd, "_support_resistance_strength_v81", None
                    ),
                    "v81_energy_distribution": getattr(
                        mmd, "_volume_price_energy_distribution_v81", None
                    ),
                    "v81_execution_window": getattr(mmd, "_signal_execution_window_v81", None),
                    # V82 缠论增强条件（条件260-263）
                    "v82_age_decay": getattr(mmd, "_mmd_age_decay_v82", None),
                    "v82_breakout_retest": getattr(mmd, "_breakout_retest_confirm_v82", None),
                    "v82_macd_resonance": getattr(mmd, "_macd_multi_tf_resonance_v82", None),
                    "v82_volatility_compression": getattr(
                        mmd, "_volatility_compression_breakout_v82", None
                    ),
                    # V102 缠论决策支持（条件264-267）
                    "v102_multi_signal_correlation": getattr(
                        mmd, "_multi_signal_correlation", None
                    ),
                    "v102_signal_quality": getattr(mmd, "_signal_quality_scorecard", None),
                    "v102_decision_support": getattr(mmd, "_decision_support", None),
                    "v102_pattern_match": getattr(mmd, "_historical_pattern_match", None),
                    # V68 条件205 区间套（多级别共振一致性）：字面意义的「区间套」
                    # ——仅 3 类买卖点计算（需 >=40 根 K 线），含 multi_level_score
                    # （0-1）与置信度调整；便于前端标注与回测分组统计。
                    "v68_range_set_multi_level": getattr(mmd, "_range_set_multi_level_v68", None),
                    # 真·区间套（统一实现）：与条件205 单级别伪区间套区分开。
                    # 无递归级别时 _qujiantao 为 None，前端据此不显示「真区间套」卡片。
                    "qujiantao": getattr(mmd, "_qujiantao", None),
                }
                for mmd in self.mmds
            ],
            "bcs": [
                {
                    "type": bc.bc_type.value,
                    "bc": bc.bc,
                    # 背驰发生点日期（前端统一消费 date 字段）：
                    # 优先当前笔结束日，回退到前一笔结束日，避免缺失字段导致前端崩溃。
                    "date": (
                        self._fmt_dt(self._fx_anchor_datetime(bc.curr.end))
                        if bc.curr
                        else self._fmt_dt(self._fx_anchor_datetime(bc.prev.end))
                        if bc.prev
                        else None
                    ),
                    "curr_date": (
                        self._fmt_dt(self._fx_anchor_datetime(bc.curr.end)) if bc.curr else None
                    ),
                    "prev_date": (
                        self._fmt_dt(self._fx_anchor_datetime(bc.prev.end)) if bc.prev else None
                    ),
                    # 背驰锚定价格/索引：主图标注落在触发笔终点分型极值上，
                    # 副图仍展示 MACD 柱依据，主副图可对照核对。
                    "anchor_val": (
                        round(bc.curr.end.val, 2)
                        if bc.curr
                        else round(bc.prev.end.val, 2)
                        if bc.prev
                        else None
                    ),
                    "anchor_bar_index": (
                        bc.curr.end.bar_index
                        if bc.curr
                        else bc.prev.end.bar_index
                        if bc.prev
                        else None
                    ),
                    "msg": bc.msg,
                }
                for bc in self.bcs
            ],
            "levels": {
                # 笔级别 = 单级别基础结果（本级别笔 → 线段 → 中枢 → 背驰 → 买卖点）
                "bi": self._level_payload(
                    "笔级别",
                    self.bis,
                    self.xds,
                    self.zss,
                    self.mmds,
                    self.bcs,
                    self.zsds,
                    self.qsds,
                ),
                **self._recursive_levels_payload(),
            },
        }

    def _fx_to_dict(self, fx: FX) -> dict[str, Any]:
        """分型序列化为前端可用的精简字典（与 router 中 fractals 字段结构一致）。"""
        return {
            "fx_type": fx.fx_type.value,
            "date": self._fmt_dt(self._fx_anchor_datetime(fx)),
            "val": round(fx.val, 2),
            "index": fx.index,
            "bar_index": fx.bar_index,
        }

    def valid_fractals_to_dict(self) -> list[dict[str, Any]]:
        return [self._fx_to_dict(fx) for fx in self.valid_fractals]


class ChanlunAnalyser:
    """缠论分析器。

    接收 easy_tdx K 线 DataFrame，执行缠论计算管道。

    用法：
        analyser = ChanlunAnalyser("SZ000001", "DAILY")
        analyser.process_klines(df)
        result = analyser.result
    """

    def __init__(
        self,
        code: str = "",
        frequency: str = "",
        config: ChanlunConfig | None = None,
    ) -> None:
        self._code = code
        self._frequency = frequency
        self._config = config or ChanlunConfig()
        self._result = ChanlunResult(
            code=code,
            frequency=frequency,
        )
        self._prev_df: pd.DataFrame | None = None

    @property
    def config(self) -> ChanlunConfig:
        return self._config

    @property
    def result(self) -> ChanlunResult:
        return self._result

    def process_klines(self, df: pd.DataFrame) -> ChanlunResult:
        """处理 K 线 DataFrame，执行缠论计算管道。

        Args:
            df: easy_tdx 返回的 K 线 DataFrame

        Returns:
            ChanlunResult 包含所有缠论计算结果
        """
        self._prev_df = df.copy()
        # Step 1: DataFrame → Kline 列表
        klines = _df_to_klines(df)
        self._result.klines = klines

        # 重置递归级别结果：每次 process_klines 都重新计算（否则在追加数据后
        # 若新的线段数不足会残留上一次的递归结果）。
        self._result.recursive_levels = []
        self._result.xds_l1 = []
        self._result.zss_l1 = []
        self._result.mmds_l1 = []
        self._result.bcs_l1 = []
        self._result.zsds_l1 = []
        self._result.qsds_l1 = []

        if not klines:
            return self._result

        # Step 2: K线包含处理
        cklines = merge_klines(klines)
        self._result.cklines = cklines

        # Step 3: 分型识别
        fractals = find_fractals(cklines, self._config)
        self._result.fractals = fractals

        # Step 4: 笔计算（传入 cklines 用于分型稳定性校验）
        bis = find_bis(fractals, self._config, cklines=self._result.cklines)
        # 修正每笔 high/low 为笔区间内原始K线真实极值。
        # find_bis 用端点分型值 max/min(start.val,end.val) 初始化 high/low，但在
        # 「区间内存在更高顶/更低底却因 gap 不足未成笔端点」时会漏算——例如两底
        # 之间的最高顶因 gap 不足无法作为笔端点，其价格仍落在笔区间内，端点 high
        # 偏低会令中枢 zg 偏窄。缠论原文：笔的极值为笔区间内所有K线的最高/最低价。
        for bi in bis:
            si = bi.start.bar_index
            ei = bi.end.bar_index
            if 0 <= si <= ei < len(klines):
                seg = klines[si : ei + 1]
                if seg:
                    bi.high = max(k.high for k in seg)
                    bi.low = min(k.low for k in seg)
        self._result.bis = bis

        # Step 4.5: 有效分型 = 笔端点分型（去重）。用于前端展示，要求顶底交替且
        # 相邻分型不共用 K 线（缠论原文：中间至少 1 根独立K线）。
        # 注意：不能只靠 find_bis 的 gap 规则保证独立性——bi_type="simple" 是
        # legacy 口径，只要顶底交替就成笔，会让共用 K 线的分型成为笔端点，此时
        # 笔端点分型集合不再满足独立性（实测 simple 下退化成全部 266 个原始分型，
        # 184 对相邻违规）。故这里再独立施加一次独立性过滤。
        seen: set[tuple[int, str]] = set()
        valid: list[FX] = []
        for bi in bis:
            for fx in (bi.start, bi.end):
                key = (fx.bar_index, fx.fx_type.value)
                if key not in seen:
                    seen.add(key)
                    valid.append(fx)
        valid = _enforce_fx_independence(valid, self._config)
        self._result.valid_fractals = valid

        # Step 5: 中枢计算
        zss = find_zss(bis, self._config)
        self._result.zss = zss

        # Step 6: MACD 计算
        closes = [k.close for k in klines]
        self._result.macd = calc_macd(
            closes, self._config.macd_fast, self._config.macd_slow, self._config.macd_signal
        )

        # Step 7: 线段计算
        xds = find_xds(bis, self._config)
        self._result.xds = xds

        # Step 7.1: 走势段/趋势段（由线段合并，用于更高级别画图与择时）
        self._result.zsds = find_zsds(xds, self._config)
        self._result.qsds = find_qsds(xds, self._config)

        # Step 7.5: BOLL 指标计算
        if len(closes) >= 20:
            from easy_tdx.chanlun.types import BOLLResult

            _upper, _mid, _lower = BOLL(closes, N=20, P=2)
            _width = [
                (_upper[i] - _lower[i]) / _mid[i] if _mid[i] > 0 else 0 for i in range(len(_upper))
            ]
            _pb = []
            for i in range(len(closes)):
                ub = _upper[i]
                lb = _lower[i]
                _pb.append((closes[i] - lb) / (ub - lb) if (ub - lb) > 0 else 0.5)
            self._result.boll = BOLLResult(
                upper=_upper.tolist(),
                mid=_mid.tolist(),
                lower=_lower.tolist(),
                width=_width,
                percent_b=_pb,
            )

        # Step 8: 买卖点识别（传入收盘价用于MACD力度计算）
        # 提取成交量序列
        volumes = [k.amount for k in klines]
        # V5: 计算波动率用于动态阈值
        from easy_tdx.chanlun.mmd_conditions import _calc_atr_volatility

        volatility = _calc_atr_volatility(closes) if len(closes) > 0 else None
        # V12: 传递highs/lows用于真实ADX计算
        highs = [k.high for k in klines]
        lows = [k.low for k in klines]
        mmds = find_mmds_v44(
            bis,
            zss,
            closes=closes,
            config=self._config,
            volumes=volumes,
            macd_data=self._result.macd,
            volatility=volatility,
            highs=highs,
            lows=lows,
        )
        self._result.mmds = mmds

        # Step 9: 背驰判断（传入收盘价用于MACD面积计算）
        bcs = check_bi_beichi(bis, zss, closes=closes, config=self._config)
        self._result.bcs = bcs

        # Step 10: 多级别递归（Level 1 = 以低级别线段作为高级别的「笔」）。
        # 缠论递归：本级别线段 → 更高级别笔 → 更高级别线段/中枢/背驰/买卖点。
        # recursion_depth>=2 时继续把上一级线段当作更高级别笔逐级递归。
        if self._config.multi_level and len(xds) >= 3:
            recursive_levels = compute_recursive_levels(
                xds,
                depth=self._config.recursion_depth,
                closes=closes,
                volumes=volumes,
                macd_data=self._result.macd,
                volatility=volatility,
                highs=highs,
                lows=lows,
                config=self._config,
            )
            self._result.recursive_levels = recursive_levels
            # Level-1 快捷字段：向后兼容（recursive_levels[0] 即 *_l1）。
            if recursive_levels:
                r0 = recursive_levels[0]
                self._result.xds_l1 = r0.xds
                self._result.zss_l1 = r0.zss
                self._result.mmds_l1 = r0.mmds
                self._result.bcs_l1 = r0.bcs
                self._result.zsds_l1 = r0.zsds
                self._result.qsds_l1 = r0.qsds

        # Step 10.5: 真·区间套确认（统一实现，见 chanlun/qujiantao.py）。
        # 以递归级别作为「低级别」，对基础级别每个 MMD 做跨级别确认。
        # 无递归级别时 qujiantao_for_result 整列返回 None（不编造评分）。
        if mmds:
            try:
                from easy_tdx.chanlun.qujiantao import qujiantao_for_result

                qt_results = qujiantao_for_result(self._result, 0)
                for m, qt in zip(mmds, qt_results):
                    m._qujiantao = qt
            except Exception:
                # 区间套是增强信息，失败不影响主流程
                pass

        return self._result

    def append_klines(self, df_new: pd.DataFrame) -> ChanlunResult:
        """增量追加 K 线数据并重新计算。

        将新数据追加到之前处理过的 DataFrame 后面，
        然后在完整数据上重新执行缠论计算管道。

        相比手动拼接 + process_klines 的优势：
        - API 更简洁，无需用户管理 DataFrame 拼接
        - 未来可优化为只重新计算受影响的部分

        Args:
            df_new: 新增的 K 线 DataFrame

        Returns:
            更新后的 ChanlunResult

        Raises:
            RuntimeError: 如果之前没有调用过 process_klines
        """
        if self._prev_df is None:
            msg = "请先调用 process_klines() 初始化，再使用 append_klines()"
            raise RuntimeError(msg)

        # 拼接旧数据 + 新数据
        combined = pd.concat([self._prev_df, df_new], ignore_index=True)

        # 去重（防止重复追加）
        if "datetime" in combined.columns:
            combined = combined.drop_duplicates(subset=["datetime"], keep="last")
            combined = combined.reset_index(drop=True)

        return self.process_klines(combined)

    def get_bis(self) -> list[BI]:
        return self._result.bis

    def get_zss(self) -> list[ZS]:
        return self._result.zss

    def get_fxs(self) -> list[FX]:
        return self._result.fractals

    def get_klines(self) -> list[Kline]:
        return self._result.klines

    def get_cklines(self) -> list[CLKline]:
        return self._result.cklines
