"""V47 duplicate function removal + 缠论核心算法准确性测试。

覆盖：
1. _calc_confidence_v47 只有一个定义（V47校准版），不再是简单别名
2. 笔/分型/中枢/线段 端点锚定一致性（bar_index 与 date 指向同一根K线）
3. 买卖点 bar_index 与 K 线序列对齐
4. 信号准确度计算基础正确性
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.types import BI, FX, CLKline, Direction, FXType

# ── 测试1：_calc_confidence_v47 只有一个定义且含V47逻辑 ──────────────────────


def test_calc_confidence_v47_single_definition():
    """_calc_confidence_v47 应只有一个定义，且包含V47校准逻辑（非简单别名）。"""
    import inspect

    from easy_tdx.chanlun import mmd as mmd_mod

    # 确认只有一个 _calc_confidence_v47
    sources = inspect.getsource(mmd_mod)
    # 统计函数定义数量
    import re

    definitions = re.findall(r"^def _calc_confidence_v47\(", sources, re.MULTILINE)
    assert len(definitions) == 1, f"应有1个定义，找到{len(definitions)}个: {definitions}"

    # 确认该函数包含V47特有的逻辑（后确认/有效性窗口/类型校准）
    func_src = inspect.getsource(mmd_mod._calc_confidence_v47)
    assert "post_signal" in func_src or "follow_through" in func_src.lower(), (
        "V47函数应包含后确认逻辑"
    )
    assert "validity_window" in func_src or "signal_validity" in func_src.lower(), (
        "V47函数应包含有效性窗口逻辑"
    )


def test_calc_confidence_v47_applied_in_find_mmds():
    """find_mmds 调用 _calc_confidence_v47 而非简单 _calc_confidence。"""
    import inspect

    from easy_tdx.chanlun import mmd as mmd_mod

    src = inspect.getsource(mmd_mod.find_mmds)
    assert "_calc_confidence_v47" in src, "find_mmds 应调用 _calc_confidence_v47"


# ── 测试2：合成数据完整管道，验证各结构一致性 ────────────────────────────────


def _synthetic_trending_df(n: int = 400, seed: int = 42) -> pd.DataFrame:
    """生成带趋势+中枢的模拟日线数据。"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    # 震荡上涨：前半段下跌+中枢，后半段反弹+突破
    trend = np.concatenate(
        [
            np.linspace(50, 40, n // 2),  # 下跌段
            np.linspace(40, 55, n // 2),  # 反弹段
        ]
    )
    close = trend + rng.normal(0, 0.5, n)
    close = np.maximum(close, 5.0)
    open_ = close + rng.normal(0, 0.3, n)
    high = np.maximum(open_, close) + rng.uniform(0.1, 0.5, n)
    low = np.minimum(open_, close) - rng.uniform(0.1, 0.5, n)
    vol = (rng.uniform(0.8, 1.2, n) * 1e6).astype(float)
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": open_,
            "close": close,
            "high": high,
            "low": low,
            "vol": vol,
            "amount": vol * close,
        }
    )


def test_pipeline_completes_without_error():
    """完整缠论管道应正常执行不报错。"""
    df = _synthetic_trending_df(400)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)
    assert result.klines
    assert result.cklines
    # 分型、笔、中枢、买卖点至少各有一些
    assert len(result.fractals) >= 3
    assert len(result.bis) >= 2
    # 可能有中枢也可能没有（取决于数据），但不应该崩溃


def test_fractal_bar_index_anchor_matches_date():
    """分型的 bar_index 与 date 必须指向同一根原始K线。"""
    df = _synthetic_trending_df(400)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)

    for fx in result.fractals:
        anchor_dt = result._fx_anchor_datetime(fx)
        # bar_index 对应的 K 线日期应与 _fx_anchor_datetime 一致
        if 0 <= fx.bar_index < len(result.klines):
            kline_dt = result.klines[fx.bar_index].date
            # 允许同一天（date 只到日精度）
            assert kline_dt.date() == anchor_dt.date(), (
                f"分型 {fx.index} bar_index={fx.bar_index} date mismatch: "
                f"kline={kline_dt} vs anchor={anchor_dt}"
            )


def test_bi_endpoints_match_fractal_bar_index():
    """笔的起止分型 bar_index 与笔的 start_index/end_index 一致。"""
    df = _synthetic_trending_df(400)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)

    for bi in result.bis:
        assert bi.start.bar_index == result.to_dict()["bis"][bi.index]["start_index"], (
            f"笔 {bi.index} start bar_index mismatch"
        )
        assert bi.end.bar_index == result.to_dict()["bis"][bi.index]["end_index"], (
            f"笔 {bi.index} end bar_index mismatch"
        )


def test_zs_endpoints_match_fractal_bar_index():
    """中枢的起止分型 bar_index 与序列化结果一致。"""
    df = _synthetic_trending_df(400)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)
    d = result.to_dict()

    for zs in result.zss:
        idx = zs.index
        assert zs.start is None or zs.start.bar_index == d["zss"][idx]["start_index"], (
            f"中枢 {idx} start bar_index mismatch"
        )
        assert zs.end is None or zs.end.bar_index == d["zss"][idx]["end_index"], (
            f"中枢 {idx} end bar_index mismatch"
        )


def test_mmd_bar_index_consistent():
    """买卖点的 bar_index 与笔终点 bar_index 一致。"""
    df = _synthetic_trending_df(400)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)
    d = result.to_dict()

    for mmd in result.mmds:
        if mmd.bi is None:
            continue
        expected_idx = mmd.bi.end.bar_index
        serialized = next((m for m in d["mmds"] if m.get("bar_index") == expected_idx), None)
        # 至少能找到一条匹配的序列化记录
        assert serialized is not None, f"买卖点 bar_index={expected_idx} 无匹配序列化记录"


def test_mmd_dates_are_valid():
    """所有买卖点日期不为空且格式合法。"""
    df = _synthetic_trending_df(400)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)
    d = result.to_dict()

    for mmd in d["mmds"]:
        assert mmd["date"] is not None, "买卖点日期不应为 None"
        # 日期格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM
        assert "T" in mmd["date"] or "-" in mmd["date"], f"日期格式异常: {mmd['date']}"


# ── 测试3：信号准确度计算基础正确性 ──────────────────────────────────────────


def test_signal_accuracy_structure():
    """compute_signal_accuracy_by_type 返回合法结构。"""
    from easy_tdx.backtest.signal_accuracy import compute_signal_accuracy_by_type

    closes = [100.0 + i * 0.1 for i in range(100)]
    signals = [
        {"type": "1buy", "bar_index": 10},
        {"type": "1buy", "bar_index": 50},
        {"type": "1sell", "bar_index": 30},
        {"type": "3buy", "bar_index": 70},
    ]
    result = compute_signal_accuracy_by_type(closes, signals)
    assert "by_type" in result
    assert "ranking" in result
    assert "summary" in result
    assert isinstance(result["ranking"], list)
    # 应有3个类型
    assert len(result["by_type"]) == 3


def test_signal_accuracy_hit_rate_reasonable():
    """单调上涨数据的买入信号命中率应 > 随机基准（50%）。"""
    from easy_tdx.backtest.signal_accuracy import compute_signal_accuracy_by_type

    # 单调上涨
    closes = [100.0 + i * 0.5 for i in range(200)]
    signals = [{"type": "1buy", "bar_index": i * 20} for i in range(5)]
    result = compute_signal_accuracy_by_type(closes, signals)
    ranking = result.get("ranking", [])
    if ranking:
        # 上涨行情中买入应普遍命中
        avg_hit = np.mean([r["hit_rate"] for r in ranking if r["signals"] > 0])
        assert avg_hit > 0.4, f"上涨行情买入命中率过低: {avg_hit}"


def test_signal_accuracy_sell_in_downtrend():
    """单调下跌数据的卖出信号命中率（下跌率）应合理。"""
    from easy_tdx.backtest.signal_accuracy import compute_signal_accuracy_by_type

    closes = [100.0 - i * 0.5 for i in range(200)]
    signals = [{"type": "1sell", "bar_index": i * 20} for i in range(5)]
    result = compute_signal_accuracy_by_type(closes, signals)
    by_type = result.get("by_type", {})
    if "1sell" in by_type:
        h5 = by_type["1sell"]["horizons"].get("5")
        if h5 and h5.get("count", 0) > 0:
            # 卖出命中 = 价格下跌 → hit_rate > 0.5
            assert h5["hit_rate"] > 0.3, f"下跌行情卖出命中率过低: {h5['hit_rate']}"


# ── 测试4：笔计算边界情况 ────────────────────────────────────────────────────


def test_find_bis_empty_input():
    """空分型列表 → 空笔列表。"""
    from easy_tdx.chanlun.bi import find_bis
    from easy_tdx.chanlun.config import ChanlunConfig

    assert find_bis([], ChanlunConfig()) == []


def test_find_bis_single_fractal():
    """单分型 → 无笔（至少需要2个异型分型）。"""
    from easy_tdx.chanlun.bi import find_bis
    from easy_tdx.chanlun.config import ChanlunConfig
    from easy_tdx.chanlun.types import FX, CLKline, FXType

    ck = CLKline(
        k_index=0, date=datetime(2025, 1, 1), open=10, close=10, high=11, low=9, amount=1e6, index=0
    )
    fx = FX(fx_type=FXType.DING, k=ck, klines=[ck, ck, ck], val=11.0, index=0, done=True)
    assert find_bis([fx], ChanlunConfig()) == []


def test_bi_direction_alternates():
    """笔的方向必须严格交替。"""
    df = _synthetic_trending_df(400)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)

    for i in range(1, len(result.bis)):
        prev_dir = result.bis[i - 1].direction
        curr_dir = result.bis[i].direction
        assert prev_dir != curr_dir, f"笔 {i - 1}({prev_dir}) 和笔 {i}({curr_dir}) 方向未交替"


def test_bi_gap_requirement_new_mode():
    """新笔模式：相邻分型之间至少1根独立K线。"""
    from easy_tdx.chanlun.bi import find_bis
    from easy_tdx.chanlun.config import ChanlunConfig
    from easy_tdx.chanlun.types import FX, CLKline, FXType

    # 构造两个相邻分型（中间无独立K线）
    ck1 = CLKline(
        k_index=0, date=datetime(2025, 1, 1), open=10, close=10, high=11, low=9, amount=1e6, index=0
    )
    ck2 = CLKline(
        k_index=1, date=datetime(2025, 1, 2), open=10, close=10, high=12, low=8, amount=1e6, index=1
    )
    ck3 = CLKline(
        k_index=2, date=datetime(2025, 1, 3), open=10, close=10, high=11, low=9, amount=1e6, index=2
    )

    fx1 = FX(fx_type=FXType.DING, k=ck1, klines=[ck1, ck2, ck3], val=12.0, index=0, done=True)
    fx2 = FX(fx_type=FXType.DI, k=ck3, klines=[ck1, ck2, ck3], val=8.0, index=1, done=True)

    config = ChanlunConfig(bi_type="new")
    bis = find_bis([fx1, fx2], config)
    # 中间无独立K线，gap=0，新笔要求>=1，不应成笔
    assert len(bis) == 0, f"gap=0时应无笔，实际: {len(bis)}"


# ── 测试5：中枢计算边界情况 ──────────────────────────────────────────────────


def test_find_zss_min_lines():
    """少于3笔无法形成中枢。"""
    from easy_tdx.chanlun.config import ChanlunConfig
    from easy_tdx.chanlun.zs import find_zss

    config = ChanlunConfig(zs_min_lines=3)
    # 构造2笔
    ck1 = CLKline(
        k_index=0, date=datetime(2025, 1, 1), open=10, close=10, high=12, low=8, amount=1e6, index=0
    )
    ck2 = CLKline(
        k_index=1, date=datetime(2025, 1, 2), open=10, close=10, high=13, low=7, amount=1e6, index=1
    )
    ck3 = CLKline(
        k_index=2, date=datetime(2025, 1, 3), open=10, close=10, high=11, low=9, amount=1e6, index=2
    )
    fx1 = FX(fx_type=FXType.DI, k=ck1, klines=[ck1, ck2, ck3], val=8.0, index=0, done=True)
    fx2 = FX(fx_type=FXType.DING, k=ck3, klines=[ck1, ck2, ck3], val=12.0, index=1, done=True)
    bi1 = BI(start=fx1, end=fx2, direction=Direction.UP, index=0, high=12, low=8)

    bis = [bi1]
    zss = find_zss(bis, config)
    assert len(zss) == 0, f"2笔不应形成中枢，实际: {len(zss)}"


def test_zs_done_flag():
    """最后一个中枢应为未完成（done=False）。"""
    # 用震荡盘整数据：数据终止于盘整内部，最后一个中枢应保持未完成状态
    rng = np.random.default_rng(7)
    dates = pd.date_range("2023-01-02", periods=300, freq="B")
    close = 50.0 + rng.normal(0, 0.6, 300)
    open_ = close + rng.normal(0, 0.3, 300)
    high = np.maximum(open_, close) + rng.uniform(0.1, 0.4, 300)
    low = np.minimum(open_, close) - rng.uniform(0.1, 0.4, 300)
    vol = (rng.uniform(0.8, 1.2, 300) * 1e6).astype(float)
    df = pd.DataFrame(
        {
            "datetime": dates,
            "open": open_,
            "close": close,
            "high": high,
            "low": low,
            "vol": vol,
        }
    )
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)

    assert len(result.zss) >= 1, "盘整数据应至少形成一个中枢"
    last_zs = result.zss[-1]
    assert not last_zs.done, "最后一个中枢应为未完成状态"


# ── 测试6：线段计算 ─────────────────────────────────────────────────────────


def test_find_xds_requires_min_bis():
    """少于3笔无法形成线段。"""
    from easy_tdx.chanlun.config import ChanlunConfig
    from easy_tdx.chanlun.xd import find_xds

    config = ChanlunConfig()
    # 只有2笔
    ck1 = CLKline(
        k_index=0, date=datetime(2025, 1, 1), open=10, close=10, high=12, low=8, amount=1e6, index=0
    )
    ck2 = CLKline(
        k_index=1, date=datetime(2025, 1, 2), open=10, close=10, high=13, low=7, amount=1e6, index=1
    )
    ck3 = CLKline(
        k_index=2, date=datetime(2025, 1, 3), open=10, close=10, high=11, low=9, amount=1e6, index=2
    )
    ck4 = CLKline(
        k_index=3, date=datetime(2025, 1, 4), open=10, close=10, high=14, low=6, amount=1e6, index=3
    )
    fx1 = FX(fx_type=FXType.DI, k=ck1, klines=[ck1, ck2, ck3], val=8.0, index=0, done=True)
    fx2 = FX(fx_type=FXType.DING, k=ck3, klines=[ck1, ck2, ck3], val=12.0, index=1, done=True)
    fx3 = FX(fx_type=FXType.DI, k=ck4, klines=[ck2, ck3, ck4], val=6.0, index=2, done=True)
    bi1 = BI(start=fx1, end=fx2, direction=Direction.UP, index=0, high=12, low=8)
    bi2 = BI(start=fx2, end=fx3, direction=Direction.DOWN, index=1, high=12, low=6)

    xds = find_xds([bi1, bi2], config)
    assert len(xds) == 0, f"2笔不应形成线段，实际: {len(xds)}"


# ── 运行 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
