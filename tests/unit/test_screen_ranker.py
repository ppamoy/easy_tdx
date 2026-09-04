"""screen/ranker.py 回测排名引擎边界测试（V398）。

ranker.py 此前覆盖率 40%：RankEntry/to_json/to_table/load_signals/_json_default
与 rank 排序/截断/进度回调从未被直接测试。本文件补纯函数与 mock 回测路径。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from easy_tdx.screen.ranker import (
    RankEntry,
    SignalRanker,
    _json_default,
    load_signals,
)


def _entry(code: str, sharpe: float) -> RankEntry:
    return RankEntry(
        rank=0,
        code=code,
        market="SZ",
        name="",
        signal_date=20240101,
        last_close=10.0,
        performance={
            "sharpe": sharpe,
            "total_return": 0.1,
            "annual_return": 0.2,
            "max_drawdown": 0.05,
            "win_rate": 0.5,
            "total_trades": 10,
        },
    )


class TestPureFunctions:
    def test_rank_entry_defaults(self) -> None:
        e = RankEntry(
            rank=0,
            code="000001",
            market="SZ",
            name="",
            signal_date=0,
            last_close=0.0,
            performance={},
        )
        assert e.accuracy is None and e.trust is None and e.oos is None

    def test_to_json(self) -> None:
        e = _entry("000001", 1.5)
        e.rank = 1
        text = SignalRanker.to_json([e], "rsi", "sharpe")
        data = json.loads(text)
        assert data["strategy"] == "rsi"
        assert data["total_ranked"] == 1
        assert data["ranking"][0]["code"] == "000001"

    def test_to_table_empty(self) -> None:
        assert SignalRanker.to_table([], "sharpe") == "无有效排名结果"

    def test_to_table_rows(self) -> None:
        e = _entry("000001", 1.5)
        e.rank = 1
        text = SignalRanker.to_table([e], "sharpe")
        assert "信号排名" in text
        assert "SZ000001" in text

    def test_to_table_with_accuracy_and_trust(self) -> None:
        e = _entry("000001", 1.5)
        e.rank = 1
        e.accuracy = {"hit_rate": 0.7, "excess_hit_rate": 0.1}
        e.trust = {"score": 80, "grade": "A", "verdict": "ok"}
        text = SignalRanker.to_table([e], "sharpe")
        assert "5根命中" in text

    def test_json_default(self) -> None:
        import numpy as np

        assert _json_default(np.float64(1.5)) == 1.5
        with pytest.raises(TypeError):
            _json_default(1.5)


class TestLoadSignals:
    def test_load_from_file(self, tmp_path) -> None:
        f = tmp_path / "sig.json"
        f.write_text(
            json.dumps(
                {"signals": [{"code": "000001"}], "strategy": "rsi", "strategy_file": "a.py"}
            ),
            encoding="utf-8",
        )
        signals, name, sfile = load_signals(str(f))
        assert signals == [{"code": "000001"}]
        assert name == "rsi"
        assert sfile == "a.py"

    def test_load_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_signals("/nonexistent/x.json")


class TestRank:
    def _rank(self, signals, sort_by="sharpe", top_n=0, run_oos=False):
        r = SignalRanker(strategy_cls=MagicMock, vipdoc_path="/tmp")
        # 直接替换 _backtest_result 避免真实回测
        r._backtest_result = MagicMock(
            return_value=(MagicMock(performance={"sharpe": 1.0}), MagicMock())
        )  # type: ignore[method-assign]
        return r.rank(signals, sort_by=sort_by, top_n=top_n, run_oos=run_oos)

    def test_rank_sort_and_top_n(self) -> None:
        signals = [
            {"code": "000001", "market": "SZ", "signal_date": 1},
            {"code": "000002", "market": "SZ", "signal_date": 2},
        ]
        sharpes = {"000001": 1.0, "000002": 2.0}

        def fake_result(market: str, code: str) -> tuple[MagicMock, MagicMock]:
            return MagicMock(performance={"sharpe": sharpes[code]}), MagicMock()

        with patch.object(SignalRanker, "_backtest_result", side_effect=fake_result):
            r = SignalRanker(strategy_cls=MagicMock, vipdoc_path="/tmp")
            entries = r.rank(signals, sort_by="sharpe", top_n=1)
        assert len(entries) == 1
        assert entries[0].rank == 1
        assert entries[0].code == "000002"  # sharpe 2.0 在前

    def test_rank_skips_none_result(self) -> None:
        r = SignalRanker(strategy_cls=MagicMock, vipdoc_path="/tmp")
        r._backtest_result = MagicMock(return_value=None)  # type: ignore[method-assign]
        entries = r.rank([{"code": "000001", "market": "SZ"}])
        assert entries == []
