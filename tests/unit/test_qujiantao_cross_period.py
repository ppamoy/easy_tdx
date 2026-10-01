"""跨周期真区间套测试（缠论原文语义：日线信号 + 30分钟真实结构确认）。

重点：
1. 用**两份独立行情**（高级别日线 / 低级别30分钟），而非同序列递归。
2. 时间对齐按**行情时间重叠**（不是 bar_index）。
3. 防未来函数：低周期结构结束时间不得晚于高级别信号笔结束。
4. 无低周期数据时返回 None，不编造评分。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace as NS

from easy_tdx.chanlun.qujiantao import compute_qujiantao_cross_period


def _mk_bi(sd: datetime, ed: datetime, direction: str = "up", val_s=1.0, val_e=2.0):
    """构造带时间的假笔：start/end 是分型，分型的 k.date 是时间锚点。"""
    s = NS(k=NS(date=sd), val=val_s)
    e = NS(k=NS(date=ed), val=val_e)
    return NS(start=s, end=e, direction=NS(value=direction))


def _mk_mmd(t: str, bi):
    return NS(bi=bi, mmd_type=NS(value=t))


def _mk_bc(bi, bc: bool = True):
    return NS(curr=bi, bc=bc, bc_type=NS(value="BI"))


D0 = datetime(2024, 1, 1)


class TestCrossPeriod:
    def test_no_low_data_returns_none(self):
        """无低周期数据 → 全部 None（不编造评分）。"""
        hi = _mk_mmd("1buy", _mk_bi(D0, D0 + timedelta(days=10)))
        assert compute_qujiantao_cross_period([hi]) == [None]

    def test_buy_confirmed_by_low_bottom_divergence(self):
        """买点：低周期窗口内出现底背驰（向下笔）→ 确认。"""
        hi = _mk_mmd("1buy", _mk_bi(D0, D0 + timedelta(days=10)))
        # 低周期底背驰：curr 向下笔，落在窗口内且不晚于窗口结束
        low_bi = _mk_bi(D0 + timedelta(days=2), D0 + timedelta(days=6), "down")
        res = compute_qujiantao_cross_period([hi], bcs_low=[_mk_bc(low_bi)])[0]
        assert res["nested"] is True
        assert res["method"] == "cross_period"

    def test_buy_not_confirmed_by_top_divergence(self):
        """买点：低周期是顶背驰（向上笔）→ 方向不符，不确认。"""
        hi = _mk_mmd("1buy", _mk_bi(D0, D0 + timedelta(days=10)))
        low_bi = _mk_bi(D0 + timedelta(days=2), D0 + timedelta(days=6), "up")
        res = compute_qujiantao_cross_period([hi], bcs_low=[_mk_bc(low_bi)])[0]
        assert res["nested"] is False

    def test_future_function_rejected(self):
        """低周期背驰结束晚于高级别信号 → 未来函数 → 不确认。"""
        hi = _mk_mmd("1buy", _mk_bi(D0, D0 + timedelta(days=10)))
        # 结束在窗口之后
        low_bi = _mk_bi(D0 + timedelta(days=5), D0 + timedelta(days=20), "down")
        res = compute_qujiantao_cross_period([hi], bcs_low=[_mk_bc(low_bi)])[0]
        assert res["nested"] is False

    def test_outside_window_not_confirmed(self):
        """低周期结构完全在窗口之前 → 不确认。"""
        hi = _mk_mmd("1buy", _mk_bi(D0 + timedelta(days=50), D0 + timedelta(days=60)))
        low_bi = _mk_bi(D0 + timedelta(days=2), D0 + timedelta(days=6), "down")
        res = compute_qujiantao_cross_period([hi], bcs_low=[_mk_bc(low_bi)])[0]
        assert res["nested"] is False

    def test_time_alignment_not_bar_index(self):
        """验证用时间对齐而非 bar_index：低周期笔时间与窗口相交即算。

        低周期笔横跨窗口边界（部分重叠）应被计入。
        """
        hi = _mk_mmd("1sell", _mk_bi(D0 + timedelta(days=5), D0 + timedelta(days=15)))
        # 低周期笔 从 day1 到 day8：与窗口 [5,15] 相交
        low_bi = _mk_bi(D0 + timedelta(days=1), D0 + timedelta(days=8), "up")
        res = compute_qujiantao_cross_period([hi], bcs_low=[_mk_bc(low_bi)], bis_low=[low_bi])[0]
        # 卖点需要顶背驰（up）→ 确认；且该笔被计为窗口内低周期笔
        assert res["nested"] is True
        assert res["detail"]["low_bi_count"] == 1

    def test_sell_confirmed_by_top_divergence(self):
        """卖点：低周期顶背驰（向上笔）→ 确认。"""
        hi = _mk_mmd("1sell", _mk_bi(D0, D0 + timedelta(days=10)))
        low_bi = _mk_bi(D0 + timedelta(days=3), D0 + timedelta(days=7), "up")
        res = compute_qujiantao_cross_period([hi], bcs_low=[_mk_bc(low_bi)])[0]
        assert res["nested"] is True

    def test_low_mmd_secondary_confirmation(self):
        """无背驰但窗口内有同方向低周期买卖点 → 次一级确认。"""
        hi = _mk_mmd("1buy", _mk_bi(D0, D0 + timedelta(days=10)))
        low_bi = _mk_bi(D0 + timedelta(days=2), D0 + timedelta(days=6), "down")
        res = compute_qujiantao_cross_period([hi], mmds_low=[_mk_mmd("2buy", low_bi)])[0]
        assert res["nested"] is True
        assert res["score"] > 0

    def test_no_bi_mmd_returns_none(self):
        """高级别信号没有锚定笔 → None。"""
        hi = _mk_mmd("1buy", None)
        low_bi = _mk_bi(D0, D0 + timedelta(days=5), "down")
        assert compute_qujiantao_cross_period([hi], bcs_low=[_mk_bc(low_bi)]) == [None]


class TestCrossPeriodCausalCounting:
    """V-18 因果性修复：bi_count/zs_count 只计**结束不晚于信号笔结束**的结构。

    实测背景（000001 日线×30分钟，2000 根）：相交口径下 19% 的低周期笔
    结束晚于高级别信号笔——它们携带的是信号之后才走出的信息，计入
    score 等于用未来信息给历史信号加分。
    """

    def test_bi_ending_after_signal_excluded_from_count(self):
        """低周期笔结束晚于信号笔结束 → 不得计入 low_bi_count。"""
        hi = _mk_mmd("1sell", _mk_bi(D0 + timedelta(days=5), D0 + timedelta(days=15)))
        # 该笔结束在 day20 > 窗口结束 day15：相交但越界
        late_bi = _mk_bi(D0 + timedelta(days=12), D0 + timedelta(days=20), "up")
        res = compute_qujiantao_cross_period([hi], bis_low=[late_bi])[0]
        assert res["detail"]["low_bi_count"] == 0
        # score 只剩 0（≥3 笔才 +0.2）
        assert res["score"] == 0.0

    def test_bi_ending_within_signal_counted(self):
        """结束在窗口内的低周期笔照常计入（回归对照）。"""
        hi = _mk_mmd("1sell", _mk_bi(D0 + timedelta(days=5), D0 + timedelta(days=15)))
        ok_bi = _mk_bi(D0 + timedelta(days=6), D0 + timedelta(days=10), "up")
        res = compute_qujiantao_cross_period([hi], bis_low=[ok_bi])[0]
        assert res["detail"]["low_bi_count"] == 1

    def test_zs_ending_after_signal_excluded_from_count(self):
        """低周期中枢结束晚于信号笔结束 → 不得计入 low_zs_count。"""
        hi = _mk_mmd("1buy", _mk_bi(D0, D0 + timedelta(days=10)))
        late_zs = NS(
            start=NS(k=NS(date=D0 + timedelta(days=1))),
            end=NS(k=NS(date=D0 + timedelta(days=18))),
        )
        res = compute_qujiantao_cross_period([hi], zss_low=[late_zs])[0]
        assert res["detail"]["low_zs_count"] == 0

    def test_zs_ending_within_signal_counted(self):
        """结束在窗口内的低周期中枢照常计入（回归对照）。"""
        hi = _mk_mmd("1buy", _mk_bi(D0, D0 + timedelta(days=10)))
        ok_zs = NS(
            start=NS(k=NS(date=D0 + timedelta(days=2))),
            end=NS(k=NS(date=D0 + timedelta(days=8))),
        )
        res = compute_qujiantao_cross_period([hi], zss_low=[ok_zs])[0]
        assert res["detail"]["low_zs_count"] == 1
