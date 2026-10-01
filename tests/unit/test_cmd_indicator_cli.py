"""技术指标 CLI（cmd_indicator.py）回归测试（V-41）。

该模块此前 0 测试（覆盖率 27.1%）。覆盖三层：
1. ``_parse_indicator_params``：通配符/指标前缀、int vs float 分型、
   空串/空段/多点位/科学计数/负数等边界（行为以实测为准）；
2. ``indicator`` 命令：CliRunner + mock get_mac_client（CM 链：
   ``cm.return_value.__enter__.return_value``）走全链路——JSON 输出含指标列、
   --no-ohlcv、未知指标报错、空数据报错、参数覆盖传参；
3. ``indicator-list`` 命令：JSON/Table 双格式。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from click.testing import CliRunner

from easy_tdx.cli.cmd_indicator import _parse_indicator_params, indicator, indicator_list

# ── _parse_indicator_params ──────────────────────────────────────────────


class TestParseIndicatorParams:
    def test_wildcard_params(self) -> None:
        assert _parse_indicator_params("SHORT=10,LONG=22") == {"*": {"SHORT": 10, "LONG": 22}}

    def test_indicator_prefixed_params(self) -> None:
        out = _parse_indicator_params("MACD.SHORT=10,KDJ.N=14")
        assert out == {"MACD": {"SHORT": 10}, "KDJ": {"N": 14}}

    def test_prefix_uppercased(self) -> None:
        assert _parse_indicator_params("macd.short=10") == {"MACD": {"short": 10}}

    def test_float_vs_int_split(self) -> None:
        out = _parse_indicator_params("P=1.5,N=10")
        assert out["*"]["P"] == 1.5 and isinstance(out["*"]["P"], float)
        assert out["*"]["N"] == 10 and isinstance(out["*"]["N"], int)

    def test_negative_number(self) -> None:
        assert _parse_indicator_params("SHORT=-5") == {"*": {"SHORT": -5}}

    def test_scientific_notation_is_float(self) -> None:
        out = _parse_indicator_params("P=1.5e3")
        assert out["*"]["P"] == 1500.0  # "e" 使 "." 分支命中 → float

    def test_empty_and_blank_segments_skipped(self) -> None:
        assert _parse_indicator_params(",,A=1,,") == {"*": {"A": 1}}
        assert _parse_indicator_params("") == {}
        assert _parse_indicator_params("   ") == {}

    def test_pairs_without_equals_skipped(self) -> None:
        assert _parse_indicator_params("junk,A=1") == {"*": {"A": 1}}

    def test_multi_dot_key_keeps_rest_as_param(self) -> None:
        """实测行为锁定：'MACD.SHORT.X' → indicator=MACD, param='SHORT.X'。"""
        assert _parse_indicator_params("MACD.SHORT.X=3") == {"MACD": {"SHORT.X": 3}}

    def test_whitespace_tolerant(self) -> None:
        assert _parse_indicator_params(" A = 2 , B =3 ") == {"*": {"A": 2, "B": 3}}

    def test_non_numeric_raises(self) -> None:
        """非数值参数值不静默吞——ValueError 由 CLI 层捕获为错误输出。"""
        with pytest.raises(ValueError):
            _parse_indicator_params("A=yes")


# ── indicator 命令（CliRunner 全链路） ───────────────────────────────────


def _kline_df(n: int = 250) -> pd.DataFrame:
    close = 100 + np.cumsum(np.random.default_rng(3).normal(0, 1, n))
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "vol": np.ones(n) * 1000,
            "amount": np.ones(n) * 1e5,
        }
    )


def _mock_mac_client(df: pd.DataFrame | None) -> MagicMock:
    """get_mac_client 是 @contextmanager；patch 点在其定义模块。"""
    cm = MagicMock()
    cm.return_value.__enter__.return_value.get_stock_kline.return_value = (
        df if df is not None else pd.DataFrame()
    )
    return cm


class TestIndicatorCommand:
    def test_json_output_contains_indicator_columns(self) -> None:
        cm = _mock_mac_client(_kline_df())
        with patch("easy_tdx.cli.conn.get_mac_client", cm):
            result = CliRunner().invoke(
                indicator, ["MACD", "-m", "SH", "-c", "600519", "--count", "5"]
            )
        assert result.exit_code == 0
        rows = json.loads(result.output)
        assert len(rows) == 5  # tail=count
        assert {"MACD_DIF", "MACD_DEA", "MACD_HIST"} <= set(rows[0])
        assert "close" in rows[0]  # 默认保留 OHLCV

    def test_no_ohlcv_drops_price_columns(self) -> None:
        cm = _mock_mac_client(_kline_df())
        with patch("easy_tdx.cli.conn.get_mac_client", cm):
            result = CliRunner().invoke(indicator, ["MACD", "-m", "SH", "-c", "1", "--no-ohlcv"])
        assert result.exit_code == 0
        row = json.loads(result.output)[0]
        assert "close" not in row and "open" not in row
        assert "MACD_DIF" in row

    def test_params_forwarded_to_compute(self) -> None:
        cm = _mock_mac_client(_kline_df())
        with (
            patch("easy_tdx.cli.conn.get_mac_client", cm),
            patch("easy_tdx.indicator.compute_indicators", wraps=None) as m_compute,
        ):
            m_compute.side_effect = lambda df, inds, params, **kw: df
            result = CliRunner().invoke(
                indicator,
                ["MACD,KDJ", "-m", "SH", "-c", "1", "--params", "SHORT=10,KDJ.N=14"],
            )
        assert result.exit_code == 0
        params = m_compute.call_args.args[2]
        # 语义（docstring「无前缀的参数应用到所有请求的指标」）：SHORT=10 是
        # 通配 → 并入 KDJ；KDJ.N=14 是专属 → 只进 KDJ。
        assert params["MACD"] == {"SHORT": 10}
        assert params["KDJ"] == {"SHORT": 10, "N": 14}

    def test_wildcard_applies_to_all(self) -> None:
        cm = _mock_mac_client(_kline_df())
        with (
            patch("easy_tdx.cli.conn.get_mac_client", cm),
            patch("easy_tdx.indicator.compute_indicators") as m_compute,
        ):
            m_compute.side_effect = lambda df, inds, params, **kw: df
            CliRunner().invoke(indicator, ["MACD,KDJ", "-m", "SH", "-c", "1", "--params", "N=9"])
        params = m_compute.call_args.args[2]
        assert params["MACD"] == {"N": 9} and params["KDJ"] == {"N": 9}

    def test_empty_kline_prints_error(self) -> None:
        cm = _mock_mac_client(None)
        with patch("easy_tdx.cli.conn.get_mac_client", cm):
            result = CliRunner().invoke(indicator, ["MACD", "-m", "SH", "-c", "1"])
        assert result.exit_code == 0
        assert "未获取到K线数据" in result.output

    def test_unknown_indicator_prints_error(self) -> None:
        cm = _mock_mac_client(_kline_df())
        with patch("easy_tdx.cli.conn.get_mac_client", cm):
            result = CliRunner().invoke(indicator, ["NOPE", "-m", "SH", "-c", "1"])
        assert "未知指标" in result.output

    def test_client_exception_caught(self) -> None:
        cm = MagicMock()
        cm.return_value.__enter__.side_effect = RuntimeError("conn boom")
        with patch("easy_tdx.cli.conn.get_mac_client", cm):
            result = CliRunner().invoke(indicator, ["MACD", "-m", "SH", "-c", "1"])
        assert "RuntimeError" in result.output and "conn boom" in result.output

    def test_fetch_count_at_least_200(self) -> None:
        cm = _mock_mac_client(_kline_df())
        with patch("easy_tdx.cli.conn.get_mac_client", cm):
            CliRunner().invoke(indicator, ["MACD", "-m", "SH", "-c", "1", "--count", "10"])
        assert cm.return_value.__enter__.return_value.get_stock_kline.call_args.kwargs[
            "count"
        ] == max(120 + 10, 200)


# ── indicator-list 命令 ──────────────────────────────────────────────────


class TestIndicatorListCommand:
    def test_json_list(self) -> None:
        result = CliRunner().invoke(indicator_list, [])
        assert result.exit_code == 0
        rows = json.loads(result.output)
        names = {r["name"] for r in rows}
        assert {"MACD", "KDJ"} <= names
        assert all("default_params" in r for r in rows)

    def test_table_list(self) -> None:
        result = CliRunner().invoke(indicator_list, ["--table"])
        assert result.exit_code == 0
        assert "MACD" in result.output
