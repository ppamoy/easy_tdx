"""V733：审计脚本的口径回归测试（防止"看起来在测、其实测错了"）。

背景：我在 V733 里犯了两次同类错误，都是**统计脚本自己写错**，而且都能
通过全量单测，因为单测根本不覆盖这些脚本：

1. **买卖方向判错**：`st.endswith("buy")` 匹配不到 `"2buy_s"`（类二买），
   于是类二买被当成卖点、收益取反 —— 滚动脚本里它稳定显示 −8.28%，
   实为 **+8.28%**。而类二买/类二卖在三个审计脚本的 BUY/SELL 集合里
   **被整体漏掉**，从来没有进入过统计。

2. **置换检验期望写错**：断言"打乱后 |ρ| 中位数 < 原始 |ρ|"，
   但 n=39 时随机置换的 |ρ| 中位数本就在 ~0.12，当原始 |ρ|=0.09 时必然失败，
   与实现无关 —— 这是一个**统计上不成立**的期望。

本文件把这两类错误变成可执行断言。
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


class TestBuySellClassification:
    """类二买/类二卖必须被正确归类（endswith 陷阱）。"""

    # 项目里真实的 8 种买卖点类型（见 chanlun/types.py MMDType）
    ALL_TYPES = {
        "1buy",
        "2buy",
        "2buy_s",
        "3buy",
        "1sell",
        "2sell",
        "2sell_s",
        "3sell",
    }

    def test_endswith_buy_is_wrong(self) -> None:
        """牙齿验证：`endswith("buy")` 会漏掉 `2buy_s` —— 这是踩过的坑。"""
        endswith_buy = {t for t in self.ALL_TYPES if t.endswith("buy")}
        assert "2buy_s" not in endswith_buy, "前提不成立：endswith('buy') 竟然匹配了 2buy_s"
        # 正确写法：`"buy" in t`（类型名的方向标记在中间）
        contains_buy = {t for t in self.ALL_TYPES if "buy" in t}
        assert contains_buy == {"1buy", "2buy", "2buy_s", "3buy"}
        assert "2buy_s" in contains_buy

    def test_contains_buy_covers_all_buy_types(self) -> None:
        """`"buy" in t` 必须把 4 种买点全包括，且不含任何卖点。"""
        buys = {t for t in self.ALL_TYPES if "buy" in t}
        sells = {t for t in self.ALL_TYPES if "sell" in t}
        assert len(buys) == 4, f"买点应有 4 种，实得 {sorted(buys)}"
        assert len(sells) == 4, f"卖点应有 4 种，实得 {sorted(sells)}"
        assert buys | sells == self.ALL_TYPES, "买卖分类未覆盖全部类型"
        assert not (buys & sells), "同一类型不能既是买点又是卖点"

    @pytest.mark.parametrize(
        "rel",
        [
            "scripts/audit_predictive_power.py",
            "scripts/audit_timing_with_costs.py",
            "scripts/audit_qujiantao_power.py",
            "scripts/audit_rolling_oos.py",
        ],
    )
    def test_audit_scripts_include_leilei_types(self, rel: str) -> None:
        """四个审计脚本必须把类二买/类二卖纳入统计（V733 曾全部漏掉）。"""
        path = ROOT / rel
        if not path.exists():
            pytest.skip(f"{rel} 不存在")
        src = path.read_text(encoding="utf-8")
        assert "2buy_s" in src, f"{rel} 未纳入类二买 2buy_s（会静默漏统计）"
        assert "2sell_s" in src, f"{rel} 未纳入类二卖 2sell_s（会静默漏统计）"

    @pytest.mark.parametrize(
        "rel",
        [
            "scripts/audit_predictive_power.py",
            "scripts/audit_timing_with_costs.py",
            "scripts/audit_qujiantao_power.py",
            "scripts/audit_rolling_oos.py",
        ],
    )
    def test_audit_scripts_do_not_use_endswith_buy(self, rel: str) -> None:
        """禁止再写 `endswith("buy")` 判方向 —— 它会把 2buy_s 判成卖点。"""
        path = ROOT / rel
        if not path.exists():
            pytest.skip(f"{rel} 不存在")
        src = path.read_text(encoding="utf-8")
        assert 'endswith("buy")' not in src, (
            f'{rel} 仍用 endswith("buy") 判方向 —— 2buy_s 会被误判为卖点'
            "（收益取反），应改用 `'buy' in st`"
        )


class TestBaselineConvention:
    """基准口径：必须用同窗极值，不能用全样本极值。"""

    def test_full_sample_baseline_is_documented_as_too_optimistic(self) -> None:
        """全样本基准偏乐观（3buy +0.66% → 同窗 −1.22%，符号翻转）。

        锁这条是为了防止有人"优化"回全样本基准（它更快、数字更好看）。
        断言：滚动脚本必须显式说明这件事。
        """
        path = ROOT / "scripts" / "audit_rolling_oos.py"
        if not path.exists():
            pytest.skip("audit_rolling_oos.py 不存在")
        src = path.read_text(encoding="utf-8")
        assert "同窗" in src or "滚动窗" in src, (
            "audit_rolling_oos.py 应说明基准是同窗/滚动窗内的局部极值"
        )

    def test_cost_script_uses_same_window_baseline(self) -> None:
        """成本脚本的基准必须与滚动脚本一致（同为同窗），否则两套结论打架。"""
        path = ROOT / "scripts" / "audit_timing_with_costs.py"
        if not path.exists():
            pytest.skip("audit_timing_with_costs.py 不存在")
        src = path.read_text(encoding="utf-8")
        assert "同窗" in src or "同一滚动窗" in src, (
            "audit_timing_with_costs.py 仍用全样本基准 —— 会把 3buy 从 −1.22% "
            "算成 +0.66%（符号翻转），与 rolling_oos 结论矛盾"
        )
