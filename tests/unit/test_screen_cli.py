"""screen/cli.py 命令边界测试（V398）。

screen/cli.py 此前覆盖率 38%。本文件用 CliRunner 覆盖 scan/rank/strength 三个
子命令的 help 与缺失必填参数错误分支，不触网。
"""

from __future__ import annotations

from click.testing import CliRunner

from easy_tdx.screen.cli import screen


class TestScreenScan:
    def test_help(self) -> None:
        r = CliRunner().invoke(screen, ["scan", "--help"])
        assert r.exit_code == 0
        assert "--strategy" in r.output

    def test_missing_strategy(self) -> None:
        r = CliRunner().invoke(screen, ["scan"])
        assert r.exit_code == 2
        assert "Missing option" in r.output


class TestScreenRank:
    def test_help(self) -> None:
        r = CliRunner().invoke(screen, ["rank", "--help"])
        assert r.exit_code == 0
        assert "--from" in r.output

    def test_missing_from(self) -> None:
        r = CliRunner().invoke(screen, ["rank"])
        assert r.exit_code == 2
        assert "Missing option" in r.output


class TestScreenStrength:
    def test_help(self) -> None:
        r = CliRunner().invoke(screen, ["strength", "--help"])
        assert r.exit_code == 0
        assert "--preset" in r.output

    def test_bad_preset(self) -> None:
        r = CliRunner().invoke(screen, ["strength", "--preset", "nope"])
        assert r.exit_code == 2
        assert "Invalid value" in r.output
