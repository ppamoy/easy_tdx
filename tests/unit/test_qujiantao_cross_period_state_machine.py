"""V853 沉淀测试：第61课区间套状态机 —— 真跨周期路径（AGENTS.md §7）。

`compute_qujiantao_cross_period`（日线信号 + 真实 30min 低级别）现输出
`state`（ASSUMED/CONFIRMED/REJECTED）+ `chain`（逐重链）。

实测（真跨周期，20 只日线+30min）：ASSUMED 46 / CONFIRMED 45 / REJECTED 15。
REJECTED（背驰段不成立，力度未衰减）此前被并入「未确认」nested=False，与
ASSUMED 不可区分——状态机把它单列出来（第61课「力度大于前者…背驰段不成立」）。
本测试构造三态，锁状态机在跨周期路径存在；删 state 字段即失败。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

from easy_tdx.chanlun.qujiantao import compute_qujiantao_cross_period

D0 = datetime(2024, 1, 1)


def _mk_bi(sd, ed, direction="up", val_s=1.0, val_e=2.0):
    s = NS(k=NS(date=sd), val=val_s)
    e = NS(k=NS(date=ed), val=val_e)
    return NS(start=s, end=e, direction=NS(value=direction))


def _mk_mmd(t, bi):
    return NS(bi=bi, mmd_type=NS(value=t))


def _mk_bc(bi, bc=True):
    return NS(curr=bi, bc=bc, bc_type=NS(value="BI"))


def _mk_zs(sd, ed):
    # 跨周期中枢：z.start.k.date / z.end.k.date 是时间锚点
    return NS(start=NS(k=NS(date=sd)), end=NS(k=NS(date=ed)), line_count=3)


# 高级别 1买锚定笔窗口 [D0, D0+6天]（向下笔 = 底背驰方向）
_HI_BI = _mk_bi(D0, D0 + timedelta(days=6), "down")
_HI_MMD = _mk_mmd("1buy", _HI_BI)


def test_cross_period_confirmed():
    """低周期窗口内同向底背驰 ⇒ CONFIRMED。"""
    low_bi = _mk_bi(D0 + timedelta(days=1), D0 + timedelta(days=4), "down")
    res = compute_qujiantao_cross_period([_HI_MMD], bcs_low=[_mk_bc(low_bi)])[0]
    assert res["state"] == "CONFIRMED", f"{res['state']} ({res['msg']})"
    assert res["nested"] is True
    assert res["chain"][0]["state"] == "CONFIRMED"
    assert res["chain"][0]["has_bc_same_dir"] is True
    assert res["method"] == "cross_period"


def test_cross_period_rejected():
    """低周期走了结构（≥1中枢+≥3笔）却无同向背驰 ⇒ REJECTED（力度未衰减）。"""
    bis = [
        _mk_bi(D0 + timedelta(days=i), D0 + timedelta(days=i + 1), "down" if i % 2 else "up")
        for i in range(3)
    ]  # 3 笔在 [D0, D0+6] 内
    zss = [_mk_zs(D0 + timedelta(days=1), D0 + timedelta(days=3))]  # 1 中枢在窗口
    # 无 bcs_low / mmds_low ⇒ 无同向背驰 ⇒ not confirmed，但有结构 ⇒ REJECTED
    res = compute_qujiantao_cross_period([_HI_MMD], bis_low=bis, zss_low=zss)[0]
    assert res["state"] == "REJECTED", f"{res['state']} ({res['msg']})"
    assert res["nested"] is False
    assert res["chain"][0]["zs_count"] >= 1 and res["chain"][0]["bi_count"] >= 3


def test_cross_period_assumed():
    """低周期结构不足（<3 笔）⇒ ASSUMED。"""
    res = compute_qujiantao_cross_period([_HI_MMD], bis_low=[_mk_bi(D0, D0 + timedelta(days=1))])[0]
    assert res["state"] == "ASSUMED", f"{res['state']} ({res['msg']})"
    assert res["nested"] is False
    assert res["chain"][0]["state"] == "ASSUMED"


def test_cross_period_no_low_returns_none():
    """无低周期数据 ⇒ None（不编造，与 compute_qujiantao 的 ASSUMED+chain=[] 区分）。"""
    out = compute_qujiantao_cross_period([_HI_MMD])
    assert out == [None]


def test_cross_period_chain_serializable():
    """chain 必须 list[dict] 可 JSON 序列化（前端逐重渲染）。"""
    low_bi = _mk_bi(D0 + timedelta(days=1), D0 + timedelta(days=4), "down")
    res = compute_qujiantao_cross_period([_HI_MMD], bcs_low=[_mk_bc(low_bi)])[0]
    assert isinstance(res["chain"], list)
    js = json.dumps(res["chain"], default=str)
    assert len(js) > 0
    assert res["chain"][0]["level"] == "次周期"
