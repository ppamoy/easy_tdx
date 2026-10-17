"""长赢缠论前视守卫的行为级回归测试。

使用真实日线 fixture 跑策略初始化和缠论信号生成；测试关注真实候选信号集合，
不通过源码文本或成员存在性冒充行为验证。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from easy_tdx.backtest.strategies import get_registry
from easy_tdx.backtest.strategies.changying_chanlun import Season

_FIXTURE = Path(__file__).parents[1] / "fixtures" / "chanlun_000001_daily.json"


def _fixture_df() -> pd.DataFrame:
    rows = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["amount"] = 0.0
    return df


def _strategy(df: pd.DataFrame, **params: object) -> Any:
    """构建/绑定/初始化一个长赢缠论策略实例（不跑 next）。"""
    strategy = get_registry().get("changying_chanlun").build(params)
    strategy._bind_data(df)
    strategy._call_init()
    return strategy


def _signals(df: pd.DataFrame, **params: object) -> list[tuple[int, str]]:
    strategy = _strategy(df, **params)
    return [(bar_idx, mmd_type) for bar_idx, mmd_type, _confidence in strategy._chanlun_signals]


def _emitted_bars(strategy: Any, n: int) -> list[tuple[int, str]]:
    """按 bar 顺序驱动真实信号消费路径，收集实际发出的 Signal。

    不走 ``next()``（避开每根 K 线重跑缠论分析），只固定季节 + 设置 bar index，
    然后调用真实的 ``_generate_signals()`` 消费预计算队列并用 ``_clear_signals()``
    取出真正 push 到引擎的信号。
    """
    strategy._current_season = Season.SPRING
    emitted: list[tuple[int, str]] = []
    for bar_idx in range(n):
        strategy._set_bar_index(bar_idx)
        strategy._generate_signals()
        for signal in strategy._clear_signals():
            emitted.append((bar_idx, signal.direction))
    return emitted


def test_guard_off_vs_on_changes_real_signal_count_and_effective_bars() -> None:
    """守卫必须真实删除伪影并把保留信号延后，而不只是暴露一个参数。"""
    df = _fixture_df()

    off_strategy = _strategy(df, lookahead_guard=False)
    on_strategy = _strategy(df, lookahead_guard=True, confirm_lag=3, guard_window=400)

    off = [(b, t) for b, t, _c in off_strategy._chanlun_signals]
    on = [(b, t) for b, t, _c in on_strategy._chanlun_signals]

    # V735 重新标定：切缠论原文口径后，原 (38,"1sell")、(62,"2sell") 被去掉。
    # 依据原文第21课：「一个**上涨趋势确定后**，不可能再有第一类与第二类买点」
    # （对卖点同理）—— 1卖/2卖 要求此前已形成**两个依次同向向上**的中枢
    # （原文第17课：趋势 = ≥2 个依次同向中枢）。该样本在 bar 38/62 处不满足，
    # 只剩符合原文第20课的 3sell。⇒ 这是按原文收紧，不是回归。
    #
    # V851：`(146, "3buy")` 也消失。该信号是**前视伪影**，已用截断法证明：
    #   数据截断到 bar n：140/145/146/150/153/160
    #   ⇒ 3buy@146 只在 n>=150 时才出现（依赖 bar 147-153 的数据）
    # 而当前代码在所有截断点上都不产生它。原文第20课第三类买卖点定理：
    # 「一个次级别走势类型向上离开缠中说禅走势中枢，然后以一个次级别走势类型
    #   回试，其低点不跌破 ZG，则构成第三类买点」
    # bar146 时 zs2（lines=[bi8,bi9,bi10,bi11]）的末笔 bi11 要到 bar153 才结束，
    # 中枢未成立、更没有回试笔 ⇒ 不可能有 3买。旧实现靠全局中枢统计把未来的
    # 中枢算进来，属于典型前视，与 V731 as-of 修复同源。
    assert off == [
        (62, "3sell"),
        (125, "3buy"),
        (153, "3sell"),
    ]
    assert on == [(65, "3sell"), (128, "3buy"), (156, "3sell")]
    # V857(偏差B)：新增 (153,"3sell")/(156,"3sell")。bi.high/low 回归端点分型值
    # （62课L20）→ 中枢 ZD 升高（端点值 ≤ 区间极值）→ 跌破 ZD 后回抽不破 ZD 的
    # 3卖（20课第三类卖点定理）新触发。区间极值覆盖偏离原文（属 bug），端点值是
    # 原文正确口径，故新增 3卖 是收紧而非回归。守卫仍验证非前视：default==explicit
    # 且 on bars == off bars + lag(3)（153→156）。
    # V851：信号数由 3 → 2（去掉前视伪影 3buy@146）；守卫的真实作用仍是
    # 「把保留信号延后 lag 根」，延后由下面 _emitted_bars(125→128) 钉死。
    assert [b for b, _ in on] == [b + 3 for b, _ in off], "守卫应把每个信号延后 lag=3 根"

    # 真实发出的策略信号（走队列消费 + 下单路径），守卫开启使生效 bar 延后 lag=3 根
    assert _emitted_bars(off_strategy, len(df)) == [(125, "BUY")]
    assert _emitted_bars(on_strategy, len(df)) == [(128, "BUY")]


def test_guard_defaults_on_and_matches_explicit_guard() -> None:
    """默认回测必须走守卫，显式关闭才保留未经前缀复核的候选。"""
    df = _fixture_df()

    default = _signals(df)
    explicit = _signals(df, lookahead_guard=True, confirm_lag=3, guard_window=400)

    # V851：同上，前视伪影 3buy@146 已被去掉（见上一条用例的截断法证明）。
    # 原 1sell/2sell 因不符原文第21课被去掉，3buy@146 因前视被去掉。
    # V857(偏差B)：新增 (156,"3sell")（端点值使中枢 ZD 升高→3卖新触发，见上条用例）。
    assert default == explicit == [(65, "3sell"), (128, "3buy"), (156, "3sell")]


def test_guarded_signals_reproduce_on_their_confirmation_prefix() -> None:
    """与 chanlun._apply_lookahead_guard 同口径，防漂移。"""
    df = _fixture_df()
    lag = 3
    guarded = _signals(df, lookahead_guard=True, confirm_lag=lag, guard_window=400)

    for effective_bar, mmd_type in guarded:
        anchor_bar = effective_bar - lag
        prefix = df.iloc[: effective_bar + 1].reset_index(drop=True)
        prefix_signals = _signals(prefix, lookahead_guard=False)
        assert (anchor_bar, mmd_type) in prefix_signals
