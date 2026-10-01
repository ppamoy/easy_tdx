"""fundamental 路由成功/降级分支契约测试（V-36 补齐，openspec 2.4 延伸）。

既有 test_web_routers_contract.py 只覆盖参数校验错误分支（400）。
本文件用 patch 把 pipeline/indicators 层 mock 掉（不碰真实财报缓存与网络），
验证 5 个端点的成功路径与 503/空数据降级路径的真实行为：
- indicator: 200（rows 结构/valuation 注入）、503（无财报文件）、空 rows
- season: 200（SeasonResult.as_dict 形态）、503（指数不可用）
- verify: 200（run_verify 透传）
- scan: 200（cache 字段补齐）、markets 过滤 400
- cache: 200（stats 透传）
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from easy_tdx.fundamental.season import SeasonResult  # noqa: E402


def _make_app_client() -> TestClient:
    from easy_tdx.web.app import _create_app

    app = _create_app(enable_mac=True, enable_ex=True)
    app.state.tdx_client = None
    app.state.mac_client = None
    app.state.ex_client = None
    return TestClient(app)


# ── indicator：成功 + 降级 ────────────────────────────────────────────────


class TestIndicatorSuccessAndFallback:
    def test_indicator_returns_rows_and_valuation(self) -> None:
        """price 提供时注入 valuation，rows 字段对齐 _INDICATOR_COLS。"""
        from easy_tdx.web.routers.fundamental import _INDICATOR_COLS

        row = {
            "report_date": date(2024, 3, 31),
            "eps": 1.5,
            "bps": 12.0,
            "data_source": "gpcw",
        }
        with (
            patch("easy_tdx.fundamental.pipeline.pick_report_zips", return_value=["a.zip"]),
            patch("easy_tdx.fundamental.indicators.load_all_periods_frame") as m_frame,
            patch("easy_tdx.fundamental.indicators.pick_report", return_value=row),
            patch(
                "easy_tdx.fundamental.pipeline._valuation",
                return_value={"pe": 10.0, "pb": 1.25},
            ),
        ):
            m_frame.return_value = pd_like_frame()  # empty=False：走过空判断后由 pick_report 出行
            resp = _make_app_client().get(
                "/api/v1/fundamental/indicator/SZ/000001",
                params={"as_of": "2024-06-01", "price": 15.0},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["rows"][0]["valuation"] == {"pe": 10.0, "pb": 1.25}
        assert body["rows"][0]["data_source"] == "gpcw"
        for col in _INDICATOR_COLS:
            assert col in body["rows"][0]

    def test_indicator_no_zips_is_503(self) -> None:
        """pick_report_zips 与本地缓存都为空 → 503（坏版本会 500/裸异常）。"""
        with (
            patch("easy_tdx.fundamental.pipeline.pick_report_zips", return_value=[]),
            patch("easy_tdx.fundamental.cache.cache_stats", return_value={"zips": []}),
        ):
            resp = _make_app_client().get(
                "/api/v1/fundamental/indicator/SZ/000001", params={"as_of": "2024-06-01"}
            )
        assert resp.status_code == 503
        assert "gpcw" in resp.json()["detail"]

    def test_indicator_empty_frame_returns_empty_rows(self) -> None:
        with (
            patch("easy_tdx.fundamental.pipeline.pick_report_zips", return_value=["a.zip"]),
            patch("easy_tdx.fundamental.indicators.load_all_periods_frame") as m_frame,
        ):
            m_frame.return_value = pd_like_frame(None, empty=True)
            resp = _make_app_client().get(
                "/api/v1/fundamental/indicator/SZ/000001", params={"as_of": "2024-06-01"}
            )
        assert resp.status_code == 200
        assert resp.json()["rows"] == []
        assert "error" in resp.json()

    def test_indicator_no_disclosed_report_warning(self) -> None:
        """pick_report 返回 None → warning 而非异常。"""
        with (
            patch("easy_tdx.fundamental.pipeline.pick_report_zips", return_value=["a.zip"]),
            patch("easy_tdx.fundamental.indicators.load_all_periods_frame") as m_frame,
            patch("easy_tdx.fundamental.indicators.pick_report", return_value=None),
        ):
            m_frame.return_value = pd_like_frame({"eps": 1.0})
            resp = _make_app_client().get(
                "/api/v1/fundamental/indicator/SZ/000001", params={"as_of": "2024-06-01"}
            )
        assert resp.status_code == 200
        assert resp.json()["rows"] == []
        assert "warning" in resp.json()


# ── season：成功 + 降级 ──────────────────────────────────────────────────


class TestSeasonBranches:
    def test_season_returns_as_dict_shape(self) -> None:
        sr = SeasonResult(season="spring", signals={"k": "v"})
        with patch("easy_tdx.fundamental.pipeline.detect_season_for_date", return_value=sr):
            resp = _make_app_client().post(
                "/api/v1/fundamental/season", json={"date": "2024-04-01"}
            )
        assert resp.status_code == 200
        body = resp.json()
        for key in ("season", "label", "color", "position_range", "action", "signals"):
            assert key in body

    def test_season_no_index_data_is_503(self) -> None:
        """detect_season_for_date 返回 None（指数不可用）→ 503。"""
        with patch("easy_tdx.fundamental.pipeline.detect_season_for_date", return_value=None):
            resp = _make_app_client().post(
                "/api/v1/fundamental/season", json={"date": "2024-04-01"}
            )
        assert resp.status_code == 503
        assert "上证" in resp.json()["detail"]


# ── verify / scan / cache ────────────────────────────────────────────────


class TestVerifyScanCachePassthrough:
    def test_verify_rejects_non_dict_pool_entries(self) -> None:
        """pool 混入非 dict 项（如裸字符串）→ 400，不会透传给 pipeline。"""
        with patch("easy_tdx.fundamental.pipeline.run_verify") as m:
            resp = _make_app_client().post(
                "/api/v1/fundamental/verify",
                json={
                    "dates": ["2024-04-01"],
                    "pool": [{"market": "sh", "code": "1"}, "junk-without-code"],
                },
            )
        assert resp.status_code == 400
        m.assert_not_called()

    def test_verify_passes_normalized_pool(self) -> None:
        with patch("easy_tdx.fundamental.pipeline.run_verify", return_value={"hit": 1}) as m:
            resp = _make_app_client().post(
                "/api/v1/fundamental/verify",
                json={
                    "dates": ["2024-04-01"],
                    "pool": [{"market": "sh", "code": "1"}],
                },
            )
        assert resp.status_code == 200
        assert resp.json() == {"hit": 1}
        called_pool = m.call_args.args[1]
        assert called_pool == [{"market": "SH", "code": "000001"}]  # 大写 + zfill(6)

    def test_verify_bad_date_is_400_with_detail(self) -> None:
        resp = _make_app_client().post(
            "/api/v1/fundamental/verify",
            json={"dates": ["2024-04-01", "bad-date"], "pool": [{"code": "1"}]},
        )
        assert resp.status_code == 400
        assert "bad-date" in resp.json()["detail"]

    def test_scan_invalid_markets_is_400(self) -> None:
        resp = _make_app_client().post(
            "/api/v1/fundamental/scan", json={"date": "2024-04-01", "markets": ["BJ", "XX"]}
        )
        assert resp.status_code == 400
        assert "SH" in resp.json()["detail"]

    def test_scan_success_adds_cache_block(self) -> None:
        with (
            patch("easy_tdx.fundamental.pipeline.scan_market", return_value={"results": []}),
            patch(
                "easy_tdx.fundamental.cache_stats",
                return_value={
                    "zips_count": 1,
                    "total_rows": 9,
                    "db_bytes": 100,
                    "zips": [{"filename": "gpcw.zip"}],
                },
            ),
            patch("easy_tdx.fundamental.sina_cache_stats", return_value={"codes_count": 0}),
        ):
            resp = _make_app_client().post("/api/v1/fundamental/scan", json={"date": "2024-04-01"})
        assert resp.status_code == 200
        assert resp.json()["cache"]["zips"] == ["gpcw.zip"]

    def test_cache_endpoint_passthrough(self) -> None:
        with (
            patch("easy_tdx.fundamental.cache_stats", return_value={"zips_count": 2}),
            patch("easy_tdx.fundamental.sina_cache_stats", return_value={"codes_count": 3}),
        ):
            resp = _make_app_client().get("/api/v1/fundamental/cache")
        assert resp.status_code == 200
        body = resp.json()
        assert body["zips_count"] == 2
        assert body["sina"]["codes_count"] == 3


# ── 测试辅助 ─────────────────────────────────────────────────────────────


def pd_like_frame(row: dict | None = None, empty: bool = False):
    """构造端点实际用到的最小 DataFrame 形态替身。

    端点对 frame 只有两类用法：
    - ``frame.empty``（空 → 返回 error 分支）；
    - 交给 pick_report（本文件已 patch，不接触 frame 本身）。
    用 SimpleNamespace 提供 ``empty`` 属性即可，不需要引入 pandas 细节。
    """
    from types import SimpleNamespace

    return SimpleNamespace(empty=bool(empty))
