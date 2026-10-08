"""真实 HTTP 路由 e2e：POST /api/v1/chanlun/train/session 的防作弊闸门。

不 mock build_train_session_payload，而是走真实 FastAPI 路由 + 真实
ChanlunAnalyser，只把 TDX 取数客户端换成 fixture（无网络依赖）。
目的：验证「路由层 mode=train/review 的 reveal_limit 语义」与
「payload 里真实下发的值」都符合闸门要求 —— 单测只覆盖到 builder 函数，
路由层的 mode→_gate 映射（train+None→0）此前无人验证。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
from fastapi.testclient import TestClient

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "chanlun_000333_daily.json"

ANCHOR_FIELDS = ("end_index", "bar_index", "anchor_bar_index")


def _fixture_df() -> pd.DataFrame:
    rows = json.loads(FIX.read_text(encoding="utf-8"))
    return pd.DataFrame(rows)


def _client() -> TestClient:
    from easy_tdx.web.app import _create_app

    app = _create_app(enable_mac=True)
    app.state.tdx_client = AsyncMock()
    app.state.mac_client = AsyncMock()
    return TestClient(app)


def _post(client: TestClient, **qs) -> dict:
    body = {"market": "SZ", "code": "000333", "category": "DAY", "count": 400, "start": 0}
    return client.post("/api/v1/chanlun/train/session", params=qs, json=body).json()


def _over(p: dict, n: int) -> list[tuple[str, dict]]:
    """返回 [(key, 越界样例)] —— 顶层结构数组 + levels 子结构全扫。"""
    bad: list[tuple[str, dict]] = []
    for key, val in p.items():
        if key in ("code", "frequency", "category", "candidates", "mmd_outcomes"):
            continue
        if key == "levels" and isinstance(val, dict):
            for lname, lv in val.items():
                if not isinstance(lv, dict):
                    continue
                for k, arr in lv.items():
                    if not isinstance(arr, list):
                        continue
                    fields = ("start_index",) if k == "zss" else ANCHOR_FIELDS
                    for it in arr:
                        ix = next(
                            (int(it[f]) for f in fields if isinstance(it.get(f), (int, float))),
                            0,
                        )
                        if ix > n:
                            bad.append((f"levels.{lname}.{k}", it))
            continue
        if not isinstance(val, list):
            continue
        fields = ("start_index",) if key == "zss" else ANCHOR_FIELDS
        for it in val:
            if not isinstance(it, dict):
                continue
            ix = next((int(it[f]) for f in fields if isinstance(it.get(f), (int, float))), 0)
            if ix > n:
                bad.append((key, it))
    return bad


def main() -> None:
    df = _fixture_df()
    client = _client()
    with patch(
        "easy_tdx.web.routers.chanlun._fetch_request_klines", new=AsyncMock(return_value=df)
    ):
        print("=== mode=train, reveal_limit 缺省（路由应折算为 0）===")
        r0 = _post(client, mode="train")
        print("  bars:", len(r0["bars"]), "| mmds:", len(r0["mmds"]),
              "| bcs:", len(r0["bcs"]), "| zsds:", len(r0["zsds"]),
              "| qsds:", len(r0["qsds"]), "| mmd_outcomes:", len(r0["mmd_outcomes"]))
        bad = _over(r0, 0)
        print("  越界条目:", len(bad), bad[:2])
        assert not bad, f"HTTP 路由开局泄露: {bad}"
        assert len(r0["bars"]) == 1, f"bars 应为 1，实得 {len(r0['bars'])}"

        print("=== mode=train, reveal_limit=50 ===")
        r50 = _post(client, mode="train", reveal_limit=50)
        print("  bars:", len(r50["bars"]), "| mmds:", len(r50["mmds"]),
              "| bis:", len(r50["bis"]), "| mmd_outcomes:", len(r50["mmd_outcomes"]))
        bad = _over(r50, 50)
        print("  越界条目:", len(bad), bad[:2])
        assert not bad, f"HTTP 路由 N=50 泄露: {bad}"
        assert len(r50["bars"]) == 51

        print("=== mode=review（复盘，必须全量）===")
        rr = _post(client, mode="review")
        print("  bars:", len(rr["bars"]), "| mmds:", len(rr["mmds"]),
              "| bis:", len(rr["bis"]), "| mmd_outcomes:", len(rr["mmd_outcomes"]))
        assert len(rr["bars"]) == len(df), f"复盘 bars 应全量 {len(df)}，实得 {len(rr['bars'])}"
        assert rr["mmd_outcomes"], "复盘模式必须有 mmd_outcomes（F2 复盘讲解依赖）"
        assert len(rr["mmds"]) == 3, f"复盘 mmds 应 3 个，实得 {len(rr['mmds'])}"

        print("=== mode=train, reveal_limit=159（全量揭示，阳性对照）===")
        rf = _post(client, mode="train", reveal_limit=len(df) - 1)
        print("  bars:", len(rf["bars"]), "| mmds:", len(rf["mmds"]), "| bis:", len(rf["bis"]))
        assert len(rf["bars"]) == len(df)
        assert len(rf["mmds"]) == len(rr["mmds"]), "全量揭示应与复盘模式结构一致"
        assert len(rf["bis"]) == len(rr["bis"])
    print("\n全部通过：HTTP 路由层闸门生效，复盘模式不受影响。")


if __name__ == "__main__":
    main()
