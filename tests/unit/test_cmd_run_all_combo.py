"""cli/cmd_run_all.py _run_combo_screen 边界测试（V402）。"""

from __future__ import annotations

import click

from easy_tdx.cli.cmd_run_all import _run_combo_screen


class TestRunComboScreen:
    def test_insufficient_strategies(self, monkeypatch) -> None:
        lines: list[str] = []

        def echo(s: str = "") -> None:
            lines.append(str(s))

        monkeypatch.setattr(click, "echo", echo)
        _run_combo_screen({"ma_cross": object}, None, 1e6, 0.0003, (2, 3), "equal")
        assert any("策略数量不足" in ln for ln in lines)
