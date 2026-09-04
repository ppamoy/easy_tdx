"""cli/cmd_verify.py 校验分支测试（V399t）。

覆盖 verify 命令的 --params 非法 JSON 与未知策略两个离线错误分支。
"""

from __future__ import annotations

from click.testing import CliRunner

from easy_tdx.cli.cmd_verify import verify


def _base_args():
    return ["SZ", "000001", "--count", "100"]


class TestVerifyValidation:
    def test_invalid_json(self) -> None:
        r = CliRunner().invoke(verify, _base_args() + ["--params", "not-json"])
        assert r.exit_code == 1
        assert "不是合法 JSON" in r.output

    def test_unknown_strategy(self) -> None:
        r = CliRunner().invoke(verify, _base_args() + ["--strategy", "definitely_not_a_strategy"])
        assert r.exit_code == 1
