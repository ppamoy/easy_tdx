"""全市场选股「过滤 + 截断 top_n」金标（V611）。

注入固定候选集，锁定 scan_market 的复合逻辑：
盈利硬门槛 → 评分排序 → 市值门槛 → 截断 top_n。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from easy_tdx.fundamental import pipeline
from easy_tdx.fundamental.screener import ScreenResult


def _mk(
    code: str, market: str, category: str, score: float, net_profit: float, total_shares: float
):
    return ScreenResult(
        code=code,
        market=market,
        category=category,
        scores={category: score},
        details={},
        report_date=date(2025, 12, 31),
        indicators={"net_profit": net_profit, "total_shares": total_shares},
    )


def test_scan_market_profit_mcap_topn(monkeypatch) -> None:
    # A/B 应保留，C 亏损被盈利门槛排除，D 市值 50 亿被市值门槛排除
    a = _mk("600001", "SH", "tree", 95.0, 1e9, 2e9)
    b = _mk("600002", "SH", "grain", 90.0, 1e9, 2e9)
    c = _mk("600003", "SH", "tree", 99.0, -1e9, 2e9)  # 亏损
    d = _mk("300001", "SZ", "vegetable", 98.0, 1e9, 5e8)  # 小市值(50亿)

    by_code = {r.code: r for r in (a, b, c, d)}
    frame = pd.DataFrame(
        [
            {"code": "600001", "market": "SH"},
            {"code": "600002", "market": "SH"},
            {"code": "600003", "market": "SH"},
            {"code": "300001", "market": "SZ"},
        ]
    )

    monkeypatch.setattr(pipeline, "pick_report_zips", lambda *a, **k: ["gpcwX.zip"])
    monkeypatch.setattr(pipeline, "load_all_periods_frame", lambda *a, **k: frame)
    monkeypatch.setattr(pipeline, "pick_reports_bulk", lambda *a, **k: frame)
    monkeypatch.setattr(pipeline, "detect_season_for_date", lambda *a, **k: None)
    monkeypatch.setattr(
        pipeline,
        "screen_stock",
        lambda row, pool_size=1: by_code.get(row.get("code")),
    )
    monkeypatch.setattr(
        pipeline,
        "_market_quote",
        lambda market, code, target, client=None: {"close": 10.0, "float_shares": None},
    )

    out = pipeline.scan_market(
        date(2026, 5, 1),
        markets=("SH", "SZ"),
        stock_type="all",
        top_n=2,
        min_score=0.0,
        with_performance=False,
        min_mcap_yi=100.0,
        require_profit=True,
    )

    codes = [r["code"] for r in out["results"]]
    assert codes == ["600001", "600002"], f"应保留 A/B，实际 {codes}"
    # total_scanned = 候选池总数（4），盈利门槛在评分阶段排除 C
    assert out["total_scanned"] == 4
