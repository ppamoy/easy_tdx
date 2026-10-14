"""V732：波动率阈值「逐笔 as-of」回归测试 —— 锁死缠论未来函数泄漏。

背景（实测，非推测）
--------------------
`_calc_atr_volatility(closes)` 取 `closes[-lookback:]`，即**序列尾部**。
`analyser.py` 用它把**整段历史**算出一个全局 `volatility` 标量，再套用到
所有历史信号上；于是「后面又录入一批数据」会改写早期信号。

实测证据（scripts/audit_future_leak_real.py，32 只真实日线 × 7 个截断
检查点 = 224 组）：修复前 **40 组**历史信号被改写（18/32 只标的受影响）。
典型案例 sh600009：截断 600 根时 bar199 无 1buy，补齐到 1500 根后凭空多出
1buy@199 —— ATR 波动率从 0.0136 变到 0.0070（相对差 93.5%），跨越了
0.01 的「低波动 → 收紧阈值」档位边界。把该值固定为常数后 40 组违反全消失，
证明这是唯一泄漏源。

本测试锁死三件事
----------------
1. `_calc_atr_volatility_asof` 的窗口锚在**指定 bar**，不随序列长度变化；
2. 同一标的截断后，早期信号集合**必须完全一致**（未来免疫，行为级判定）；
3. 牙齿验证：把 as-of 换回尾部口径，测试**必须失败**（否则是假通过）。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402
from easy_tdx.chanlun.mmd_conditions import (  # noqa: E402
    _calc_atr_volatility,
    _calc_atr_volatility_asof,
)


def _seg(
    n: int, o: float, c: float, jitter: float = 0.05
) -> list[tuple[float, float, float, float]]:
    out = []
    for i in range(n):
        t0 = o + (c - o) * (i / n)
        t1 = o + (c - o) * ((i + 1) / n)
        lo, hi = min(t0, t1), max(t0, t1)
        out.append((t0, t1, hi + jitter, lo - jitter))
    return out


def _mk(
    bars: list[tuple[float, float, float, float]], start: datetime | None = None
) -> pd.DataFrame:
    rows = []
    dt = start or datetime(2024, 1, 2)
    for o, c, h, ln in bars:
        rows.append({"datetime": dt, "open": o, "close": c, "high": h, "low": ln, "vol": 1e6})
        dt += timedelta(days=1)
    return pd.DataFrame(rows)


def _textbook(leaving_bars: int = 32) -> list[tuple[float, float, float, float]]:
    """教科书下跌趋势 + 背驰离开段 + 回调不创新低。"""
    b: list = []
    b += _seg(12, 20.0, 16.0)
    b += _seg(6, 16.0, 17.0) + _seg(6, 17.0, 16.0) + _seg(6, 16.0, 17.0)
    b += _seg(14, 17.0, 14.0)
    b += _seg(6, 14.0, 15.0) + _seg(6, 15.0, 14.0) + _seg(6, 14.0, 15.0)
    b += _seg(leaving_bars, 15.0, 12.5)  # 背驰离开段，创新低
    b += _seg(8, 12.5, 15.0)  # 反弹
    b += _seg(6, 15.0, 14.0)  # 回调不创新低
    b += _seg(8, 14.0, 16.0)
    return b


def _extend(bars: list, n_extra: int) -> list:
    """在尾部追加 n_extra 根「未来」K 线（延续最后方向）。"""
    last_close = bars[-1][1]
    direction = 1.0 if last_close >= bars[-2][1] else -1.0
    out = list(bars)
    cur = last_close
    for _ in range(n_extra):
        nxt = max(1.0, cur + direction * 0.12)
        out.append((cur, nxt, max(cur, nxt) + 0.05, min(cur, nxt) - 0.05))
        cur = nxt
    return out


def _load(name: str) -> pd.DataFrame:
    p = Path(__file__).resolve().parents[1] / "fixtures" / name
    rows = json.loads(p.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df


def _sig(result, cap: int) -> set[tuple[str, int]]:
    return {
        (m.mmd_type.value, m.bi.end.bar_index)
        for m in result.mmds
        if m.bi and m.bi.end.bar_index < cap
    }


class TestAtrVolatilityAsOf:
    """_calc_atr_volatility_asof 的窗口必须锚在指定 bar。"""

    def test_asof_ignores_tail(self) -> None:
        """追加尾部数据后，同一 bar 的 as-of 波动率不变。"""
        base = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        v_short = _calc_atr_volatility_asof(base, 3)
        long = base + [16.0, 17.0, 30.0, 31.0]  # 尾部大幅波动
        v_long = _calc_atr_volatility_asof(long, 3)
        assert v_short == pytest.approx(v_long), "as-of 波动率不应受尾部新增数据影响"

    def test_tail_version_is_affected(self) -> None:
        """对照组：尾部口径**确实**会变（证明两者语义不同，不是同一函数）。

        ⚠️ 自误报修正：第一版用 6 根序列，`len(closes) < lookback+1` 直接返回
        默认 0.02，两个长度都走默认分支 → 相等 → 误判「尾部口径不受影响」。
        必须用**长于 lookback(=20)** 的序列才能真正进入 ATR 计算分支。
        """
        import random

        rng = random.Random(7)
        base = [100.0]
        for _ in range(60):
            base.append(round(base[-1] * (1 + rng.uniform(-0.01, 0.01)), 4))
        v_short = _calc_atr_volatility(base)
        long = base + [base[-1] * 1.5, base[-1] * 0.6]  # 尾部大幅波动
        v_long = _calc_atr_volatility(long)
        assert len(base) > 21, "前提：序列必须长于 lookback+1 才进 ATR 分支"
        assert v_short != pytest.approx(v_long), "尾部口径必须随数据增长而改变（对照组）"
        # 同时确认 as-of 口径在同一 bar 上不变
        assert _calc_atr_volatility_asof(base, 30) == pytest.approx(
            _calc_atr_volatility_asof(long, 30)
        )

    def test_asof_clamps_out_of_range(self) -> None:
        """越界索引被钳制，不抛异常。"""
        seq = [10.0, 11.0, 12.0]
        assert _calc_atr_volatility_asof(seq, 999) > 0
        assert _calc_atr_volatility_asof(seq, -5) > 0
        assert _calc_atr_volatility_asof([], 0) == pytest.approx(0.02)
        assert _calc_atr_volatility_asof(None, 0) == pytest.approx(0.02)


class TestVolatilityFutureImmunity:
    """行为级：截断序列与全量序列的早期信号必须一致。"""

    def test_real_data_history_not_rewritten(self) -> None:
        """真实数据：截断 600 根 vs 补齐 1200 根，早期信号必须一致。

        fixture 来源：sh600009（上海机场）真实日线前复权，600 根为 base、
        再 600 根为「未来」。这是审计中**实测能分化**的形态：
        * base 600 根 → 尾部 ATR 波动率 0.0136（常态档）
        * 补到 1200 根 → 尾部波动率 0.0070（跌破 0.01「低波动」档）
        旧实现用后者去判 bar199 的背驰，于是凭空多出 1buy@199。
        """
        base = _load("v732_vol_leak_base.json")
        future = _load("v732_vol_leak_future.json")
        cap = len(base) - 20  # 前瞻缓冲

        r_short = ChanlunAnalyser(
            code="600009", frequency="daily", config=ChanlunConfig(zs_from_xd=False)
        ).process_klines(base)
        r_long = ChanlunAnalyser(
            code="600009", frequency="daily", config=ChanlunConfig(zs_from_xd=False)
        ).process_klines(pd.concat([base, future], ignore_index=True))

        s, ln = _sig(r_short, cap), _sig(r_long, cap)
        assert len(s) >= 3, f"可比信号仅 {len(s)}，样本不足（假通过风险）"
        assert s == ln, f"历史信号被改写  新增={sorted(ln - s)}  消失={sorted(s - ln)}"

    def test_teeth_tail_volatility_breaks_it(self) -> None:
        """牙齿验证：换回尾部口径后，上面那条未来免疫断言**必须**被打破。

        为什么必须单独做这一步：如果退化成旧实现后依然免疫，说明
        `test_real_data_history_not_rewritten` 测的东西与被测实现无关
        —— 那是"看起来在测、其实没牙齿"的假测试。

        ⚠️ 自误报修正：第一版用教科书合成形态（`_textbook`）做牙齿，实测
        该形态在**任何**波动率口径下结果都相同（4 个振幅档位 × 2 个 leaving
        长度全部免疫），退化后仍免疫 → 断言失败。合成形态无法暴露这个泄漏，
        必须用真实数据中实测能分化的那一段（sh600009 前 600 根）。
        """
        import easy_tdx.chanlun.mmd as mmd_mod

        base = _load("v732_vol_leak_base.json")
        future = _load("v732_vol_leak_future.json")
        cap = len(base) - 20
        original = mmd_mod._calc_atr_volatility_asof
        try:
            # 换成「永远取尾部」的退化实现 = 修复前的行为
            mmd_mod._calc_atr_volatility_asof = lambda closes, end_index=None, lookback=20: (
                _calc_atr_volatility(closes, lookback)
            )
            r_short = ChanlunAnalyser(
                code="600009", frequency="daily", config=ChanlunConfig(zs_from_xd=False)
            ).process_klines(base)
            r_long = ChanlunAnalyser(
                code="600009", frequency="daily", config=ChanlunConfig(zs_from_xd=False)
            ).process_klines(pd.concat([base, future], ignore_index=True))
            s, ln = _sig(r_short, cap), _sig(r_long, cap)
            assert s != ln, (
                "退化到尾部口径后竟然仍免疫 —— "
                "test_real_data_history_not_rewritten 没有牙齿，未覆盖该泄漏"
            )
            # 顺带锁定具体形态：旧实现会凭空多出 1buy@199
            assert ("1buy", 199) in (ln - s), f"预期旧实现多出 1buy@199，实得 {sorted(ln - s)}"
        finally:
            mmd_mod._calc_atr_volatility_asof = original
