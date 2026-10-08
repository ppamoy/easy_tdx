"""level_synth 合成低级别数据的**可复现性**审计。

背景（V731 审计发现）：
:mod:`easy_tdx.chanlun.level_synth` 的 docstring 与 ``seed`` 参数说明都写着
「保证可复现——回测必须可复现」。但实测**区间套确认结果依赖随机种子**：

    9 个高级别信号中 5 个（56%）的 ``nested`` 标签随 seed 翻转。

根因是 ``_expand_ohlc`` 里两个随机源：
  1. ``first_ext = h if rng.random() < 0.5 else low`` —— 决定子 bar 路径
     **先摸高还是先探低**。这个顺序会改变子 bar 序列形态，进而改变低级别的
     分型/笔/中枢结构，对区间套结论影响最大。
  2. ``rng.normal(...)`` 路径噪声 —— 影响幅度较小但同样会翻转边界情形。

危害链：``nested`` 是**布尔**，而 ``chanlun_pair._nested_pass`` 在
``require_qujiantao=True`` 时按 ``nested is True`` 过滤交易信号 ⇒ 随机种子
直接决定某笔交易做不做 ⇒ 回测结论不可复现。

修复：把 (1) 改为由 OHLC **确定性**推断，(2) 改为确定性抖动序列
（仍保留波动形态，但不含随机数）。修复后实测翻转率 0/5 seed。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.level_synth import synthesize_lower_level
from easy_tdx.chanlun.qujiantao import compute_qujiantao_cross_period

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# 参与验证的样本（合成 + 缠论分析开销较大，取有高级别信号的 3 个）
SAMPLES = [
    "chanlun_000333_daily.json",
    "chanlun_000001_daily.json",
]
# 合成 + 全量缠论分析开销大，取 3 个 seed 已足以暴露翻转（实测 4 个 seed
# 下翻转率 56%，3 个 seed 即可覆盖）
SEEDS = [20240101, 1, 999]


def _nested_tuple(fixture: str, seed: int) -> tuple[bool | None, ...]:
    rows = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    hi = ChanlunAnalyser(code="HI", frequency="daily", config=ChanlunConfig()).process_klines(df)
    low = synthesize_lower_level(df, high_level="DAY", low_level="MIN_30", seed=seed)
    lr = ChanlunAnalyser(code="LOW", frequency="low", config=ChanlunConfig()).process_klines(low)
    qt = compute_qujiantao_cross_period(
        hi.mmds,
        bis_low=lr.bis,
        zss_low=lr.zss,
        bcs_low=lr.bcs,
        mmds_low=lr.mmds,
    )
    return tuple((q or {}).get("nested") if isinstance(q, dict) else None for q in qt)


@pytest.mark.parametrize("fixture", SAMPLES)
def test_nested_is_seed_independent(fixture: str) -> None:
    """核心断言：区间套确认结果必须与 seed 无关（回测可复现的前提）。"""
    results = {_nested_tuple(fixture, s) for s in SEEDS}
    assert len(results) == 1, (
        f"{fixture}: 不同 seed 得到 {len(results)} 种不同的区间套结论 "
        f"{sorted(results)} —— 回测不可复现"
    )


def test_synth_bar_count_is_seed_independent() -> None:
    """合成出的低级别 K 线根数必须与 seed 无关（形状层面的稳定性）。"""
    rows = json.loads((FIXTURES / SAMPLES[0]).read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    lens = {len(synthesize_lower_level(df, seed=s)) for s in SEEDS}
    assert len(lens) == 1, f"合成根数随 seed 变化：{sorted(lens)}"


def test_low_level_structure_is_seed_independent() -> None:
    """低级别笔/中枢数量必须与 seed 无关（结构层面的稳定性）。"""
    rows = json.loads((FIXTURES / SAMPLES[0]).read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    shapes = set()
    for s in SEEDS:
        low = synthesize_lower_level(df, high_level="DAY", low_level="MIN_30", seed=s)
        lr = ChanlunAnalyser(code="LOW", frequency="low", config=ChanlunConfig()).process_klines(
            low
        )
        shapes.add((len(lr.bis), len(lr.zss)))
    assert len(shapes) == 1, f"低级别结构随 seed 变化：{sorted(shapes)}"


def test_first_extreme_order_is_deterministic() -> None:
    """单根 bar 展开必须是确定性的：同输入多次调用结果完全一致。"""
    import numpy as np

    from easy_tdx.chanlun.level_synth import _expand_ohlc

    def call(seed: int):
        rng = np.random.default_rng(seed)
        return _expand_ohlc(10.0, 11.0, 9.0, 10.5, 8, rng)

    a, b = call(1), call(20240101)
    for x, y in zip(a, b):
        assert (x == y).all(), "同输入不同 seed 得到不同展开结果"
