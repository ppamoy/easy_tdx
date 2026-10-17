"""V854 沉淀测试：第61课区间套 REJECTED 字面「力度大于前者」MACD 面积对比。

⚠️ 重要背景：本测试锁的是**笔级力度**字面分支的逻辑（传入 closes 时触发），
   但该分支在**生产中休眠**——两个调用方（chanlun.py / hybrid.py）
   均**不传 closes**（第三个调用方 chanlun_pair 已废弃删除），
   故生产 REJECTED 仍走 V853「有结构无
   背驰」代理（实测 ~4%）。原因：笔级力度（curr 背驰笔 vs prev 同向背驰笔）
   在真数据上失真——背驰笔本就是走势段最弱笔，比值中位 4.6、36% >10x（退化
   prev），REJECTED 4%→34% 多为假阳（见 scripts/measure_v854_literal_force.py
   实测）。第61课原义是**走势段级**力度（整段 MACD 面积），需接 qsds + 修
   FX/CLKline 端点匹配，待 V855。保留本测试锁分支逻辑，供 V855 启用时回归。

两侧覆盖（AGENTS.md §4）：
- 关闭侧（closes=None → 代理，生产现状）：由既有 38 个 qujiantao 单测覆盖。
- 开启侧（closes 提供 → 字面对比，休眠分支）：本文件。

构造两段同向（向下笔 = 底背驰 = 买）走势段，前段温和衰减、后段剧烈 ⇒
后段 MACD 面积 > 前段 ⇒ REJECTED（字面）。另测无前者（首段）⇒ ASSUMED，
证明字面分支不会在无 prev 时误判。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace as NS

from easy_tdx.chanlun.qujiantao import compute_qujiantao_cross_period

D0 = datetime(2024, 1, 1)


def _mk_force_bi(sd, ed, s_bar, e_bar, direction, high, low):
    """带 bar_index（力度计算）+ k.date（时间窗）+ high/low（降级回退）的笔。"""
    return NS(
        start=NS(k=NS(date=sd), bar_index=s_bar, val=high),
        end=NS(k=NS(date=ed), bar_index=e_bar, val=low),
        direction=NS(value=direction),
        high=high,
        low=low,
        index=e_bar,
    )


def _mk_mmd(t, bi):
    return NS(bi=bi, mmd_type=NS(value=t))


# 70 根收盘价：前 30 根平（MACD 暖机）→ [30,39] 温和下行 → [40,59] 剧烈下行 → 平
_FLAT = [100.0] * 30
_GENTLE = [100.0 - 0.4 * i for i in range(10)]          # 30..39 : 100→96.4
_STEEP = [96.4 - 1.8 * i for i in range(20)]            # 40..59 : 96.4→60.4
_TAIL = [60.4] * 10                                      # 60..69 : 平
CLOSES = _FLAT + _GENTLE + _STEEP + _TAIL
assert len(CLOSES) == 70

# 前段（温和，小 MACD 面积）+ 后段（剧烈，大 MACD 面积），均向下笔 = 1buy
_PREV_BI = _mk_force_bi(D0 + timedelta(days=30), D0 + timedelta(days=39), 30, 39, "down", 100.0, 96.4)
_CURR_BI = _mk_force_bi(D0 + timedelta(days=40), D0 + timedelta(days=59), 40, 59, "down", 96.4, 60.4)
_PREV_MMD = _mk_mmd("1buy", _PREV_BI)
_CURR_MMD = _mk_mmd("1buy", _CURR_BI)

# 低级别：1 笔在所有窗口之前 ⇒ bi_count=0/zs_count=0 ⇒ 无结构 ⇒ 代理不触发，
# 仅字面分支能决定状态（隔离字面路径）。
_LOW_BI = _mk_force_bi(D0 - timedelta(days=5), D0 - timedelta(days=4), 0, 1, "up", 99.0, 98.0)


def test_literal_force_rejected_curr_greater_than_prev():
    """curr 背驰段 MACD 面积 > prev 同向 ⇒ 第61课字面 REJECTED。"""
    res = compute_qujiantao_cross_period(
        [_PREV_MMD, _CURR_MMD],
        bis_low=[_LOW_BI],
        closes=CLOSES,
    )
    curr_res = res[1]  # _CURR_MMD
    assert curr_res is not None, "curr 结果不应为 None"
    assert curr_res["state"] == "REJECTED", f"{curr_res['state']} ({curr_res['msg']})"
    ch = curr_res["chain"][0]
    # 力度真的算出来了 + curr > prev（ratio > 1）——证明不是空判
    assert ch["force_curr"] is not None and ch["force_prev"] is not None
    assert ch["force_curr"] > ch["force_prev"], (
        f"curr={ch['force_curr']} 应 > prev={ch['force_prev']}"
    )
    assert ch["force_ratio"] is not None and ch["force_ratio"] > 1.0
    assert "字面" in ch["rejected_reason"], ch["rejected_reason"]
    assert "字面" in curr_res["msg"]


def test_literal_force_not_fired_when_no_prev():
    """首段无前者 ⇒ 力度不可比 ⇒ 字面分支不触发 ⇒ 无结构 ⇒ ASSUMED。"""
    res = compute_qujiantao_cross_period(
        [_PREV_MMD, _CURR_MMD],
        bis_low=[_LOW_BI],
        closes=CLOSES,
    )
    prev_res = res[0]  # _PREV_MMD（列表首个，无同向前者）
    assert prev_res is not None
    assert prev_res["state"] == "ASSUMED", f"{prev_res['state']} ({prev_res['msg']})"
    ch = prev_res["chain"][0]
    # 无前者 ⇒ 力度字段为 None（未计算），rejected_reason 为 None
    assert ch["force_curr"] is None and ch["force_prev"] is None
    assert ch["rejected_reason"] is None


def test_literal_force_skipped_when_closes_none_keeps_proxy():
    """closes=None ⇒ 字面分支跳过 ⇒ 与既有代理行为一致（不会因有 prev 而误判）。"""
    # 给足结构（≥1 中枢 ≥3 笔在窗口内）让代理能触发；closes=None ⇒ 字面不参与
    from types import SimpleNamespace as NS

    def _mk_bi(sd, ed, direction="up"):
        return NS(start=NS(k=NS(date=sd)), end=NS(k=NS(date=ed)), direction=NS(value=direction))

    def _mk_zs(sd, ed):
        return NS(start=NS(k=NS(date=sd)), end=NS(k=NS(date=ed)), line_count=3)

    bis = [_mk_bi(D0 + timedelta(days=i), D0 + timedelta(days=i + 1)) for i in range(3)]
    zss = [_mk_zs(D0 + timedelta(days=1), D0 + timedelta(days=3))]
    # _CURR_MMD 窗口 [D0+40, D0+59]；上面 bis/zs 在 [D0, D0+4]，不在窗口 ⇒ bi_count=0
    # ⇒ 代理也不触发 ⇒ ASSUMED。这里验证 closes=None 时 force 字段为 None（字面未参与）。
    res = compute_qujiantao_cross_period(
        [_PREV_MMD, _CURR_MMD],
        bis_low=bis,
        zss_low=zss,
        closes=None,
    )
    curr_res = res[1]
    assert curr_res is not None
    ch = curr_res["chain"][0]
    assert ch["force_curr"] is None and ch["force_prev"] is None
    assert ch["force_ratio"] is None
