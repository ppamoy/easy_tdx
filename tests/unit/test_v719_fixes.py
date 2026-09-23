"""V719 飞轮第 1 轮修复的回归测试。

覆盖：
- F1  /api/* 未知路径必须 JSON 404（不再被 SPA 兜底成 200 + HTML），
      同时前端路由仍返回 index.html；
- F2  自选池路径选股会上报进度（report_progress 被调用）；
- F4  参数/状态错误用 4xx：monitor/create 空 stocks→400、monitor check 未知任务→404、
      screening/evaluate 缺参/坏日期→400；
- F5  top_n 非法值给出可读 400（不泄漏 int() 内部报错）。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from easy_tdx.web import create_app


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── F1: /api/* 未知路径 = JSON 404 ──────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/does-not-exist",
        "/api/v1/monitor/nope/nope",
        "/api/v1/stock-pick/nope",
        "/api/v1/bars/nope",
    ],
)
def test_unknown_api_path_is_json_404(client: TestClient, path: str) -> None:
    """V719-F1：未注册的 /api/* 必须返回 JSON 404，而不是 SPA 的 200 + HTML。"""
    resp = client.get(path)
    assert resp.status_code == 404, f"{path} → {resp.status_code}（应为 404）"
    ctype = resp.headers.get("content-type", "")
    assert "application/json" in ctype, f"{path} content-type={ctype}（应为 JSON）"
    assert not resp.text.lstrip().startswith("<"), f"{path} 返回了 HTML"


def test_spa_route_still_served(client: TestClient) -> None:
    """V719-F1：非 /api 的前端路由仍由 SPA 兜底（HTML），不能被误伤。"""
    resp = client.get("/optimize")
    # dist 不存在时（纯 API 模式）允许 404；存在时必须是 HTML 首页
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        assert resp.text.lstrip().startswith("<")


# ── F2: 池路径上报进度 ──────────────────────────────────────────────────────


def test_pool_screen_reports_progress() -> None:
    """V719-F2：自选池路径选股同样上报进度（此前 progress 恒 null）。"""
    from easy_tdx.web.routers import stock_pick as sp

    calls: list[tuple[float | None, str]] = []

    def _spy(pct=None, note=""):
        calls.append((pct, note))

    with (
        patch.object(sp, "report_progress", _spy),
        patch("easy_tdx.fundamental.pipeline.run_screen") as mock_run,
    ):
        mock_run.return_value = {"results": []}
        out = sp._screen_run_sync(
            __import__("datetime").date(2026, 9, 1),
            ["SH"],
            [{"market": "SH", "code": "600519"}],
            pool_scope="pool",
            top_n=5,
        )
    assert out["total"] == 0
    assert calls, "池路径未上报任何进度"
    pcts = [c[0] for c in calls if c[0] is not None]
    assert pcts == sorted(pcts), f"进度应单调不降: {pcts}"
    assert pcts[-1] == 100.0, f"最后一次进度应为 100: {pcts}"


# ── F4: 4xx 语义 ───────────────────────────────────────────────────────────


def test_monitor_create_empty_stocks_is_400(client: TestClient) -> None:
    """V719-F4：monitor/create 空 stocks → 400（此前 200 + error 会让前端拿到 undefined id）。"""
    resp = client.post("/api/v1/monitor/create", json={"stocks": [], "category": "DAY"})
    assert resp.status_code == 400
    assert "detail" in resp.json()


def test_monitor_check_unknown_task_is_404(client: TestClient) -> None:
    """V719-F4：monitor/{id}/check 未知任务 → 404（此前 200 + error）。"""
    resp = client.post("/api/v1/monitor/does-not-exist/check")
    assert resp.status_code == 404
    assert "detail" in resp.json()


@pytest.mark.parametrize(
    "payload",
    [{"market": "SZ"}, {"market": "SZ", "code": "000001", "date": "bad"}],
)
def test_screening_evaluate_param_errors_are_400(client: TestClient, payload: dict) -> None:
    """V719-F4：screening/evaluate 缺参或坏日期 → 400。"""
    resp = client.post("/api/v1/screening/evaluate", json=payload)
    assert resp.status_code == 400
    assert "detail" in resp.json()


# ── F5: 参数解析可读报错 ────────────────────────────────────────────────────


def test_screen_top_n_invalid_is_clean_400(client: TestClient) -> None:
    """V719-F5：top_n='abc' → 400 且 detail 可读（不泄漏 int() 内部报错）。"""
    resp = client.post(
        "/api/v1/stock-pick/screen",
        json={"date": "2026-09-01", "markets": ["SH"], "top_n": "abc"},
    )
    assert resp.status_code == 400
    detail = resp.json().get("detail", "")
    assert "top_n" in detail, f"detail={detail}"
    assert "invalid literal" not in detail, f"泄漏内部报错: {detail}"


def test_int_arg_bounds() -> None:
    """V719-F5：_int_arg 的边界/非法处理。"""
    from easy_tdx.web.routers.stock_pick import _int_arg

    assert _int_arg(None, "x", 7, 1, 10) == 7
    assert _int_arg("", "x", 7, 1, 10) == 7
    assert _int_arg("3", "x", 7, 1, 10) == 3
    assert _int_arg(0, "x", 7, 1, 10) == 1  # 下限夹取
    assert _int_arg(999, "x", 7, 1, 10) == 10  # 上限夹取
    with pytest.raises(Exception):
        _int_arg("abc", "top_n", 7, 1, 10)
