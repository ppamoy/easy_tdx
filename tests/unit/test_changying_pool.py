"""长盈标的池本地沉淀测试（V591）。"""

from __future__ import annotations

import json
from datetime import date

import pytest

from easy_tdx.fundamental import changying_pool
from easy_tdx.fundamental.changying_pool import (
    ChangyingStore,
    load_changying_pool,
    refresh_changying_pool,
)


@pytest.fixture()
def store(tmp_path) -> ChangyingStore:
    s = ChangyingStore(tmp_path / "pool.db")
    return s


def _result(market: str, code: str, category: str, score: float, mcap: float) -> dict:
    return {
        "market": market,
        "code": code,
        "category": category,
        "score": score,
        "scores": {category: score},
        "total_mcap_yi": mcap,
        "performance": {"as_of_close": 10.0},
        "report_date": "2025-03-31",
        "data_source": "gpcw",
        "details": {},
        "indicators": {"total_shares": 1e9},
    }


def test_store_roundtrip(store: ChangyingStore) -> None:
    store.save_pool(
        "2025-06-01",
        [
            _result("SH", "600519", "tree", 95.0, 150.0),
            _result("SZ", "000333", "grain", 88.0, 120.0),
        ],
    )
    loaded = store.load_pool()
    assert loaded is not None
    assert loaded["total"] == 2
    by_code = {r["code"]: r for r in loaded["results"]}
    assert by_code["600519"]["category"] == "tree"
    assert by_code["600519"]["scores"] == {"tree": 95.0}
    assert by_code["600519"]["total_mcap_yi"] == 150.0


def test_store_replace(store: ChangyingStore) -> None:
    store.save_pool("2025-06-01", [_result("SH", "600519", "tree", 95.0, 150.0)])
    store.save_pool(
        "2025-06-02",
        [_result("SZ", "000333", "grain", 88.0, 120.0)],
    )
    loaded = store.load_pool()
    assert loaded["total"] == 1
    assert loaded["results"][0]["code"] == "000333"
    assert loaded["date"] == "2025-06-02"


def test_store_load_empty(tmp_path) -> None:
    store = ChangyingStore(tmp_path / "empty.db")
    assert store.load_pool() is None


def test_refresh_calls_scan_and_persists(tmp_path, monkeypatch) -> None:
    def fake_scan_market(target, **kwargs):
        return {
            "date": "2025-06-01",
            "season": None,
            "by_category": {"tree": 1, "grain": 0, "vegetable": 0},
            "total_scanned": 2,
            "results": [
                _result("SH", "600519", "tree", 95.0, 150.0),
                _result("SZ", "000333", "grain", 88.0, 120.0),
            ],
        }

    monkeypatch.setattr(changying_pool, "_config_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "easy_tdx.fundamental.changying_pool._refresh",
        lambda *a, **k: fake_scan_market(a[0], **k),
    )
    out = refresh_changying_pool(date(2025, 6, 1), top_n=2)
    assert out["count"] == 2
    assert out["min_mcap_yi"] == 100.0
    loaded = load_changying_pool()
    assert loaded is not None and loaded["results"][0]["code"] == "600519"


def test_load_changying_pool_default_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(changying_pool, "_config_dir", lambda: tmp_path)
    assert load_changying_pool() is None


def test_indicators_json_parse(store: ChangyingStore) -> None:
    store.save_pool("2025-06-01", [_result("SH", "600519", "tree", 95.0, 150.0)])
    loaded = store.load_pool()
    assert json.dumps(loaded["results"][0]["indicators"]) is not None
