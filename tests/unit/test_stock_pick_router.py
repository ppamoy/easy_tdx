"""选股两步流路由纯函数测试（v590）。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from easy_tdx.web.routers.stock_pick import (
    _default_pool,
    _df_to_bars,
    _novice_advice,
    _run_timing_one,
    _verdict,
)


class _FakeMmd:
    def __init__(self, value: str, confidence: float) -> None:
        self.mmd_type = type("T", (), {"value": value})()
        self.confidence = confidence


def test_default_pool_hot() -> None:
    pool = _default_pool(["SZ", "SH"])
    assert len(pool) == 30
    assert {"market": "SH", "code": "600519"} in pool


def test_verdict_buy_sell_wait() -> None:
    assert _verdict([])["action"] == "观望"
    assert _verdict([_FakeMmd("1buy", 0.9)])["action"] == "买入"
    assert _verdict([_FakeMmd("3sell", 0.7)])["action"] == "卖出"


def test_verdict_low_confidence_downgrades_to_wait() -> None:
    v = _verdict([_FakeMmd("1buy", 0.45)])
    assert v["action"] == "观望"
    assert "置信度偏低" in v["reason"]


def test_df_to_bars_contract() -> None:
    df = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-02", periods=2, freq="B"),
            "open": [10, 10],
            "close": [11, 11],
            "high": [11.5, 11.5],
            "low": [9.5, 9.5],
            "vol": [100, 100],
        }
    )
    bars = _df_to_bars(df)
    assert bars[0]["datetime"].startswith("2025-01-02")
    assert bars[0]["high"] == 11.5


class _FakeBi:
    def __init__(self, end_val: float, bar_index: int) -> None:
        self.end = type("FX", (), {"val": end_val, "bar_index": bar_index})()


class _K:
    def __init__(self, close: float, high: float, low: float) -> None:
        self.close = close
        self.high = high
        self.low = low


class _FakeResult:
    def __init__(self) -> None:
        self.mmds = []
        self.klines = [_K(10.0 + i * 0.1, 10.2 + i * 0.1, 9.9 + i * 0.1) for i in range(20)]

    def with_buy(self) -> _FakeResult:
        mmd = type(
            "M",
            (),
            {"mmd_type": type("T", (), {"value": "1buy"})(), "bi": _FakeBi(10.5, 10), "zs": None},
        )()
        self.mmds = [mmd]
        return self


def test_verdict_confidence_boundary() -> None:
    # 置信度阈值 _MIN_CONF=0.6：恰为 0.6 给建议，0.59 降级观望
    assert _verdict([_FakeMmd("1buy", 0.6)])["action"] == "买入"
    assert _verdict([_FakeMmd("1buy", 0.59)])["action"] == "观望"


def test_novice_advice_buy_gives_entry_stop_target() -> None:
    res = _FakeResult().with_buy()
    out = _novice_advice(res, {"signal": "1buy", "action": "买入"})
    assert out["direction"] == "buy"
    assert out["entry"] is not None
    assert out["stop"] is not None
    assert out["target"] is not None
    # 买点三档价必须有序：止损 < 入场 < 目标
    assert out["stop"] < out["entry"] < out["target"], out
    assert "1buy" in out["explanation"]
    assert "小仓位" in out["position_note"]


def test_novice_advice_missing_bi_gives_wait() -> None:
    res = _FakeResult()
    res.mmds = [
        type("M", (), {"mmd_type": type("T", (), {"value": "1buy"})(), "bi": None, "zs": None})()
    ]
    out = _novice_advice(res, {"signal": "1buy", "action": "买入"})
    assert out["entry"] is None
    assert "缺少触发笔" in out["explanation"]


def test_novice_advice_empty_is_wait() -> None:
    out = _novice_advice(_FakeResult(), {"signal": None})
    assert "观望" in out["explanation"]
    assert out["entry"] is None


def test_run_timing_one_short_window() -> None:
    df = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-02", periods=10, freq="B"),
            "open": [10] * 10,
            "close": [10] * 10,
            "high": [10.5] * 10,
            "low": [9.5] * 10,
            "vol": [100] * 10,
        }
    )
    out = _run_timing_one(df, "SH:600519", "SH", "600519", date(2025, 1, 20))
    assert "error" in out and "不足" in out["error"]