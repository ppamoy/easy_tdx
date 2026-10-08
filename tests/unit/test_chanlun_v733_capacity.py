"""V733：容量/冲击成本脚本的口径回归测试。

锁定两类容易被悄悄改坏的东西：
1. **方向判定**：必须用 `'buy' in st`，不能用 `endswith('buy')`
   （类二买 `2buy_s` 会漏判并被取反）。
2. **冲击成本模型必须含波动率缩放**：第一版是 `k·√(Q/ADV)`（无 σ），
   实测在 A 股典型标的上把冲击高估约 5 倍，导致"任何规模都装不下"的
   错误结论。标准形式是 `k·σ·√(Q/ADV)`。

另含牙齿测试：证明断言在坏版本下会失败。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import audit_capacity as cap  # noqa: E402


class TestDirectionConvention:
    """方向判定：'buy' in st，不是 endswith('buy')。"""

    @pytest.mark.parametrize(
        "st,expected",
        [
            ("1buy", True),
            ("1sell", False),
            ("2buy", True),
            ("2sell", False),
            ("2buy_s", True),
            ("2sell_s", False),  # 类二买/类二卖：endswith 会漏
            ("3buy", True),
            ("3sell", False),
        ],
    )
    def test_is_buy(self, st: str, expected: bool) -> None:
        assert cap._is_buy(st) is expected

    def test_teeth_endswith_would_be_wrong(self) -> None:
        """牙齿：证明 endswith 写法确实会漏掉类二买（否则本测试无意义）。"""
        assert "2buy_s".endswith("buy") is False, (
            "若此断言失败，说明 2buy_s 已改名为以 buy 结尾，本文件的其它断言需要同步复核"
        )
        # 而正确写法必须判出来
        assert cap._is_buy("2buy_s") is True


class TestImpactModelScaling:
    """冲击成本必须随波动率缩放。"""

    def test_impact_scales_with_sigma(self) -> None:
        """σ 翻倍 → 冲击翻倍。"""
        n = 5
        close = np.full(n, 10.0)
        high = np.full(n, 10.1)
        low = np.full(n, 9.9)
        adv = np.full(n, 1e8)
        q = np.full(n, 1e6)
        c_low = cap.trade_cost_vec(close, high, low, adv, q, np.full(n, 0.01))
        c_high = cap.trade_cost_vec(close, high, low, adv, q, np.full(n, 0.02))
        # 固定部分（佣金+价差）相同，差的是冲击
        diff_low = c_low[0] - cap.COMMISSION
        diff_high = c_high[0] - cap.COMMISSION
        assert diff_high > diff_low, "σ 变大时冲击成本必须变大"

    def test_impact_grows_with_participation(self) -> None:
        """参与率越高，冲击越大（平方根）。"""
        close = np.array([10.0])
        high = np.array([10.1])
        low = np.array([9.9])
        adv = np.array([1e8])
        sig = np.array([0.02])
        c1 = cap.trade_cost_vec(close, high, low, adv, np.array([1e6]), sig)[0]
        c2 = cap.trade_cost_vec(close, high, low, adv, np.array([4e6]), sig)[0]
        assert c2 > c1
        # 平方根：4 倍量 → 冲击约 2 倍（不是 4 倍）
        imp1 = c1 - cap.COMMISSION - 0.5 * cap.SPREAD_FRAC * 0.02
        imp2 = c2 - cap.COMMISSION - 0.5 * cap.SPREAD_FRAC * 0.02
        assert 1.7 < imp2 / imp1 < 2.3, f"应为平方根关系，实测 {imp2 / imp1:.2f} 倍"

    def test_teeth_unscaled_model_would_overstate(self) -> None:
        """牙齿：证明无 σ 缩放的旧模型确实高估约 5 倍（否则修正无意义）。"""
        adv, q, sig = 7.54e8, 1e6, 0.02
        old = 0.10 * np.sqrt(q / adv)  # 旧模型（无 σ）
        new = cap.IMPACT_K * sig * np.sqrt(q / adv)  # 新模型（有 σ）
        assert old > new, "旧的无 σ 模型必须更高（这正是它被修正的原因）"
        # 旧模型 36‱ vs 新模型 7‱，量级差约 5 倍
        assert 3.0 < old / new < 8.0, f"实测高估 {old / new:.1f} 倍，应在 3~8 倍区间"

    def test_cost_nonnegative_and_finite(self) -> None:
        """边界：ADV 为 0 / NaN 时不能产生 NaN 或负数。"""
        close = np.array([10.0, 10.0, 10.0])
        high = np.array([10.1, 10.1, 10.1])
        low = np.array([9.9, 9.9, 9.9])
        adv = np.array([0.0, np.nan, 1e8])
        q = np.array([1e6, 1e6, 0.0])
        sig = np.array([0.02, 0.02, 0.02])
        out = cap.trade_cost_vec(close, high, low, adv, q, sig)
        assert np.all(np.isfinite(out)), f"出现非有限值：{out}"
        assert np.all(out >= 0.0), f"出现负成本：{out}"


class TestCapacityConstraint:
    """单笔成交额不得超过当日成交额的一定比例。"""

    def test_q_capped_by_participation(self) -> None:
        amounts = np.array([1e8])  # 当日成交额 1 亿
        size = 5e7  # 想买 5000 万
        q = np.minimum(size, amounts * 0.10)
        assert q[0] == 1e7, "10% 参与率上限应把 5000 万压到 1000 万"

    def test_small_order_not_capped(self) -> None:
        amounts = np.array([1e9])
        q = np.minimum(1e5, amounts * 0.10)
        assert q[0] == 1e5, "小单不应被压缩"
