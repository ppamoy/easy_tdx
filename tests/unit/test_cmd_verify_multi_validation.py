"""cli/cmd_verify.py verify-multi/verify-portfolio 校验分支测试（V400）。"""

from __future__ import annotations

from click.testing import CliRunner

from easy_tdx.cli.cmd_verify import verify_multi, verify_portfolio


class TestVerifyMultiValidation:
    def test_invalid_json(self) -> None:
        r = CliRunner().invoke(verify_multi, ["SZ 000001", "--params", "not-json"])
        assert r.exit_code == 1
        assert "不是合法 JSON" in r.output

    def test_unknown_strategy(self) -> None:
        r = CliRunner().invoke(
            verify_multi, ["SZ 000001", "--strategy", "definitely_not_a_strategy"]
        )
        assert r.exit_code == 1


class TestVerifyPortfolioValidation:
    def test_invalid_json(self) -> None:
        r = CliRunner().invoke(verify_portfolio, ["SZ 000001", "--params", "not-json"])
        assert r.exit_code == 1
        assert "不是合法 JSON" in r.output

    def test_unknown_strategy(self) -> None:
        r = CliRunner().invoke(
            verify_portfolio, ["SZ 000001", "--strategy", "definitely_not_a_strategy"]
        )
        assert r.exit_code == 1
