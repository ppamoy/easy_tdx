"""P2 财务指标缓存（SQLite）单元测试：store/load roundtrip、格式版本失效、stats/clear/warm。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from easy_tdx.fundamental import cache


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "code": "600519",
                "market": "SH",
                "report_date": date(2026, 6, 30),
                "disclosure_date": date(2026, 8, 15),
                "eps": 21.76,
                "bps": 185.0,
                "roe": 11.7,
                "revenue": 1.4e10,
                "net_profit": 6.9e9,
                "gross_margin": 89.8,
                "net_margin": 50.5,
                "debt_ratio": 12.1,
                "ocf": 5.1e9,
                "ocf_ps": 4.0,
                "rev_yoy": 6.3,
                "np_yoy": 1.5,
                "asset_yoy": 8.0,
                "op_yoy": 2.0,
                "total_shares": 1.26e9,
                "circ_a": 1.26e9,
            },
            {
                "code": "000858",
                "market": "SZ",
                "report_date": date(2026, 6, 30),
                "disclosure_date": date(2026, 8, 18),
                "eps": 3.2,
                "bps": 40.0,
                "roe": 8.0,
                "revenue": 4.0e10,
                "net_profit": 1.7e10,
                "gross_margin": 78.0,
                "net_margin": 42.0,
                "debt_ratio": 30.0,
                "ocf": 6.0e9,
                "ocf_ps": 1.5,
                "rev_yoy": 12.0,
                "np_yoy": 10.0,
                "asset_yoy": 5.0,
                "op_yoy": 9.0,
                "total_shares": 1.9e9,
                "circ_a": 1.9e9,
            },
        ]
    )


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """把缓存库重定向到临时目录，测试之间互不污染。"""
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "gpcw_frames.db")


class TestCacheRoundtrip:
    def test_store_then_load_roundtrip(self):
        n = cache.store_frame("gpcw20260630.zip", _frame())
        assert n == 2
        loaded = cache.load_frame("gpcw20260630.zip")
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded["eps"].tolist() == [21.76, 3.2]
        # 日期类型还原
        assert loaded["report_date"].tolist() == [date(2026, 6, 30), date(2026, 6, 30)]
        assert loaded["disclosure_date"].iloc[0] == date(2026, 8, 15)

    def test_idempotent_resotre_overwrites(self):
        cache.store_frame("z.zip", _frame())
        cache.store_frame("z.zip", _frame().iloc[:1])
        loaded = cache.load_frame("z.zip")
        assert loaded is not None
        assert len(loaded) == 1

    def test_missing_returns_none(self):
        assert cache.load_frame("gpcw20251231.zip") is None
        assert cache.has_frame("gpcw20251231.zip") is False

    def test_format_version_invalidation(self, monkeypatch):
        cache.store_frame("z.zip", _frame())
        # 模拟指标口径升级：格式版本 +1 → 旧缓存应失效
        monkeypatch.setattr(cache, "FORMAT_VERSION", cache.FORMAT_VERSION + 1)
        assert cache.has_frame("z.zip") is False
        assert cache.load_frame("z.zip") is None

    def test_empty_frame_not_cached(self):
        assert cache.store_frame("z.zip", pd.DataFrame()) == 0
        assert cache.load_frame("z.zip") is None


class TestCacheStats:
    def test_stats_counts(self):
        cache.store_frame("a.zip", _frame())
        cache.store_frame("b.zip", _frame())
        st = cache.cache_stats()
        assert st["zips_count"] == 2
        assert st["total_rows"] == 4
        assert {z["filename"] for z in st["zips"]} == {"a.zip", "b.zip"}
        assert st["format_version"] == cache.FORMAT_VERSION

    def test_clear_cache(self):
        cache.store_frame("a.zip", _frame())
        assert cache.clear_cache() == 1
        assert cache.cache_stats()["zips_count"] == 0


class TestCacheWarm:
    def test_warm_parses_and_stores(self, monkeypatch):
        from easy_tdx.fundamental import cache as _cache

        calls: list[str] = []

        def _fake_records(fn, client=None):
            calls.append(fn)
            from easy_tdx.fundamental.indicators import ReportRecord

            return [
                ReportRecord(
                    code="600519",
                    market="SH",
                    report_date=date(2026, 6, 30),
                    disclosure_date=date(2026, 8, 15),
                    values={"基本每股收益": 21.76, "净资产收益率": 11.7},
                ),
            ]

        monkeypatch.setattr("easy_tdx.fundamental.indicators.records_from_zip", _fake_records)
        monkeypatch.setattr(
            "easy_tdx.fundamental.indicators.build_indicator_frame",
            lambda recs: _frame().iloc[:1] if recs else pd.DataFrame(),
        )

        res = _cache.warm(["gpcw20260630.zip"])
        assert res["warmed"] == ["gpcw20260630.zip"]
        assert res["already_cached"] == []
        assert _cache.has_frame("gpcw20260630.zip")

    def test_warm_skips_already_cached(self, monkeypatch):
        cache.store_frame("z.zip", _frame())
        from easy_tdx.fundamental import cache as _cache

        def _boom(fn, client=None):
            raise AssertionError("不应再次解析已缓存报告期")

        monkeypatch.setattr("easy_tdx.fundamental.indicators.records_from_zip", _boom)
        res = _cache.warm(["z.zip"])
        assert res["already_cached"] == ["z.zip"]
        assert res["warmed"] == []
