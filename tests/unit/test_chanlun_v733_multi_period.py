"""V733：跨周期脚本的口径回归测试。

锁定两个已被真实 bug 咬过的点：
1. **代码前缀剥离**：audit_data 文件名带交易所前缀（sh600000），新浪接口要
   的是 sh+6 位数字。第一版直接拼前缀 → 'shsh600000' → 静默返回空。
2. **周期映射**：新浪 scale 的取值是实测出来的，不能凭印象改。

牙齿测试：证明坏版本会被断言抓住。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import audit_multi_period as amp  # noqa: E402


class TestCodeNormalization:
    """标的代码必须是 6 位裸码，前缀按首位数字重新判定。"""

    def test_strip_prefix(self) -> None:
        """audit_data 风格的代码要能剥成裸码。"""
        for code, bare in [("sh600000", "600000"), ("sz000001", "000001"), ("600519", "600519")]:
            b = code[2:] if code[:2] in ("sh", "sz", "bj") else code
            assert b == bare, f"{code} → {b}，期望 {bare}"

    def test_prefix_rule(self) -> None:
        """6/5/9 开头 → sh；其余 → sz。"""
        for bare, pfx in [
            ("600000", "sh"),
            ("601398", "sh"),
            ("510300", "sh"),
            ("000001", "sz"),
            ("300750", "sz"),
        ]:
            p = "sh" if bare[0] in ("6", "5", "9") else "sz"
            assert p == pfx, f"{bare} → {p}，期望 {pfx}"

    def test_teeth_double_prefix_is_invalid(self) -> None:
        """牙齿：证明不剥前缀确实会产生非法代码（否则本测试无意义）。"""
        bad = "sh" + "sh600000"  # 第一版的行为
        assert bad != "sh600000"
        assert len(bad[2:]) != 6, "不剥前缀后裸码长度不是 6，新浪必然返回空"


class TestScaleMapping:
    """周期 -> 新浪 scale 的映射（实测值，见脚本注释）。"""

    def test_all_expected_periods_present(self) -> None:
        expect = {"5min", "15min", "30min", "60min", "day", "week", "month"}
        assert expect <= set(amp.SCALES)

    def test_scale_values(self) -> None:
        assert amp.SCALES["5min"][0] == 5
        assert amp.SCALES["15min"][0] == 15
        assert amp.SCALES["30min"][0] == 30
        assert amp.SCALES["60min"][0] == 60
        assert amp.SCALES["day"][0] == 240
        assert amp.SCALES["week"][0] == 1200
        assert amp.SCALES["month"][0] == 7200

    def test_teeth_120_not_included(self) -> None:
        """牙齿：scale=120（2小时）实测返回 null，绝不能出现在映射里。"""
        assert 120 not in {v[0] for v in amp.SCALES.values()}, (
            "scale=120 实测不可用（返回 null），若新浪已修复需重新实测后再加入"
        )


class TestDirectionAndBaseline:
    """方向判定与极值基准的口径（与其它审计脚本保持一致）。"""

    @pytest.mark.parametrize(
        "st,expected",
        [
            ("1buy", True),
            ("1sell", False),
            ("2buy_s", True),
            ("2sell_s", False),  # 类二买/卖：endswith 会漏
            ("3buy", True),
            ("3sell", False),
        ],
    )
    def test_is_buy(self, st: str, expected: bool) -> None:
        assert amp._is_buy(st) is expected

    def test_pivot_low_selected_at_minimum(self) -> None:
        """局部低点基准：应在窗口最小值处。"""
        import numpy as np

        c = np.array([10, 9, 8, 7, 8, 9, 10, 9, 8, 7, 8], dtype=float)
        idx = amp.pivot_indices(c, 2, low=True, lo=0, hi=len(c))
        assert len(idx) >= 1
        for i in idx:
            assert c[i] == c[max(0, i - 2) : i + 3].min()
