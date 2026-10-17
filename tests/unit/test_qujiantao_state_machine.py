"""V853 沉淀测试：第61课区间套状态机（AGENTS.md §7）。

原文第61课：区间套 = 嵌套背驰段逐重链，状态机
  ASSUMED（假设进入背驰段，无证据否定前）→ CONFIRMED（力度衰减，本重背驰成立）
                                                  / REJECTED（力度未衰减，背驰段不成立）。

compute_qujiantao 现输出 `state`（ASSUMED/CONFIRMED/REJECTED）+ `chain`（逐重链）。
本测试构造三种情形，锁三态可达 + chain 结构；若状态机被删/退化为单 bool 即失败。
"""
from __future__ import annotations

from types import SimpleNamespace

from easy_tdx.chanlun.qujiantao import compute_qujiantao
from easy_tdx.chanlun.types import BC, BI, MMD, BCType, Direction, MMDType


def _fake_bi(start_idx: int, end_idx: int, direction: str = "up") -> BI:
    start_fx = SimpleNamespace(bar_index=start_idx, k=SimpleNamespace(date=None, close=0.0))
    end_fx = SimpleNamespace(bar_index=end_idx, k=SimpleNamespace(date=None, close=0.0))
    bi = SimpleNamespace()
    bi.start = start_fx
    bi.end = end_fx
    bi.direction = Direction.UP if direction == "up" else Direction.DOWN
    bi.index = end_idx
    return bi


def _fake_mmd(mmd_type: str, bi: BI) -> MMD:
    return MMD(mmd_type=MMDType(mmd_type), bi=bi)  # type: ignore[arg-type]


def _fake_bc(curr_direction: str, end_idx: int, bc: bool = True) -> BC:
    curr = _fake_bi(end_idx - 5, end_idx, curr_direction)
    return BC(bc_type=BCType.QS, bc=bc, curr=curr)  # type: ignore[arg-type]


def _fake_zs(start_idx: int, end_idx: int):
    z = SimpleNamespace()
    z.start = SimpleNamespace(bar_index=start_idx)
    z.end = SimpleNamespace(bar_index=end_idx)
    z.line_count = 3
    return z


# 1买（底背驰段）锚定笔窗口 [0, 20]
_BI = _fake_bi(0, 20, "down")


def test_state_machine_confirmed():
    """次级别窗口内有同向底背驰 ⇒ CONFIRMED（力度衰减，本重背驰成立）。"""
    m = _fake_mmd("1buy", _BI)
    bc = _fake_bc("down", 15, bc=True)  # 底背驰，落在 [0,20]
    res = compute_qujiantao(m, bcs_low=[bc])
    assert res["state"] == "CONFIRMED", f"应 CONFIRMED，实际 {res['state']} ({res['msg']})"
    assert res["nested"] is True
    assert isinstance(res["chain"], list) and len(res["chain"]) >= 1
    assert res["chain"][0]["state"] == "CONFIRMED"
    assert res["chain"][0]["has_bc_same_dir"] is True


def test_state_machine_rejected():
    """次级别走了结构（≥1中枢+≥3笔）却无同向背驰 ⇒ REJECTED（力度未衰减）。"""
    m = _fake_mmd("1buy", _BI)
    bis = [_fake_bi(0, 5), _fake_bi(5, 10), _fake_bi(10, 15)]  # 3 笔在窗口
    zss = [_fake_zs(2, 12)]  # 1 中枢在窗口
    # 不给 bcs_low / mmds_low ⇒ 无同向背驰 ⇒ not confirmed，但有结构 ⇒ REJECTED
    res = compute_qujiantao(m, bis_low=bis, zss_low=zss)
    assert res["state"] == "REJECTED", f"应 REJECTED，实际 {res['state']} ({res['msg']})"
    assert res["nested"] is False
    assert res["chain"][0]["state"] == "REJECTED"
    assert res["chain"][0]["zs_count"] >= 1 and res["chain"][0]["bi_count"] >= 3


def test_state_machine_assumed():
    """次级别结构不足（<3 笔）⇒ ASSUMED（假设成立，待观察）。"""
    m = _fake_mmd("1buy", _BI)
    res = compute_qujiantao(m, bis_low=[_fake_bi(0, 5)])  # 仅 1 笔，无中枢
    assert res["state"] == "ASSUMED", f"应 ASSUMED，实际 {res['state']} ({res['msg']})"
    assert res["nested"] is False
    assert res["chain"][0]["state"] == "ASSUMED"


def test_state_machine_no_low_data_assumed():
    """无低级别数据 ⇒ ASSUMED + chain=[]（不编造评分）。"""
    m = _fake_mmd("1buy", _BI)
    res = compute_qujiantao(m)
    assert res["state"] == "ASSUMED"
    assert res["chain"] == []
    assert res["method"] == "none"


def test_chain_is_list_and_serializable():
    """chain 必须是 list[dict]，可 JSON 序列化（前端逐重渲染）。"""
    import json
    m = _fake_mmd("1buy", _BI)
    bc = _fake_bc("down", 15, bc=True)
    res = compute_qujiantao(m, bcs_low=[bc])
    assert isinstance(res["chain"], list)
    js = json.dumps(res["chain"], default=str)
    assert len(js) > 0
