"""偏差C(V859)守卫：2买/2卖用次级别走势（线段）回调（原文 17/21/53/101 课）。

原文「次级别回调 / 走势结束点」：
  - 17 课「第一次次级别回调」
  - 21 课「第二段次级别走势低点」
  - 53 课「次级别走势结束点」
  - 101 课「第二类买点跌破第一类买点……这是完全可以的」

现状（process_klines 默认）：用**同级别笔**找回调（近似，与 czsc 库
cxt_second_bs_V240524 用同级别并列一致）。偏差C 仅在
process_klines_cross_timeframe（真实跨周期）传入 lower_xds 时启用
原文精确口径——2买 = 1买后第一个次级别向下线段（回调走势）的终点。

双向验证（§4）：
  - ON（lower_xds 传入）：2买/2卖 msg 含「次级别回调」，bi 为日线笔（对齐）。
  - OFF（lower_xds=None，默认）：走同级别笔回调，msg 不含「次级别回调」。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.mmd import (
    _find_second_type_mmds,
    _find_sublevel_callback_xd,
    _remap_sublevel_xd_to_daily_bi,
)
from easy_tdx.chanlun.types import BI, Direction, FX, FXType, MMDType, XD, ZS

DATA_DIR = Path(__file__).resolve().parents[2] / "audit_data"
MIN_DIR = Path(__file__).resolve().parents[2] / "audit_data_min"


def _mk_xd(index: int, direction: str, high: float, low: float,
           start_date: datetime, end_date: datetime) -> XD:
    """构造次级别线段（走势）用于偏差C helper 测试。"""
    start_fx = FX(
        fx_type=FXType.DI if direction == "up" else FXType.DING,
        k=type("CLK", (), {"k_index": index * 10, "index": index, "date": start_date})(),
        klines=[], val=low, index=index, done=True,
    )
    end_fx = FX(
        fx_type=FXType.DING if direction == "up" else FXType.DI,
        k=type("CLK", (), {"k_index": index * 10 + 5, "index": index, "date": end_date})(),
        klines=[], val=high, index=index, done=True,
    )
    return XD(
        start=start_fx, end=end_fx,
        direction=Direction.UP if direction == "up" else Direction.DOWN,
        index=index, high=high, low=low,
    )


def _mk_bi_dated(index: int, direction: str, high: float, low: float,
                 end_date: datetime) -> BI:
    """构造日线笔（带 end.k.date）用于 _remap 对齐测试。"""
    start_fx = FX(
        fx_type=FXType.DI if direction == "up" else FXType.DING,
        k=type("CLK", (), {"k_index": index * 10, "index": index,
                            "date": datetime(2024, 1, 1)})(),
        klines=[], val=low, index=index, done=True,
    )
    end_fx = FX(
        fx_type=FXType.DING if direction == "up" else FXType.DI,
        k=type("CLK", (), {"k_index": index * 10 + 5, "index": index,
                            "date": end_date})(),
        klines=[], val=high, index=index, done=True,
    )
    return BI(
        start=start_fx, end=end_fx,
        direction=Direction.UP if direction == "up" else Direction.DOWN,
        index=index, high=high, low=low,
    )


def test_deviation_c_find_sublevel_callback_down() -> None:
    """偏差C helper：1买后第一个次级别向下线段 = 回调。"""
    d0, d1, d2, d3 = (datetime(2024, 1, 1), datetime(2024, 1, 3),
                      datetime(2024, 1, 5), datetime(2024, 1, 7))
    lower_xds = [
        _mk_xd(0, "up", 10.0, 8.0, d0, d1),    # 1买前向上（反弹）
        _mk_xd(1, "down", 10.0, 7.0, d1, d2),  # 1买后向下（回调）= 2买
        _mk_xd(2, "up", 9.0, 7.5, d2, d3),     # 回调后向上
    ]
    cb = _find_sublevel_callback_xd(lower_xds, d1, "down")
    assert cb is not None
    assert cb.direction.value == "down"
    assert cb.low == 7.0  # 回调低点


def test_deviation_c_find_sublevel_callback_none_after_anchor() -> None:
    """偏差C helper：1买后无向下线段 → None（原文要求次级别回调，无则无 2买）。"""
    d0, d1 = datetime(2024, 1, 1), datetime(2024, 1, 3)
    lower_xds = [_mk_xd(0, "up", 10.0, 8.0, d0, d1)]  # 仅向上，无回调
    cb = _find_sublevel_callback_xd(lower_xds, d1, "down")
    assert cb is None


def test_deviation_c_remap_sublevel_xd_to_daily_bi() -> None:
    """偏差C helper：次级别线段终点 → 日线笔（时间对齐）。"""
    d1, d2, d3 = (datetime(2024, 1, 3), datetime(2024, 1, 5),
                  datetime(2024, 1, 7))
    xd = _mk_xd(1, "down", 10.0, 7.0, d1, d2)  # 终点 d2
    bis = [
        _mk_bi_dated(0, "up", 9.0, 8.0, d1),   # 终点 d1 < d2
        _mk_bi_dated(1, "down", 9.0, 7.5, d3),  # 终点 d3 >= d2 ✓
    ]
    target = _remap_sublevel_xd_to_daily_bi(xd, bis)
    assert target is not None
    assert target.index == 1  # 对齐到 d3 的日线笔


def test_deviation_c_unit_2nd_buy_uses_sublevel() -> None:
    """偏差C 单元集成：lower_xds 传入时 2买走次级别线段回调（msg 含「次级别回调」）。

    构造：1买（向下笔底）+ 中枢 + 1买后次级别向下线段（回调）。
    调 _find_second_type_mmds(lower_xds=...)，断言 2买 msg 含「次级别回调」、
    bi 为日线笔（对齐）、MMDType.BUY_2。这是 ON 侧行为验证（§4）。
    """
    d0, d1, d2 = (datetime(2024, 1, 1), datetime(2024, 1, 3), datetime(2024, 1, 5))
    # 1买：向下笔，底=8，end.k.date=d1
    buy_1_bi = _mk_bi_dated(0, "down", 10.0, 8.0, d1)
    zs = ZS(lines=[buy_1_bi], zg=9.0, zd=7.0, gg=10.0, dd=6.0, index=0)
    from easy_tdx.chanlun.types import MMD
    buy_1_mmd = MMD(mmd_type=MMDType.BUY_1, zs=zs, bi=buy_1_bi, msg="1买")
    leave_bi = _mk_bi_dated(1, "up", 9.0, 8.0, d2)
    bis = [buy_1_bi, leave_bi]
    # 次级别线段：1买(d1)后向下线段（回调）
    lower_xds = [
        _mk_xd(0, "up", 10.0, 9.0, d0, d1),
        _mk_xd(1, "down", 10.0, 7.0, d1, d2),
    ]
    mmds = _find_second_type_mmds(
        bis, [zs], [buy_1_mmd], ChanlunConfig(), lower_xds=lower_xds
    )
    buy2 = [m for m in mmds if m.mmd_type == MMDType.BUY_2]
    assert len(buy2) == 1, f"应产出1个2买，实际 {len(buy2)}：{[m.msg[:50] for m in mmds]}"
    assert "次级别回调" in buy2[0].msg
    assert buy2[0].bi is not None
    assert buy2[0].bi.index in (0, 1)  # 对齐到日线笔


def test_deviation_c_unit_2nd_buy_off_uses_daily_bi() -> None:
    """偏差C OFF 侧（§4 对照）：lower_xds=None 时 2买走同级别笔回调，msg 不含「次级别回调」。

    同一构造，但不传 lower_xds。2买（若有）走下方同级别笔回调判定，
    msg 不含「次级别回调」——证默认 process_klines 行为不变。
    """
    d0, d1, d2 = (datetime(2024, 1, 1), datetime(2024, 1, 3), datetime(2024, 1, 5))
    buy_1_bi = _mk_bi_dated(0, "down", 10.0, 8.0, d1)
    zs = ZS(lines=[buy_1_bi], zg=9.0, zd=7.0, gg=10.0, dd=6.0, index=0)
    from easy_tdx.chanlun.types import MMD
    buy_1_mmd = MMD(mmd_type=MMDType.BUY_1, zs=zs, bi=buy_1_bi, msg="1买")
    leave_bi = _mk_bi_dated(1, "up", 9.0, 8.0, d2)
    bis = [buy_1_bi, leave_bi]
    # 不传 lower_xds（默认 process_klines 口径）
    mmds = _find_second_type_mmds(bis, [zs], [buy_1_mmd], ChanlunConfig())
    for m in mmds:
        if m.mmd_type == MMDType.BUY_2:
            assert "次级别回调" not in m.msg, (
                f"偏差C OFF：默认 lower_xds=None 不应走次级别回调，msg：{m.msg}"
            )


def test_deviation_c_cross_tf_2nd_msg_contains_sublevel() -> None:
    """偏差C 集成：cross_timeframe 的 2买/2卖 msg 含「次级别回调」。

    用 sh600000 真实数据跑 process_klines_cross_timeframe（传入 lower_xds），
    断言 2买/2卖 走偏差C 分支（msg 含「次级别回调」），证 ON 生效。
    不断言中枢数（V853 same_level 接入的既有 failure 与偏差C 无关）。
    """
    p_d = DATA_DIR / "sh600000_daily.json"
    p_30 = MIN_DIR / "sh600000_30min.json"
    if not p_d.exists() or not p_30.exists():
        pytest.skip("缺少 sh600000 audit 数据")
    df_d = pd_json_load(p_d)
    df_30 = pd_json_load(p_30)
    cfg = ChanlunConfig()
    a = ChanlunAnalyser(config=cfg)
    r = a.process_klines_cross_timeframe(df_d, df_30)
    # 收集 2买/2卖
    second_mmds = [m for m in r.mmds if m.mmd_type.value in ("buy_2", "sell_2")]
    if not second_mmds:
        pytest.skip("sh600000 cross_tf 无 2买/2卖，无法验证偏差C")
    for m in second_mmds:
        assert "次级别回调" in m.msg, (
            f"偏差C ON：cross_timeframe 的 {m.mmd_type.value} msg 应含「次级别回调」，"
            f"实际：{m.msg}"
        )


def pd_json_load(p: Path):
    import pandas as pd
    rows = json.loads(p.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df
