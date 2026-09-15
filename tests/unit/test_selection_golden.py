"""选股挑 20 只的输出路径金标（V610）。

锁定 stock_pick 结果行归一化（质量分正确取 scores[category]，修掉旧的质量分恒 0 bug）
与长盈池本地存储的按分数排序。
"""

from __future__ import annotations

from easy_tdx.fundamental.changying_pool import ChangyingStore
from easy_tdx.web.routers.stock_pick import _normalize_result_row


def test_normalize_result_row_uses_scores_category() -> None:
    r = {
        "market": "SH",
        "code": "600519",
        "category": "tree",
        "scores": {"tree": 88.5, "grain": 70.0, "vegetable": 60.0},
        "total_mcap_yi": 18000.0,
        "details": {},
        "indicators": {},
        "novice_summary": {"risk_level": "低"},
    }
    out = _normalize_result_row(r)
    assert out["quality_score"] == 88.5  # 从 scores[category] 取，而非恒 0
    assert out["symbol"] == "SH:600519"
    assert out["total_mcap_yi"] == 18000.0
    assert out["detail"]["novice_summary"]["risk_level"] == "低"


def test_normalize_result_row_score_field_priority() -> None:
    r = {
        "market": "SH",
        "code": "600519",
        "category": "tree",
        "score": 95.0,
        "scores": {"tree": 90.0},
    }
    out = _normalize_result_row(r)
    assert out["quality_score"] == 95.0  # score 字段优先


def test_changying_store_sorts_by_score_desc(tmp_path) -> None:
    store = ChangyingStore(tmp_path / "pool.db")
    store.save_pool(
        "2025-06-01",
        [
            {
                "market": "SZ",
                "code": "000333",
                "category": "grain",
                "score": 88.0,
                "scores": {"grain": 88.0},
                "total_mcap_yi": 100.0,
                "performance": {"as_of_close": 10.0},
                "report_date": "2025-03-31",
                "data_source": "gpcw",
                "details": {},
                "indicators": {},
            },
            {
                "market": "SH",
                "code": "600519",
                "category": "tree",
                "score": 95.0,
                "scores": {"tree": 95.0},
                "total_mcap_yi": 18000.0,
                "performance": {"as_of_close": 10.0},
                "report_date": "2025-03-31",
                "data_source": "gpcw",
                "details": {},
                "indicators": {},
            },
        ],
    )
    loaded = store.load_pool()
    assert loaded is not None
    assert [r["code"] for r in loaded["results"]] == ["600519", "000333"]
    assert loaded["results"][0]["total_mcap_yi"] == 18000.0
