"""长盈选股模型金标（V609）。

用手工标注的财报行锁定「树粮菜」三维打分与分类结论，
以及市值/盈利两个硬门槛的纯函数口径。
"""

from __future__ import annotations

from datetime import date, timedelta

from easy_tdx.fundamental.pipeline import _profitable, _total_mcap_yi
from easy_tdx.fundamental.screener import screen_stock
from easy_tdx.fundamental.season import detect_season

TREE_ROW = {
    "code": "600001",
    "market": "SH",
    "report_date": "2025-12-31",
    "net_profit": 3e9,
    "revenue": 2e10,
    "roe": 25.0,
    "gross_margin": 45.0,
    "rev_yoy": 15.0,
    "np_yoy": 20.0,
    "debt_ratio": 50.0,
    "ocf_ps": 1.5,
    "eps": 2.0,
    "net_margin": 10.0,
}

GRAIN_ROW = {
    "code": "600002",
    "market": "SH",
    "report_date": "2025-12-31",
    "net_profit": 1e9,
    "revenue": 5e9,
    "roe": 12.0,
    "gross_margin": 30.0,
    "rev_yoy": 0.0,
    "np_yoy": 0.0,
    "debt_ratio": 35.0,
    "ocf_ps": 1.0,
    "eps": 1.2,
    "net_margin": 8.0,
}

VEGETABLE_ROW = {
    "code": "300001",
    "market": "SZ",
    "report_date": "2025-12-31",
    "net_profit": 5e8,
    "revenue": 3e9,
    "roe": 8.0,
    "gross_margin": 20.0,
    "rev_yoy": 25.0,
    "np_yoy": 35.0,
    "debt_ratio": 30.0,
    "ocf_ps": 0.8,
    "eps": 0.0,
    "net_margin": 15.0,
}


def test_tree_golden() -> None:
    sr = screen_stock(TREE_ROW, pool_size=1)
    assert sr is not None
    assert sr.category == "tree"
    assert sr.scores == {"tree": 100.0, "grain": 92.0, "vegetable": 72.0}
    d = sr.as_dict()
    assert d["novice_summary"]["risk_level"] == "低"


def test_grain_golden() -> None:
    sr = screen_stock(GRAIN_ROW, pool_size=1)
    assert sr is not None
    assert sr.category == "grain"
    assert sr.scores == {"tree": 39.0, "grain": 100.0, "vegetable": 45.0}


def test_vegetable_golden() -> None:
    sr = screen_stock(VEGETABLE_ROW, pool_size=1)
    assert sr is not None
    assert sr.category == "vegetable"
    assert sr.scores == {"tree": 49.0, "grain": 80.0, "vegetable": 100.0}


# ── 四季周期金标 ──────────────────────────────────────────────────────

def _season(cs, vols=None):
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(len(cs))]
    return detect_season(dates, cs, dates[-1], volumes=vols)


def test_season_summer_golden() -> None:
    sr = _season([100 + i * 0.6 for i in range(80)])
    assert sr.season == "summer"


def test_season_winter_golden() -> None:
    # 持续下跌 + 持续缩量 → 冬季；且强跌的 price_score 必须为 -2（锁 V616 修复）
    sr = _season([100 - i * 0.6 for i in range(80)], vols=[1000 - i * 10 for i in range(80)])
    assert sr.season == "winter"
    assert sr.signals["price_score"] == -2


def test_season_unknown_short_data() -> None:
    sr = _season([100 + i * 0.1 for i in range(30)])
    assert sr.season == "unknown"


def test_total_mcap_yi_golden() -> None:
    # 总股本 20 亿股 × 10 元 = 200 亿
    assert _total_mcap_yi({"total_shares": 2e9}, {"close": 10.0, "float_shares": None}) == 200.0
    # 无总股本时回退流通股本：10 万股 × 1e4 × 10 元 = 100 亿
    assert _total_mcap_yi({}, {"close": 10.0, "float_shares": 1e5}) == 100.0
    assert _total_mcap_yi({}, {"close": None, "float_shares": None}) is None


def test_profitable_golden() -> None:
    assert _profitable({"net_profit": 1.0}) is True
    assert _profitable({"net_profit": 0.0}) is False
    assert _profitable({"net_profit": None}) is False