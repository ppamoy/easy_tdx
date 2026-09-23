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
    # 类二买/类二卖 也应按类型名中的 buy/sell 正确判定方向
    assert _verdict([_FakeMmd("2buy_s", 0.9)])["action"] == "买入"
    assert _verdict([_FakeMmd("2sell_s", 0.9)])["action"] == "卖出"


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


def test_verdict_includes_direction() -> None:
    """择时结论携带方向字段，供前端与递归结构对齐。"""
    assert _verdict([])["direction"] is None
    assert _verdict([_FakeMmd("1buy", 0.9)])["direction"] == "buy"
    assert _verdict([_FakeMmd("3sell", 0.7)])["direction"] == "sell"
    assert _verdict([_FakeMmd("1buy", 0.45)])["direction"] is None  # 低置信度观望


class _FakeLevelMmd:
    def __init__(self, value: str, confidence: float, dt: date) -> None:
        self.mmd_type = type("T", (), {"value": value})()
        self.confidence = confidence
        k = type("K", (), {"date": dt})()
        self.bi = type("B", (), {"end": type("FX", (), {"k": k})()})()


class _FakeRecResult:
    def __init__(self, levels_mmds: list[list[_FakeLevelMmd]]) -> None:
        self.recursive_levels = [type("L", (), {"mmds": mmds})() for mmds in levels_mmds]


def test_recursion_context_finds_available_signal() -> None:
    """多级别递归确认：折取最高可用级别的买卖点信号。"""
    from easy_tdx.web.routers.stock_pick import _recursion_context

    # level1 有、level2 无 → 取 level1；level1 无、level2 有 → 取 level2
    rc1 = _recursion_context(_FakeRecResult([[_FakeLevelMmd("1buy", 0.66, date(2026, 6, 30))], []]))
    assert rc1["depth_produced"] == 2
    assert rc1["latest"]["direction"] == "buy"
    assert rc1["latest"]["level"] == 1
    assert rc1["latest"]["date"] == "2026-06-30"

    rc2 = _recursion_context(_FakeRecResult([[], [_FakeLevelMmd("2sell", 0.8, date(2026, 7, 2))]]))
    assert rc2["latest"]["level"] == 2
    assert rc2["latest"]["direction"] == "sell"


def test_recursion_context_empty() -> None:
    """无递归级别时返回干净的空上下文，不抛错。"""
    from easy_tdx.web.routers.stock_pick import _recursion_context

    rc = _recursion_context(type("R", (), {"recursive_levels": []})())
    assert rc["depth_produced"] == 0
    assert rc["latest"] is None

    rc2 = _recursion_context(object())
    assert rc2["depth_produced"] == 0


def test_dashboard_async_validates_date() -> None:
    """dashboard 异步端点：缺 date/格式错误 → 400；未知任务 → 404。"""
    from fastapi.testclient import TestClient

    from easy_tdx.web import create_app

    app = create_app()
    with TestClient(app) as client:
        r1 = client.post("/api/v1/stock-pick/dashboard/async", json={})
        assert r1.status_code == 400
        r2 = client.post("/api/v1/stock-pick/dashboard/async", json={"date": "bad-date"})
        assert r2.status_code == 400
        r3 = client.get("/api/v1/stock-pick/dashboard/task/nonexistent")
        assert r3.status_code == 404


def test_dashboard_async_submits_task() -> None:
    """dashboard 异步端点：合法请求提交任务返回 task_id + 描述。"""
    from fastapi.testclient import TestClient

    from easy_tdx.web import create_app

    app = create_app()
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/stock-pick/dashboard/async",
            json={"date": "2026-09-01", "pool_scope": "pool", "top_n": 5, "time_n": 2},
        )
        assert r.status_code == 200
        d = r.json()
        assert d.get("task_id")
        assert "今日可操作" in (d.get("description") or "")
        # 轮询接口可查到该任务（状态为 pending/running/done/failed 之一）
        st = client.get(f"/api/v1/stock-pick/dashboard/task/{d['task_id']}")
        assert st.status_code == 200
        assert st.json().get("status") in ("pending", "running", "done", "failed")
