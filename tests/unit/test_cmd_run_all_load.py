"""cli/cmd_run_all.py _load_strategy_class 测试（V399z）。"""

from __future__ import annotations

from pathlib import Path

from easy_tdx.cli.cmd_run_all import _load_strategy_class


class TestLoadStrategyClass:
    def test_loads_strategy(self, tmp_path: Path) -> None:
        f = tmp_path / "s.py"
        f.write_text(
            "from easy_tdx.backtest.strategy import Strategy\nclass MyStrat(Strategy):\n    pass\n",
            encoding="utf-8",
        )
        cls = _load_strategy_class(f)
        assert cls is not None
        assert cls.__name__ == "MyStrat"

    def test_missing_file(self, tmp_path: Path) -> None:
        assert _load_strategy_class(tmp_path / "nope.py") is None

    def test_syntax_error(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("def broken(\n", encoding="utf-8")
        assert _load_strategy_class(f) is None

    def test_no_strategy_subclass(self, tmp_path: Path) -> None:
        f = tmp_path / "plain.py"
        f.write_text("x = 1\n", encoding="utf-8")
        assert _load_strategy_class(f) is None
