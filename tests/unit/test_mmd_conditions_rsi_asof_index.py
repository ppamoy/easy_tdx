"""V731：`_calc_rsi` / `_calc_rsi_momentum` 按"截至位置"取值的回归测试。

缺陷（由 ``scripts/verify_confidence_drift_bisect.py`` 因果二分定位）

置信度前视残留里，**RSI 单独占 60%**（总偏差 0.025 中贡献 0.015）。两个问题：

1. ``_calc_rsi(closes, period=14)`` 内部固定 ``range(-period, 0)`` —— 永远取
   **序列最后 period 根**。给历史信号打分时，等于用信号之后的未来数据。
2. 更隐蔽：调用点写成 ``_calc_rsi(closes, bi_end_idx)``，本意传"截至位置"
   （其上一行 ``_calc_adx_strength(..., bi_end_idx)`` 确实支持按位置取，可见原意），
   但因为当时没有 idx 形参，**bi_end_idx 被当成 period** —— 位置也错、周期也错。

修复：两者新增 ``idx`` 形参，``None`` 保留序列末尾行为（实时语境合法，且现有
调用点 12713/20900 不受影响）；置信度里的历史信号调用改为传 ``idx=bi_end_idx``。

实测：固定 mmd 对象的置信度总偏差 0.0250 → 0.0110（-56%），多个信号降到 0。
"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun.mmd_conditions import _calc_rsi, _calc_rsi_momentum

PERIOD = 14


def _rising(n: int) -> list[float]:
    return [10.0 + i * 0.1 for i in range(n)]


def _falling(n: int) -> list[float]:
    return [100.0 - i * 0.1 for i in range(n)]


class TestRsiAsOfIndex:
    """核心：同一段数据里，idx 之前的结果不许被 idx 之后的数据影响。"""

    def test_continuous_rise_is_100(self) -> None:
        # 一路向上没有回撤 → avg_loss=0 → RSI=100
        assert _calc_rsi(_rising(60), PERIOD) == 100.0
        assert _calc_rsi(_rising(60), PERIOD, idx=30) == 100.0

    def test_continuous_fall_is_0(self) -> None:
        assert _calc_rsi(_falling(60), PERIOD) == 0.0

    def test_tail_appending_does_not_change_past_idx(self) -> None:
        """反向锁定前视：在 idx 之后追加数据，idx 处的 RSI 必须不变。"""
        base = _rising(10) + [10.0 + i * 0.1 for i in range(20)]
        past = _calc_rsi(base, PERIOD, idx=25)
        extended = base + [9876.5, -1.0, 3.3, 4.4, 5.5]  # 后面乱追加
        assert _calc_rsi(extended, PERIOD, idx=25) == past, (
            "在 idx 之后追加数据改变了该处的 RSI（前视）"
        )

    def test_idx_none_equals_tail(self) -> None:
        c = _rising(60)
        assert _calc_rsi(c, PERIOD) == _calc_rsi(c, PERIOD, idx=len(c))

    def test_idx_clamped_to_length(self) -> None:
        """idx 超出长度时收敛到末尾，不越界。"""
        c = _rising(60)
        assert _calc_rsi(c, PERIOD, idx=10_000) == _calc_rsi(c, PERIOD)

    def test_insufficient_data_returns_neutral_50(self) -> None:
        assert _calc_rsi([10.0, 11.0], PERIOD, idx=1) == 50.0
        assert _calc_rsi(None, PERIOD) == 50.0


class TestRsiMomentumAsOfIndex:
    def test_series_with_pullbacks_has_nonzero_momentum(self) -> None:
        # 注意：必须用**含回撤**的序列。一路无回撤上涨会让 avg_loss=0，RSI 恒定
        # 饱和在 100，动量恒为 0（我头两次都被这个假象骗了 —— 是测试数据错了，
        # 不是代码错了）。实测这个序列动量 = -5.4422，确有变化。
        c = [10.0 + i * 0.1 - (i % 3) * 0.15 for i in range(60)]
        assert _calc_rsi_momentum(c, PERIOD, idx=59) == pytest.approx(
            5.4422, abs=1e-3
        )

    def test_tail_appending_does_not_change_past_idx(self) -> None:
        c = [10.0 + (i**1.2) * 0.02 for i in range(60)]
        past = _calc_rsi_momentum(c, PERIOD, idx=40)
        extended = c + [123.0, 456.0, 789.0, 12.0, 34.0]
        assert _calc_rsi_momentum(extended, PERIOD, idx=40) == past

    def test_insufficient_returns_zero(self) -> None:
        assert _calc_rsi_momentum([10.0, 11.0], PERIOD) == 0.0
        assert _calc_rsi_momentum(None, PERIOD) == 0.0

    def test_idx_none_equals_tail(self) -> None:
        c = [10.0 + (i**1.2) * 0.02 for i in range(60)]
        assert _calc_rsi_momentum(c, PERIOD) == _calc_rsi_momentum(
            c, PERIOD, idx=len(c)
        )


class TestBackwardCompatibility:
    """对照：不传 idx 时行为必须与原实现完全一致（实时语境不受影响）。"""

    @pytest.mark.parametrize("n", [10, 15, 30, 100])
    def test_default_matches_tail_of_reference(self, n: int) -> None:
        """手算参考实现：只看最后 period 根。"""
        closes = _rising(n) + [11.0 - (i % 3) * 0.05 for i in range(n)]

        def reference(cs: list[float], period: int = 14) -> float:
            if len(cs) < period + 1:
                return 50.0
            gains, losses = [], []
            for i in range(-period, 0):
                d = cs[i] - cs[i - 1]
                gains.append(max(d, 0))
                losses.append(max(-d, 0))
            ag, al = sum(gains) / period, sum(losses) / period
            if al <= 0:
                return 100.0
            return 100.0 - (100.0 / (1.0 + ag / al))

        assert _calc_rsi(closes, PERIOD) == pytest.approx(reference(closes))
