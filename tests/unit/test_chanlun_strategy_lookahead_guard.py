"""ChanlunStrategy 前视守卫测试（与 chanlun_pair 守卫测试同语义）。

背景（V-AUDIT 审计发现）：笔端点 `bi.end.bar_index` 是事后标签——分型需
后续反向分型封口才成为笔终点。无守卫的 ChanlunStrategy 在端点当根即用
信号入场，实证全部入场落在「当根不可知」锚点（教科书级未来函数）。
守卫把候选信号放到只含历史的前缀上复现，复现成功才保留并延后 lag 根。
"""

# ── V-24 实测补充（真实金标 fixture 复核）─────────────────────────────
# 在 tests/fixtures/chanlun_000001_daily.json（160 根，3 个守卫关候选）上：
#   - b=146 3buy：前缀复现成功 → 守卫保留（延后 3 根）；
#   - b=38 1sell / b=62 2sell：前缀[:b+4] 复现失败——根因是**窗口太短
#     （42/66 根不足以稳定成笔）**，而非依赖未来数据；两信号直到前缀右端
#     k=148（后笔锁定结构）才可复现。守卫固定 lag=3 在短数据+稀疏笔场景
#     属于**保守丢弃**（宁可少做、不做错），与 chanlun_pair 同款设计取舍，
#     不是缺陷。金标 fixture 无 amount 列且 datetime 为 ISO 字符串，
#     直接喂 BacktestEngine 需先 pd.to_datetime + 补 amount。

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.backtest.strategies import get_registry

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _mk_df(n: int = 500, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    wave = 10.0 + 1.6 * np.sin(t / 17.0) + 0.9 * np.sin(t / 5.0) + 0.004 * t
    close = np.maximum(wave + rng.normal(0, 0.05, n), 1.0)
    high = close + np.abs(rng.normal(0, 0.08, n))
    low = close - np.abs(rng.normal(0, 0.08, n))
    open_ = np.clip(low + (high - low) * rng.uniform(0.2, 0.8, n), low, high)
    return pd.DataFrame(
        {
            "datetime": pd.bdate_range("2022-01-03", periods=n),
            "open": open_,
            "high": np.maximum(high, np.maximum(close, open_)),
            "low": np.minimum(low, np.minimum(close, open_)),
            "close": close,
            "vol": np.full(n, 1e6),
            "amount": np.full(n, 1e7),
        }
    )


def _signals(df: pd.DataFrame, **kw) -> list[tuple[int, str]]:
    """返回 (bar_idx, type) 列表（读策略信号队列）。"""
    s = get_registry().get("chanlun").build(kw)
    s._bind_data(df)
    s._call_init()
    return [(x[0], x[1]) for x in s._chanlun_signals]


class TestChanlunLookaheadGuard:
    def test_guard_off_vs_on_changes_signal_set(self):
        """守卫必须真的改变信号集（延迟生效点），否则没生效。"""
        df = _mk_df()
        off = _signals(df, lookahead_guard=False)
        on = _signals(df, lookahead_guard=True, confirm_lag=3)
        assert off != on

    def test_guard_default_is_on(self):
        """默认必须开守卫（不能让前视悄悄漏过）。"""
        strat = get_registry().get("chanlun").build({})
        assert strat.p["lookahead_guard"] is True
        assert strat.p["confirm_lag"] >= 1

    def test_guard_signals_reproducible_on_prefix(self):
        """核心回归：守卫开信号必须能被「截至生效 bar 的前缀」复现。

        若信号 e 依赖 e 之后的数据，用 df[:e+1] 跑（关守卫）应得不到
        对应锚点 (b=e-lag)。主体必须可复现（允许尾部边界少数例外）。
        """
        df = _mk_df()
        lag = 3
        on = _signals(df, lookahead_guard=True, confirm_lag=lag)
        if not on:
            pytest.skip("无守卫后信号")
        unreproducible = []
        for e, typ in on:
            b = e - lag
            sub = df.iloc[: e + 1].reset_index(drop=True)
            s_sub = _signals(sub, lookahead_guard=False)
            if not any(x[0] == b and x[1] == typ for x in s_sub):
                unreproducible.append((e, typ, b))
        assert len(unreproducible) <= max(1, len(on) // 5), (
            f"守卫后仍有 {len(unreproducible)}/{len(on)} 个信号无法在前缀上复现 → 仍有前视"
        )

    def test_guard_off_signals_are_not_reproducible(self):
        """对照组：关守卫的信号在「端点当根前缀」上大多复现不出（证明守卫必要）。

        用 df[:b+1]（端点当根，未含确认所需后续数据）跑：若端点信号在此前缀
        上不可见，说明无守卫的入场确实是前视。
        """
        df = _mk_df()
        off = _signals(df, lookahead_guard=False)
        if len(off) < 3:
            pytest.skip("信号太少，对照意义不足")
        invisible = 0
        for b, typ in off:
            sub = df.iloc[: b + 1].reset_index(drop=True)
            s_sub = _signals(sub, lookahead_guard=False)
            if not any(x[0] == b and x[1] == typ for x in s_sub):
                invisible += 1
        # 大多数端点锚点在当根前缀上不可见 → 守卫有真实防御对象
        assert invisible >= len(off) * 0.5, (
            f"端点当根可见比例过高（{len(off) - invisible}/{len(off)}），对照失效"
        )

    def test_guard_reproducible_across_runs(self):
        """同参数两次跑结果一致（可复现）。"""
        df = _mk_df()
        a = _signals(df, lookahead_guard=True, confirm_lag=3)
        b = _signals(df, lookahead_guard=True, confirm_lag=3)
        assert a == b
