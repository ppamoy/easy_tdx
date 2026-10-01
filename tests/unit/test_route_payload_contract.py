"""路由 payload 完整性运行时契约：手工组装的返回 dict 必须带全结构字段。

背景：静态契约（scripts/verify_fx_contract.py）靠正则扫描源码；本文件用
真实 ChanlunAnalyser 跑一遍，断言**实际返回的 dict** 覆盖前端图表消费的
字段全集——静态检查防「写漏」，运行时断言防「算漏」（如 train/session 曾
漏 valid_fractals/macd/levels：函数体内算了，return 手工清单没带）。

离线运行（合成 K 线，无网络、无 TDX 依赖），进 CI。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
from easy_tdx.web.routers.chanlun import build_train_session_payload

# 前端 ChanlunChart / 页面消费的结构字段（与 verify_fx_contract.CHART_CONSUMED 对齐；
# 在此重复是为让本测试对脚本改动免疫——两处漂移会有本测试兜底）。
CHART_FIELDS = (
    "bars",
    "bis",
    "xds",
    "zss",
    "zsds",
    "qsds",
    "mmds",
    "bcs",
    "fractals",
    "valid_fractals",
    "macd",
    "levels",
)


def _make_df(n: int = 120, seed: int = 7) -> pd.DataFrame:
    """构造带趋势转折的合成 OHLCV（正弦+噪声，保证分型/笔/线段都出得来）。"""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    close = 100.0 + 8 * np.sin(t / 6.0) + rng.normal(0, 0.4, n).cumsum() * 0.05
    high = close + np.abs(rng.normal(0, 0.3, n))
    low = close - np.abs(rng.normal(0, 0.3, n))
    open_ = low + (high - low) * rng.uniform(0.2, 0.8, n)
    vol = rng.integers(1_000_000, 5_000_000, n).astype(float)
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "vol": vol,
        }
    )


@pytest.fixture(scope="module")
def analyse_result():
    """跑一次真实分析，模块内复用。"""
    analyser = ChanlunAnalyser(
        code="TEST", frequency="daily", config=ChanlunConfig(recursion_depth=1)
    )
    return analyser, analyser.process_klines(_make_df())


def test_payload_covers_chart_fields(analyse_result) -> None:
    """train/session payload 必须带全图表消费字段（曾漏 valid_fractals/macd/levels）。"""
    analyser, result = analyse_result
    payload = build_train_session_payload(result, _make_df(), "DAY", "easy", 0)
    missing = [f for f in CHART_FIELDS if f not in payload]
    assert not missing, f"train/session 返回漏了结构字段: {missing}"


def test_payload_field_values_consistent(analyse_result) -> None:
    """字段不仅要存在，值还必须与 to_dict()/valid_fractals_to_dict() 一致。

    注意 to_dict() 本身不含 fractals/valid_fractals（只有 *_count），payload 的
    分型来自 result.fractals 与 result.valid_fractals_to_dict()——分支分别断言。
    """
    analyser, result = analyse_result
    payload = build_train_session_payload(result, _make_df(), "DAY", "easy", 0)
    d = result.to_dict()
    for f in ("bis", "macd", "levels", "zsds", "qsds"):
        assert payload.get(f) == d.get(f), f"payload.{f} 与 to_dict().{f} 不一致"
    assert payload["fractals"] == [
        {
            "fx_type": fx.fx_type.value,
            "date": result._fmt_dt(result._fx_anchor_datetime(fx)),
            "val": round(fx.val, 2),
            "index": fx.index,
            "bar_index": fx.bar_index,
        }
        for fx in result.fractals
    ], "payload.fractals 与 result.fractals 序列化不一致"
    assert payload["valid_fractals"] == result.valid_fractals_to_dict(), (
        "payload.valid_fractals 与 valid_fractals_to_dict() 不一致"
    )


def test_payload_macd_aligned_with_bars(analyse_result) -> None:
    """macd.dif/dea/hist 必须与 bars 等长对齐（副图逐根对应，错位即错图）。"""
    analyser, result = analyse_result
    payload = build_train_session_payload(result, _make_df(), "DAY", "easy", 0)
    n = len(payload["bars"])
    for k in ("dif", "dea", "hist"):
        assert len(payload["macd"][k]) == n, f"macd.{k} 长度 {len(payload['macd'][k])} != bars {n}"


def test_payload_levels_xd_complete(analyse_result) -> None:
    """levels.xd 必须是 _level_payload 全字段（train 页线段切换读它，曾整个缺失）。"""
    analyser, result = analyse_result
    payload = build_train_session_payload(result, _make_df(), "DAY", "easy", 0)
    xd = (payload.get("levels") or {}).get("xd")
    assert xd, "levels.xd 缺失 —— train 页线段级别切换将退化为空图"
    for f in ("bis", "xds", "zss", "mmds", "bcs", "zsds", "qsds"):
        assert f in xd, f"levels.xd 缺 {f}"


def test_payload_fractals_semantics(analyse_result) -> None:
    """valid_fractals 必须是 fractals 的子集且互不共用K线（展示层只用干净分型）。"""
    analyser, result = analyse_result
    payload = build_train_session_payload(result, _make_df(), "DAY", "easy", 0)
    valid_idx = {f["bar_index"] for f in payload["valid_fractals"]}
    all_idx = {f["bar_index"] for f in payload["fractals"]}
    assert valid_idx <= all_idx, "valid_fractals 出现了 fractals 里没有的 bar_index"
    vfx = sorted(payload["valid_fractals"], key=lambda x: x["bar_index"])
    for a, b in zip(vfx, vfx[1:]):
        assert b["bar_index"] - a["bar_index"] >= 3, (
            f"valid 分型 {a['bar_index']} 与 {b['bar_index']} 共用K线"
        )


# ── stock-pick/timing 链路（手工清单 #2）───────────────────────────────────


def test_timing_payload_covers_chart_fields(analyse_result) -> None:
    """_run_timing_one 的手工清单必须覆盖 to_dict 图表字段全集（曾漏 zsds/qsds）。"""
    from easy_tdx.web.routers.stock_pick import _run_timing_one

    _analyser, _result = analyse_result
    df = _make_df()
    target = df["datetime"].iloc[-1].date()
    payload = _run_timing_one(df, "SZ:000001", "SZ", "000001", target)
    assert "error" not in payload, f"合成数据竟报错: {payload.get('error')}"
    missing = [f for f in CHART_FIELDS if f not in payload]
    assert not missing, f"timing 返回漏了结构字段: {missing}"


def test_timing_macd_aligned(analyse_result) -> None:
    """timing 的 macd 序列必须与 bars 等长（副图逐根对应）。"""
    from easy_tdx.web.routers.stock_pick import _run_timing_one

    _analyser, _result = analyse_result
    df = _make_df()
    target = df["datetime"].iloc[-1].date()
    payload = _run_timing_one(df, "SZ:000001", "SZ", "000001", target)
    n = len(payload["bars"])
    for k in ("dif", "dea", "hist"):
        assert len(payload["macd"][k]) == n, f"macd.{k} 长度 != bars"


# ── multi-level 链路（手工清单 #3：fmt_result + _attach_signal_accuracy）───


def test_fmt_result_covers_chart_fields_and_accuracy(analyse_result) -> None:
    """multi-level 的 _multi_fmt_result 必须带全图表字段与 signal_accuracy（曾漏后者）。

    注意 bars 是例外：multi 模式下前端单独调 fetchBars 加载行情（ChanlunView
    955 行），分析响应从不携带 bars（to_dict 也无此键）——这是设计而非漏传。
    """
    from easy_tdx.web.routers.chanlun import _multi_fmt_result

    _analyser, result = analyse_result
    d = _multi_fmt_result(result)
    missing = [f for f in CHART_FIELDS if f not in d and f != "bars"]
    assert not missing, f"fmt_result 漏了结构字段: {missing}"
    assert "bars" not in d, "fmt_result 不应带 bars（行情由前端单独拉取，勿膨胀响应）"
    # signal_accuracy 曾只在 chanlun_analyze 主路径挂载，multi-level 恒缺
    assert "signal_accuracy" in d, "multi-level 缺 signal_accuracy —— 准确度面板永不显示"
