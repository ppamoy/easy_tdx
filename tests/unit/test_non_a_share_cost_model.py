"""非 A 股成本模型的契约测试。

这个成本模型是我在 R22 新加的，用来补"剩余项"里
「非A股未建模交易成本故仅比方向」这条缺口。

⚠️ 为什么这类测试重要：成本模型最容易出的错是**静默空操作** ——
模型写了、参数传了、结果照样打印，但**根本没从毛超额里扣掉**，
于是报告里"扣成本后 +1.12%"其实还是毛超额 +1.17%（只差四舍五入）。
本文件把"扣成本必须真的扣"锁死。
"""

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_non_a_share.py"


def _src() -> str:
    return SCRIPT.read_text(encoding="utf-8")


class TestCostModelExists:
    def test_has_cost_models(self) -> None:
        assert "COST_MODELS" in _src()

    def test_has_zero_cost_control(self) -> None:
        """必须保留零成本档作对照，否则无法判断扣成本的净效果。"""
        assert "零成本" in _src()

    def test_has_optimistic_and_conservative(self) -> None:
        s = _src()
        assert "零售实际" in s
        assert "保守加倍" in s

    def test_scenarios_are_cli_selectable(self) -> None:
        s = _src()
        assert "--scenarios" in s
        assert "choices=list(COST_MODELS)" in s


class TestCostsMatchMarketReality:
    """成本必须符合各市场**真实**收费结构，不能照抄 A 股。"""

    def test_us_has_no_stamp_duty(self) -> None:
        """美股**无印花税**。若照抄 A 股的 0.1% 就是错的。"""
        s = _src()
        us = s.split('"美股": (')[1].split(")")[0]
        assert "0.0005" in us and "0.0007" in us

    def test_hk_stamp_duty_only_on_sell(self) -> None:
        """港股印花税**只在卖出**收，故 sell_cost 明显 > buy_cost。"""
        s = _src()
        hk = s.split('"港股": (')[1].split(")")[0]
        buy, sell = hk.split(",")[0], hk.split(",")[1]
        assert float(sell) > float(buy), "港股卖出成本必须高于买入（印花税只在卖出）"

    def test_sell_cost_exceeds_buy_in_all_markets(self) -> None:
        """三个市场都是卖出更贵（印花税/卖出费只在卖出）。"""
        s = _src()
        for mkt in ("美股", "港股", "A股"):
            seg = s.split(f'"{mkt}": (')[1].split(")")[0]
            buy, sell = [x.strip() for x in seg.split(",")[:2]]
            assert float(sell) > float(buy), f"{mkt} 卖出成本应高于买入"

    def test_documents_min_commission_limitation(self) -> None:
        """未建模最低佣金是真实偏差，必须**说出来**而不是藏起来。"""
        s = _src()
        assert "最低佣金" in s
        assert "低于" in s, "必须说明真实净超额会比比例模型更低"


class TestCostIsActuallySubtracted:
    """⚠️ 最危险：成本模型写成空操作。"""

    def test_subtracts_cost_from_excess(self) -> None:
        s = _src()
        assert "net = g - (bc if t in BUY else bc + sc)" in s

    def test_buy_signals_pay_only_buy_side(self) -> None:
        s = _src()
        assert "bc if t in BUY" in s, "买入信号只付买入那一笔的成本"

    def test_sell_signals_pay_both_sides(self) -> None:
        s = _src()
        assert "bc + sc" in s, "卖出信号已持有仓位，只付卖出那一笔"

    def test_has_teeth_for_cost_model(self) -> None:
        """AGENTS.md §7：必须先验证脚本确实能抓到。"""
        s = _src()
        assert "牙齿：成本模型不是空操作" in s
        assert "成本模型没生效" in s

    def test_teeth_checks_all_markets_and_signals(self) -> None:
        s = _src()
        assert 'for t in ("1buy", "1sell")' in s
        assert "diffs" in s


class TestHonestLimitations:
    def test_declares_proportional_model_only(self) -> None:
        s = _src()
        assert "比例模型" in s

    def test_declares_slippage_not_modelled(self) -> None:
        s = _src()
        assert "滑点" in s

    def test_declares_institutional_differ(self) -> None:
        """T+0/无涨跌停是制度差异，成本模型覆盖不到。"""
        s = _src()
        assert "涨跌停" in s
        assert "T+0" in s

    def test_declares_small_sample(self) -> None:
        s = _src()
        assert "样本量" in s

    def test_does_not_claim_proves_chanlun(self) -> None:
        """非A股方向一致 ≠ 缠论有效，不得过度解读。"""
        s = _src()
        assert "方向参考" in s or "仅作方向" in s
