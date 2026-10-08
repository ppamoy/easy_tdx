"""跨实现的前瞻收益「单位契约」护栏（V736）。

背景：系统里曾有两条并行的前瞻收益实现，单位不一致：
- ``web/signal_ledger.py::forward_returns`` 曾返回**百分数**（27.2727）
- ``backtest/signal_accuracy.py::_horizon_stats`` 一直是**小数**（0.2727）

两者相差 100 倍。``forward_returns`` 的百分数经 ``signal_returns`` →
``SignalReturnRecord`` → ``signal_accuracy._signal_type_stats`` 一路喂进
``_horizon_stats``，**实测已污染** ``compute_signal_accuracy_by_type`` 的
avg_return / median_return / ranking.avg_return（真实 BUG，非假想）。

本测试把「两条实现同为小数口径」钉死：任何一处改回百分数（乘/除 100）
都必须失败。

全部断言为**行为级**（真调函数、断言数值），不含源码文本断言。
"""

from __future__ import annotations

import numpy as np
import pytest

from easy_tdx.backtest.signal_accuracy import (
    _horizon_stats,
    _safe_fwd,
    compute_signal_accuracy_by_type,
)
from easy_tdx.web.signal_ledger import (
    aggregate_signal_returns,
    forward_returns,
    signal_returns,
)

# 索引 10~14 为 11,12,13,14,15。bar_index=10 的基准价是 11（不是 10），
# horizon=3 后到 14：14/11 - 1 = 0.272727…（小数口径 = +27.27%）
STEP_CLOSES = [10.0] * 10 + [11.0, 12.0, 13.0, 14.0, 15.0]
EXPECTED_H3 = pytest.approx(14.0 / 11.0 - 1.0, abs=1e-9)
ABS_TOL = 1e-9


def test_forward_returns_returns_decimal_not_percent() -> None:
    """核心单位契约：forward_returns 返回小数（0.2727），不是百分数（27.2727）。"""
    raw, bench, excess = forward_returns(STEP_CLOSES, 10, 3)
    assert raw is not None
    assert raw == EXPECTED_H3, "forward_returns 必须是小数口径（0.2727 表示 +27.27%）"
    assert bench is None and excess is None
    # 反向锁：明确不是放大 100 倍的值
    assert raw != pytest.approx(27.2727, abs=1e-4)
    assert raw < 1.0, "小数口径下 27% 收益应落在 (0, 1) 附近，不该是 27.27"


def test_forward_returns_percent_magnitude_is_impossible() -> None:
    """数量级护栏：常见收益必须落在合理小数区间（-1, 10）。

    若有人改回百分数，像 +27.27% 这样的值会变成 27.27，直接越界。
    """
    raw, _, _ = forward_returns(STEP_CLOSES, 10, 3)
    assert raw is not None
    assert -1.0 <= raw <= 10.0, f"收益 {raw} 超出小数口径合理区间，疑似单位漂移"


def test_forward_returns_benchmark_and_excess_are_decimal() -> None:
    """指数收益与超额同样是小数量纲（三者必须同单位才能相减）。"""
    closes = [10.0, 11.0, 12.0]
    index = [100.0, 102.0, 103.0]
    raw, bench, excess = forward_returns(closes, 0, 2, index)
    assert raw == pytest.approx(0.20)
    assert bench == pytest.approx(0.03)
    assert excess == pytest.approx(0.17)
    # 同量纲：excess = raw - bench 必须成立（若单位不一致此式不成立）
    assert raw is not None and bench is not None and excess is not None
    assert excess == pytest.approx(raw - bench, abs=ABS_TOL)
    # 三者必须以 raw 为基准按同一比例返回（三者中任一另行乘 100 都会破坏此式）
    assert excess == pytest.approx(0.17) and excess != pytest.approx(17.0)


def test_forward_returns_edge_cases_still_decimal() -> None:
    """退化/边界：单位切换不得破坏 None 语义与零基价哨兵。"""
    closes = [10.0, 11.0, 12.0, 0.0, 9.0]
    # 越界 → 全 None
    assert forward_returns(closes, 3, 5) == (None, None, None)
    # 负索引 → 全 None
    assert forward_returns(closes, -1, 2) == (None, None, None)
    # bar 3 基准价是 0 → 零基价走「全 None」分支（None 语义不因单位变化）
    assert forward_returns(closes, 3, 1) == (None, None, None)
    # bar 0 / bar 2 两种情形都要验证，避免只覆盖到正收益
    # bar 0 (10.0) → j=2 (12.0)：12/10 - 1 = 0.2（小数口径）
    raw, _, _ = forward_returns(closes, 0, 2)
    assert raw == pytest.approx(0.2, abs=1e-9), "单位切换不得改变数值语义"
    # bar 2 (12.0) → j=3 (0.0)：0/12 - 1 = -1.0（小数口径下的 -100%）
    raw0, _, _ = forward_returns(closes, 2, 1)
    assert raw0 == pytest.approx(-1.0, abs=1e-9)
    assert forward_returns(closes, 4, 1) == (None, None, None)


def test_horizon_stats_stays_decimal() -> None:
    """_horizon_stats 保持小数口径（0.0433 表示 +4.33%）。"""
    stats = _horizon_stats(np.array([0.05, 0.10, -0.02]))
    assert stats["count"] == 3
    assert stats["avg_return"] == pytest.approx(0.0433333333333, abs=1e-9)
    assert stats["median_return"] == pytest.approx(0.05, abs=1e-9)
    # 反向锁：明确不是百分数
    assert stats["avg_return"] != pytest.approx(4.33333)
    assert stats["hit_rate"] == pytest.approx(2.0 / 3.0, abs=1e-9)


def test_safe_fwd_is_decimal() -> None:
    """_safe_fwd 是小数量纲（它同时供随机基线与 signal 路径使用）。"""
    assert float(_safe_fwd(10.0, 13.0)) == pytest.approx(0.3, abs=ABS_TOL)
    # 零价哨兵 = -1.0（小数口径的 -100%），不是 -100.0
    assert float(_safe_fwd(0.0, 5.0)) == pytest.approx(-1.0, abs=ABS_TOL)


def test_two_implementations_agree_on_same_input() -> None:
    """等价性契约：两条实现对同一输入必须给出**同一个数**（不是百倍关系）。"""
    closes = STEP_CLOSES
    bar, h = 10, 3

    # 路线 A：ledger
    raw, _, _ = forward_returns(closes, bar, h)
    # 路线 B：accuracy 内部的 _safe_fwd + _horizon_stats
    fwd = np.asarray([float(_safe_fwd(closes[bar], closes[bar + h]))])
    stats_b = _horizon_stats(fwd)

    assert raw is not None
    assert raw == pytest.approx(stats_b["avg_return"], abs=ABS_TOL), (
        "两条前瞻收益实现口径不一致 —— 典型症状是相差 100 倍"
    )
    # 显式的「不是 100 倍」断言：给出可读的失败信息
    assert raw != pytest.approx(stats_b["avg_return"] * 100, rel=1e-6)
    assert raw != pytest.approx(stats_b["avg_return"] / 100, rel=1e-6)


def test_ledger_record_fields_are_decimal() -> None:
    """SignalReturnRecord 的三个字段必须同为小数量纲。"""
    closes = [10.0, 10.0, 11.0]
    recs = signal_returns(
        closes,
        [
            {"type": "2buy", "bar_index": 0},
            {"type": "3sell", "bar_index": 0},
        ],
        horizons=(2,),
    )
    buy = next(r for r in recs if r.direction == "buy")
    sell = next(r for r in recs if r.direction == "sell")
    # 11/10 - 1 = 0.1 → 小数
    assert buy.ret_pct == pytest.approx(0.1, abs=1e-6)
    assert sell.ret_pct == pytest.approx(-0.1, abs=1e-6)
    assert (
        buy.raw_ret_pct == pytest.approx(0.1, abs=1e-6) == pytest.approx(sell.raw_ret_pct, abs=1e-6)
    )


def test_aggregate_avg_return_is_decimal_and_matches_horizon_stats() -> None:
    """aggregate 的 avg_return 与 _horizon_stats 的 avg_return 同单位可比。"""
    recs = signal_returns(
        STEP_CLOSES,
        [
            {"type": "1buy", "bar_index": 10},
            {"type": "1buy", "bar_index": 11},
        ],
        horizons=(3,),
    )
    assert len(recs) == 2
    agg = aggregate_signal_returns(recs)
    lagger_avg = agg["overall"]["avg_return"]
    assert lagger_avg is not None

    fwd = np.asarray([r.raw_ret_pct for r in recs], dtype=float)
    stats_avg = _horizon_stats(fwd)["avg_return"]
    assert lagger_avg == pytest.approx(stats_avg, abs=1e-4)
    assert abs(lagger_avg) < 10.0, "小数口径下 5 根收益不该达到数十的量级"


def test_panel_by_type_avg_return_is_decimal() -> None:
    """端到端：面板报告的 avg_return 必须与 baseline_avg_return 同数量级。

    这是历史 BUG 的现场——台账百分数混进来后，avg_return 比
    baseline_avg_return 大 ~100 倍，而二者本应同为小数。
    """
    rng = np.arange(80, dtype=float)
    closes = np.round(100 + 8 * np.sin(rng / 5.0) + 0.15 * rng, 4)
    signals = [
        {"type": "1buy", "bar_index": 5},
        {"type": "2buy", "bar_index": 20},
        {"type": "1buy", "bar_index": 35},
        {"type": "3sell", "bar_index": 12},
        {"type": "3sell", "bar_index": 45},
    ]
    rep = compute_signal_accuracy_by_type(list(closes), signals, horizons=(5,))
    checked = 0
    for sig_type, report in rep["by_type"].items():
        h5 = report["horizons"].get("5")
        if not h5 or h5.get("count", 0) == 0:
            continue
        avg = float(h5["avg_return"])
        base_ret = float(h5["baseline_avg_return"])
        # 真实 5 根涨跌几乎不可能超过 ±100%：百分数化会让 |avg| 达到几十
        assert abs(avg) < 1.0, f"{sig_type}: avg_return={avg} 超出小数口径合理范围"
        assert abs(base_ret) < 1.0, f"{sig_type}: baseline={base_ret} 口径异常"
        # 二者必须同量纲（可安全相减）
        assert abs(avg - base_ret) < 2.0, f"{sig_type}: avg 与 baseline 量纲不一致"
        # ranking 摘要同源，必须一致
        rank = next(x for x in rep["ranking"] if x["type"] == sig_type)
        assert float(rank["avg_return"]) == pytest.approx(avg, abs=1e-6)
        checked += 1
    assert checked >= 2, f"样本不足，未形成有效断言（checked={checked}）"


def test_panel_matches_ledger_by_type() -> None:
    """跨实现对账：面板 by_type 与 ledger by_type 的 5 根均值逐值一致。"""
    rng = np.arange(80, dtype=float)
    closes = np.round(100 + 8 * np.sin(rng / 5.0) + 0.15 * rng, 4)
    signals = [
        {"type": "1buy", "bar_index": 5},
        {"type": "2buy", "bar_index": 20},
        {"type": "3sell", "bar_index": 45},
    ]
    sa = compute_signal_accuracy_by_type(list(closes), signals, horizons=(5,))
    recs = signal_returns(closes, signals, horizons=(5,))
    agg = aggregate_signal_returns(recs)

    for sig_type, report in sa["by_type"].items():
        h5 = report["horizons"].get("5")
        ledger_stats = agg["by_type"].get(sig_type)
        if not h5 or h5.get("count", 0) == 0 or ledger_stats is None:
            continue
        assert float(ledger_stats["avg_return"]) == pytest.approx(
            float(h5["avg_return"]), abs=1e-4
        ), f"{sig_type}: 台账与面板均值口径不一致（差 100 倍？）"
        assert ledger_stats["hit_rate"] == pytest.approx(h5["hit_rate"], abs=1e-6), (
            f"{sig_type}: 命中率口径不一致"
        )
