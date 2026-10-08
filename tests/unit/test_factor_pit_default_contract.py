"""``merge_fundamentals`` 默认值契约测试（把危险行为固化成显式契约）。

背景：``point_in_time`` 默认 ``False`` —— 把该股票**最新一期** eps/bps
广播给所有历史 K 线，历史截面因此含未来数据（前视偏差）。

审计确认该函数**没有生产调用方**（见同目录 grep/AST 证据，结论记录在
``src/easy_tdx/factor/engine.py`` 的 docstring warning 里），所以这里
**不改默认值**（改了会引起大面积行为变化），而是：

1. 用测试锁死"默认 False 时确实广播最新值" —— 让这个危险行为成为
   **显式契约**，而不是默默存在；
2. 同时锁死"point_in_time=True 时不泄漏"，保证修复路径可用。

全部为行为级断言（真调用 merge_fundamentals）。
"""

from __future__ import annotations

import pandas as pd
import pytest

from easy_tdx.factor.engine import merge_fundamentals

# ── 夹具 ──────────────────────────────────────────────────────────────────────


def _ohlcv(dates: list[str]) -> pd.DataFrame:
    """按给定日期造 OHLCV（含 datetime/close，满足合并前提）。"""
    return pd.DataFrame(
        {
            "datetime": pd.to_datetime(dates),
            "close": [100.0 + 10.0 * i for i in range(len(dates))],
        }
    )


def _frame() -> pd.DataFrame:
    """两期财报：一季报（4/25 披露）+ 中报（8/15 披露）。

    关键：K 线从 2026-04-01 起，早于一季报披露日 —— 若用"最新一期"，
    则 4/01 这根 K 线会拿到 8/15 才披露的中报数据（前视偏差）。
    """
    return pd.DataFrame(
        {
            "code": ["000001", "000001"],
            "report_date": pd.to_datetime(["2026-03-31", "2026-06-30"]),
            "disclosure_date": pd.to_datetime(["2026-04-25", "2026-08-15"]),
            "eps": [2.0, 5.0],
            "bps": [10.0, 20.0],
        }
    )


# ── 契约 1：默认 False == 广播最新一期（危险行为，显式固化） ───────────────────


def test_default_broadcasts_latest_period_to_every_bar() -> None:
    """默认（不传 point_in_time）时，每根 K 线都拿到最新一期的值。"""
    df = _ohlcv(["2026-04-01", "2026-05-01", "2026-08-20"])
    merged = merge_fundamentals({"000001": df}, _frame())

    out = merged["000001"]
    # 三根 K 线全是中报（最新一期）的 5.0/20.0 —— 包括 4/01 那根
    assert list(out["eps"]) == [5.0, 5.0, 5.0]
    assert list(out["bps"]) == [20.0, 20.0, 20.0]
    # 常量列：首根 == 末根（这就是"广播"的判据）
    assert out["eps"].iloc[0] == out["eps"].iloc[-1]


def test_default_leaks_future_report_into_past_bars() -> None:
    """默认行为确实泄漏未来财报：4/01 的 K 线拿到 8/15 才披露的中报。

    这条断言把"危险"钉死 —— 将来若有人把默认值改成 True，本测试会红，
    提醒他：这是**刻意**的兼容性默认值变更，需要同步评估所有接线方。
    """
    df = _ohlcv(["2026-04-01", "2026-05-01", "2026-08-20"])
    merged = merge_fundamentals({"000001": df}, _frame())

    out = merged["000001"]
    # 4/01 时点，中报（8/15 披露）根本不存在，但默认值给了它 5.0
    assert out["eps"].iloc[0] == pytest.approx(5.0)
    assert out["report_date"].iloc[0] == pd.Timestamp("2026-06-30")

    # 对照：point_in_time=True 时同一根 K 线拿不到任何财报（4/25 之前无披露）
    pit = merge_fundamentals({"000001": df}, _frame(), point_in_time=True)["000001"]
    assert pd.isna(pit["eps"].iloc[0]), "point-in-time 下 4/01 不应有任何财报"


def test_default_is_false_when_kwarg_omitted() -> None:
    """显式传 False 与不传完全等价（默认就是 False）。"""
    df = _ohlcv(["2026-04-01", "2026-05-01", "2026-08-20"])
    implicit = merge_fundamentals({"000001": df}, _frame())
    explicit = merge_fundamentals({"000001": df}, _frame(), point_in_time=False)

    pd.testing.assert_frame_equal(implicit["000001"], explicit["000001"])


# ── 契约 2：point_in_time=True 不泄漏（修复路径可用） ─────────────────────────


def test_point_in_time_true_uses_only_disclosed_reports() -> None:
    """point_in_time=True：逐根只取「截至该日已披露」的最新一期。"""
    df = _ohlcv(["2026-04-01", "2026-05-01", "2026-08-20"])
    merged = merge_fundamentals({"000001": df}, _frame(), point_in_time=True)

    out = merged["000001"]
    assert pd.isna(out["eps"].iloc[0])  # 4/01：一季报尚未披露
    assert out["eps"].iloc[1] == pytest.approx(2.0)  # 5/01：已披露一季报
    assert out["eps"].iloc[2] == pytest.approx(5.0)  # 8/20：已披露中报


def test_point_in_time_differs_from_default_on_history() -> None:
    """两条路径在历史截面上必须不同（否则 point_in_time 形同虚设）。"""
    df = _ohlcv(["2026-04-01", "2026-05-01"])
    default = merge_fundamentals({"000001": df}, _frame())["000001"]
    pit = merge_fundamentals({"000001": df}, _frame(), point_in_time=True)["000001"]

    # 4/01：默认拿中报 5.0，PIT 应为 NaN
    assert default["eps"].iloc[0] == pytest.approx(5.0)
    assert pd.isna(pit["eps"].iloc[0])
    # 5/01：默认仍拿中报 5.0，PIT 应拿一季报 2.0
    assert default["eps"].iloc[1] == pytest.approx(5.0)
    assert pit["eps"].iloc[1] == pytest.approx(2.0)


# ── 契约 3：边界行为不受默认值影响 ────────────────────────────────────────────


def test_empty_frame_returns_copies_unchanged() -> None:
    """frame 为 None/空 → 原样返回副本，不加任何列。"""
    df = _ohlcv(["2026-04-01", "2026-05-01"])
    for frame in (None, pd.DataFrame()):
        merged = merge_fundamentals({"000001": df}, frame)
        assert "eps" not in merged["000001"].columns
        assert "bps" not in merged["000001"].columns


def test_unknown_code_gets_null_columns() -> None:
    """frame 里没有该股票 → eps/bps 全空（默认与 PIT 都应如此）。"""
    df = _ohlcv(["2026-04-01", "2026-05-01"])
    for kwargs in ({}, {"point_in_time": True}):
        merged = merge_fundamentals({"600036": df}, _frame(), **kwargs)
        assert merged["600036"]["eps"].isna().all()
        assert merged["600036"]["bps"].isna().all()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
