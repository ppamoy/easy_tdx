"""统一信号台账测试（V722，R4 口径统一护栏）。

核心护栏：compute_signal_accuracy_by_type（面板口径）与
signal_ledger.signal_returns + aggregate（审计口径）对同一输入
的命中率/平均收益必须逐值一致——任何一处单独改算法都会被拦下。
"""

from __future__ import annotations

import numpy as np
import pytest

from easy_tdx.backtest.signal_accuracy import compute_signal_accuracy_by_type
from easy_tdx.web.signal_ledger import (
    aggregate_signal_returns,
    forward_returns,
    signal_returns,
)


def _mk_closes(n: int = 60) -> np.ndarray:
    """确定性价格序列：锯齿 + 趋势，保证正负收益都有。"""
    t = np.arange(n, dtype=float)
    return np.round(100 + 10 * np.sin(t / 6) + 0.2 * t, 2)


CLOSES = _mk_closes()
SIGNALS = [
    {"type": "1buy", "bar_index": 5},
    {"type": "1buy", "bar_index": 20},
    {"type": "2buy", "bar_index": 30},
    {"type": "3sell", "bar_index": 10},
    {"type": "3sell", "bar_index": 40},
    {"type": "2buy", "bar_index": None},  # 缺 bar_index → 跳过
    {"type": "1buy", "bar_index": 59},  # 越界（无 5 根前瞻）→ 各窗口跳过
]


def test_forward_returns_basic() -> None:
    closes = [10.0, 11.0, 12.0, 0.0, 9.0]
    # bar 0, horizon 2: 12/10 - 1 = +20%
    raw, bench, excess = forward_returns(closes, 0, 2)
    assert raw == pytest.approx(0.20)
    assert bench is None and excess is None
    # 越界 → 全 None
    assert forward_returns(closes, 3, 5) == (None, None, None)
    # 零基价 → -100%（与面板 _safe_fwd 的退化数据处理一致，不产生 nan）
    raw2, _, _ = forward_returns(closes, 2, 1)
    assert raw2 == pytest.approx(-1.0)


def test_forward_returns_with_index_benchmark() -> None:
    closes = [10.0, 11.0, 12.0]
    index = [100.0, 102.0, 103.0]
    raw, bench, excess = forward_returns(closes, 0, 2, index)
    assert raw == pytest.approx(0.20)
    assert bench == pytest.approx(0.03)
    assert excess == pytest.approx(0.17)


def test_signal_returns_direction_alignment() -> None:
    closes = [10.0, 10.0, 11.0]
    recs = signal_returns(
        closes,
        [
            {"type": "2buy", "bar_index": 0},
            {"type": "3sell", "bar_index": 0},
        ],
        horizons=(2,),
    )
    assert len(recs) == 2
    buy = next(r for r in recs if r.direction == "buy")
    sell = next(r for r in recs if r.direction == "sell")
    assert buy.ret_pct == pytest.approx(0.10)  # 涨 10% 对买入是好事
    assert sell.ret_pct == pytest.approx(-0.10)  # 涨 10% 对卖出是坏事
    assert buy.raw_ret_pct == pytest.approx(0.10) == sell.raw_ret_pct


def test_signal_returns_skips_insufficient() -> None:
    recs = signal_returns([1.0, 2.0], [{"type": "1buy", "bar_index": 0}], horizons=(1, 5))
    assert len(recs) == 1  # 只有 horizon=1 有数据
    assert recs[0].horizon == 1


def test_aggregate_shape() -> None:
    recs = signal_returns(CLOSES, SIGNALS, horizons=(5,))
    agg = aggregate_signal_returns(recs)
    assert set(agg.keys()) == {"overall", "by_type"}
    # bar 59 无 5 根前瞻被跳过；缺 bar_index 被跳过；其余 5 条有效
    assert agg["overall"]["signals"] == 5  # 1buy×2 + 2buy×1 + 3sell×2
    assert agg["by_type"]["3sell"]["signals"] == 2
    for stats in [agg["overall"], *agg["by_type"].values()]:
        assert 0.0 <= stats["hit_rate"] <= 1.0
        assert stats["avg_return"] is not None


def test_ledger_matches_panel_by_type() -> None:
    """对账护栏：面板与审计对同一输入的 5 根命中率/平均收益一致。"""
    sa = compute_signal_accuracy_by_type(list(CLOSES), SIGNALS)
    recs = signal_returns(CLOSES, SIGNALS, horizons=(5,))
    agg = aggregate_signal_returns(recs)

    for sig_type, report in sa["by_type"].items():
        h5 = report["horizons"].get("5")
        ledger_stats = agg["by_type"].get(sig_type)
        if not h5 or h5.get("count", 0) == 0:
            continue
        assert ledger_stats is not None, sig_type
        # 命中率：面板方向对齐（SELL 用 fwd<0）vs 台账 sign 域 → 同值
        assert h5["hit_rate"] == pytest.approx(ledger_stats["hit_rate"], abs=1e-6), sig_type
        # 平均收益：面板 avg_return 已是方向对齐后的百分比
        assert float(ledger_stats["avg_return"]) == pytest.approx(
            float(h5["avg_return"]), abs=1e-3
        ), sig_type


def test_ledger_counts_match_panel() -> None:
    """台账信号数与面板统计数一致（跳过规则相同）。"""
    sa = compute_signal_accuracy_by_type(list(CLOSES), SIGNALS)
    recs = signal_returns(CLOSES, SIGNALS, horizons=(5,))
    agg = aggregate_signal_returns(recs)
    panel_counts = {
        t: r["horizons"]["5"]["count"]
        for t, r in sa["by_type"].items()
        if r["horizons"].get("5", {}).get("count")
    }
    ledger_counts = {t: s["signals"] for t, s in agg["by_type"].items()}
    assert panel_counts == ledger_counts
