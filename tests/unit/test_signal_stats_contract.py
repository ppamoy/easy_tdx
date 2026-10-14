"""signal_stats 口径的牙齿测试（端到端行为级，非存在性断言）。

为什么单独一个文件：
    `2buy_s`（类二买）**不以 "buy" 结尾**（以 `_s` 结尾）。判买卖方向时若用
    `t.endswith("buy")`，`2buy_s` 会被判成**卖点** ⇒ 收益**取反** ⇒
    产出**稳定且显著的反向假信号**。本项目已**两次**踩这个坑：
      1. V733_AUDIT_REPORT.md 五之九（文档警告过，但没拦住复发）
      2. scripts/verify_chanlun_correctness.py（新脚本又写了一次）

    所以这里的牙是**行为级**的：造一段"买点后必涨"的数据，
    断言 2buy_s **必须判为正向**。用 `endswith` 的坏版本会让这个测试变红。

另有 CI 守门脚本 `scripts/check_mmd_type_guard.py` 扫源码，两者互补：
    - 本文件：拦住**行为**回归（真跑一遍）
    - 守门脚本：拦住**新写的代码**（静态扫描，覆盖到没被测试碰到的路径）
"""

from __future__ import annotations

import pytest

from easy_tdx.backtest.signal_stats import (
    bonferroni_crit,
    directional,
    evaluate_type,
    forward,
    is_buy_type,
    lcg,
    mean,
    paired_t,
    random_baseline,
)


# ── 核心牙齿：2buy_s 必须判为买点 ────────────────────────────────────────────

@pytest.mark.parametrize(
    "t,expected",
    [
        ("1buy", True),
        ("2buy", True),
        ("2buy_s", True),   # ← 曾因 endswith("buy") 被误判为 False
        ("3buy", True),
        ("1sell", False),
        ("2sell", False),
        ("2sell_s", False),
        ("3sell", False),
    ],
)
def test_buy_type_classification(t, expected):
    assert is_buy_type(t) is expected


def test_endswith_would_have_missed_2s_variants():
    """牙齿有效性前提：`endswith` 版本**确实**会漏判 `_s` 后缀。

    若哪天这个断言不成立（比如类型名改了），说明牙本身失效，
    需要重新找一种能抓住该 bug 的检验方式。
    """
    assert "2buy_s".endswith("buy") is False
    assert "2sell_s".endswith("sell") is False
    # 而正确口径能识别
    assert is_buy_type("2buy_s") is True
    assert is_buy_type("2sell_s") is False


def test_directional_sign_for_2s_types():
    """行为级：同一个正收益，对 2buy_s 是"对了"，对 2sell_s 是"错了"。"""
    ret = 0.05
    assert directional(is_buy_type("2buy_s"), ret) == pytest.approx(+0.05)
    assert directional(is_buy_type("2sell_s"), ret) == pytest.approx(-0.05)


# ── 端到端：一段"买点后必涨"的数据，所有买点类型都必须判为正向 ───────────────

def _uptrend(n: int = 200) -> list[float]:
    """温和上涨序列：任意一点往后看大概率是涨的。"""
    return [100.0 * (1.001 ** i) for i in range(n)]


def test_all_buy_types_score_positive_on_uptrend():
    """买点类型 × 前瞻 5 根，在上涨序列上方向化均值必须为正。

    这是抓 endswith bug 的行为级断言：坏版本会让 `2buy_s` 取反成负。
    """
    closes = _uptrend(200)
    for t in ("1buy", "2buy", "2buy_s", "3buy"):
        assert is_buy_type(t), f"{t} 必须是买点"
        # 在整个序列上取平均前瞻收益（等价于"到处都是买点"）
        fwd = []
        for b in range(0, len(closes) - 5 - 1, 10):
            r = forward(closes, b, 5)
            if r is not None:
                fwd.append(r)
        sv = mean([directional(is_buy_type(t), x) for x in fwd])
        assert sv > 0, f"{t} 在上涨序列上应为正，实得 {sv}"


def test_all_sell_types_score_negative_on_uptrend():
    """卖点类型在上涨序列上方向化均值必须为负（反向对照）。"""
    closes = _uptrend(200)
    for t in ("1sell", "2sell", "2sell_s", "3sell"):
        assert not is_buy_type(t), f"{t} 必须是卖点"
        fwd = []
        for b in range(0, len(closes) - 5 - 1, 10):
            r = forward(closes, b, 5)
            if r is not None:
                fwd.append(r)
        sv = mean([directional(is_buy_type(t), x) for x in fwd])
        assert sv < 0, f"{t} 在上涨序列上应为负，实得 {sv}"


# ── 统计原语的性质 ───────────────────────────────────────────────────────────

def test_random_baseline_matches_single_entry():
    """随机基准的每一项都必须能在序列里找到**同一个 j** 使其成立。

    曾写成 `p[int(r()*e)+h] / p[int(r()*e)]`（两次 r() ⇒ 分子分母不同下标），
    算出来的不是任何一次入场的收益，方差被人为放大 ⇒ 显著性失真。
    """
    closes = [100.0 + i * 0.5 for i in range(200)]
    h = 5
    out = random_baseline(closes, 40, h, seed=20241010)
    assert len(out) == 40
    eligible = len(closes) - h
    for r in out:
        assert any(
            abs(closes[j + h] / closes[j] - 1 - r) < 1e-9 for j in range(eligible)
        ), f"{r} 不是任何单一入场下标的前瞻收益 ⇒ 随机基准被污染"


def test_random_baseline_teeth_two_calls_is_wrong():
    """牙齿：两次调用 r() 的坏版本必须被上面那条检验抓到。"""
    closes = [100.0 + i * 0.5 for i in range(200)]
    h = 5
    e = len(closes) - h
    r = lcg(20241010)

    def bad():
        return [
            closes[min(int(r() * e), e - 1) + h] / closes[min(int(r() * e), e - 1)] - 1
            for _ in range(40)
        ]

    out = bad()
    eligible = len(closes) - h
    missed = 0
    for v in out:
        if not any(abs(closes[j + h] / closes[j] - 1 - v) < 1e-9 for j in range(eligible)):
            missed += 1
    assert missed > 0, "前提失效：坏版本竟全部命中，本牙齿无意义"


def test_bonferroni_tightens_with_more_tests():
    """检验次数越多阈值越严 —— 否则测 24 次必然有约 1 次"显著"是运气。"""
    a = bonferroni_crit(1)
    b = bonferroni_crit(24)
    c = bonferroni_crit(100)
    assert a < b < c
    assert a == pytest.approx(1.96, abs=0.02)
    assert b == pytest.approx(3.08, abs=0.05)


def test_paired_t_zero_variance_nonzero_mean():
    """差值非零但方差为 0 ⇒ 效应完美一致，数学上 t→∞，不能返回 0。"""
    t, d = paired_t([0.05] * 20, [0.0] * 20)
    assert d == pytest.approx(0.05)
    assert t > 3.0, "完美一致的效应必须给出大 t，返回 0 会被误读成没有效应"


def test_evaluate_type_requires_two_stocks():
    assert evaluate_type([(0.1, 0.0)], 3.0)["verdict"] == "样本不足"
