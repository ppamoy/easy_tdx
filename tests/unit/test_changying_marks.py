"""长盈全市场树/粮/菜标记测试（V722）。

覆盖：marks 落库/过滤/截断、半成品保护、报告期检测、
/stock-pick 本地回退链（local-full → local → online）。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from easy_tdx.fundamental import marks as marks_mod
from easy_tdx.fundamental.marks import (
    ChangyingMarkStore,
    detect_new_report_period,
    derive_pool_from_marks,
    load_changying_marks,
    marks_selfcheck,
    refresh_changying_marks,
)


@pytest.fixture(autouse=True)
def _isolate_real_db(tmp_path, monkeypatch):
    """默认把真实 marks 库指向 tmp_path（V722 修复：真实 changying-mark
    落库后 1602 条数据泄漏进单测，空库/自检假设被打破）。"""
    monkeypatch.setattr(marks_mod, "_db_path", lambda: tmp_path / "marks.db")


@pytest.fixture()
def store(tmp_path) -> ChangyingMarkStore:
    return ChangyingMarkStore(tmp_path / "marks.db")


def _mark(market: str, code: str, category: str, score: float, mcap: float) -> dict:
    return {
        "market": market,
        "code": code,
        "category": category,
        "score": score,
        "scores": {category: score},
        "total_mcap_yi": mcap,
        "report_date": "2025-03-31",
        "data_source": "gpcw",
        "details": {},
        "indicators": {"total_shares": 1e9},
    }


# ── 存储层 ────────────────────────────────────────────────────────────────


def test_marks_roundtrip(store: ChangyingMarkStore) -> None:
    store.save_marks(
        "2025-06-01",
        [
            _mark("SH", "600519", "tree", 95.0, 150.0),
            _mark("SZ", "000333", "grain", 88.0, 120.0),
            _mark("SZ", "002594", "vegetable", 80.0, 900.0),
        ],
    )
    loaded = store.load_marks()
    assert loaded is not None
    assert loaded["total"] == 3
    assert loaded["by_category"] == {"tree": 1, "grain": 1, "vegetable": 1}
    by_code = {r["code"]: r for r in loaded["results"]}
    assert by_code["600519"]["category"] == "tree"
    assert by_code["600519"]["total_mcap_yi"] == 150.0
    assert by_code["002594"]["category"] == "vegetable"


def test_marks_filters_and_topn(store: ChangyingMarkStore) -> None:
    store.save_marks(
        "2025-06-01",
        [
            _mark("SH", "600519", "tree", 95.0, 150.0),
            _mark("SZ", "000333", "grain", 88.0, 120.0),
            _mark("BJ", "830799", "tree", 70.0, 110.0),
        ],
    )
    tree_only = store.load_marks(stock_type="tree")
    assert tree_only is not None
    assert [r["code"] for r in tree_only["results"]] == ["600519", "830799"]
    # by_category 统计基于过滤后的全量（截断前）
    assert tree_only["by_category"] == {"tree": 2}

    sh_only = store.load_marks(markets=["SH"])
    assert sh_only is not None
    assert [r["code"] for r in sh_only["results"]] == ["600519"]

    capped = store.load_marks(top_n=1)
    assert capped is not None
    assert capped["total"] == 1
    assert capped["results"][0]["code"] == "600519"  # 得分最高


def test_marks_empty_returns_none(store: ChangyingMarkStore) -> None:
    assert store.load_marks() is None
    assert marks_selfcheck()["count"] is None


def test_snapshot_meta(store: ChangyingMarkStore) -> None:
    store.save_marks("2025-06-01", [_mark("SH", "600519", "tree", 95.0, 150.0)])
    meta = store.last_snapshot_meta()
    assert meta is not None
    assert meta["count"] == 1
    assert meta["trade_date"] == "2025-06-01"


# ── 半成品保护 ────────────────────────────────────────────────────────────


def test_half_guard_rejects_shrink(tmp_path, monkeypatch) -> None:
    """本次标的数 < 上期 80% 时拒绝覆盖且旧数据完好。"""
    monkeypatch.setattr(marks_mod, "_db_path", lambda: tmp_path / "marks.db")
    store = ChangyingMarkStore(tmp_path / "marks.db")
    store.save_marks(
        "2025-06-01",
        [_mark("SH", f"60030{i}", "grain", 80.0, 200.0) for i in range(10)],
    )

    def _fake_scan(target, **kwargs):
        # 只有 5 只合格（= 上期 50%，触发保护）
        return {
            "results": [_mark("SH", f"60030{i}", "grain", 80.0, 200.0) for i in range(5)],
            "total_scanned": 100,
        }

    with patch("easy_tdx.fundamental.pipeline.scan_market", _fake_scan):
        with pytest.raises(RuntimeError, match="半成品保护"):
            refresh_changying_marks(date(2025, 7, 1))

    # 旧快照完好
    loaded = store.load_marks()
    assert loaded is not None
    assert loaded["total"] == 10


def test_half_guard_force_overrides(tmp_path, monkeypatch) -> None:
    """--force 跳过半成品保护。"""
    monkeypatch.setattr(marks_mod, "_db_path", lambda: tmp_path / "marks.db")
    store = ChangyingMarkStore(tmp_path / "marks.db")
    store.save_marks(
        "2025-06-01",
        [_mark("SH", f"60030{i}", "grain", 80.0, 200.0) for i in range(10)],
    )

    def _fake_scan(target, **kwargs):
        return {
            "results": [_mark("SH", "600001", "tree", 90.0, 300.0)],
            "total_scanned": 100,
        }

    with patch("easy_tdx.fundamental.pipeline.scan_market", _fake_scan):
        out = refresh_changying_marks(date(2025, 7, 1), force=True)
    assert out["count"] == 1
    loaded = store.load_marks()
    assert loaded is not None
    assert loaded["total"] == 1


def test_first_run_no_guard(tmp_path, monkeypatch) -> None:
    """首次运行（无历史快照）不触发保护。"""
    monkeypatch.setattr(marks_mod, "_db_path", lambda: tmp_path / "marks.db")

    def _fake_scan(target, **kwargs):
        return {"results": [_mark("SH", "600001", "tree", 90.0, 300.0)], "total_scanned": 50}

    with patch("easy_tdx.fundamental.pipeline.scan_market", _fake_scan):
        out = refresh_changying_marks(date(2025, 7, 1))
    assert out["count"] == 1
    assert out["min_mcap_yi"] == 100.0


def test_refresh_passes_no_truncation_args(tmp_path, monkeypatch) -> None:
    """refresh 必须以超大 top_n + 市值门槛调用 scan_market（全量语义）。"""
    monkeypatch.setattr(marks_mod, "_db_path", lambda: tmp_path / "marks.db")
    captured: dict = {}

    def _fake_scan(target, **kwargs):
        captured.update(kwargs)
        return {"results": [], "total_scanned": 0}

    with patch("easy_tdx.fundamental.pipeline.scan_market", _fake_scan):
        refresh_changying_marks(date(2025, 7, 1))
    assert captured["top_n"] >= 10000  # 不截断
    assert captured["min_mcap_yi"] == 100.0
    assert captured["with_performance"] is False


# ── 报告期检测（季报兜底）────────────────────────────────────────────────


def test_detect_new_report_period(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EASY_TDX_CONFIG_DIR", str(tmp_path))
    cache = tmp_path / "gpcw_cache"
    cache.mkdir()
    (cache / "gpcw20251231.zip").write_bytes(b"x")

    assert detect_new_report_period() is True  # 无 known 记录 → 新期

    # 标记成功后记录当前期，再次检测应为无新期
    marks_mod._record_periods()
    assert detect_new_report_period() is False

    # 出现新报告期 → True
    (cache / "gpcw20260331.zip").write_bytes(b"x")
    assert detect_new_report_period() is True


# ── 精选池派生 ────────────────────────────────────────────────────────────


def test_derive_pool_from_marks(tmp_path, monkeypatch) -> None:
    marks_db = tmp_path / "marks.db"
    store = ChangyingMarkStore(marks_db)
    store.save_marks(
        "2025-06-01",
        [
            _mark("SH", "600519", "tree", 95.0, 150.0),
            _mark("SZ", "000333", "grain", 88.0, 120.0),
            _mark("SZ", "002594", "vegetable", 80.0, 900.0),
        ],
    )
    monkeypatch.setattr(marks_mod, "_db_path", lambda: marks_db)
    with patch(
        "easy_tdx.fundamental.changying_pool._db_path",
        lambda: tmp_path / "pool.db",
    ):
        out = derive_pool_from_marks(top_n=2)
    assert out is not None
    assert out["count"] == 2
    # 精选池按得分取前 2：tree 95 / grain 88
    from easy_tdx.fundamental.changying_pool import ChangyingStore

    pool = ChangyingStore(tmp_path / "pool.db").load_pool()
    assert pool is not None
    assert [r["code"] for r in pool["results"]] == ["600519", "000333"]


# ── /stock-pick 回退链 ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stock_pick_prefers_marks(tmp_path, monkeypatch) -> None:
    """/stock-pick 本地路径：marks 非空时 source=local-full。"""
    from easy_tdx.web.routers import stock_pick

    marks_db = tmp_path / "marks.db"
    ChangyingMarkStore(marks_db).save_marks(
        "2025-06-01",
        [
            _mark("SH", "600519", "tree", 95.0, 150.0),
            _mark("SZ", "000333", "grain", 88.0, 120.0),
        ],
    )
    monkeypatch.setattr(marks_mod, "_db_path", lambda: marks_db)
    monkeypatch.setattr(
        "easy_tdx.fundamental.changying_pool._db_path", lambda: tmp_path / "pool.db"
    )

    resp = await stock_pick.stock_pick_screen(
        {"date": "2025-07-01", "stock_type": "all", "top_n": 50}
    )
    assert resp["source"] == "local-full"
    assert resp["total"] == 2


@pytest.mark.asyncio
async def test_stock_pick_falls_back_to_pool(tmp_path, monkeypatch) -> None:
    """/stock-pick 本地路径：marks 为空时回退精选池 source=local。"""
    from easy_tdx.web.routers import stock_pick

    empty_marks = tmp_path / "marks.db"
    ChangyingMarkStore(empty_marks)  # 建空表
    monkeypatch.setattr(marks_mod, "_db_path", lambda: empty_marks)

    from easy_tdx.fundamental.changying_pool import ChangyingStore

    ChangyingStore(tmp_path / "pool.db").save_pool(
        "2025-06-01", [_mark("SH", "600519", "tree", 95.0, 150.0)]
    )
    monkeypatch.setattr(
        "easy_tdx.fundamental.changying_pool._db_path", lambda: tmp_path / "pool.db"
    )

    resp = await stock_pick.stock_pick_screen(
        {"date": "2025-07-01", "stock_type": "all", "top_n": 50}
    )
    assert resp["source"] == "local"
    assert resp["total"] == 1
