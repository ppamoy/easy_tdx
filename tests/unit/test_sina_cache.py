"""V91 新浪财报指标缓存（SQLite）+ scan_market 新浪补充：单元测试。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from easy_tdx.fundamental import sina_cache


class _Row:
    """模拟 SinaFinancialRow（与 sina_adapter 同构）。"""

    def __init__(self, report_date, disclosure_date, indicators):
        self.code = "600519"
        self.market = "SH"
        self.report_date = report_date
        self.disclosure_date = disclosure_date
        self.indicators = indicators


def _rows():
    return [
        _Row(
            date(2026, 6, 30), date(2026, 8, 31),
            {"eps": 35.57, "roe": 16.98, "gross_margin": 89.73},
        ),
        _Row(
            date(2026, 3, 31), date(2026, 4, 30),
            {"eps": 21.76, "roe": 9.7, "gross_margin": 91.2},
        ),
        _Row(
            date(2025, 12, 31), date(2026, 4, 30),
            {"eps": 35.0, "roe": 22.0, "gross_margin": 90.0},
        ),
    ]


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(sina_cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sina_cache, "DB_PATH", tmp_path / "sina_rows.db")


class TestSinaCacheStore:
    def test_roundtrip(self):
        n = sina_cache.store_rows("600519", "SH", _rows())
        assert n == 3
        loaded = sina_cache.load_rows("600519")
        assert loaded is not None
        assert len(loaded) == 3
        assert loaded[0]["indicators"]["eps"] == 35.57
        # 日期还原
        assert loaded[0]["report_date"] == date(2026, 6, 30)

    def test_missing_code_none(self):
        assert sina_cache.load_rows("000001") is None
        assert sina_cache.has_rows("000001") is False

    def test_idempotent_overwrite(self):
        sina_cache.store_rows("600519", "SH", _rows())
        sina_cache.store_rows("600519", "SH", _rows()[:1])
        loaded = sina_cache.load_rows("600519")
        assert loaded is not None
        assert len(loaded) == 1

    def test_stats_and_clear(self):
        sina_cache.store_rows("600519", "SH", _rows())
        sina_cache.store_rows("000858", "SZ", _rows()[:1])
        st = sina_cache.cache_stats()
        assert st["codes_count"] == 2
        assert st["total_rows"] == 4
        assert st["db_bytes"] > 0
        assert sina_cache.clear_cache() == 2
        assert sina_cache.cache_stats()["codes_count"] == 0

    def test_version_invalidation(self, monkeypatch):
        sina_cache.store_rows("600519", "SH", _rows())
        monkeypatch.setattr(sina_cache, "FORMAT_VERSION", sina_cache.FORMAT_VERSION + 1)
        assert sina_cache.load_rows("600519") is None


class TestSinaAdapterCacheIntegration:
    """load_sina_rows 的缓存优先路径（不依赖网络，直接注缓存）。"""

    def test_cached_rows_used_without_http(self, monkeypatch):
        sina_cache.store_rows("600519", "SH", _rows())

        from easy_tdx.fundamental import sina_adapter

        def _boom(*a, **k):
            raise AssertionError("命中缓存时不应触发 HTTP")

        monkeypatch.setattr("easy_tdx.sina.client.SinaClient", _boom)
        rows = sina_adapter.load_sina_rows("600519", "SH", num=2)
        assert len(rows) == 2
        assert rows[0].indicators["eps"] == 35.57

    def test_use_cache_false_forces_fetch(self, monkeypatch):
        from easy_tdx.fundamental import sina_adapter

        def _fake_client(timeout: int = 40):
            class _C:
                def get_financial_report(self, code, rtype, num=40):
                    import pandas as pd

                    if rtype == "lrb":
                        return pd.DataFrame([{"报告期": "2026-06-30", "营业总收入": 100.0,
                                              "归属于母公司所有者的净利润": 20.0,
                                              "基本每股收益": 2.0,
                                              "营业成本": 55.0,
                                              "营业总收入_同比": 0.1,
                                              "归属于母公司所有者的净利润_同比": 0.2}])
                    if rtype == "fzb":
                        return pd.DataFrame([{"报告期": "2026-06-30",
                                              "所有者权益(或股东权益)合计": 80.0,
                                              "资产总计": 200.0,
                                              "负债合计": 80.0}])
                    return pd.DataFrame([{"报告期": "2026-06-30",
                                          "经营活动产生的现金流量净额": 25.0}])

            return _C()

        monkeypatch.setattr("easy_tdx.sina.client.SinaClient", _fake_client)
        rows = sina_adapter.load_sina_rows("600519", "SH", num=2, use_cache=False)
        assert rows and len(rows) == 1
        assert rows[0].indicators["gross_margin"] == 45.0  # (100-55)/100*100


class TestScanMarketSinaFallback:
    """scan_market 在 gpcw 空帧 + sina_pool 时的补充路径（纯逻辑）。"""

    def test_sina_fallback_fills_frame(self, monkeypatch):
        from easy_tdx.fundamental import pipeline

        # gpcw 无覆盖 → 空帧
        monkeypatch.setattr(
            pipeline, "load_all_periods_frame", lambda *a, **k: pd.DataFrame()
        )
        monkeypatch.setattr(pipeline, "detect_season_for_date", lambda *a, **k: None)
        monkeypatch.setattr(pipeline, "subsequent_performance", lambda *a, **k: {})

        def _fake_sina(code, market="SZ", num=40, use_cache=True):
            from easy_tdx.fundamental.sina_adapter import SinaFinancialRow

            return [
                SinaFinancialRow(
                    code=code, market=market,
                    report_date=date(2019, 9, 30), disclosure_date=date(2019, 10, 31),
                    indicators={
                        "eps": 24.24, "roe": 23.28, "revenue": 6.09e10,
                        "net_profit": 3.04e10, "gross_margin": 91.2, "net_margin": 49.9,
                        "debt_ratio": 20.5, "ocf": 4.4e10, "rev_yoy": 15.54, "np_yoy": 23.13,
                    },
                ),
            ]

        monkeypatch.setattr("easy_tdx.fundamental.sina_adapter.load_sina_rows", _fake_sina)

        # target 在披露日(2019-10-31)之后，三季报可用
        out = pipeline.scan_market(
            date(2019, 11, 15),
            top_n=5, with_performance=False, min_score=0,
            sina_pool=[{"market": "SH", "code": "600519"}],
        )
        results = out.get("results", [])
        assert results, "新浪补充应产出行"
        assert results[0]["code"] == "600519"
        assert results[0]["data_source"] == "sina"
        assert results[0]["report_date"] == "2019-09-30"

    def test_gpcw_rows_marked_gpcw(self, monkeypatch):
        from easy_tdx.fundamental import pipeline
        from easy_tdx.fundamental.indicators import indicator_values

        ind = indicator_values(
            {
                "基本每股收益": 1.5, "净资产收益率": 18.0,
                "其中：营业收入": 100.0, "其中：营业成本": 60.0,
                "归属于母公司所有者的净利润": 20.0,
                "资产总计": 200.0, "负债合计": 80.0,
                "经营活动产生的现金流量净额": 25.0,
                "营业收入增长率(%)": 12.0, "净利润增长率(%)": 15.0,
            }
        )
        frame = pd.DataFrame(
            [{
                "code": "600519", "market": "SH",
                "report_date": date(2026, 3, 31), "disclosure_date": date(2026, 4, 25),
                **ind,
            }]
        )
        monkeypatch.setattr(
            pipeline, "load_all_periods_frame", lambda *a, **k: frame
        )
        monkeypatch.setattr(pipeline, "detect_season_for_date", lambda *a, **k: None)
        monkeypatch.setattr(pipeline, "subsequent_performance", lambda *a, **k: {})

        out = pipeline.scan_market(date(2026, 5, 1), top_n=5, with_performance=False, min_score=0)
        results = out.get("results", [])
        assert results
        assert results[0]["data_source"] == "gpcw"
