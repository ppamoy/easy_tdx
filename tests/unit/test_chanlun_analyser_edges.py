"""ChanlunAnalyser 空态金标测试（V674）。

锁定空 K 线输入时的管道行为：不崩溃、返回空结构、levels 结构完整。
"""

from __future__ import annotations

import pandas as pd

from easy_tdx.chanlun import ChanlunAnalyser


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": pd.to_datetime([]),
            "open": pd.Series([], dtype=float),
            "close": pd.Series([], dtype=float),
            "high": pd.Series([], dtype=float),
            "low": pd.Series([], dtype=float),
            "vol": pd.Series([], dtype=float),
        }
    )


def test_process_empty_klines_returns_empty_result() -> None:
    analyser = ChanlunAnalyser(code="000001", frequency="daily")
    result = analyser.process_klines(_empty_df())
    d = result.to_dict()

    assert d["kline_count"] == 0
    assert d["bi_count"] == 0
    assert d["xd_count"] == 0
    assert d["zsd_count"] == 0
    assert d["qsd_count"] == 0
    assert d["levels"]["bi"]["bi_count"] == 0
    assert d["levels"]["xd"]["bi_count"] == 0


def test_process_empty_klines_keeps_code_frequency() -> None:
    analyser = ChanlunAnalyser(code="600519", frequency="30min")
    d = analyser.process_klines(_empty_df()).to_dict()
    assert d["code"] == "600519"
    assert d["frequency"] == "30min"
