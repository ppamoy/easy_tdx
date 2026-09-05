"""screen/scanner.py _get_strategy_file/_load_strategy_class 测试（V400）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from easy_tdx.screen.scanner import _get_strategy_file, _load_strategy_class


class _TestStrategy:
    def init(self) -> None:
        pass


class TestGetStrategyFile:
    def test_from_module(self) -> None:
        # 标准 import 模块有 __file__
        from easy_tdx.backtest.strategies.changying_chanlun import ChangyingChanlunStrategy

        path = _get_strategy_file(ChangyingChanlunStrategy)
        assert path.endswith("changying_chanlun.py")

    def test_no_source_raises(self) -> None:
        class Dynamic:
            __module__ = "not_a_real_module_name"
            pass

        with pytest.raises(ValueError, match="无法定位源文件路径"):
            _get_strategy_file(Dynamic)


class TestLoadStrategyClass:
    def test_loads(self, tmp_path: Path) -> None:
        f = tmp_path / "s.py"
        f.write_text(
            "from easy_tdx.backtest.strategy import Strategy\nclass S(Strategy):\n    pass\n",
            encoding="utf-8",
        )
        cls = _load_strategy_class(str(f))
        assert cls is not None
        assert cls.__name__ == "S"

    def test_no_strategy_subclass(self, tmp_path: Path) -> None:
        f = tmp_path / "plain.py"
        f.write_text("x = 1\n", encoding="utf-8")
        assert _load_strategy_class(str(f)) is None
