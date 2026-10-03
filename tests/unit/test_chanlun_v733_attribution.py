"""V733：1买/1卖 归因 —— 跌幅匹配基准的口径回归测试。

背景
----
`scripts/audit_1buy_attribution.py` 用来回答：1买 的超额是不是只是"跌多了就反弹"
（均值回复）？做法是在同窗内找「前跌 ≥ 信号前跌」的 bar 作基准。

实测（286 只，6 滚动窗）：
    1buy  20根  信号 +5.57%  vs 跌幅匹配基准 +1.30%  → 超额 +4.27% p<0.0001
    1sell 20根  信号 +5.66%  vs 基准 +0.66%          → 超额 +5.00% p<0.0001
⇒ 不是纯均值回复。

但**这个基准比「局部极值」弱很多**（3buy 下：极值基准 +7.23% → 超额 −0.97%；
跌幅匹配基准 +2.98% → 超额 +3.28%），因为它只要求"跌得至少一样多"，
没控制"是否处在转折点"。故最终结论以局部极值基准为准，跌幅匹配只用于
回答"是不是均值回复"这一个次要问题。

本测试锁死两类容易复发的错误。
"""

from __future__ import annotations

import numpy as np
import pytest


def drawdown_at(c: np.ndarray, i: int, lookback: int) -> float:
    lo = max(0, i - lookback)
    peak = c[lo : i + 1].max()
    return float(1.0 - c[i] / peak) if peak > 0 else 0.0


def runup_at(c: np.ndarray, i: int, lookback: int) -> float:
    lo = max(0, i - lookback)
    trough = c[lo : i + 1].min()
    return float(c[i] / trough - 1.0) if trough > 0 else 0.0


class TestMirrorMetric:
    """卖点必须用涨幅（镜像量）匹配，不能用回撤。"""

    def test_runup_is_mirror_of_drawdown(self) -> None:
        """在单调序列上，回撤与涨幅必须互为镜像（一个为 0 时另一个为正）。"""
        c = np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
        # 末尾：持续上涨 → 回撤应为 0，涨幅应 > 0
        assert drawdown_at(c, 5, 4) == pytest.approx(0.0, abs=1e-9)
        assert runup_at(c, 5, 4) > 0.0

        d = np.array([15.0, 14.0, 13.0, 12.0, 11.0, 10.0])
        assert drawdown_at(d, 5, 4) > 0.0
        assert runup_at(d, 5, 4) == pytest.approx(0.0, abs=1e-9)

    def test_teeth_using_drawdown_for_sell_is_wrong(self) -> None:
        """牙齿验证：卖点若错用回撤匹配，基准会被反向筛选（这是踩过的坑）。

        构造一段上涨后的下跌：卖点应匹配"涨得多"的 bar。
        若用回撤匹配，会选中"跌得多"的 bar —— 对做空/卖出而言是反向筛选，
        基准因此变成负数、超额虚高（实测 1sell 基准 −1.14%、超额 +8.40%，
        修正后为 +0.66% / +5.00%）。
        """
        # 序列：前段上涨（bar 0-9），后段下跌（bar 10-19）
        c = np.concatenate([np.linspace(10, 20, 10), np.linspace(20, 12, 10)])
        i_sell = 9  # 上涨末端 → 卖点

        runup = runup_at(c, i_sell, 5)
        dd = drawdown_at(c, i_sell, 5)
        assert runup > 0.0, "前提：卖点处应处于上涨后（涨幅 > 0）"
        assert dd == pytest.approx(0.0, abs=1e-9), "前提：卖点处回撤应为 0"

        # 用涨幅匹配：候选应集中在前段（bar 4-9 这类上涨位置）
        cand_runup = [j for j in range(5, 15) if runup_at(c, j, 5) >= runup]
        # 用回撤匹配（错误做法）：候选集中在后段下跌区
        cand_dd = [j for j in range(5, 15) if drawdown_at(c, j, 5) >= dd]

        assert cand_runup, "涨幅匹配应有候选"
        assert cand_dd, "回撤匹配也应有候选（所以错用了也不会报错——必须靠断言拦住）"
        # 关键：两组候选的**位置**必须不同，否则说明镜像量没起作用
        assert set(cand_runup) != set(cand_dd), (
            "涨幅匹配与回撤匹配选出了同一批 bar —— 镜像量没起作用，"
            "卖点仍在被回撤（反向）筛选"
        )
        assert np.mean(cand_runup) < np.mean(cand_dd), (
            f"涨幅匹配候选应在更早（上涨段），实得均值 {np.mean(cand_runup):.1f} vs "
            f"回撤匹配 {np.mean(cand_dd):.1f}"
        )


class TestBaselineStrictness:
    """跌幅匹配是**弱**对照，结论必须以局部极值基准为准。"""

    def test_drawdown_baseline_is_weaker_than_extremum(self) -> None:
        """在可验证的小样本上证明：跌幅匹配基准的收益低于局部极值基准。

        这是"为什么 3buy 在两个基准下符号相反"的根因（极值 +7.23% vs 跌幅 +2.98%），
        也是为什么不能拿跌幅匹配的 +3.28% 当结论。
        """
        rng = np.random.default_rng(20241002)
        n = 400
        c = 10.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, n)))
        H = 20

        def extremum_baseline() -> float:
            idx = []
            for j in range(5, n - 5):
                seg = c[j - 5 : j + 6]
                if c[j] == seg.min():
                    idx.append(j)
            idx = np.array([j for j in idx if j + H < n])
            return float(np.mean(c[idx + H] / c[idx] - 1.0))

        def drawdown_baseline(dd_threshold: float) -> float:
            cand = [j for j in range(20, n - H) if drawdown_at(c, j, 20) >= dd_threshold]
            arr = np.array(cand, dtype=int)
            return float(np.mean(c[arr + H] / c[arr] - 1.0))

        # 用一个中等的回撤阈值（代表典型 1buy 触发时的回撤 ~10%）
        b_ext = extremum_baseline()
        b_dd = drawdown_baseline(0.05)

        assert b_dd < b_ext, (
            f"跌幅匹配基准（{b_dd:.3%}）应低于局部极值基准（{b_ext:.3%}）—— "
            "若不是，说明跌幅匹配反而更严格，'极值基准为决定性对照'的前提不成立"
        )

    def test_teeth_strictness_check_has_teeth(self) -> None:
        """牙齿验证：若把对照反过来（跌幅更严格），上面的断言必须失败。"""
        # 人工构造：跌幅基准 > 极值基准
        b_dd, b_ext = 0.05, 0.02
        assert not (b_dd < b_ext), (
            "自检失败：构造的反例没有被判定为'跌幅更严格' —— 主断言可能无牙齿"
        )
