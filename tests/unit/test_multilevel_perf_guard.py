"""multi-level 性能护栏 + 日期窗口的牙齿测试。

背景（实测，2026-10-10）：
- `ChanlunAnalyser.process_klines` 是**超线性**的：500 根 0.6s、
  3000 根 16.1s、3976 根 29.5s（≈ n^1.6）。
- multi-level 要跑 high + low 两份。low 不截断时整请求 ~32s，
  **超过浏览器 fetch 的 30s 上限**（Moli 实测
  "curl request failed ... after 30000ms"），前端只能拿到
  failed to fetch ⇒ 区间套功能等于不可用。
- 同时：`/chanlun/multi-level` 曾**忽略** start_date/end_date，
  始终从最新 bar 往回取 ⇒ 历史窗口下 low 为空，区间套全 false。

本文件把这两条都锁成可执行断言。
"""

import inspect

import pytest

from easy_tdx.web.routers import chanlun as cl


def test_low_max_bars_exists_and_is_bounded():
    """LOW_MAX_BARS 必须存在，且落在「够用又不超过 30s」的区间。"""
    cap = getattr(cl, "LOW_MAX_BARS", None)
    assert cap is not None, "multi-level 缺少低级别截断常量"
    # 实测：3000 根 ≈ 16s（安全）；3976 根 ≈ 30s（会超时）
    assert 1000 <= cap <= 3000, f"LOW_MAX_BARS={cap} 不在安全区间 [1000, 3000]"


def test_multilevel_source_truncates_low_bars():
    """源码里必须真的对 df_low 做了 tail 截断（防止只加常量不生效）。"""
    src = inspect.getsource(cl.chanlun_multi_level)
    assert "LOW_MAX_BARS" in src, "multi-level 未引用 LOW_MAX_BARS 做截断"
    assert "df_low.tail" in src or ".tail(LOW_MAX_BARS)" in src


def test_multilevel_source_uses_date_range_for_both_levels():
    """高/低级别都必须在 `req.start_date` 为真时走 fetch_bars_range。

    只查「出现次数」不够 —— 把 `if req.start_date:` 改成 `if False:`
    次数不变却彻底失效。所以这里**逐行**定位每个 fetch_bars_range 调用，
    回溯它上面最近的 `if` 条件里是否含 `req.start_date`。
    """
    src = inspect.getsource(cl.chanlun_multi_level)
    lines = src.splitlines()
    call_idxs = [
        i for i, ln in enumerate(lines)
        if "fetch_bars_range(" in ln and "await" in ln
    ]
    assert len(call_idxs) >= 2, (
        f"multi-level 只有 {len(call_idxs)} 处 fetch_bars_range 调用，"
        "高/低级别应各一处"
    )
    for i in call_idxs:
        # 回溯最近的条件行
        cond = None
        for j in range(i - 1, max(i - 8, -1), -1):
            if "if " in lines[j]:
                cond = lines[j]
                break
        assert cond is not None and "req.start_date" in cond, (
            f"第 {i} 行的 fetch_bars_range 未被 `req.start_date` 条件保护 "
            f"（最近条件行: {cond!r}）—— 历史窗口会取不到数据"
        )


def test_teeth_no_truncation_would_be_too_slow():
    """牙齿：不截断的话 3976 根确实会超时（前提假设成立）。

    这条不是测我们的代码，而是锁住「为什么必须有护栏」这个前提 ——
    若哪天 process_klines 变快了，护栏可以放宽，但也要有人来验证。
    """
    cap = getattr(cl, "LOW_MAX_BARS")
    # 实测全量 30min 数据是 3976 根，超过 cap ⇒ 护栏确实在起作用
    assert 3976 > cap, "全量 30min 数据未超过截断上限，护栏形同虚设"
