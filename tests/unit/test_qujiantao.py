"""真·区间套（chanlun/qujiantao.py）单元测试。

重点验证与旧「条件205」伪区间套的本质区别：
- **无低级别数据时返回 None / 不编造评分**（qujiantao_for_result 整列 None）。
- 低级别背驰落在高级别笔时间窗口内 → nested=True；窗口外（未来函数）→ 不确认。
- 方向必须一致：买点↔底背驰，卖点↔顶背驰。
"""

from __future__ import annotations

from types import SimpleNamespace

from easy_tdx.chanlun.qujiantao import (
    compute_qujiantao,
    qujiantao_for_result,
)
from easy_tdx.chanlun.types import BC, BI, MMD, BCType, Direction, MMDType


def _fake_bi(start_idx: int, end_idx: int, direction: str = "up") -> BI:
    """构造带 bar_index 的假笔。"""
    start_fx = SimpleNamespace(bar_index=start_idx, k=SimpleNamespace(date=None, close=0.0))
    end_fx = SimpleNamespace(bar_index=end_idx, k=SimpleNamespace(date=None, close=0.0))
    bi = SimpleNamespace()
    bi.start = start_fx
    bi.end = end_fx
    bi.direction = Direction.UP if direction == "up" else Direction.DOWN
    bi.index = end_idx
    return bi


def _fake_mmd(mmd_type: str, bi: BI) -> MMD:
    m = MMD(mmd_type=MMDType(mmd_type), bi=bi)  # type: ignore[arg-type]
    return m


def _fake_bc(curr_direction: str, end_idx: int, bc: bool = True) -> BC:
    """构造低级别背驰：curr 是某方向笔，锚定 end_idx。"""
    curr = _fake_bi(end_idx - 5, end_idx, curr_direction)
    bc_obj = BC(bc_type=BCType.QS, bc=bc, curr=curr)  # type: ignore[arg-type]
    return bc_obj


class TestNoLowLevelReturnsNone:
    """无低级别数据时不编造评分。"""

    def test_compute_qujiantao_no_low_returns_none_like(self) -> None:
        """无低级别数据 → nested=False、method='none'，不构成伪装评分。"""
        m = _fake_mmd("1buy", _fake_bi(0, 10))
        res = compute_qujiantao(m)
        assert res["method"] == "none"
        assert res["nested"] is False
        assert res["score"] == 0.0
        assert "无法做区间套确认" in res["msg"]

    def test_qujiantao_for_result_no_recursion_all_none(self) -> None:
        """无递归级别时整列返回 None。"""
        result = SimpleNamespace(mmds=[_fake_mmd("1buy", _fake_bi(0, 10))], recursive_levels=[])
        res = qujiantao_for_result(result, 0)
        assert res == [None]

    def test_qujiantao_for_result_out_of_range_none(self) -> None:
        """low_level_index 越界 → 全部 None。"""
        low = SimpleNamespace(xds=[], zss=[], bcs=[], mmds=[])
        result = SimpleNamespace(mmds=[_fake_mmd("1buy", _fake_bi(0, 10))], recursive_levels=[low])
        res = qujiantao_for_result(result, 5)
        assert res == [None]


class TestDirectionAlignment:
    """方向必须一致。"""

    def test_buy_needs_bottom_divergence(self) -> None:
        """买点：低级别底背驰（向下笔背驰）→ nested=True。"""
        m = _fake_mmd("1buy", _fake_bi(0, 20))
        bc = _fake_bc("down", 15)  # 向下笔背驰 = 底背驰 → 对应买点
        res = compute_qujiantao(m, bcs_low=[bc])
        assert res["nested"] is True

    def test_buy_with_top_divergence_not_confirmed(self) -> None:
        """买点：低级别顶背驰 → 方向不符，不确认。"""
        m = _fake_mmd("1buy", _fake_bi(0, 20))
        bc = _fake_bc("up", 15)  # 向上笔背驰 = 顶背驰 → 对应卖点，买点不认
        res = compute_qujiantao(m, bcs_low=[bc])
        assert res["nested"] is False

    def test_sell_needs_top_divergence(self) -> None:
        """卖点：低级别顶背驰（向上笔背驰）→ nested=True。"""
        m = _fake_mmd("1sell", _fake_bi(0, 20))
        bc = _fake_bc("up", 15)
        res = compute_qujiantao(m, bcs_low=[bc])
        assert res["nested"] is True


class TestTimeWindow:
    """时间锚定（防未来函数）。"""

    def test_bc_after_signal_not_confirmed(self) -> None:
        """低级别背驰在信号笔结束之后 → 未来函数 → 不确认。"""
        m = _fake_mmd("1buy", _fake_bi(0, 20))
        bc = _fake_bc("down", 25)  # 25 > 20，信号之后
        res = compute_qujiantao(m, bcs_low=[bc])
        assert res["nested"] is False

    def test_bc_before_signal_window_confirmed(self) -> None:
        """低级别背驰在信号笔区间内 → 确认。"""
        m = _fake_mmd("1buy", _fake_bi(10, 30))
        bc = _fake_bc("down", 20)  # 在区间内
        res = compute_qujiantao(m, bcs_low=[bc])
        assert res["nested"] is True

    def test_bc_non_divergent_not_confirmed(self) -> None:
        """低级别结构虽在窗口但 bc=False（非真背驰）→ 不确认。"""
        m = _fake_mmd("1buy", _fake_bi(10, 30))
        bc = _fake_bc("down", 20)
        bc.bc = False
        res = compute_qujiantao(m, bcs_low=[bc])
        # bc=False → bc 字段 None → 仅靠 mmds_low 兜底；这里没给 mmds_low
        assert res["nested"] is False


class TestScoring:
    """评分与置信度调整。"""

    def test_strong_confirmation_score(self) -> None:
        """窗口内同方向背驰 + ≥2 中枢 + ≥3 笔 → 高分 +0.08。"""
        m = _fake_mmd("1buy", _fake_bi(0, 40))
        bc = _fake_bc("down", 30)
        zss = [
            SimpleNamespace(start=SimpleNamespace(bar_index=5), end=SimpleNamespace(bar_index=15)),
            SimpleNamespace(start=SimpleNamespace(bar_index=20), end=SimpleNamespace(bar_index=35)),
        ]
        bis = [_fake_bi(i, i + 5) for i in range(0, 36, 5)]
        res = compute_qujiantao(m, bis_low=bis, zss_low=zss, bcs_low=[bc])
        assert res["nested"] is True
        assert res["score"] >= 0.8
        assert res["confidence_adjust"] == 0.08

    def test_no_confirmation_negative_adjust(self) -> None:
        """未确认 → 置信度微降 -0.02。"""
        m = _fake_mmd("1sell", _fake_bi(0, 20))
        res = compute_qujiantao(m, bis_low=[_fake_bi(0, 5)])
        assert res["nested"] is False
        assert res["confidence_adjust"] == -0.02


class TestIntegration:
    """与真实 ChanlunAnalyser 集成。"""

    def test_recursive_backed_qujiantao_on_synthetic(self) -> None:
        """用真实 analyser + 递归级别给 MMD 算真区间套。"""
        import numpy as np
        import pandas as pd

        from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

        rng = np.random.default_rng(7)
        n = 600
        base = np.maximum(10.0 + np.cumsum(rng.normal(0.05, 0.5, n)), 1.0)
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2020-01-01", periods=n, freq="D"),
                "open": base + rng.uniform(-0.1, 0.1, n),
                "close": base + rng.uniform(-0.1, 0.1, n),
                "high": base + rng.uniform(0, 0.3, n),
                "low": base - rng.uniform(0, 0.3, n),
                "vol": [1_000_000.0] * n,
                "amount": [10_000_000.0] * n,
            }
        )
        r = ChanlunAnalyser(
            code="T", frequency="daily", config=ChanlunConfig(recursion_depth=2, zs_from_xd=False)
        ).process_klines(df)
        assert len(r.recursive_levels) >= 1
        for m in r.mmds:
            # 每个 MMD 都有 _qujiantao 字段（dict 或 None）
            qt = getattr(m, "_qujiantao", "MISSING")
            assert qt is not None, "缺少 _qujiantao 字段"
            assert isinstance(qt, dict)
            assert "nested" in qt and "score" in qt


class TestMethodLabeling:
    """method 字段语义（V-26 bad-first）。

    method 必须如实区分数据来源：
    - "cross_period": 调用方显式给了跨周期 mmds_low 列表（compute_qujiantao_cross_period 路径）
    - "recursive":  qujiantao_for_result 的递归级别路径（即使低级别 mmds 为空列表）
    - "single":     只有 zss_low / bis_low 等部分结构
    - "none":       完全无低级别数据

    修复前 bug：method 由 ``mmds_low is not None`` 判定，而 qujiantao_for_result
    恒传列表（空列表也非 None）→ 递归结果被误标为 "cross_period"。
    """

    def test_qujiantao_for_result_method_is_recursive(self) -> None:
        """递归路径的 method 必须是 'recursive'（修复前误标 cross_period）。"""
        low = SimpleNamespace(xds=[], zss=[], bcs=[], mmds=[])
        result = SimpleNamespace(mmds=[_fake_mmd("1buy", _fake_bi(0, 10))], recursive_levels=[low])
        res = qujiantao_for_result(result, 0)
        assert len(res) == 1 and res[0] is not None
        assert res[0]["method"] == "recursive"

    def test_explicit_mmds_low_is_cross_period(self) -> None:
        """对照组：显式传入跨周期结构（含 mmds_low 列表）→ 'cross_period' 不变。"""
        m = _fake_mmd("1buy", _fake_bi(0, 10))
        res = compute_qujiantao(
            m,
            bis_low=[_fake_bi(2, 6)],
            zss_low=[],
            bcs_low=[],
            mmds_low=[],
        )
        assert res["method"] == "cross_period"

    def test_partial_structure_is_single(self) -> None:
        """只给中枢不给 mmds_low → 'single'（既有语义，防回归）。"""
        m = _fake_mmd("1buy", _fake_bi(0, 10))
        res = compute_qujiantao(m, zss_low=[], mmds_low=None)
        assert res["method"] == "single"
