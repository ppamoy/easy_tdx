"""V373: CLI 输出层（easy_tdx.cli.output）单元测试。

补齐 format_output / print_output / print_error / 表格渲染的
json / csv / table / 空表 / 非法格式 / 无 tabulate 回退 / stderr 等分支，
此前该模块只有被 CLI 命令间接调用，无直接单测覆盖。
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import click
import pandas as pd
import pytest


def _sample_df() -> pd.DataFrame:
    """带中文与日期列的样例 DataFrame（验证 force_ascii=False 与 ISO 日期）。"""
    return pd.DataFrame(
        {
            "symbol": ["SH600000", "SZ000001"],
            "name": ["平安银行", "招商银行"],
            "date": [pd.Timestamp("2024-03-15"), pd.Timestamp("2024-03-18")],
            "price": [10.5, 12.3],
        }
    )


def test_format_output_json_records_with_utf8_and_iso_dates() -> None:
    """json：records 数组、中文不被转义（force_ascii=False）、日期 ISO。"""
    from easy_tdx.cli.output import format_output

    text = format_output(_sample_df(), "json")
    assert '"symbol":"SH600000"' in text
    assert "平安银行" in text  # 中文原样保留
    assert "\\u" not in text
    assert "2024-03-15T00:00:00" in text  # date_format=iso


def test_format_output_csv() -> None:
    """csv：以逗号分隔、含表头。"""
    from easy_tdx.cli.output import format_output

    text = format_output(_sample_df(), "csv")
    assert text.splitlines()[0] == "symbol,name,date,price"
    assert "SH600000,平安银行" in text


def test_format_output_empty_df() -> None:
    """空表：json 返回 []，csv/table 返回空串（调用方不输出）。"""
    from easy_tdx.cli.output import format_output

    empty = pd.DataFrame()
    assert format_output(empty, "json") == "[]"
    assert format_output(empty, "csv") == ""
    assert format_output(empty, "table") == ""


def test_format_output_unsupported_raises_usage_error() -> None:
    """非法输出格式：抛 click.UsageError 并提示。"""
    from easy_tdx.cli.output import format_output

    with pytest.raises(click.UsageError, match="不支持的输出格式: xml"):
        format_output(_sample_df(), "xml")


def test_format_output_table_with_tabulate(monkeypatch) -> None:
    """table：有 tabulate 时走 grid 渲染（stub 验证 import 分支）。"""
    from easy_tdx.cli.output import format_output

    stub = SimpleNamespace(tabulate=lambda *a, **k: "GRID-TABLE-STUB")
    monkeypatch.setitem(sys.modules, "tabulate", stub)
    assert format_output(_sample_df(), "table") == "GRID-TABLE-STUB"


def test_format_output_table_fallback_without_tabulate(monkeypatch) -> None:
    """table：无 tabulate 时回退文本渲染（真实环境未装 tabulate 的路径）。"""
    from easy_tdx.cli.output import format_output

    monkeypatch.setitem(sys.modules, "tabulate", None)  # import 抛 ImportError
    text = format_output(_sample_df(), "table")
    assert "symbol | name | date | price" in text
    assert "SH600000 | 平安银行" in text


def test_print_output_writes_stdout(capsys) -> None:
    """print_output：JSON 内容写到 stdout。"""
    from easy_tdx.cli.output import print_output

    print_output(_sample_df(), "json")
    captured = capsys.readouterr()
    assert '"symbol":"SH600000"' in captured.out
    assert captured.err == ""


def test_print_output_empty_writes_nothing(capsys) -> None:
    """print_output：空表 csv 不向 stdout 输出任何内容。"""
    from easy_tdx.cli.output import print_output

    print_output(pd.DataFrame(), "csv")
    assert capsys.readouterr().out == ""


def test_print_error_writes_stderr_with_prefix(capsys) -> None:
    """print_error：错误消息带「错误: 」前缀写 stderr。"""
    from easy_tdx.cli.output import print_error

    print_error("boom")
    captured = capsys.readouterr()
    assert captured.err == "错误: boom\n"
    assert captured.out == ""


def test_render_table_truncates_object_columns() -> None:
    """_render_table：object 列长文本截断到 30 字符。"""
    from easy_tdx.cli.output import _render_table

    df = pd.DataFrame({"url": ["x" * 100], "n": [1]})
    text = _render_table(df)
    assert "x" * 30 in text
    assert "x" * 31 not in text


def test_render_table_full_keeps_long_text() -> None:
    """_render_table_full：不截断长文本（url/title 等字段完整展示）。"""
    from easy_tdx.cli.output import _render_table_full

    long = "y" * 100
    df = pd.DataFrame({"url": [long]})
    text = _render_table_full(df)
    assert long in text


def test_render_table_impl_empty_returns_no_data() -> None:
    """_render_table_impl：空表渲染为「(无数据)」。"""
    from easy_tdx.cli.output import _render_table_impl

    assert _render_table_impl(pd.DataFrame(), 30) == "(无数据)"
    assert _render_table_impl(pd.DataFrame(), None) == "(无数据)"
