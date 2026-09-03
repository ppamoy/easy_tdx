"""screen/strength.py 强势股排名引擎边界测试（V394）。

strength.py 此前覆盖率 44%。本文件补 compute_strength_metrics 纯函数的
数值/边界/波动率调整分支、StrengthRanker 初始化校验、to_json/to_table 序列化、
_fmt_date 与 _json_default 辅助函数。全程离线。
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from easy_tdx.screen.strength import (
    STRENGTH_PRESETS,
    StrengthRanker,
    StrengthResult,
    _compute_strength_one,
    _fmt_date,
    _json_default,
    compute_strength_metrics,
)


def _make_closes(n: int = 90, start: float = 10.0, drift: float = 0.01) -> pd.Series:
    """构造带趋势+波动的收盘价序列。"""
    rng = np.random.default_rng(7)
    rets = drift + rng.normal(0, 0.02, n)
    return pd.Series(start * np.cumprod(1 + rets))


class TestComputeStrengthMetrics:
    def test_insufficient_data(self) -> None:
        assert compute_strength_metrics(_make_closes(64), 0.2, 0.3, 0.5, True) is None

    def test_zero_weights(self) -> None:
        assert compute_strength_metrics(_make_closes(), 0.0, 0.0, 0.0, True) is None

    def test_steady_vol_adjusted(self) -> None:
        metrics = compute_strength_metrics(_make_closes(), 0.2, 0.3, 0.5, True)
        assert metrics is not None
        for key in ("ret_5", "ret_20", "ret_60", "vol_20", "strength"):
            assert key in metrics
        assert metrics["vol_20"] > 0
        # 波动率调整后 strength = raw / vol_20
        raw = 0.2 * metrics["ret_5"] + 0.3 * metrics["ret_20"] + 0.5 * metrics["ret_60"]
        assert metrics["strength"] == pytest.approx(raw / metrics["vol_20"])

    def test_breakout_no_vol_adjust(self) -> None:
        metrics = compute_strength_metrics(_make_closes(), 0.6, 0.3, 0.1, False)
        assert metrics is not None
        raw = 0.6 * metrics["ret_5"] + 0.3 * metrics["ret_20"] + 0.1 * metrics["ret_60"]
        assert metrics["strength"] == pytest.approx(raw)

    def test_weights_normalized(self) -> None:
        """权重自动归一化：w_sum != 1 时等价于归一化后加权。"""
        m1 = compute_strength_metrics(_make_closes(), 2.0, 3.0, 5.0, False)
        m2 = compute_strength_metrics(_make_closes(), 0.2, 0.3, 0.5, False)
        assert m1 is not None and m2 is not None
        assert m1["strength"] == pytest.approx(m2["strength"])


class TestStrengthRanker:
    def test_unknown_preset_raises(self) -> None:
        with pytest.raises(ValueError, match="未知预设"):
            StrengthRanker(preset="nope")

    def test_presets_structure(self) -> None:
        assert set(STRENGTH_PRESETS) == {"steady", "breakout", "balanced"}
        for cfg in STRENGTH_PRESETS.values():
            assert "w5" in cfg and "w20" in cfg and "w60" in cfg
            assert "vol_adjusted" in cfg

    def test_custom_weights_override_preset(self, tmp_path) -> None:
        r = StrengthRanker(
            vipdoc_path=str(tmp_path),
            preset="steady",
            w5=0.7,
            w20=0.2,
            w60=0.1,
            vol_adjusted=False,
        )
        assert r._w5 == 0.7
        assert r._w60 == 0.1
        assert r._vol_adjusted is False
        assert r.preset == "steady"

    def test_rank_empty_universe(self, tmp_path) -> None:
        r = StrengthRanker(vipdoc_path=str(tmp_path))
        assert r.rank(universe="all") == []

    def test_to_json(self) -> None:
        res = StrengthResult(code="000001", market="SZ", last_close=10.5, strength=2.3)
        res.rank = 1
        text = StrengthRanker.to_json([res], "steady", 20240101)
        data = json.loads(text)
        assert data["preset"] == "steady"
        assert data["total_ranked"] == 1
        assert data["ranking"][0]["code"] == "000001"

    def test_to_table_empty(self) -> None:
        assert StrengthRanker.to_table([], "steady", 20240101) == "无有效排名结果"

    def test_to_table_rows(self) -> None:
        res = StrengthResult(code="600519", market="SH", last_close=1500.0, strength=1.5)
        res.rank = 1
        text = StrengthRanker.to_table([res], "steady", 20240101)
        assert "强势股排名" in text
        assert "SH600519" in text


class TestHelpers:
    def test_fmt_date(self) -> None:
        assert _fmt_date(20240101) == "2024-01-01"
        assert _fmt_date(123) == "123"

    def test_json_default(self) -> None:
        assert _json_default(np.float64(1.5)) == 1.5
        with pytest.raises(TypeError):
            _json_default(object())


class TestComputeStrengthOne:
    def test_insufficient_bars(self, tmp_path) -> None:
        # 空文件 → read_daily_bars 返回空 → None
        day = tmp_path / "x.day"
        day.write_bytes(b"")
        assert _compute_strength_one(str(day), "SZ", "000001", 0.2, 0.3, 0.5, True, 65, 0.0) is None
