"""P0 缠论学习训练会话：build_train_session_payload 纯函数测试。

用合成 K 线数据跑完整缠论管道，验证训练会话负载结构：
- bars / 结构字段齐全
- candidates 覆盖买卖点信号 + 分型干扰项，坐标合法
- mmd_outcomes 事后 N 日收益计算正确
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.web.routers.chanlun import build_train_session_payload


def _synthetic_df(n: int = 300, seed: int = 7) -> pd.DataFrame:
    import math
    import random

    rng = random.Random(seed)
    base = 10.0
    rows: list[dict] = []
    dt = datetime(2024, 1, 2)
    for i in range(n):
        wave = math.sin(i / 22.0) * 1.2 + math.sin(i / 7.0) * 0.25
        drift = 0.01 * math.sin(i / 90.0)
        open_ = base + wave
        close = open_ + drift + rng.uniform(-0.15, 0.15)
        high = max(open_, close) + rng.uniform(0.02, 0.25)
        low = min(open_, close) - rng.uniform(0.02, 0.25)
        rows.append(
            {
                "date": dt,  # datetime 对象（与 TDX 返回一致）
                "open": round(open_, 3),
                "close": round(close, 3),
                "high": round(high, 3),
                "low": round(low, 3),
                "vol": float(rng.randint(50_000, 200_000)),
                "amount": float(rng.randint(500_000, 2_000_000)),
            }
        )
        dt += timedelta(days=1)
    return pd.DataFrame(rows)


def _run_session(n: int = 300) -> dict:
    df = _synthetic_df(n=n)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)
    return build_train_session_payload(result, df, "DAY")


def test_session_payload_structure() -> None:
    d = _run_session()
    for k in ["bars", "bis", "xds", "zss", "mmds", "fractals", "bcs", "candidates", "mmd_outcomes"]:
        assert k in d, "缺少字段 " + k
    assert len(d["bars"]) > 100
    assert d["category"] == "DAY"
    first = d["bars"][0]
    for k in ["datetime", "open", "close", "high", "low"]:
        assert k in first
    assert "T" in first["datetime"]


def test_session_candidates_cover_signals_and_distractors() -> None:
    d = _run_session()
    cands = d["candidates"]
    assert len(cands) > 0
    assert len(cands) <= 40
    idxs = [c["index"] for c in cands]
    assert idxs == sorted(idxs)
    assert all(0 <= i < len(d["bars"]) for i in idxs)
    signal_cands = [c for c in cands if c["kind"] == "mmd" and c["signal"]]
    assert len(signal_cands) >= 1, "合成数据应产出买卖点信号候选"
    for c in signal_cands:
        assert c["signal"]["type"] in {
            "1buy",
            "2buy",
            "3buy",
            "1sell",
            "2sell",
            "3sell",
            "2buy_s",
            "2sell_s",
        }
        assert 0 <= c["signal"]["confidence"] <= 1.0
    fx_cands = [c for c in cands if c["kind"] == "fractal"]
    assert len(fx_cands) >= 1
    for c in fx_cands:
        assert c["signal"] is None
        assert c["fx_type"] in {"ding", "di"}


def test_session_mmd_outcomes() -> None:
    d = _run_session()
    outcomes = d["mmd_outcomes"]
    assert len(outcomes) >= 1
    for o in outcomes:
        assert o["type"] in {"1buy", "2buy", "3buy", "1sell", "2sell", "3sell", "2buy_s", "2sell_s"}
        assert o["date"]
        for k in ["ret_5d", "ret_10d", "ret_20d"]:
            assert o[k] is None or -50 <= o[k] <= 200
        if o["max_5d"] is not None and o["min_5d"] is not None:
            assert o["max_5d"] >= o["min_5d"]


def test_session_many_mmds_no_zero_division() -> None:
    """回归（§7）：mmd_cands ≥ target_total(40) 时 distract_max=0，
    旧代码 `len(fx_cands) / 0` 抛 ZeroDivisionError，整条 /train/session 返回 500、
    P0 逐步揭示+复盘讲解全断。真数据 600000 日线 3000 根产生 75 个买卖点即触发。

    用真实 audit_data（若有）跑完整管道；无数据则 skip（CI 无缓存时不阻断）。
    """
    import json
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[2] / "audit_data" / "sh600000_daily.json"
    if not fixture.exists():
        import pytest

        pytest.skip("audit_data/sh600000_daily.json 不存在（需本地缓存）")
    df = pd.DataFrame(json.loads(fixture.read_text()))
    if len(df) < 200:
        pytest.skip("audit_data 样本过短")
    result = ChanlunAnalyser(code="SH600000", frequency="daily").process_klines(df)
    # 确认本 fixture 确实命中 bug 路径（mmd_cands ≥ 40 → distract_max=0）
    assert len(result.mmds) >= 40, f"fixture 应产生 ≥40 mmd，实得 {len(result.mmds)}"
    # 旧代码在此抛 ZeroDivisionError；修复后应正常返回
    p = build_train_session_payload(result, df, "DAY", "medium", 0, reveal_limit=0)
    assert "candidates" in p and len(p["candidates"]) >= 40
    # review 模式（reveal_limit=None）同样不应崩
    p2 = build_train_session_payload(result, df, "DAY", "medium", 0, reveal_limit=None)
    assert len(p2["mmd_outcomes"]) == len(result.mmds)
