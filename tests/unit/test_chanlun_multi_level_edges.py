"""多级别联立分析边界金标测试（V663）。

锁定 MultiLevelAnalyser 的空态、缺失级别、跨级别查询等边界，
防止多级别联立分析在数据不足/未注册级别时崩溃或返回错误结果。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.multi_level import MultiLevelAnalyser

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def _daily_df() -> pd.DataFrame:
    rows = json.loads((FIXTURE_DIR / "chanlun_000001_daily.json").read_text(encoding="utf-8"))
    return pd.DataFrame(rows)


def test_process_missing_level_raises_keyerror() -> None:
    mla = MultiLevelAnalyser()
    with pytest.raises(KeyError):
        mla.process("unknown", _daily_df())


def test_results_empty_by_default() -> None:
    assert MultiLevelAnalyser().results() == {}


def test_compute_confluence_empty_state() -> None:
    empty = MultiLevelAnalyser().compute_confluence_score("high", "low")
    assert empty["score"] == 0.0
    assert empty["high_level_signal"] is None
    assert empty["low_level_signal"] is None


def test_query_low_level_qs_empty_state() -> None:
    mla = MultiLevelAnalyser()
    high_analyser = ChanlunAnalyser(code="000001", frequency="daily")
    high_result = high_analyser.process_klines(_daily_df())
    assert high_result.bis

    empty = mla.query_low_level_qs("high", "low", high_result.bis[-1])
    assert empty["bi_count"] == 0
    assert empty["zs_count"] == 0
    assert empty["has_trend"] is False


def test_query_low_level_qs_with_registered_levels() -> None:
    """高级别最后一笔在低级别中的走势查询返回非空统计。"""
    high_analyser = ChanlunAnalyser(code="000001", frequency="daily")
    low_analyser = ChanlunAnalyser(code="000001", frequency="daily")
    high_result = high_analyser.process_klines(_daily_df())
    low_analyser.process_klines(_daily_df())

    mla = MultiLevelAnalyser()
    mla.add_level("high", high_analyser)
    mla.add_level("low", low_analyser)

    qs = mla.query_low_level_qs("high", "low", high_result.bis[-1])
    assert "bi_count" in qs
    assert qs["bi_count"] >= 0
    assert qs["zs_count"] >= 0
    # 用同一日线数据查询，低级别窗口内至少能命中若干笔/中枢
    assert qs["bi_count"] > 0
