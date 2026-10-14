"""买卖点信号统计（**唯一口径**）：方向有效性 + 胜过随机 + 显著性。

为什么要有这个模块：
  ``scripts/verify_chanlun_correctness.py``（审计脚本）与前端
  `/signal-check` 页面都需要「某类买卖点到底准不准」。若两处各写一份，
  必然漂移 —— 前端和审计给出**两个不同的数**，等于没有验证。
  本模块是唯一实现，脚本 / 接口 / 前端共用。

三层判据（越往上越硬，缺一不可）：
  L1 **方向对不对**：买点后 N 根真涨？卖点后真跌？（方向化后统一为"对了就为正"）
  L2 **胜过随机吗**：与同数量随机入场对照（固定种子 ⇒ 可复现）
  L3 **显著吗**：配对 t 检验 + **Bonferroni 多重比较校正**
     —— 不校正的话测 24 次就必然有约 1 次"显著"是运气

⚠️ 单位契约：**一律用小数**（0.0388 == +3.88%），与
   ``web/signal_ledger.py`` 一致。历史上曾出现百分数/小数混用导致
   结论差 100 倍的 bug，别再犯。

⚠️ 已修的两个坑（都曾污染过结论，别改回去）：
  1. 随机基准必须在**同一个下标**上取分子分母。曾写成
     `closes[int(r()*e)+h] / closes[int(r()*e)] - 1`（两次调用 r()），
     算出来的不是任何一次入场的收益 ⇒ 方差人为放大 ⇒ 显著性失真
     （实测 3buy 三档全被误判为无效）。
  2. 配对 t 检验在「差值非零但方差为 0」时必须返回大 t，不能返回 0 ——
     返回 0 会被读成"没有效应"，而真实含义是"每对都一样大，效应完美一致"。
"""

from __future__ import annotations

import math

# 方差为 0 且均值非零时的 t 值（"效应完美一致"，数学上 t → ∞）
T_PERFECT = 99.0


def lcg(seed: int):
    """固定种子的线性同余伪随机（不依赖 numpy 全局状态 ⇒ 可复现）。"""
    s = [seed & 0xFFFFFFFF]

    def f() -> float:
        s[0] = (s[0] * 1664525 + 1013904223) & 0xFFFFFFFF
        return s[0] / 4294967296

    return f


def forward(closes: list[float], bar: int, horizon: int) -> float | None:
    """信号 bar 之后 horizon 根的收益（小数）。越界返回 None。"""
    n = len(closes)
    j = bar + horizon
    if bar < 0 or bar >= n or j >= n or closes[bar] == 0:
        return None
    return closes[j] / closes[bar] - 1.0


def random_baseline(
    closes: list[float], k: int, horizon: int, seed: int
) -> list[float]:
    """同数量随机入场的前瞻收益（固定种子 ⇒ 可复现）。

    ⚠️ 必须在**同一个下标**上取分子和分母 —— 见模块 docstring 坑 1。
    """
    n = len(closes)
    eligible = n - horizon
    if eligible <= 0:
        return []
    r = lcg(seed)
    out = []
    for _ in range(k):
        j = min(int(r() * eligible), eligible - 1)
        out.append(closes[j + horizon] / closes[j] - 1.0)
    return out


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def paired_t(a: list[float], b: list[float]) -> tuple[float, float]:
    """配对 t 检验。返回 (t, 差值均值)。见模块 docstring 坑 2。"""
    d = [x - y for x, y in zip(a, b)]
    n = len(d)
    if n < 2:
        return 0.0, 0.0
    m = mean(d)
    var = sum((x - m) ** 2 for x in d) / (n - 1)
    if var <= 0:
        if m == 0:
            return 0.0, 0.0
        return T_PERFECT * (1.0 if m > 0 else -1.0), m
    return m / math.sqrt(var / n), m


def z_crit(alpha: float) -> float:
    """双尾检验的临界值（大样本正态近似，Newton 迭代求逆 erf，不依赖 scipy）。"""
    p = 1 - alpha / 2

    def erfinv(x: float) -> float:
        y = 0.0
        for _ in range(80):
            err = math.erf(y) - x
            if abs(err) < 1e-14:
                break
            y -= err / (2 / math.sqrt(math.pi) * math.exp(-y * y))
        return y

    return math.sqrt(2) * erfinv(2 * p - 1)


def bonferroni_crit(n_tests: int, alpha: float = 0.05) -> float:
    """多重比较校正后的 |t| 阈值。n_tests 越多越严。"""
    return z_crit(alpha / max(n_tests, 1))


def is_buy_type(mmd_type: str) -> bool:
    """买卖点类型 → 是否买点。

    ⚠️ **必须用子串判断，不能用 `endswith("buy")`**：
       `2buy_s`（类二买）以 `_s` 结尾 ⇒ `endswith("buy")` 为 False，
       会被当成**卖点取反**，产出稳定的**假反向信号**。
       这是本项目**第二次**踩同一个坑（首次见 V733_AUDIT_REPORT.md 五之九），
       权威口径与 ``chanlun/mmd.py`` 保持一致：``"buy" in mmd_type``。
    """
    return "buy" in str(mmd_type)


def directional(sign_is_buy: bool, ret: float) -> float:
    """方向化：买点看涨为正、卖点看跌为正 ⇒ 统一成"对了就为正"。"""
    return ret if sign_is_buy else -ret


def verdict(mean_dir: float, t_stat: float, crit: float) -> str:
    """三档结论。"""
    if mean_dir > 0 and t_stat > crit:
        return "✅ 方向对且显著"
    if mean_dir > 0:
        return "⚠️ 方向对但不显著"
    return "❌ 方向错/不显著"


def evaluate_type(
    per_stock: list[tuple[float, float]], crit: float
) -> dict[str, float | int | str | None]:
    """对某一信号类型 × 某一前瞻档做汇总判定。

    Args:
        per_stock: 每只票一对 (信号方向化均值, 随机方向化均值)
        crit: Bonferroni 校正后的 |t| 阈值

    Returns:
        含 count / avg / rnd / excess / t / verdict 的字典
    """
    if len(per_stock) < 2:
        return {"count": len(per_stock), "avg": None, "rnd": None,
                "excess": None, "t": None, "verdict": "样本不足"}
    sv = [p[0] for p in per_stock]
    rv = [p[1] for p in per_stock]
    t, diff = paired_t(sv, rv)
    return {
        "count": len(per_stock),
        "avg": mean(sv),
        "rnd": mean(rv),
        "excess": diff,
        "t": t,
        "verdict": verdict(mean(sv), t, crit),
    }
