"""V731：`_check_post_signal_price_follow_through` 前视修正回归。

缺陷（实测确认）

该函数是 V47「后确认价格跟随」（条件131），作用在**所有**买卖点置信度上
（`_calc_confidence_v47` 里叠加 `confidence_adjust`）。原实现：

    latest_close = closes[-1]          # 序列**最后一根**
    actual_lookback = min(lookback_bars, signal_idx)   # 信号**之前**的索引

两个问题：

1. **前视**：对历史信号，`closes[-1]` 包含信号之后直到"现在"的全部未来数据。
   实测同一个 idx=50 的 3买，随数据推进：
       数据到 55 根 → adjust=+0.04（"后确认通过"）
       数据到 80 根 → adjust=-0.05（"后确认失败"）
       数据到 200 根 → adjust=-0.05
   同一个信号"今天看好、明天看差"，**不可复现**，污染训练数据（F3）与 UI
   展示；回测按 `min_confidence` 过滤时等于用了未来信息，收益被高估。
2. **msg 撒谎**：`actual_lookback` 取的是信号之前的索引（`min(5, signal_idx)`，
   在 idx=50 时恒为 5），却写进 msg「信号后 N 根 K 线」；实际比较的是
   `closes[-1]`，与"N 根"无关。

修正：窗口固定为信号**之后**最多 `lookback_bars` 根（截断，不再取到最后一根）；
信号后数据不足时返回 neutral（不加不减）；`looked_bars` 改为真实根数。
"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun import MMDType
from easy_tdx.chanlun.mmd_conditions import (
    _check_post_signal_price_follow_through,
)

SIGNAL_IDX = 50


def _mmd(mmd_type=MMDType.BUY_3):
    class _K:
        k_index = SIGNAL_IDX

    class _B:
        k = _K()

    class _Bi:
        end = _B()

    class _M:
        bi = _Bi()

    _M.mmd_type = mmd_type
    return _M()


def _closes(n: int) -> list[float]:
    """信号(idx=50)后先涨到 60 根，之后回落。"""
    c = [10.0] * n
    for i in range(SIGNAL_IDX + 1, n):
        c[i] = 10.0 + (i - SIGNAL_IDX) * 0.1 if i <= 60 else 11.0 - (i - 60) * 0.05
    return c


class TestNoLookahead:
    """核心：同一信号的结果必须与"数据推进到哪"无关。"""

    @pytest.mark.parametrize("n", [56, 70, 100, 200, 500])
    def test_same_result_regardless_of_data_length(self, n: int) -> None:
        """反向锁定前视：数据越长结果越不该变。"""
        base = _check_post_signal_price_follow_through(_mmd(), _closes(56))
        r = _check_post_signal_price_follow_through(_mmd(), _closes(n))
        assert r["confidence_adjust"] == base["confidence_adjust"], (
            f"数据到 {n} 根时 adjust={r['confidence_adjust']}，"
            f"与到 56 根的 {base['confidence_adjust']} 不一致（前视未消除）"
        )
        assert r["follow_pct"] == base["follow_pct"]

    def test_old_behavior_would_differ(self) -> None:
        """证明这个测试有分辨力：旧实现在不同长度下确实会变。"""
        # 旧语义 = 与 closes[-1] 比较；此处直接断言"最后一根"随长度变化，
        # 说明若仍取 closes[-1]，结果必然不稳定。
        c56, c200 = _closes(56), _closes(200)
        assert c56[-1] != c200[-1], "构造的数据应使'最后一根'随长度变化"


class TestInsufficientDataIsNeutral:
    """信号后数据不足 lookback_bars 根 → neutral，不得借用未来/不得误判。"""

    @pytest.mark.parametrize("n", [51, 52, 53, 54, 55])
    def test_insufficient_returns_neutral(self, n: int) -> None:
        r = _check_post_signal_price_follow_through(_mmd(), _closes(n))
        assert r["confidence_adjust"] == 0.0, f"数据到 {n} 根应 neutral，实际 {r}"
        assert r["followed"] is False
        assert "不足" in r["msg"]

    def test_signal_at_last_bar_is_neutral(self) -> None:
        r = _check_post_signal_price_follow_through(_mmd(), _closes(SIGNAL_IDX + 1))
        assert r["confidence_adjust"] == 0.0


class TestLookedBarsMatchesMsg:
    """`looked_bars` 必须与 msg 里声称的"信号后 N 根"一致（原实现恒为 0/错位）。"""

    def test_looked_bars_is_real_window(self) -> None:
        r = _check_post_signal_price_follow_through(_mmd(), _closes(200))
        assert r["looked_bars"] == 5, f"窗口应为 5 根，实际 {r['looked_bars']}"
        assert "信号后5根K线" in r["msg"], f"msg 与窗口不一致: {r['msg']}"

    def test_follow_pct_uses_window_not_last_bar(self) -> None:
        """follow_pct 必须是"信号后 5 根"的涨幅，而不是到序列末尾。"""
        r = _check_post_signal_price_follow_through(_mmd(), _closes(200))
        # closes[55] = 10.0 + 5*0.1 = 10.5 → +5.0%
        assert r["follow_pct"] == pytest.approx(5.0, abs=0.01), (
            f"应取信号后第5根(10.5)算得 +5.0%，实际 {r['follow_pct']}%"
        )


class TestSellDirection:
    """卖出方向对称（纪律：改了分支要测两侧）。"""

    def test_sell_confirmed_on_drop(self) -> None:
        c = [10.0] * 200
        for i in range(SIGNAL_IDX + 1, 200):
            c[i] = 10.0 - (i - SIGNAL_IDX) * 0.1  # 持续下跌
        r = _check_post_signal_price_follow_through(_mmd(MMDType.SELL_3), c)
        assert r["followed"] is True
        assert r["confidence_adjust"] > 0

    def test_sell_failed_on_rise(self) -> None:
        c = [10.0] * 200
        for i in range(SIGNAL_IDX + 1, 200):
            c[i] = 10.0 + (i - SIGNAL_IDX) * 0.1  # 反而上涨
        r = _check_post_signal_price_follow_through(_mmd(MMDType.SELL_3), c)
        assert r["followed"] is False
        assert r["confidence_adjust"] < 0
