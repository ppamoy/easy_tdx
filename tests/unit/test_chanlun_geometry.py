"""缠论画图几何正确性回归测试（多周期 × 多形态）。

用户反馈：缠论 K 线图上笔/线段没有首尾相连、笔端点不在 K 线极值上。
本套件从模型层锁定以下不变量，防止回归：

1. 端点极值对齐：笔/线段/中枢/买卖点锚定的原始 K 线索引（start_index /
   end_index / bar_index）必须落在真实 K 线上，且端点价格 == 该K线极值
   （顶分型==high、底分型==low）。
2. 笔首尾相连：bi[i].end 与 bi[i+1].start 锚定同一根 K 线且价格相等。
3. 线段首尾相连 + 方向正确：xd[i].end 与 xd[i+1].start 共享转折点；
   向上线段终点价 > 起点价、向下线段终点价 < 起点价。
4. 分型 bar_index 对齐极值来源K线。

覆盖 6 种周期（DAILY/WEEK/MIN_5/MIN_15/MIN_30/MIN_60）× 4 种确定性
合成形态（多中枢下跌反转 / 长锯齿 / 强包含 / 慢牛回调），防止单一 fixture
掩盖缺陷。
"""

from __future__ import annotations

import pandas as pd
import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser

# (标签, 是否分钟, 后端 frequency)
PERIODS: list[tuple[str, bool, str]] = [
    ("DAILY", False, "daily"),
    ("WEEK", False, "weekly"),
    ("MIN_5", True, "5min"),
    ("MIN_15", True, "15min"),
    ("MIN_30", True, "30min"),
    ("MIN_60", True, "60min"),
]


def _seg(opens, closes, highs, lows, o, c, n):
    for i in range(n):
        opens.append(o + (c - o) * i / n)
        closes.append(o + (c - o) * (i + 1) / n)
        highs.append(max(opens[-1], closes[-1]) + 0.4)
        lows.append(min(opens[-1], closes[-1]) - 0.4)


def _build_df(shape: str, minute: bool = False) -> pd.DataFrame:
    """确定性K线数据（shape 选择不同形态）。"""
    opens: list[float] = []
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []

    if shape == "zigzag":
        # 长锯齿：产出 ≥2 段方向交替的线段
        _seg(opens, closes, highs, lows, 20, 26, 12)
        _seg(opens, closes, highs, lows, 26, 22, 8)
        _seg(opens, closes, highs, lows, 22, 27, 12)
        _seg(opens, closes, highs, lows, 27, 21, 10)
        _seg(opens, closes, highs, lows, 21, 28, 14)
        _seg(opens, closes, highs, lows, 28, 23, 9)
        _seg(opens, closes, highs, lows, 23, 30, 15)
        _seg(opens, closes, highs, lows, 30, 24, 8)
    elif shape == "downtrend_reversal":
        # 多中枢下跌→反转（同 test_chanlun.py 视觉日期用例）
        _seg(opens, closes, highs, lows, 24, 19.5, 10)
        _seg(opens, closes, highs, lows, 19.5, 20.5, 5)
        _seg(opens, closes, highs, lows, 20.5, 18.5, 5)
        _seg(opens, closes, highs, lows, 18.5, 19.5, 5)
        _seg(opens, closes, highs, lows, 19.5, 16.5, 8)
        _seg(opens, closes, highs, lows, 16.5, 17.5, 4)
        _seg(opens, closes, highs, lows, 17.5, 15.5, 4)
        _seg(opens, closes, highs, lows, 15.5, 16.5, 4)
        _seg(opens, closes, highs, lows, 16.5, 13.8, 4)
        _seg(opens, closes, highs, lows, 13.8, 17.0, 5)
    elif shape == "inclusion_heavy":
        # 强包含：大实体 + 小实体包含，制造合并极值来源错位的场景
        rows = [
            (10, 12, 13, 9.5),
            (11, 12.5, 12.8, 10.8),
            (12, 12.2, 12.5, 11.0),
            (11.5, 13, 13.5, 11.2),
            (12, 12.8, 13.2, 11.8),
            (12.5, 12.2, 13.0, 11.0),
            (11.8, 11.0, 12.2, 10.5),
            (11.2, 10.8, 11.5, 10.2),
            (10.5, 9.8, 10.8, 9.4),
            (9.9, 10.2, 10.5, 9.6),
            (10.0, 10.8, 11.0, 9.8),
            (10.6, 11.4, 11.8, 10.4),
            (11.2, 11.0, 11.5, 10.6),
            (10.8, 10.2, 11.0, 9.9),
            (10.0, 9.4, 10.2, 9.0),
            (9.5, 9.8, 10.1, 9.2),
            (9.6, 10.4, 10.6, 9.4),
            (10.2, 10.0, 10.5, 9.8),
            (10.1, 9.5, 10.2, 9.3),
            (9.6, 9.9, 10.2, 9.4),
            (9.8, 8.8, 10.0, 8.5),
            (8.9, 9.2, 9.5, 8.6),
            (9.1, 10.2, 10.4, 9.0),
            (10.0, 10.6, 10.8, 9.9),
            (10.4, 11.2, 11.5, 10.3),
            (10.8, 10.6, 11.0, 10.2),
        ]
        for (o, c, h, low) in rows:
            opens.append(o)
            closes.append(c)
            highs.append(h)
            lows.append(low)
    else:  # "slow_trend"
        # 慢牛回调：整体上行 + 多次回调，检验长序列连续性
        _seg(opens, closes, highs, lows, 10, 11, 6)
        _seg(opens, closes, highs, lows, 11, 10.4, 4)
        _seg(opens, closes, highs, lows, 10.4, 12, 7)
        _seg(opens, closes, highs, lows, 12, 11.3, 4)
        _seg(opens, closes, highs, lows, 11.3, 13, 8)
        _seg(opens, closes, highs, lows, 13, 12.4, 4)
        _seg(opens, closes, highs, lows, 12.4, 14.5, 9)
        _seg(opens, closes, highs, lows, 14.5, 13.8, 5)
        _seg(opens, closes, highs, lows, 13.8, 15.5, 8)

    n = len(closes)
    if minute:
        dates = pd.date_range("2025-01-02 09:30", periods=n, freq="5min")
    else:
        dates = pd.date_range("2025-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": opens,
            "close": closes,
            "high": highs,
            "low": lows,
            "vol": [1000] * n,
        }
    )


def _run(shape: str, minute: bool, freq: str) -> tuple[pd.DataFrame, dict, dict]:
    df = _build_df(shape, minute=minute)
    result = ChanlunAnalyser(code="SZ000001", frequency=freq).process_klines(df)
    d = result.to_dict()
    # 分型列表由 web router 追加；这里按相同契约补上，便于直接校验 bar_index
    d["fractals"] = [
        {
            "fx_type": fx.fx_type.value,
            "date": result._fmt_dt(fx.k.date),
            "val": round(fx.val, 2),
            "index": fx.index,
            "bar_index": fx.bar_index,
        }
        for fx in result.fractals
    ]
    return df, d, result


def _bars_list(df: pd.DataFrame) -> list[dict]:
    out: list[dict] = []
    for row in df.to_dict(orient="records"):
        row = dict(row)
        row["datetime"] = str(row["datetime"])
        out.append(row)
    return out


def _assert_bi_geometry(bars: list[dict], bis: list[dict], tag: str) -> None:
    """笔：端点极值对齐 + 首尾相连。"""
    for bi in bis:
        si, ei = bi["start_index"], bi["end_index"]
        assert 0 <= si < len(bars), f"{tag} bi{bi['index']} start_index 越界"
        assert 0 <= ei < len(bars), f"{tag} bi{bi['index']} end_index 越界"
        sb, eb = bars[si], bars[ei]
        if bi["direction"] == "up":
            assert sb["low"] == bi["start_val"], f"{tag} bi{bi['index']} 起点价不在K线极值 {bi}"
            assert eb["high"] == bi["end_val"], f"{tag} bi{bi['index']} 终点价不在K线极值 {bi}"
        else:
            assert sb["high"] == bi["start_val"], f"{tag} bi{bi['index']} 起点价不在K线极值 {bi}"
            assert eb["low"] == bi["end_val"], f"{tag} bi{bi['index']} 终点价不在K线极值 {bi}"
    for i in range(len(bis) - 1):
        prev, nxt = bis[i], bis[i + 1]
        assert prev["end_index"] == nxt["start_index"], (
            f"{tag} bi{i} 终点与 bi{i+1} 起点索引不同"
        )
        assert prev["end_val"] == nxt["start_val"], (
            f"{tag} bi{i} 终点与 bi{i+1} 起点价格不同"
        )


def _assert_xd_geometry(bars: list[dict], xds: list[dict], tag: str) -> None:
    """线段：端点极值对齐 + 首尾相连 + 方向一致。"""
    for xd in xds:
        si, ei = xd["start_index"], xd["end_index"]
        assert 0 <= si < len(bars) and 0 <= ei < len(bars), f"{tag} xd 越界 {xd}"
        sb, eb = bars[si], bars[ei]
        if xd["direction"] == "up":
            assert xd["end_val"] > xd["start_val"], f"{tag} 向上线段终点应高于起点 {xd}"
            assert sb["low"] == xd["start_val"]
            assert eb["high"] == xd["end_val"]
        else:
            assert xd["end_val"] < xd["start_val"], f"{tag} 向下线段终点应低于起点 {xd}"
            assert sb["high"] == xd["start_val"]
            assert eb["low"] == xd["end_val"]
    for i in range(len(xds) - 1):
        prev, nxt = xds[i], xds[i + 1]
        assert prev["end_index"] == nxt["start_index"], f"{tag} 相邻线段共享转折点"
        assert prev["end_val"] == nxt["start_val"], f"{tag} 相邻线段转折价格一致"


def _assert_fx_zs_mmd_geometry(bars: list[dict], d: dict, tag: str) -> None:
    """分型 bar_index、中枢 start/end、买卖点 bar_index 对齐 K 线。"""
    for fx in d.get("fractals", []):
        bi_ = fx["bar_index"]
        assert 0 <= bi_ < len(bars), f"{tag} 分型 bar_index 越界 {fx}"
        bar = bars[bi_]
        if fx["fx_type"] == "ding":
            assert bar["high"] == fx["val"], f"{tag} 顶分型未落在K线高点 {fx}"
        else:
            assert bar["low"] == fx["val"], f"{tag} 底分型未落在K线低点 {fx}"
    for zs in d.get("zss", []):
        if zs["start_index"] is not None:
            assert 0 <= zs["start_index"] < len(bars), f"{tag} 中枢 start 越界 {zs}"
        if zs["end_index"] is not None:
            assert 0 <= zs["end_index"] < len(bars), f"{tag} 中枢 end 越界 {zs}"
    for mmd in d.get("mmds", []):
        if mmd["bar_index"] is not None:
            assert 0 <= mmd["bar_index"] < len(bars), f"{tag} 买卖点 bar_index 越界 {mmd}"


SHAPES = ["downtrend_reversal", "zigzag", "inclusion_heavy", "slow_trend"]


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("period,minute,freq", PERIODS)
def test_full_geometry_matrix(shape: str, period: str, minute: bool, freq: str) -> None:
    """多周期 × 多形态 全矩阵几何不变量。"""
    df, d, _ = _run(shape, minute=minute, freq=freq)
    bars = _bars_list(df)
    tag = f"[{period}/{shape}]"
    _assert_bi_geometry(bars, d["bis"], tag)
    _assert_xd_geometry(bars, d["xds"], tag)
    _assert_fx_zs_mmd_geometry(bars, d, tag)


def test_bis_connect_end_to_end() -> None:
    """笔与笔首尾相连（保留单测，覆盖多形态）。"""
    for shape in SHAPES:
        for minute in (False, True):
            _, d, _ = _run(shape, minute=minute, freq="5min" if minute else "daily")
            if len(d["bis"]) < 2:
                continue
            for i in range(len(d["bis"]) - 1):
                prev, nxt = d["bis"][i], d["bis"][i + 1]
                assert prev["end_index"] == nxt["start_index"]
                assert prev["end_val"] == nxt["start_val"]


def test_fractal_bar_index_aligns() -> None:
    """分型 bar_index 必须指向产生极值的那根K线。"""
    df, d, _ = _run("inclusion_heavy", minute=False, freq="daily")
    bars = _bars_list(df)
    fxs = d.get("fractals", [])
    assert len(fxs) >= 2
    for fx in fxs:
        bar = bars[fx["bar_index"]]
        if fx["fx_type"] == "ding":
            assert bar["high"] == fx["val"], f"顶分型未落在K线高点 {fx}"
        else:
            assert bar["low"] == fx["val"], f"底分型未落在K线低点 {fx}"


def test_segment_tail_no_contradiction() -> None:
    """线段收尾不得产生方向矛盾（向上段终点必须高于起点）。"""
    for shape in SHAPES:
        for period, minute, freq in PERIODS:
            df, d, _ = _run(shape, minute=minute, freq=freq)
            for xd in d["xds"]:
                if xd["direction"] == "up":
                    assert xd["end_val"] > xd["start_val"], f"[{period}/{shape}] 向上段矛盾"
                else:
                    assert xd["end_val"] < xd["start_val"], f"[{period}/{shape}] 向下段矛盾"
