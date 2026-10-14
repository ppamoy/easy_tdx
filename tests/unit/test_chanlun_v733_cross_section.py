"""V733：缠论信号数量 vs 未来收益 —— 横截面选股力回归测试。

背景（实测，非推测）
--------------------
`scripts/audit_predictive_power.py` 用 **286 只 A 股真实日线**（新浪前复权，
均 ≥764 根）做横截面 Spearman，结论是**显著为负**：

    买点数 vs 未来60根收益    ρ = -0.239  p < 0.0001
    信号总数 vs 未来60根收益  ρ = -0.239  p < 0.0001
    信号密度 vs 未来60根收益  ρ = -0.256  p < 0.0001

控制「全段历史涨幅」的偏相关仍显著（信号密度 −0.253、买点数 −0.248，
p 均 <0.0001），而历史涨幅本身与未来收益无关（ρ=−0.054, p=0.36），
故不是"动量反转"能解释的。

⚠️ 这是对 V732 结论的**修正**：V732 只有 30 只样本，ρ 全部不显著，
   属于样本不足造成的**假阴性**。扩到 286 只后方向变成**显著为负** ——
   用"缠论买点多的股票"选股会**系统性选到更差的标的**。

本测试锁死两件事
----------------
1. 管道本身：给定 K 线 → 能算出信号统计，且与未来收益算出**有限**的 ρ；
   （不锁死 ρ 的具体符号 —— 那依赖外部行情数据，不应进单测）
2. **牙齿验证**：把买点数人为翻转符号后，ρ 必须跟着翻转 —— 证明这个
   统计量真的由信号统计驱动，而不是被写死的常数或空集相等骗过。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from math import erfc, sqrt

import numpy as np
import pandas as pd
import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig


def _mk_series(seed: int, n: int = 900) -> pd.DataFrame:
    """生成一条有趋势+震荡的伪行情（用于验证管道，不用于验证真实结论）。"""
    rng = np.random.default_rng(seed)
    drift = rng.uniform(-0.0008, 0.0012)
    noise = rng.normal(0, 0.02, n)
    close = 10.0 * np.exp(np.cumsum(drift + noise))
    high = np.maximum(close, np.roll(close, 1)) * (1 + abs(rng.normal(0, 0.004, n)))
    low = np.minimum(close, np.roll(close, 1)) * (1 - abs(rng.normal(0, 0.004, n)))
    high[0], low[0] = close[0], close[0]
    dt = datetime(2020, 1, 2)
    dates = [(dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]
    return pd.DataFrame(
        {
            "datetime": pd.to_datetime(dates),
            "open": close,
            "close": close,
            "high": high,
            "low": low,
            "vol": np.full(n, 1e6),
        }
    )


def _cross_section(seeds: range) -> pd.DataFrame:
    """跑一遍横截面：每只股票的信号统计 + 未来 60 根收益。"""
    rows = []
    for s in seeds:
        df = _mk_series(s)
        res = ChanlunAnalyser(
            code=f"S{s}", frequency="daily", config=ChanlunConfig(zs_from_xd=False)
        ).process_klines(df)
        c = df["close"].to_numpy(dtype=float)
        n_buy = sum(1 for m in res.mmds if m.mmd_type.value.endswith("buy"))
        n_sell = sum(1 for m in res.mmds if m.mmd_type.value.endswith("sell"))
        t = len(c) - 61
        rows.append(
            {
                "n_buy": n_buy,
                "n_sell": n_sell,
                "net": n_buy - n_sell,
                "tot": n_buy + n_sell,
                "fwd": float(c[-1] / c[t] - 1.0),
            }
        )
    return pd.DataFrame(rows)


def _spearman(a: pd.Series, b: pd.Series) -> tuple[float, float] | None:
    """秩相关 + 双侧 p；任一列无变化则返回 None（避免 0/0 假值）。"""
    v = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(v) < 10 or v["a"].std() == 0 or v["b"].std() == 0:
        return None
    rx, ry = v["a"].rank().to_numpy(), v["b"].rank().to_numpy()
    rho = float(np.corrcoef(rx, ry)[0, 1])
    n = len(v)
    if abs(rho) >= 1.0:
        return rho, 0.0
    t = rho * sqrt((n - 2) / (1 - rho**2))
    return rho, float(erfc(abs(t) / sqrt(2)))


class TestCrossSectionPipeline:
    """横截面统计管道本身必须可用（不锁死真实数据的符号）。"""

    def test_pipeline_produces_valid_stats(self) -> None:
        """信号统计必须随标的而变（常数或全 0 → 相关系数无意义）。"""
        X = _cross_section(range(1, 25))
        assert len(X) == 24
        assert X["n_buy"].sum() > 0, "一只买点都没有 → 管道没跑起来"
        assert X["n_buy"].std() > 0, "买点数恒为常数 → 横截面无变化，ρ 不可算"

    def test_spearman_is_finite_or_none(self) -> None:
        """ρ 必须是有限数或 None，绝不能是 NaN 混入结论。"""
        X = _cross_section(range(1, 25))
        r = _spearman(X["n_buy"], X["fwd"])
        if r is not None:
            rho, p = r
            assert np.isfinite(rho), f"ρ 非有限值: {rho}"
            assert 0.0 <= p <= 1.0, f"p 越界: {p}"

    def test_constant_column_returns_none(self) -> None:
        """恒定的特征列必须返回 None，而不是悄悄给出 ρ=0 的假结论。"""
        X = _cross_section(range(1, 25))
        const = pd.Series([5] * len(X))
        assert _spearman(const, X["fwd"]) is None, "恒定列应返回 None（不可计算 ρ）"


class TestCrossSectionTeeth:
    """牙齿验证：证明 ρ 真的由「信号统计」驱动。"""

    def test_teeth_flipping_sign_flips_rho(self) -> None:
        """把买点数取相反数，ρ 必须反号且绝对值不变（斯皮尔曼的性质）。

        若本测试通过（翻转后 ρ 不变），说明上面算的 ρ 与信号统计无关 ——
        那是"看起来在测、其实没牙齿"的假测试。
        """
        X = _cross_section(range(1, 40))
        assert X["n_buy"].std() > 0, "前提：买点数必须有变化"
        r = _spearman(X["n_buy"], X["fwd"])
        assert r is not None, "前提：ρ 可计算"
        rho, _ = r
        assert rho != pytest.approx(0.0, abs=1e-9), "前提：ρ 不应恰为 0"

        flipped = _spearman(-X["n_buy"], X["fwd"])
        assert flipped is not None
        rho_f, _ = flipped
        assert rho_f == pytest.approx(-rho, abs=1e-9), (
            f"买点数取反后 ρ 应为 {(-rho):.6f}，实得 {rho_f:.6f} —— "
            "横截面统计没有牙齿，ρ 不是由信号统计驱动的"
        )

    def test_teeth_permutation_null_is_calibrated(self) -> None:
        """置换检验：ρ 的显著性必须由**置换零分布**判定，而非"打乱后变小"。

        ⚠️ 自误报修正：第一版断言"打乱未来收益后 |ρ| 中位数 < 原始 |ρ|"，
        这是**统计上错误**的期望 —— n=39 时随机置换的 |ρ| 中位数本来就在
        ~0.12，当原始 |ρ|=0.09（纯噪声水平）时该断言必然失败，与实现无关。
        正确做法：把原始 ρ 放进置换零分布里算**分位 p 值**，并断言
        「p 值是 [0,1] 内的有效概率」且「置换零分布以 0 为中心」。
        """
        X = _cross_section(range(1, 40))
        r = _spearman(X["n_buy"].to_numpy(), X["fwd"].to_numpy())
        assert r is not None, "前提：ρ 可计算"
        rho, _ = r

        rng = np.random.default_rng(20241002)
        y = X["fwd"].to_numpy()
        null = []
        for _ in range(200):
            sh = rng.permutation(y)
            rr = _spearman(X["n_buy"].to_numpy(), sh)
            if rr is not None:
                null.append(rr[0])
        assert len(null) >= 100, "置换次数不足"
        null = np.array(null)
        # 零分布应以 0 为中心（置换打断了配对关系）
        assert abs(np.mean(null)) < 0.1, f"置换零分布均值 {np.mean(null):.3f} 偏离 0 过远"
        # 置换 p 值：零分布中 |ρ| ≥ 观测 |ρ| 的比例
        p_perm = float((np.abs(null) >= abs(rho)).mean())
        assert 0.0 <= p_perm <= 1.0, f"置换 p 值越界: {p_perm}"
        # 自检：p_perm 不应恒为 0 或 1（否则说明置换根本没起效）
        assert np.std(null) > 1e-6, "置换零分布无方差 → 置换没起效"
