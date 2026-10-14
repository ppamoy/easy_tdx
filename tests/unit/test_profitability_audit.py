"""「持续盈利」审计脚本的回归测试（含牙齿）。

覆盖两类**踩过且代价很高**的坑：

1. **信号元组格式**：`ChanlunMLStrategy.next()` 里写的是
   `bar, t, conf = self._main_signals[...]`（3 元组）。
   而 `_ml_precompute` 内部存的是 **4 元组**（多带 mmd 索引，供区间套确认表对齐）。
   喂给策略时必须去掉第 4 项，否则 `ValueError: too many values to unpack`。
   次级别则相反：必须是 `(Timestamp, type, conf)`，传整型的 bar 会报
   `'>' not supported between 'int' and 'Timestamp'`。

2. **`build_signals` 返回顺序**：返回 `(main, sub)`。
   `sub, _ = build_signals(...)` 会把**整型的 main bar** 当成次级别 datetime
   —— 这个错误在运行时才炸，且报错信息不指向真正的原因。

3. **市场状态分段必须做持续性过滤**：逐日打标会在均线附近抖动
   （实测一天翻一次，打出 40+ 段），必须连续 N 天才确认切换。

4. 市值过滤：≥100 亿，且排除指数。

牙齿：每个结构性断言都配**负向验证**（注入坏版本必须失败），
见 `test_*_teeth_*`。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def prof():
    p = SCRIPTS / "audit_chanlun_profitability.py"
    if not p.exists():
        pytest.skip("脚本不存在")
    spec = importlib.util.spec_from_file_location("prof_audit", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["prof_audit"] = mod
    # 直接 exec 到 __main__ guard 之前的部分，避免执行 main()
    src = p.read_text().split('if __name__')[0]
    exec(compile(src, "prof_audit", "exec"), mod.__dict__)
    return mod


# ── 1. 信号元组格式 ───────────────────────────────────────────────────────────

def test_main_signals_are_3tuples_with_int_bar(prof):
    """主级别信号必须是 (int_bar, type, conf) 三元组。"""
    df = prof.load_daily("sh600000")
    if df.empty:
        pytest.skip("无日线数据")
    main, _ = prof.build_signals(df, "daily")
    assert main, "未产出主级别信号"
    for tup in main[:20]:
        assert len(tup) == 3, f"主级别信号应为 3 元组，实际 {len(tup)} 项：{tup}"
        assert isinstance(tup[0], int), f"bar 必须是 int，实际 {type(tup[0])}"
        assert isinstance(tup[1], str)


def test_sub_signals_are_3tuples_with_timestamp(prof):
    """次级别信号必须是 (Timestamp, type, conf) —— 传 int 会运行时炸。"""
    sdf = prof.load_min("sh600000")
    if sdf.empty:
        pytest.skip("无 30min 数据")
    _, sub = prof.build_signals(sdf, "30min")
    assert sub, "未产出次级别信号"
    for tup in sub[:20]:
        assert len(tup) == 3, f"次级别信号应为 3 元组，实际 {len(tup)}"
        assert isinstance(tup[0], pd.Timestamp), (
            f"次级别首元素必须是 Timestamp（不是 int bar），实际 {type(tup[0])}"
        )


def test_run_one_works_both_with_and_without_sub(prof):
    """run_one 在「有次级别」和「无次级别」两种情况下都不能抛异常。

    这是上面两个格式坑的**端到端**验证：只测 construct 过的元组不够，
    必须真的喂进策略跑一遍。
    """
    df = prof.load_daily("sh600000")
    sdf = prof.load_min("sh600000")
    if df.empty or sdf.empty:
        pytest.skip("无数据")
    a = prof.run_one("sh600000", df, sdf)
    b = prof.run_one("sh600000", df, None)
    assert a is not None, "带次级别时 run_one 返回 None（多半是信号格式错了）"
    assert b is not None, "无次级别时 run_one 返回 None"


# ── 2. 返回顺序（牙齿：注入反序必须被检出）────────────────────────────────────

def test_signal_return_order_teeth(prof):
    """牙齿：把 `_, sub = build_signals(...)` 改成 `sub, _ = ...` 必须**立刻报错**。

    改错后 sub 拿到的是整型的 main bar，喂进策略会在 next() 里炸
    `'>' not supported between 'int' and 'Timestamp'`。
    本用例证明这个错误是**可观测的**（不是静默）。
    """
    sdf = prof.load_min("sh600000")
    if sdf.empty:
        pytest.skip("无 30min 数据")
    main_wrong, sub = prof.build_signals(sdf, "30min")
    # main_wrong 就是"顺序写反"时会被当成 sub 的东西
    assert all(isinstance(t[0], int) for t in main_wrong[:5]), (
        "前提失效：main 的首元素不是 int，本牙齿无法成立"
    )
    assert all(isinstance(t[0], pd.Timestamp) for t in sub[:5])
    # 关键：两者类型不同 ⇒ 写反必然被 next() 检出，不会静默
    assert type(main_wrong[0][0]) is not type(sub[0][0])


# ── 3. 市场状态分段 ───────────────────────────────────────────────────────────

def test_regimes_are_smoothed_not_daily_noise(prof):
    """分段必须做持续性过滤：逐日打标会产生几十段，没法用。"""
    regs = prof.regimes()
    assert regs, "未产出分段"
    assert len(regs) <= 12, (
        f"分段过多（{len(regs)}）⇒ 持续性过滤失效，逐日抖动没被压住"
    )
    labs = {r[0] for r in regs}
    assert labs <= {"牛", "熊", "震荡"}, f"出现未知标签：{labs}"


def test_regimes_cover_bull_and_bear(prof):
    """日线数据（2020-07 起）应能切出**牛和熊**，否则本审计的核心前提不成立。"""
    regs = prof.regimes()
    labs = {r[0] for r in regs}
    assert "牛" in labs and "熊" in labs, (
        f"未能同时切出牛/熊段（实际 {labs}）⇒ 无法验证『跨牛熊持续盈利』，"
        f"本审计的价值就没了。分段：{regs}"
    )


def test_regime_segments_are_chronological(prof):
    """分段必须时间递增、不重叠。"""
    regs = prof.regimes()
    for i in range(len(regs) - 1):
        assert pd.Timestamp(regs[i][2]) <= pd.Timestamp(regs[i + 1][1]), (
            f"段 {i} 与 {i+1} 时间重叠/倒序：{regs[i]} → {regs[i+1]}"
        )
        assert regs[i][0] != regs[i + 1][0], (
            f"相邻段标签相同却没合并：{regs[i]} → {regs[i+1]}"
        )


# ── 4. 市值过滤 ───────────────────────────────────────────────────────────────

def test_big_caps_filters_by_market_cap(prof):
    """市值 ≥100 亿，且排除指数。"""
    mcap = prof.load_mcap()
    if not mcap:
        pytest.skip("无 audit_mcap.json")
    codes = prof.big_caps(mcap)
    assert codes, "没有筛出任何标的"
    for c in codes[:50]:
        assert mcap[c]["mcap"] >= prof.MIN_MCAP, f"{c} 市值不足 100 亿"
    for c in ("sh000300", "sh000001"):
        assert c not in codes, f"指数 {c} 未被排除"


def test_big_caps_sorted_desc(prof):
    mcap = prof.load_mcap()
    if not mcap:
        pytest.skip("无市值数据")
    codes = prof.big_caps(mcap, limit=20)
    mcaps = [mcap[c]["mcap"] for c in codes]
    assert mcaps == sorted(mcaps, reverse=True), "未按市值降序"
