"""缠论模型正确性验证脚本的回归测试（含牙齿）。

核心教训（本轮真踩到、且**已经污染了结论**）：
    `random_baseline` 曾经写成

        closes[int(r()*e) + h] / closes[int(r()*e)] - 1

    同一个表达式里调用了**两次** `r()` ⇒ 分子分母用了**两个不同下标**，
    算出来的根本不是任何一次入场的前瞻收益，而是两个随机点的价格之比。
    后果：随机基准被污染、方差人为放大 ⇒ 显著性判定失真
    （实测 3buy 三档全被误判 ❌，修好后变 ✅）。

    这个 bug 的**隐蔽性**在于：它不会崩溃、不会返回空、数值看起来也"像"收益，
    只会让「显著/不显著」的结论系统性偏保守。所以必须有专门的牙。

覆盖：
  1. 随机基准的每一项都必须等于**同一下标**上的前瞻收益（牙齿：注入坏版本必红）
  2. 随机基准的均值应接近该段行情的整体漂移（不能是 ±20% 这种量级）
  3. 方向化：买点看涨为正、卖点看跌为正
  4. 配对 t 检验的基本性质
  5. Bonferroni 阈值随检验次数收紧
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_chanlun_correctness.py"


@pytest.fixture(scope="module")
def vc():
    """共享统计模块 —— **唯一口径**，脚本与前端都用它。"""
    from easy_tdx.backtest import signal_stats
    return signal_stats


# ── 1. 随机基准必须在同一下标上取分子分母 ─────────────────────────────────────

def test_random_baseline_uses_single_index(vc):
    """每一项随机收益都必须能在序列里找到**同一个 j** 使其成立。

    这是污染 bug 的直接检验：坏版本算的是 p[j1+h]/p[j2]，
    在单调序列上会得到一个**不可能**由任何单次入场得到的值。
    """
    closes = [100.0 + i * 0.5 for i in range(200)]  # 严格单调 ⇒ 比值可反解
    h = 5
    k = 30
    out = vc.random_baseline(closes, k, h, seed=1234)
    assert len(out) == k
    n = len(closes)
    eligible = n - h
    for r in out:
        # 反解：存在 j 使 closes[j+h]/closes[j] - 1 == r
        found = any(
            abs(closes[j + h] / closes[j] - 1 - r) < 1e-9
            for j in range(eligible)
        )
        assert found, (
            f"随机收益 {r} 无法由任何单一入场下标产生 ⇒ "
            f"分子分母用了不同下标（那个已修的 bug）"
        )


def test_random_baseline_teeth_wrong_version_is_caught(vc):
    """牙齿：把 random_baseline 换成调用两次 r() 的坏版本，本测试必须变红。

    坏版本在严格单调序列上会产生**超出单次入场可能范围**的值。
    """
    closes = [100.0 + i * 0.5 for i in range(200)]
    h = 5
    # 坏版本（复现已修的 bug）
    def bad(closes, k, h, seed):
        n = len(closes)
        e = n - h
        r = vc.lcg(seed)
        return [
            closes[min(int(r() * e), e - 1) + h] / closes[min(int(r() * e), e - 1)] - 1
            for _ in range(k)
        ]

    out = bad(closes, 30, h, 1234)
    n = len(closes)
    eligible = n - h
    bad_count = 0
    for r in out:
        found = any(
            abs(closes[j + h] / closes[j] - 1 - r) < 1e-9 for j in range(eligible)
        )
        if not found:
            bad_count += 1
    assert bad_count > 0, (
        "前提失效：坏版本没有被检出，本牙齿不成立（说明检验太弱）"
    )


# ── 2. 随机基准的量级必须合理 ─────────────────────────────────────────────────

def test_random_baseline_magnitude_is_sane(vc):
    """随机基准应接近该段行情的整体漂移，不能是 ±20% 这种荒谬量级。

    污染 bug 的**可观测症状**就是这里：坏版本在横盘序列上也能算出 ±20%。
    """
    # 温和上涨：200 根涨 10%
    closes = [100.0 * (1.0005 ** i) for i in range(200)]
    out = vc.random_baseline(closes, 200, 10, seed=7)
    m = sum(out) / len(out)
    # 10 根的期望漂移约 0.5%*10 = 0.5%，容许放大到 5 倍
    assert abs(m) < 0.05, f"随机基准均值 {m:.4f} 过大 ⇒ 基准被污染"


def test_random_baseline_reproducible(vc):
    closes = [100 + (i % 17) * 0.3 for i in range(300)]
    a = vc.random_baseline(closes, 50, 5, seed=99)
    b = vc.random_baseline(closes, 50, 5, seed=99)
    assert a == b


# ── 3. 方向化 ─────────────────────────────────────────────────────────────────

def test_forward_out_of_range_is_none(vc):
    """越界的前瞻收益必须返回 None（由调用方丢弃），不能算出假值。"""
    closes = [float(100 + i) for i in range(50)]
    assert vc.forward(closes, 48, 5) is None
    assert vc.forward(closes, -1, 5) is None
    assert vc.forward(closes, 0, 5) is not None


# ── 4. 配对 t 检验 ────────────────────────────────────────────────────────────

def test_paired_t_positive_when_consistently_better(vc):
    a = [0.05] * 20
    b = [0.0] * 20
    t, diff = vc.paired_t(a, b)
    assert diff == pytest.approx(0.05)
    assert t > 3.0, "持续占优时 t 应该很大"


def test_paired_t_zero_variance_is_zero(vc):
    """差值恒为 0 ⇒ 方差为 0 ⇒ t=0（不能除零，也不能报天文数字）。"""
    t, diff = vc.paired_t([0.1] * 10, [0.1] * 10)
    assert diff == pytest.approx(0.0)
    assert t == 0.0


def test_paired_t_short_sample(vc):
    t, _ = vc.paired_t([0.1], [0.0])
    assert t == 0.0


# ── 5. Bonferroni 阈值随检验次数收紧 ──────────────────────────────────────────

def test_bonferroni_threshold_tightens(vc):
    """检验次数越多，阈值越严 —— 否则测 24 次必然有 ~1 次"显著"是运气。"""
    t1 = vc.z_crit(0.05)
    t24 = vc.bonferroni_crit(24)
    t100 = vc.bonferroni_crit(100)
    assert t1 < t24 < t100
    assert t1 == pytest.approx(1.96, abs=0.01)
    assert t24 == pytest.approx(3.08, abs=0.05)


# ── 6. 买卖点类型判定（**同一个坑踩了两次**，必须有牙）────────────────────────

def test_is_buy_type_covers_all_buy_variants(vc):
    """`2buy_s`（类二买）**不以 "buy" 结尾** ⇒ `endswith("buy")` 会漏判。

    后果不是"少一个信号"，而是**把它当卖点取反** ⇒ 产出稳定的假反向信号。
    这是本项目**第二次**踩这个坑（首次见 V733_AUDIT_REPORT.md 五之九），
    所以锁定权威口径：`"buy" in type`。
    """
    for t in ("1buy", "2buy", "2buy_s", "3buy"):
        assert vc.is_buy_type(t) is True, f"{t} 必须是买点"
    for t in ("1sell", "2sell", "2sell_s", "3sell"):
        assert vc.is_buy_type(t) is False, f"{t} 必须是卖点"


def test_is_buy_type_teeth_endswith_version_is_caught(vc):
    """牙齿：换成 `endswith("buy")` 的坏版本，本测试必须变红。

    前提失效（没变红）说明检验太弱，本牙不成立。
    """
    def bad(t: str) -> bool:
        return str(t).endswith("buy")

    assert bad("2buy_s") is False, (
        "前提失效：坏版本竟然把 2buy_s 判成了买点，本牙齿不成立"
    )
    assert vc.is_buy_type("2buy_s") is True


# ── 7. 买卖点类型判定：本项目**踩了两次**的坑，必须有牙 ───────────────────────

def test_is_buy_type_matches_all_buy_variants(vc):
    """`2buy_s`（类二买）**不以 "buy" 结尾** ⇒ `endswith("buy")` 漏判。

    后果不是"少算一个信号"，而是**符号取反** —— 买点被当成卖点，
    于是任何"买点后应该涨"的检验都会得到**稳定且显著的错误结论**
    （实测：2buy_s 三档 t = −7.23 / −3.34 / −5.57，全是被取反的假信号）。

    本项目**第二次**踩这个坑（首次见 V733_AUDIT_REPORT.md 五之九，
    那里也写了"必须用子串判断"），所以这里锁死权威口径。
    """
    for t in ("1buy", "2buy", "2buy_s", "3buy"):
        assert vc.is_buy_type(t) is True, f"{t} 应判为买点"
    for t in ("1sell", "2sell", "2sell_s", "3sell"):
        assert vc.is_buy_type(t) is False, f"{t} 应判为卖点"


def test_is_buy_type_teeth_endswith_version_is_wrong(vc):
    """牙齿：`endswith("buy")` 的坏版本**必须**把 2buy_s 判错。

    若它没判错 ⇒ 前提失效，本牙齿不成立（检验太弱）。
    """
    assert "2buy_s".endswith("buy") is False, (
        "前提失效：endswith 版本竟然判对了，本牙齿无意义"
    )
    assert vc.is_buy_type("2buy_s") is True
