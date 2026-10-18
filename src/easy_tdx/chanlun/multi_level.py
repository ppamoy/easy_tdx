"""多级别联立分析（改进版）。

支持同时分析多个 K 线周期（如日线 + 30 分钟）的缠论数据，
查看高级别笔在低级别中的走势结构，辅助判断买卖点的有效性。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from easy_tdx.chanlun.analyser import ChanlunAnalyser, ChanlunResult
from easy_tdx.chanlun.types import BI, Direction


def _to_datetime(dt: Any) -> Any:
    """统一时间比较：date/datetime 均可比较，避免类型混用导致的查询遗漏。"""
    if dt is None:
        return dt
    return dt


class MultiLevelAnalyser:
    """多级别缠论分析器（改进版）。

    管理多个 ChanlunAnalyser 实例，每个对应一个 K 线周期。
    支持跨级别查询：高级别笔对应的低级别走势信息。
    """

    def __init__(self) -> None:
        self._analysers: dict[str, ChanlunAnalyser] = {}

    def add_level(self, name: str, analyser: ChanlunAnalyser) -> None:
        """添加一个分析级别。"""
        self._analysers[name] = analyser

    def process(self, level: str, df: object) -> ChanlunResult:
        """处理指定级别的 K 线数据。"""
        import pandas as pd

        if level not in self._analysers:
            raise KeyError(f"未注册的级别: {level}，可用: {list(self._analysers.keys())}")
        assert isinstance(df, pd.DataFrame)
        return self._analysers[level].process_klines(df)

    def get_result(self, level: str) -> ChanlunResult | None:
        """获取指定级别的分析结果。"""
        if level in self._analysers:
            return self._analysers[level].result
        return None

    def results(self) -> dict[str, ChanlunResult]:
        """获取所有级别的分析结果。"""
        return {name: a.result for name, a in self._analysers.items()}

    def compute_confluence_score(
        self,
        high_level: str,
        low_level: str,
    ) -> dict[str, Any]:
        """计算多级别一致性评分（改进版）。

        综合评估：
        1. 买卖点类型一致性（高低级别信号方向相同）
        2. 趋势方向一致性
        3. 中枢时间重叠
        4. 信号时间接近度
        """
        high_result = self.get_result(high_level)
        low_result = self.get_result(low_level)

        empty = {
            "score": 0.0,
            "high_level_signal": None,
            "low_level_signal": None,
            "trend_aligned": None,
            "zs_aligned": None,
            "time_aligned": None,
        }

        if high_result is None or low_result is None:
            return empty

        # 获取最新买卖点
        high_mmds = sorted(high_result.mmds, key=lambda m: m.bi.index if m.bi else 0)
        low_mmds = sorted(low_result.mmds, key=lambda m: m.bi.index if m.bi else 0)

        if not high_mmds or not low_mmds:
            return empty

        latest_high = high_mmds[-1]
        latest_low = low_mmds[-1]

        # 1. 买卖点类型一致性评分
        buy_types = {"1buy", "2buy", "3buy", "2buy_s"}
        sell_types = {"1sell", "2sell", "3sell", "2sell_s"}

        high_is_buy = latest_high.mmd_type.value in buy_types
        high_is_sell = latest_high.mmd_type.value in sell_types
        low_is_buy = latest_low.mmd_type.value in buy_types
        low_is_sell = latest_low.mmd_type.value in sell_types

        # 同向信号加分（都买或都卖）
        signal_alignment = 0.0
        if high_is_buy and low_is_buy:
            signal_alignment = 0.4
        elif high_is_sell and low_is_sell:
            signal_alignment = 0.4
        elif (high_is_buy and low_is_sell) or (high_is_sell and low_is_buy):
            signal_alignment = -0.2  # 反向信号降权

        # 2. 趋势方向一致性
        high_trend = _detect_trend_direction(high_result.bis)
        low_trend = _detect_trend_direction(low_result.bis)
        trend_aligned = False
        if high_trend and low_trend:
            if high_trend == low_trend:
                trend_aligned = True
                signal_alignment += 0.2
            else:
                signal_alignment -= 0.1

        # 3. 中枢时间重叠检查
        zs_aligned = False
        if latest_high.bi and latest_low.bi:
            high_bi_start = latest_high.bi.start.k.date
            high_bi_end = latest_high.bi.end.k.date
            for zs in low_result.zss:
                if zs.start and zs.end:
                    zs_start = zs.start.k.date
                    zs_end = zs.end.k.date
                    # 更严格的时间重叠：低级别中枢与高级别笔的时间范围有交集
                    if zs_start <= high_bi_end and zs_end >= high_bi_start:
                        zs_aligned = True
                        signal_alignment += 0.2
                        break

        # 4. 时间窗口对齐（改进：使用datetime直接比较，避免时区问题）
        time_aligned = False
        if latest_high.bi and latest_low.bi:
            high_end = latest_high.bi.end.k.date
            low_end = latest_low.bi.end.k.date
            # 使用实际日期差（天）而非字符串比较
            if isinstance(high_end, datetime) and isinstance(low_end, datetime):
                days_diff = abs((high_end - low_end).days)
                time_aligned = days_diff <= 3  # 3天内为时间对齐
                if time_aligned:
                    signal_alignment += 0.2
            else:
                # 回退到字符串比较
                time_aligned = abs(high_end - low_end) <= 3

        # 综合评分
        base_score = (latest_high.confidence + latest_low.confidence) / 2
        aligned_score = max(0.0, min(1.0, signal_alignment + 0.3))  # 基础分0.3
        confluence_score = base_score * aligned_score

        # 质量加成
        def _grade_factor(grade: str | None) -> float:
            if not grade:
                return 0.8
            map_ = {"S": 1.2, "A": 1.1, "B": 1.0, "C": 0.85, "D": 0.7}
            return map_.get(grade, 0.8)

        high_grade = getattr(getattr(latest_high, "quality", None), "grade", None)
        low_grade = getattr(getattr(latest_low, "quality", None), "grade", None)
        grade_factor = (_grade_factor(high_grade) + _grade_factor(low_grade)) / 2

        final_score = confluence_score * grade_factor

        return {
            "score": round(final_score, 2),
            "high_level_signal": {
                "type": latest_high.mmd_type.value,
                "date": high_result._fmt_dt(latest_high.bi.end.k.date) if latest_high.bi else None,
                "confidence": round(latest_high.confidence, 2),
                "quality_grade": getattr(getattr(latest_high, "quality", None), "grade", None),
            },
            "low_level_signal": {
                "type": latest_low.mmd_type.value,
                "date": low_result._fmt_dt(latest_low.bi.end.k.date) if latest_low.bi else None,
                "confidence": round(latest_low.confidence, 2),
                "quality_grade": getattr(getattr(latest_low, "quality", None), "grade", None),
            },
            "trend_aligned": trend_aligned,
            "zs_aligned": zs_aligned,
            "time_aligned": time_aligned,
            "grade_factor": round(grade_factor, 2),
            "signal_alignment": round(signal_alignment, 2),
        }

    def query_low_level_qs(
        self,
        high_level: str,
        low_level: str,
        high_bi: BI,
    ) -> dict[str, Any]:
        """查询高级别笔在低级别中的走势信息（改进版）。

        查找低级别中时间范围落在高级别笔内的所有笔和中枢。
        """
        high_result = self.get_result(high_level)
        low_result = self.get_result(low_level)

        empty = {
            "bi_count": 0,
            "zs_count": 0,
            "has_trend": False,
            "has_consolidation": False,
            "trend_direction": None,
            "bi_overlap": False,
            "divergence_possible": False,
        }

        if high_result is None or low_result is None:
            return empty

        # 高级别笔的时间范围（统一转为 naive datetime，兼容 date/datetime 混用）
        start_date = _to_datetime(high_bi.start.k.date)
        end_date = _to_datetime(high_bi.end.k.date)

        # 若高级别笔位于数据末端（未完成笔），将窗口延伸到低级别数据末尾，
        # 避免最新一笔的低级别走势查询返回空。
        low_klines = getattr(low_result, "klines", [])
        if low_klines:
            low_last = _to_datetime(low_klines[-1].date)
            if end_date > low_last:
                end_date = low_last

        # 筛选低级别中时间范围内的笔
        low_bis = []
        for bi in low_result.bis:
            bi_start = _to_datetime(bi.start.k.date)
            bi_end = _to_datetime(bi.end.k.date)
            # 笔与范围有重叠
            if bi_start <= end_date and bi_end >= start_date:
                low_bis.append(bi)

        # 筛选低级别中枢
        low_zss = []
        for zs in low_result.zss:
            if zs.start is None or zs.end is None:
                continue
            zs_start = _to_datetime(zs.start.k.date)
            zs_end = _to_datetime(zs.end.k.date)
            if zs_start <= end_date and zs_end >= start_date:
                low_zss.append(zs)

        has_trend = len(low_zss) >= 2
        has_consolidation = len(low_zss) >= 1

        # 趋势方向判断
        trend_direction = _detect_trend_direction(low_bis)

        # 笔重叠判断
        bi_overlap = _detect_bi_overlap(low_bis)

        # 背驰条件判断
        divergence_possible = _check_divergence_condition(low_bis, low_zss)

        return {
            "bi_count": len(low_bis),
            "zs_count": len(low_zss),
            # V731：把筛选出来的**真实**低级别笔/中枢对象一并暴露。
            # 此前只返回计数，而 compute_qujiantao_cross_period 需要对象
            # 列表（bis_low / zss_low）才能做逐信号确认 —— 真实数据已经算了
            # 出来却被丢弃，跨周期区间套只好去用 level_synth 的**合成**数据。
            # 有了这两个字段，「真实行情 + 逐信号」的真区间套路径才成立。
            "bis": low_bis,
            "zss": low_zss,
            "has_trend": has_trend,
            "has_consolidation": has_consolidation,
            "trend_direction": trend_direction,
            "bi_overlap": bi_overlap,
            "divergence_possible": divergence_possible,
        }


def _detect_trend_direction(bis: list[BI]) -> str | None:
    """判断笔序列的趋势方向（改进版）。

    如果连续 3 笔以上高点递增且低点递增 → 上升趋势。
    如果连续 3 笔以上高点递减且低点递减 → 下降趋势。
    """
    if len(bis) < 3:
        return None

    # V857 偏差14（multi_level subagent 报告偏差5）：原用 bis[0::2] 当上升笔、
    # bis[1::2] 当下降笔——假设序列必以上升笔开头。但 BI 自带 direction 字段
    # （types.py:112 Direction.UP/DOWN），窗口切片首笔可能是下降笔，导致双向误判。
    # 改用 BI.direction 按方向分组（第17课趋势/盘整只与中枢有关，方向判定靠笔本身）。
    up_bis = [b for b in bis if b.direction == Direction.UP]
    down_bis = [b for b in bis if b.direction == Direction.DOWN]

    # 上升趋势：上升笔高点递增 + 下降笔低点递增
    if len(up_bis) >= 3:
        up_highs_ascending = all(
            up_bis[i].high > up_bis[i - 1].high for i in range(1, min(4, len(up_bis)))
        )
        down_lows_ascending = len(down_bis) >= 2 and all(
            down_bis[i].low > down_bis[i - 1].low for i in range(1, min(4, len(down_bis)))
        )
        if up_highs_ascending and down_lows_ascending:
            return "up"

    # 下降趋势：下降笔低点递减 + 上升笔高点递减
    if len(down_bis) >= 3:
        down_lows_descending = all(
            down_bis[i].low < down_bis[i - 1].low for i in range(1, min(4, len(down_bis)))
        )
        up_highs_descending = len(up_bis) >= 2 and all(
            up_bis[i].high < up_bis[i - 1].high for i in range(1, min(4, len(up_bis)))
        )
        if down_lows_descending and up_highs_descending:
            return "down"

    return None


def _detect_bi_overlap(bis: list[BI]) -> bool:
    """检测是否存在 3 笔构成的价格重叠区间（盘整/中枢特征）。

    V857 偏差15（multi_level subagent 报告偏差6）：原实现逐对相邻笔判
    `prev.low <= curr.high and curr.low <= prev.high`——但缠论笔由顶底
    分型交替构成，相邻笔**必然共享端点分型**，该判据在真实笔序列上恒真，
    无信息量。第17课「向上+向下+向上必然产生中枢」⇒ 改为检测连续 3 笔
    的价格重叠区间（中枢雏形）：区间 = [max(low), min(high)]，存在即重叠。
    """
    if len(bis) < 3:
        return False

    for i in range(2, len(bis)):
        tri = bis[i - 2 : i + 1]
        hi = min(b.high for b in tri)
        lo = max(b.low for b in tri)
        if hi > lo:  # 三笔价格区间有重叠 → 中枢雏形
            return True

    return False


def _check_divergence_condition(
    bis: list[BI],
    zss: list[Any],
) -> bool:
    """检查是否具备背驰条件（改进版）。

    背驰条件：
    1. 至少 2 个中枢（趋势结构）
    2. 有足够的笔（至少 5 笔）
    3. 最后一笔的力度小于前一波同向笔
    """
    if len(zss) < 2 or len(bis) < 5:
        return False

    last_bi = bis[-1]
    # 找最后一笔之前同方向的笔
    for i in range(len(bis) - 3, -1, -1):
        prev_bi = bis[i]
        if prev_bi.direction == last_bi.direction:
            last_force = abs(last_bi.end.k.close - last_bi.start.k.close)
            prev_force = abs(prev_bi.end.k.close - prev_bi.start.k.close)
            if prev_force > 0 and last_force < prev_force * 0.85:
                return True
            break

    return False
