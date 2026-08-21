"""多级别联立分析。

支持同时分析多个 K 线周期（如日线 + 30 分钟）的缠论数据，
查看高级别笔在低级别中的走势结构，辅助判断买卖点的有效性。
"""

from __future__ import annotations

from typing import Any

from easy_tdx.chanlun.analyser import ChanlunAnalyser, ChanlunResult
from easy_tdx.chanlun.types import BI


class MultiLevelAnalyser:
    """多级别缠论分析器。

    管理多个 ChanlunAnalyser 实例，每个对应一个 K 线周期。
    支持跨级别查询：高级别笔对应的低级别走势信息。

    用法::

        mla = MultiLevelAnalyser()
        mla.add_level("daily", ChanlunAnalyser("SZ000001", "DAILY"))
        mla.add_level("30min", ChanlunAnalyser("SZ000001", "30MIN"))
        mla.process("daily", df_daily)
        mla.process("30min", df_30min)

        # 查看日线最后一笔在 30 分钟级别中的走势
        info = mla.query_low_level_qs("daily", "30min", last_bi)
    """

    def __init__(self) -> None:
        self._analysers: dict[str, ChanlunAnalyser] = {}

    def add_level(self, name: str, analyser: ChanlunAnalyser) -> None:
        """添加一个分析级别。

        Args:
            name: 级别名称（如 "daily", "30min"）
            analyser: 对应的 ChanlunAnalyser 实例
        """
        self._analysers[name] = analyser

    def process(self, level: str, df: object) -> ChanlunResult:
        """处理指定级别的 K 线数据。

        Args:
            level: 级别名称
            df: K 线 DataFrame

        Returns:
            该级别的缠论分析结果
        """
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
        """计算多级别一致性评分。

        比较高级别和低级别的买卖点信号，判断是否存在区间套确认。
        返回综合评分和各子评分。

        Returns:
            dict with keys:
                score: 综合一致性评分 0-1
                high_level_signal: 高级别最近买卖点信息
                low_level_signal: 低级别最近买卖点信息
                trend_aligned: 趋势方向是否一致
                zs_aligned: 中枢位置是否合理
                time_aligned: 时间窗口是否重叠
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

        # 获取高级别最近买卖点
        high_mmds = sorted(high_result.mmds, key=lambda m: m.bi.index if m.bi else 0)
        low_mmds = sorted(low_result.mmds, key=lambda m: m.bi.index if m.bi else 0)

        if not high_mmds or not low_mmds:
            return empty

        latest_high = high_mmds[-1]
        latest_low = low_mmds[-1]

        # 1. 趋势对齐检查
        high_trend = _detect_trend_direction(high_result.bis)
        low_trend = _detect_trend_direction(low_result.bis)
        trend_aligned = False
        if high_trend and low_trend:
            # 买信号：高低级别都看涨；卖信号：都看跌
            high_is_buy = latest_high.mmd_type.value in ("1buy", "2buy", "3buy", "2buy_s")
            low_is_buy = latest_low.mmd_type.value in ("1buy", "2buy", "3buy", "2buy_s")
            high_is_sell = latest_high.mmd_type.value in ("1sell", "2sell", "3sell", "2sell_s")
            low_is_sell = latest_low.mmd_type.value in ("1sell", "2sell", "3sell", "2sell_s")
            if (high_is_buy and low_is_buy and high_trend == "up" and low_trend == "up"):
                trend_aligned = True
            elif (high_is_sell and low_is_sell and high_trend == "down" and low_trend == "down"):
                trend_aligned = True

        # 2. 中枢对齐检查
        zs_aligned = False
        if latest_high.bi and latest_low.bi:
            # 检查低级别中枢是否与高级别买卖点时间重叠
            high_bi_start = latest_high.bi.start.k.date
            high_bi_end = latest_high.bi.end.k.date
            for zs in low_result.zss:
                if zs.start and zs.end:
                    zs_start = zs.start.k.date
                    zs_end = zs.end.k.date
                    if zs_start <= high_bi_end and zs_end >= high_bi_start:
                        zs_aligned = True
                        break

        # 3. 时间窗口对齐
        time_aligned = False
        if latest_high.bi and latest_low.bi:
            high_end = latest_high.bi.end.k.date
            low_end = latest_low.bi.end.k.date
            # 允许低级别信号在高级别信号前后5根K线内
            time_aligned = abs((high_end - low_end).days) <= 5

        # 综合评分
        components = []
        if trend_aligned:
            components.append(0.4)
        if zs_aligned:
            components.append(0.3)
        if time_aligned:
            components.append(0.3)

        # V4 质量加成：高质量买卖点（S/A）在区间套中权重更高
        def _grade_factor(grade: str | None) -> float:
            """将质量评级转换为加成系数。"""
            if not grade:
                return 0.8
            map_ = {"S": 1.2, "A": 1.1, "B": 1.0, "C": 0.85, "D": 0.7}
            return map_.get(grade, 0.8)

        high_grade = getattr(getattr(latest_high, "quality", None), "grade", None)
        low_grade = getattr(getattr(latest_low, "quality", None), "grade", None)
        grade_factor = (_grade_factor(high_grade) + _grade_factor(low_grade)) / 2

        # 基础分：取高、低级别的平均置信度，乘以质量加成
        base_score = (latest_high.confidence + latest_low.confidence) / 2
        weighted_components = sum(components) if components else 0.5
        confluence_score = base_score * weighted_components * grade_factor

        return {
            "score": round(confluence_score, 2),
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
        }

    def query_low_level_qs(
        self,
        high_level: str,
        low_level: str,
        high_bi: BI,
    ) -> dict[str, Any]:
        """查询高级别笔在低级别中的走势信息。

        查找低级别中时间范围落在高级别笔内的所有笔和中枢，
        分析趋势方向、笔重叠（盘整特征）和背驰条件。

        Args:
            high_level: 高级别名称
            low_level: 低级别名称
            high_bi: 高级别的笔

        Returns:
            dict with keys:
                bi_count: 低级别笔数
                zs_count: 低级别中枢数
                has_trend: 是否形成趋势 (>=2 个中枢)
                has_consolidation: 是否形成盘整 (>=1 个中枢)
                trend_direction: 趋势方向 ("up"/"down"/None)
                bi_overlap: 相邻笔是否有重叠 (盘整特征)
                divergence_possible: 是否具备背驰条件
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

        # 高级别笔的时间范围（使用原始K线时间）
        start_date = high_bi.start.k.date
        end_date = high_bi.end.k.date

        # 筛选低级别中时间范围内的笔
        # 放宽匹配：只要低级别笔与高级别笔的时间范围有交集
        low_bis = []
        for bi in low_result.bis:
            bi_start = bi.start.k.date
            bi_end = bi.end.k.date
            # 笔与范围有重叠
            if bi_start <= end_date and bi_end >= start_date:
                low_bis.append(bi)

        # 筛选低级别中枢
        low_zss = []
        for zs in low_result.zss:
            if zs.start is None or zs.end is None:
                continue
            zs_start = zs.start.k.date
            zs_end = zs.end.k.date
            # 中枢与范围有重叠
            if zs_start <= end_date and zs_end >= start_date:
                low_zss.append(zs)

        has_trend = len(low_zss) >= 2
        has_consolidation = len(low_zss) >= 1

        # 趋势方向判断：连续笔的高低点是否递增或递减
        trend_direction = _detect_trend_direction(low_bis)

        # 笔重叠判断：相邻笔的价格区间是否重叠
        bi_overlap = _detect_bi_overlap(low_bis)

        # 背驰条件：至少 2 个中枢 + 最后一笔进入最后一个中枢
        divergence_possible = _check_divergence_condition(low_bis, low_zss)

        return {
            "bi_count": len(low_bis),
            "zs_count": len(low_zss),
            "has_trend": has_trend,
            "has_consolidation": has_consolidation,
            "trend_direction": trend_direction,
            "bi_overlap": bi_overlap,
            "divergence_possible": divergence_possible,
        }


def _detect_trend_direction(bis: list[BI]) -> str | None:
    """判断笔序列的趋势方向。

    如果连续 3 笔以上高点递增且低点递增 → 上升趋势。
    如果连续 3 笔以上高点递减且低点递减 → 下降趋势。
    否则 → None（盘整或数据不足）。

    Args:
        bis: 低级别笔列表

    Returns:
        "up", "down", 或 None
    """
    if len(bis) < 3:
        return None

    # 取偶数索引笔（上升笔）和奇数索引笔（下降笔）的高低点
    up_bis = bis[0::2]  # 上升笔
    down_bis = bis[1::2]  # 下降笔

    # 上升趋势：上升笔高点递增 + 下降笔低点递增
    up_highs_ascending = all(up_bis[i].high > up_bis[i - 1].high for i in range(1, len(up_bis)))
    down_lows_ascending = len(down_bis) >= 2 and all(
        down_bis[i].low > down_bis[i - 1].low for i in range(1, len(down_bis))
    )

    if up_highs_ascending and (len(down_bis) < 2 or down_lows_ascending):
        return "up"

    # 下降趋势：下降笔低点递减 + 上升笔高点递减
    down_lows_descending = all(
        down_bis[i].low < down_bis[i - 1].low for i in range(1, len(down_bis))
    )
    up_highs_descending = len(up_bis) >= 2 and all(
        up_bis[i].high < up_bis[i - 1].high for i in range(1, len(up_bis))
    )

    if down_lows_descending and (len(up_bis) < 2 or up_highs_descending):
        return "down"

    return None


def _detect_bi_overlap(bis: list[BI]) -> bool:
    """检测相邻笔是否有价格重叠（盘整特征）。

    两笔重叠 = 一笔的低点 <= 另一笔的高点（反向）。
    如果存在重叠 → 盘整，不重叠 → 趋势。

    Args:
        bis: 低级别笔列表

    Returns:
        True 如果存在相邻笔重叠
    """
    if len(bis) < 2:
        return False

    for i in range(1, len(bis)):
        prev = bis[i - 1]
        curr = bis[i]
        # 两笔重叠：前笔低点 <= 后笔高点 且 后笔低点 <= 前笔高点
        if prev.low <= curr.high and curr.low <= prev.high:
            return True

    return False


def _check_divergence_condition(
    bis: list[BI],
    zss: list[Any],
) -> bool:
    """检查是否具备背驰条件。

    背驰条件（简化版）：
    1. 至少 2 个中枢（趋势结构）
    2. 有足够的笔（至少 5 笔，即 a+A0+b+A1+c 结构）
    3. 最后一笔的斜率或幅度小于前一笔（力度衰减）

    Args:
        bis: 低级别笔列表
        zss: 低级别中枢列表

    Returns:
        True 如果可能形成背驰
    """
    if len(zss) < 2 or len(bis) < 5:
        return False

    # 简化背驰判断：最后一笔的幅度 < 倒数第三笔的幅度
    # （倒数第三笔是与最后一笔同方向的笔）
    last_bi = bis[-1]
    for i in range(len(bis) - 3, -1, -2):
        prev_bi = bis[i]
        # 比较同方向笔的幅度
        last_amp = abs(last_bi.end.k.close - last_bi.start.k.close)
        prev_amp = abs(prev_bi.end.k.close - prev_bi.start.k.close)
        if prev_amp > 0 and last_amp < prev_amp:
            return True
        break

    return False
