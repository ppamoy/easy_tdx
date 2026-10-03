"""V733 非 A 股样本脚本的契约测试。

⚠️ 纪律要求：脚本本身也要被审计 ——
   - 不能出现 `endswith("buy")`（会把 2buy_s 漏判并被取反）；
   - 数据源必须有自检（防止取到错数据还不自知）；
   - 不能包含新浪 CN 接口（实测不支持非 A 股）。
"""

from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
NON_A = SCRIPTS / "audit_non_a_share.py"


def _src() -> str:
    return NON_A.read_text(encoding="utf-8")


class TestNonAShareScriptExists:
    def test_script_present(self) -> None:
        assert NON_A.exists(), f"缺少 {NON_A}"

    def test_has_argparse_and_cache(self) -> None:
        s = _src()
        assert "argparse" in s
        assert "--limit" in s
        # 必须有缓存，否则重复联网会被限流
        assert "CACHE" in s


class TestButtonSideConvention:
    """买卖方向判定必须用 'buy' in st。"""

    def test_no_endswith_buy(self) -> None:
        assert "endswith(\"buy\")" not in _src(), (
            "禁止 endswith('buy')：'2buy_s'.endswith('buy') 为 False，"
            "会把类二买误判成卖方向并被取反")

    def test_uses_in_buy(self) -> None:
        assert '"buy" in st' in _src()

    def test_sell_is_mirrored(self) -> None:
        s = _src()
        # 卖方向必须取负
        assert "if not is_buy:" in s
        assert "rr = -rr" in s


class TestDataSourceSelfCheck:
    """数据源自检：防止取到错数据还当成结论。"""

    def test_has_sanity_check(self) -> None:
        s = _src()
        assert "数据源抽检" in s, "必须有数据源抽检"

    def test_sanity_check_records_result(self) -> None:
        s = _src()
        assert "符合美股" in s
        assert "结果不可信" in s

    def test_sample_size_alarm(self) -> None:
        assert "缓存仅" in _src(), "样本过少必须告警"

    def test_uses_yahoo_not_sina_cn(self) -> None:
        """实测新浪 CN_MarketData 不支持非 A 股（hk00700/gb_aapl 均 null）。

        ⚠️ 只检查**代码行**：脚本 docstring 里提到该接口名是为了说明
        "为什么不用它"，第一版我用全文匹配导致误判，已改为排除注释/docstring。
        """
        s = _src()
        code_lines = [
            ln for ln in s.splitlines()
            if not ln.lstrip().startswith("#")
        ]
        # 去掉模块 docstring（文件开头的三引号块）
        code = "\n".join(code_lines)
        code = code.split('"""', 2)[-1] if code.count('"""') >= 2 else code
        assert "query1.finance.yahoo.com" in code
        assert "CN_MarketData" not in code


class TestUniverseSpread:
    """样本不能全是科技股，否则结论只在单一行业成立。"""

    def test_us_universe_is_diversified(self) -> None:
        s = _src()
        for sym in ("KO", "JNJ", "XOM", "JPM", "CAT"):
            assert sym in s, f"美股样本应包含非科技股 {sym}"

    def test_has_hk_symbols(self) -> None:
        s = _src()
        assert "0700.HK" in s
        assert "1299.HK" in s

    def test_skips_missing_data(self) -> None:
        s = _src()
        assert "数据不足" in s, "数据不足的标的必须跳过而非静默计入"


class TestLimitationsDisclosed:
    def test_discloses_no_cost_model(self) -> None:
        s = _src()
        assert "未建模" in s and "交易成本" in s

    def test_discloses_regime_difference(self) -> None:
        s = _src()
        assert "T+0" in s or "涨跌停" in s

    def test_discloses_small_sample(self) -> None:
        assert "样本量远小于 A 股" in _src()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
