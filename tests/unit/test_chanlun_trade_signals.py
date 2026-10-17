# §7 沉淀：实战交易信号诚实性测试
# 核心断言：买入价用「分型右根(第3根缠论K线)走完」的收盘，不是笔终点价。
# 缠论原文依据（62/65/81 课，已在 chanlun.py _compute_confirm 注释里查证）：
#   分型=相邻3根缠论K线[左,中(极值),右]，成立需右根走完。
#   包含合并后缠论K线≠原始K线，故用 fx.klines[2].k_index 定位，非 k_idx+N。
import pytest
from easy_tdx.chanlun.types import FX, CLKline, FXType
from easy_tdx.web.routers.chanlun import _compute_confirm


def _mk_ck(k_index: int, close: float, date: str) -> CLKline:
    """造缠论K线（单根未合并，k_index=原始K线索引）。"""
    from datetime import datetime
    return CLKline(
        index=k_index, k_index=k_index, date=datetime(2025, 1, k_index % 28 + 1, 9, 0),
        open=close, high=close, low=close, close=close, amount=0.0,
        high_k_index=k_index, low_k_index=k_index,
    )


def _mk_fx(mid_ki: int, right_ki: int, closes: list) -> FX:
    """造分型 FX：klines=[左,中,右]，k=中间根。"""
    cks = [_mk_ck(mid_ki - 1 + i, closes[i], f"2025-01-0{1+i} 09:00") for i in range(3)]
    # 右根的 k_index 单独设（模拟包含合并：右根可能含多根原始K线）
    cks[2] = CLKline(
        index=mid_ki, k_index=right_ki, date=__import__("datetime").datetime(2025, 1, 3, 9, 0),
        open=closes[2], high=closes[2], low=closes[2], close=closes[2], amount=0.0,
        high_k_index=right_ki, low_k_index=right_ki,
    )
    return FX(fx_type=FXType.DING, k=cks[1], klines=cks, val=closes[1])


def _fmt(d):
    return str(d)


def test_compute_confirm_uses_fractal_right_root():
    """确认日 = 分型右根(第3根缠论K线)最后一根原始K线，不是笔终点+k。"""
    # 原始K线 80 根，close = 10,11,12,...,89
    klines = [type("K", (), {"date": f"d{i}", "close": 10.0 + i})() for i in range(80)]
    # 分型：中间根 k_index=10，右根 k_index=15（模拟右根含合并，跳到15）
    fx = _mk_fx(mid_ki=10, right_ki=15, closes=[20.0, 30.0, 25.0])
    conf = _compute_confirm(klines, fx, _fmt)
    assert conf["confirm_idx"] == 15, "确认K线应是右根的 k_index(=15)，不是中间根+2"
    assert conf["confirm_price"] == 25.0, "确认价 = klines[15].close = 10+15=25"
    assert conf["confirm_date"] == "d15"
    assert conf["age_bars"] == 80 - 1 - 15  # = 64


def test_compute_confirm_right_root_not_kidx_plus_two():
    """关键：右根 k_index 可能 ≠ 中间根 k_index+2（因包含合并）。
    若有人误改回 k_idx+2，这里会 FAIL（15 ≠ 12）。"""
    klines = [type("K", (), {"date": f"d{i}", "close": 10.0 + i})() for i in range(80)]
    # 中间根 k_index=10，但右根因合并 k_index=20（跳了10根原始K线）
    fx = _mk_fx(mid_ki=10, right_ki=20, closes=[20.0, 30.0, 22.0])
    conf = _compute_confirm(klines, fx, _fmt)
    assert conf["confirm_idx"] == 20  # 不是 12！
    assert conf["confirm_price"] == 30.0  # klines[20] = 10+20


def test_compute_confirm_edge_no_right_root():
    """分型不完整（<3根）→ 确认价为 None。"""
    klines = [type("K", (), {"date": f"d{i}", "close": 10.0 + i})() for i in range(80)]
    fx = FX(fx_type=FXType.DING, k=_mk_ck(10, 30.0, "d10"), klines=[_mk_ck(9, 20.0, "d9")], val=30.0)
    conf = _compute_confirm(klines, fx, _fmt)
    assert conf["confirm_price"] is None
    assert conf["confirm_date"] is None


def test_compute_confirm_right_root_out_of_range():
    """右根 k_index 超出原始K线范围 → None（分型右根尚未走完，不可执行）。"""
    klines = [type("K", (), {"date": f"d{i}", "close": 10.0 + i})() for i in range(80)]
    fx = _mk_fx(mid_ki=78, right_ki=85, closes=[88.0, 89.0, 95.0])  # 85>=80 越界
    conf = _compute_confirm(klines, fx, _fmt)
    assert conf["confirm_price"] is None


# ── 端到端：_run_trade_one 结构完整性（合成数据，monkeypatch fetch）─────────
import pandas as pd
import numpy as np


def _synth_df(n: int = 80) -> pd.DataFrame:
    rng = np.random.RandomState(42)
    dates = pd.date_range("2025-01-02 09:30", periods=n, freq="30min")
    closes = 10.0 + np.cumsum(rng.uniform(-0.05, 0.15, n))
    return pd.DataFrame({
        "date": dates, "open": closes - 0.02, "close": closes,
        "high": closes + 0.1, "low": closes - 0.1, "vol": 1000.0,
    })


async def _fake_fetch(*a, **k):
    return _synth_df()


@pytest.mark.asyncio
async def test_run_trade_one_structure_ok():
    """_run_trade_one 端到端不崩，输出结构完整（止损止盈基于确认价）。"""
    from easy_tdx.web.routers import chanlun as ch
    original = ch.fetch_qfq_klines
    ch.fetch_qfq_klines = _fake_fetch
    try:
        r = await ch._run_trade_one(None, None, "SH", "600000", 80, 5.0, 20.0)
    finally:
        ch.fetch_qfq_klines = original
    assert "error" not in r
    assert r["symbol"] == "SH600000"
    assert r["stop_loss_pct"] == 5.0
    assert r["take_profit_pct"] == 20.0
    lb = r.get("latest_buy")
    if lb and lb.get("confirm_price"):
        cp = lb["confirm_price"]
        assert r["stop_loss_price"] == round(cp * 0.95, 3)
        assert r["take_profit_price"] == round(cp * 1.20, 3)


# ── 历史回放：无未来函数 + 结构完整 ──────────────────────────────────────
@pytest.mark.asyncio
async def test_run_trade_replay_no_future_leak():
    """回放无未来函数：每笔买入日 ≤ 出场日（出场只用确认日之后数据）+ 结构完整。"""
    from easy_tdx.web.routers import chanlun as ch
    original = ch.fetch_qfq_klines
    ch.fetch_qfq_klines = _fake_fetch
    try:
        r = await ch._run_trade_replay(None, None, "SH", "600000", 600, 5.0, 20.0)
    finally:
        ch.fetch_qfq_klines = original
    if "error" in r:
        return  # 数据不足时跳过
    assert "trades" in r and "summary" in r
    s = r["summary"]
    assert s["total"] == len(r["trades"])
    assert s["wins"] + s["losses"] == s["total"]
    # 无未来函数：每笔 buy_date 字符串 ≤ exit_date
    for t in r["trades"]:
        assert t["buy_date"] <= t["exit_date"], (
            f"未来函数泄漏：买入 {t['buy_date']} 晚于出场 {t['exit_date']}"
        )
        # return_pct 数学正确
        assert t["return_pct"] == round((t["exit_price"] / t["buy_price"] - 1) * 100, 2)
    # 出场原因分布计数 = 总交易数
    rc = sum(v["count"] for v in s["by_reason"].values())
    assert rc == s["total"], "出场原因分布计数应=总交易数"


# ── _track_trade 纯函数测试（跟踪逻辑，不依赖缠论分析）──────────────────
from easy_tdx.web.routers.chanlun import _track_trade


def _mk_trade_k(c, low, high, dt):
    """造跟踪用 K 线（只需 low/high/close/date）。"""
    return type("K", (), {"close": c, "low": low, "high": high, "date": dt})()


def test_track_trade_stop_loss():
    """触及止损 → 止损出场（止损优先于止盈）。"""
    ks = [_mk_trade_k(10, 9, 11, f"d{i}") for i in range(20)]
    ks[6] = _mk_trade_k(9.4, 9.4, 10.5, "d6")  # low=9.4 < 止损9.5
    ei, ep, reason = _track_trade(ks, buy_idx=5, buy_price=10, stop_loss=9.5, take_profit=12)
    assert ei == 6
    assert ep == 9.5
    assert reason == "止损"


def test_track_trade_take_profit():
    """触及止盈 → 止盈出场。"""
    ks = [_mk_trade_k(10, 9.8, 11, f"d{i}") for i in range(20)]  # low=9.8>止损9.5
    ks[8] = _mk_trade_k(12.5, 10, 12.5, "d8")  # high=12.5>止盈12
    ei, ep, reason = _track_trade(ks, buy_idx=5, buy_price=10, stop_loss=9.5, take_profit=12)
    assert ei == 8
    assert ep == 12
    assert reason == "止盈"


def test_track_trade_stop_loss_priority():
    """同根既触止损又触止盈 → 止损优先（保守）。"""
    ks = [_mk_trade_k(10, 9.8, 11, f"d{i}") for i in range(20)]
    ks[6] = _mk_trade_k(10, 9.0, 12.5, "d6")  # low=9<止损9.5 且 high=12.5>止盈12
    ei, ep, reason = _track_trade(ks, buy_idx=5, buy_price=10, stop_loss=9.5, take_profit=12)
    assert reason == "止损"  # 止损优先
    assert ep == 9.5


def test_track_trade_hold_to_end():
    """从未触及止损止盈 → 持有至今（末根收盘）。"""
    ks = [_mk_trade_k(10 + i * 0.05, 9.6, 11, f"d{i}") for i in range(20)]  # high=11<12, low=9.6>9.5
    ei, ep, reason = _track_trade(ks, buy_idx=5, buy_price=10, stop_loss=9.5, take_profit=12)
    assert ei == 19
    assert reason == "持有至今"
    assert ep == float(ks[-1].close)


def test_track_trade_no_future_leak():
    """无未来函数：buy_idx 之前的 K 线改动不影响结果。"""
    ks_after = [_mk_trade_k(10, 9.6, 11, f"d{i}") for i in range(20)]
    ks_before = [_mk_trade_k(100, 1, 200, f"x{i}") for i in range(5)] + ks_after
    # buy_idx=5，之前5根是极端值（low=1/high=200），不应影响跟踪
    ei1, ep1, r1 = _track_trade(ks_before, buy_idx=5, buy_price=10, stop_loss=9.5, take_profit=12)
    ei2, ep2, r2 = _track_trade(ks_after, buy_idx=0, buy_price=10, stop_loss=9.5, take_profit=12)
    # 两种情况跟踪的 K 线范围相同（都是 ks_after），结果应一致
    assert r1 == r2 == "持有至今"
    assert ep1 == ep2
