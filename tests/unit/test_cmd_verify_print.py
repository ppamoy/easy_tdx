"""cli/cmd_verify.py 表格输出纯函数测试（V398）。

cmd_verify.py 此前覆盖率 37%。本文件用 monkeypatch 捕获 click.echo 输出，
覆盖 _print_verify_table / _print_verify_multi_table 各验证维度的渲染分支。
"""

from __future__ import annotations

import click

from easy_tdx.cli.cmd_verify import _print_verify_multi_table, _print_verify_table


def _run(fn, arg, monkeypatch) -> list[str]:
    lines: list[str] = []

    def _echo(s: str) -> None:
        lines.append(str(s))

    monkeypatch.setattr(click, "echo", _echo)
    fn(arg)
    return lines


class TestPrintVerifyTable:
    def test_basic(self, monkeypatch) -> None:
        lines = _run(_print_verify_table, {"performance": {}}, monkeypatch)
        text = "\n".join(lines)
        assert "单标验证" in text
        assert "总收益" in text

    def test_full_verdicts(self, monkeypatch) -> None:
        report = {
            "performance": {
                "total_return": 0.3,
                "sharpe": 1.5,
                "win_rate": 0.5,
                "total_trades": 20,
                "max_drawdown": 0.1,
                "annual_return": 0.2,
            },
            "accuracy": {"verdict": "准"},
            "robustness": {"verdict": "稳"},
            "model_trust": {"verdict": "可信"},
            "out_of_sample": {"verdict": "泛化"},
            "walk_forward": {"verdict": "滚稳"},
            "verdict": "推荐",
        }
        text = "\n".join(_run(_print_verify_table, report, monkeypatch))
        assert "汇总: 推荐" in text
        assert "准确度" in text


class TestPrintVerifyMultiTable:
    def test_empty(self, monkeypatch) -> None:
        lines = _run(_print_verify_multi_table, [], monkeypatch)
        assert "无验证结果" in lines

    def test_full_rows(self, monkeypatch) -> None:
        rows = [
            {
                "symbol": "SZ000001",
                "total_return": 0.3,
                "win_rate": 0.5,
                "hit_rate": 0.7,
                "excess_hit_rate": 0.05,
                "trust_score": 80,
                "overfit_likely": False,
                "oos_degraded": False,
                "wf_degraded": False,
            },
        ]
        text = "\n".join(_run(_print_verify_multi_table, rows, monkeypatch))
        assert "SZ000001" in text
        assert "样本外" in text
