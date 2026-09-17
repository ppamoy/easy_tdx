"""缠论精度 v590：配置项与买卖点/背驰锚定字段契约。

验证：
1. config.bi_fractal_confirm 默认 False（不再静默丢弃未确认极值导致笔画不到
   最高/最低点），bi_weak_skip 默认 False。
2. analyser 序列化 mmd/bc 均带 anchor_val / anchor_bar_index（触发笔终点
   分型极值），供前端精确标注。
3. 若某买卖点/背驰可锚定，则 anchor 价格必须等于锚定 K 线极值。
"""

from __future__ import annotations

import pandas as pd

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig


def _downtrend_df() -> pd.DataFrame:
    segs = [
        (24, 19.5, 10),
        (19.5, 20.5, 5),
        (20.5, 18.5, 5),
        (18.5, 19.5, 5),
        (19.5, 16.5, 8),
        (16.5, 17.5, 4),
        (17.5, 15.5, 4),
        (15.5, 16.5, 4),
        (16.5, 13.8, 4),
        (13.8, 17.0, 5),
    ]
    opens: list[float] = []
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    for o, c, n in segs:
        for i in range(n):
            opens.append(o + (c - o) * i / n)
            closes.append(o + (c - o) * (i + 1) / n)
            highs.append(max(opens[-1], closes[-1]) + 0.4)
            lows.append(min(opens[-1], closes[-1]) - 0.4)
    n = len(closes)
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2025-01-02", periods=n, freq="B"),
            "open": opens,
            "close": closes,
            "high": highs,
            "low": lows,
            "vol": [1000] * n,
        }
    )


def test_config_defaults_do_not_drop_extremes() -> None:
    cfg = ChanlunConfig()
    assert cfg.bi_fractal_confirm is False
    assert cfg.bi_weak_skip is False


def test_mmd_and_bc_anchor_fields_present_and_aligned() -> None:
    df = _downtrend_df()
    res = ChanlunAnalyser("SZ000001", "daily").process_klines(df)
    d = res.to_dict()
    bars = df.to_dict(orient="records")

    assert all("anchor_val" in m and "bar_index" in m for m in d["mmds"])
    assert all("anchor_val" in b and "anchor_bar_index" in b for b in d["bcs"])

    for m in d["mmds"]:
        bi_ = m["bar_index"]
        if bi_ is None or m["anchor_val"] is None:
            continue
        assert 0 <= bi_ < len(bars)
        is_buy = "buy" in m["type"]
        bar = bars[bi_]
        if is_buy:
            assert m["anchor_val"] == bar["low"], f"买点未锚定极值 {m}"
        else:
            assert m["anchor_val"] == bar["high"], f"卖点未锚定极值 {m}"

    for b in d["bcs"]:
        bi_ = b["anchor_bar_index"]
        if bi_ is None or b["anchor_val"] is None:
            continue
        assert 0 <= bi_ < len(bars)
        bar = bars[bi_]
        assert b["anchor_val"] in (bar["high"], bar["low"]), f"背驰未锚定极值 {b}"


def test_config_bi_fractal_confirm_true_keeps_endpoint_geometry() -> None:
    df = _downtrend_df()
    res = ChanlunAnalyser(
        "SZ000001", "daily", ChanlunConfig(bi_fractal_confirm=True)
    ).process_klines(df)
    d = res.to_dict()
    bars = df.to_dict(orient="records")
    for bi in d["bis"]:
        si, ei = bi["start_index"], bi["end_index"]
        sb, eb = bars[si], bars[ei]
        if bi["direction"] == "up":
            assert sb["low"] == bi["start_val"], f"confirm=True 起点未锚定极值 {bi}"
            assert eb["high"] == bi["end_val"], f"confirm=True 终点未锚定极值 {bi}"
        else:
            assert sb["high"] == bi["start_val"], f"confirm=True 起点未锚定极值 {bi}"
            assert eb["low"] == bi["end_val"], f"confirm=True 终点未锚定极值 {bi}"


def test_config_bi_fractal_confirm_toggle_runs() -> None:
    df = _downtrend_df()
    ok = ChanlunAnalyser(
        "SZ000001", "daily", ChanlunConfig(bi_fractal_confirm=True)
    ).process_klines(df)
    assert ok.bis  # 不崩溃且产出笔
