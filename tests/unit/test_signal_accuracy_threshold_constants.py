"""V733 审计：signal_accuracy 的「显著性」阈值必须**引用**常量，不能裸写。

背景（2026-10-08 实测）：模块里 0.05 / -0.05 / 0.03 三个数字散落 4 处裸写。
其中 0.05（单标的判定）与 0.03（组合口径判定）**同时存在**，读起来像"写错了
却说不清哪个对"。本次把两者**分别命名**（`_EXCESS_SIGNIFICANT` /
`_EXCESS_PORTFOLIO_SIGNIFICANT`）而非强行合并 —— 因为两者语义确实不同：
组合跨标的平均后噪声被平滑，可以用更严（更小）的门槛。

本测试锁定的是**"判定跟随常量"**这一事实，而不是某个具体数字：
改常量 ⇒ 判定门槛必须跟着移动。若有人再把数字写死回去，下面第 3 条会红。
"""

from __future__ import annotations

import pytest

from easy_tdx.backtest import signal_accuracy as SA


def _report(
    excess: float,
    n: int = 50,
    baseline_hit_rate: float = 0.5,
) -> dict:
    """构造 _build_verdict 所需的 **buy_report**（horizons 的键是**字符串**）。

    V736：必须带 ``baseline_hit_rate``。修复「n=1 也能判显著」之后，
    「显著」还要过样本量关与 z 检验关，而 z 检验要用基线命中率算标准误 ——
    缺该字段时实现兜底 0.5，会让效应量刚过门槛的用例算不出显著。
    """
    return {
        "horizons": {
            "5": {
                "excess_hit_rate": excess,
                "avg_return": 0.0,
                "count": n,
                "baseline_hit_rate": baseline_hit_rate,
            }
        }
    }


def _portfolio(avg_excess: float) -> dict:
    """构造 _build_portfolio_verdict 所需的最小 portfolio。"""
    return {
        "symbols": 30,                  # 必填：int(portfolio["symbols"])
        "symbols_with_accuracy": 30,    # 决定 hit_n > 0，否则命中率段整段跳过
        "avg_excess_hit_rate": avg_excess,
        "avg_hit_rate": 0.5,
        "positive_symbols": 20,
        "hit_above_baseline": 18,
    }


class TestExcessThresholdFollowsConstant:
    def test_boundary_at_constant_is_not_significant(self) -> None:
        """excess 恰等于常量 ⇒ 不算「显著」（代码是严格 >）。"""
        v = SA._build_verdict(_report(SA._EXCESS_SIGNIFICANT), buy_hold_return=0.0)
        assert "显著高于" not in v

    def test_just_above_constant_is_significant(self) -> None:
        """效应量刚过常量 ⇒ 显著（前提是样本量与 z 检验也过关）。

        V736：本用例原本用默认 n=50，但修复后 n=50 时 excess=0.05 的
        z = 0.05 / sqrt(0.25/50) ≈ 0.71 < 1.96 —— **本来就不该判显著**。
        旧断言固化了「裸阈值即显著」的 bug，现改用足够大的 n（500，
        z ≈ 2.24 ≥ 1.96）以检验真正的意图：判定跟随常量而非写死。
        """
        v = SA._build_verdict(
            _report(SA._EXCESS_SIGNIFICANT + 1e-9, n=500), buy_hold_return=0.0
        )
        assert "显著高于" in v, v

    def test_threshold_moves_when_constant_changes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """牙齿所在：改常量 ⇒ 单标的判定门槛必须跟着移动。

        取鉴别值 0.04：
        - 真实常量 0.05 ⇒ 0.04 **不**显著（对照组）
        - 把常量改成 0.02 ⇒ 0.04 必须显著
        两端都断言，才能证明"判定跟随常量"而非恰好蒙对。
        若有人把 0.05 写死回代码里，第二条立刻失败。
        """
        # 对照组（n=1000 让 z 检验不是瓶颈，只考察效应量门槛这一变量）
        # 注：excess=0.04 时需 n ≥ (1.96*0.5/0.04)² ≈ 600 才能让 z ≥ 1.96，
        # 故取 1000（z ≈ 2.53）—— 否则 z 检验会抢先否决，测不到常量门槛。
        assert "显著高于" not in SA._build_verdict(
            _report(0.04, n=1000), buy_hold_return=0.0
        )

        monkeypatch.setattr(SA, "_EXCESS_SIGNIFICANT", 0.02)
        assert "显著高于" in SA._build_verdict(_report(0.04, n=1000), buy_hold_return=0.0), (
            "常量下调后 0.04 应变为显著 —— 若失败说明判定又写死成 0.05 了"
        )

    def test_portfolio_threshold_is_independently_named(self) -> None:
        """组合口径用**自己的**常量，且与单标的是两个不同的值（语义不同）。"""
        assert SA._EXCESS_PORTFOLIO_SIGNIFICANT != SA._EXCESS_SIGNIFICANT, (
            "两者语义不同（组合噪声已平滑，可取更严门槛）；若被统一请同时改注释"
        )

    def test_portfolio_threshold_moves_when_constant_changes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """牙齿：组合口径同理，改常量 ⇒ 门槛跟着移动。"""
        # 对照组：真实常量 0.03 ⇒ 0.04 已超过 ⇒ 给出「高于随机」
        assert "高于随机入场基准" in SA._build_portfolio_verdict(_portfolio(0.04))

        monkeypatch.setattr(SA, "_EXCESS_PORTFOLIO_SIGNIFICANT", 0.10)
        v = SA._build_portfolio_verdict(_portfolio(0.04))
        assert "高于随机入场基准" not in v, (
            f"常量上调到 0.10 后 0.04 不应再算高于随机 —— 判定写死了？got: {v}"
        )
