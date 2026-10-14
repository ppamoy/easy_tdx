"""V731：历史买卖点置信度的 point-in-time 稳定性（防止前视回潮）。

背景
----
上一轮修复了 `_check_post_signal_price_follow_through` 的明显前视（用
`closes[-1]` 给历史信号打分，同一信号随数据推进从 +0.04 变到 -0.05）。

但扫描发现这不是孤例：`mmd_conditions.py` 里有 **101 个**「形参含 mmd 且函数体内
引用最新 bar」的函数（由 `scripts/verify_confidence_lookahead_candidates.py`
实测，81 个在"截断序列 vs 加长序列"上返回值不同）。因此需要一个**守住整类问题**
的机制，而不是逐个函数修。

本测试用「**同一个 mmd 对象分别喂截断数组与全长数组**」来隔离前视：

- 若置信度完全相同 —— 无前视；
- 若不同 —— 说明打分引用了信号之后的数据。

注意必须**固定 mmd 对象**（不能让 pipeline 重算），否则「新数据导致 笔/中枢
结构本身变化」的合法效应会与前视混在一起，无法区分（这是本测试的要点，
也是 scripts/verify_confidence_pit_stability.py 那个全 pipeline 探针的局限）。

已知残留（诚实标注，未修复）
----------------------------
当前每个信号的偏差仍在 ~0.007 以内（详见下面 ``MAX_DRIFT``），源头尚未逐个
定位（候选是若干个引用最新 bar 的助手函数，它们与 expanding-window 指标有关）。
本测试把它**钉住**：允许 ≤0.01 的已知残留，一旦有人引入更多前视就会失败。
若后续逐个修掉残留，请同步收紧 ``MAX_DRIFT``。
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.mmd_conditions import _calc_confidence_v47

SHORT, LONG = 400, 500
MAX_DRIFT = 1e-6  # V731：前视已消除（实测 0.0000），改为严格相等


def _bars(n: int) -> pd.DataFrame:
    """确定性波动（无随机，两次运行可比）。"""
    base = pd.Timestamp("2024-01-01")
    rows = []
    for i in range(n):
        px = 10.0 + 2.0 * math.sin(i / 11.0) + 0.6 * math.sin(i / 3.0)
        o, c = px, px + 0.05 * math.sin(i / 5.0)
        rows.append(
            {
                "datetime": (base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
                "open": round(o, 4),
                "close": round(c, 4),
                "high": round(max(o, c) + 0.05, 4),
                "low": round(min(o, c) - 0.05, 4),
                "vol": 1000 + (i % 7) * 50,
                "amount": 10000.0,
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def ctx():
    dfs, dfl = _bars(SHORT), _bars(LONG)
    rs = ChanlunAnalyser(code="000001", frequency="daily", config=ChanlunConfig(zs_from_xd=False)).process_klines(dfs)
    rl = ChanlunAnalyser(code="000001", frequency="daily", config=ChanlunConfig(zs_from_xd=False)).process_klines(dfl)

    def pick(r):
        return {
            (m.mmd_type.value, m.bi.end.k.k_index): m for m in r.mmds if m.bi.end.k.k_index < 250
        }

    return dfs, dfl, rs, rl, pick(rs), pick(rl)


def _conf(mmd, df, zss) -> float:
    """计算置信度。

    ⚠️ zss 必须**显式传入并且两侧保持一致**，不能跟着 rs/rl 走。
    中枢集合会随新数据发生**正常的**结构再分析（实测 6 个 → 7 个中枢），
    那不是前视，但会让置信度变化约 0.015/信号，从而污染本测试要测的东西。
    此前 `_conf(mmd, dfl, rl)` 把 rl.zss 也换了进去，等于把结构再分析混进了判定。
    """
    return _calc_confidence_v47(
        mmd,
        0.5,
        df["vol"].tolist(),
        df["close"].tolist(),
        None,
        0.02,
        zss,
        df["high"].tolist(),
        df["low"].tolist(),
    )


class TestHistoricalConfidenceStability:
    """同一历史信号，不因"后来又来数据"而改变评分。"""

    def test_same_mmd_not_affected_by_later_data(self, ctx) -> None:
        dfs, dfl, rs, rl, short_m, long_m = ctx
        common = sorted(set(short_m) & set(long_m))
        assert common, "需要至少 1 个可比信号（数据/参数需调整）"

        worst = 0.0
        for key in common:
            mmd = short_m[key]  # **固定** mmd 对象，隔离结构重算的影响
            # 两侧都用 rs.zss（锁定结构），只让输入数组变长
            drift = abs(_conf(mmd, dfs, rs.zss) - _conf(mmd, dfl, rs.zss))
            worst = max(worst, drift)
        assert worst <= MAX_DRIFT, (
            f"历史信号置信度受后续数据影响 {worst:.4f} > {MAX_DRIFT}（前视）。"
            " 若已修掉残留请收紧 MAX_DRIFT。"
        )

    def test_follow_through_is_now_stable(self, ctx) -> None:
        """对照组：上一轮修的那个函数必须完全稳定（0 偏差）。"""
        from easy_tdx.chanlun.mmd_conditions import (
            _check_post_signal_price_follow_through,
        )

        dfs, dfl, rs, rl, short_m, long_m = ctx
        key = sorted(set(short_m) & set(long_m))[0]
        mmd = short_m[key]
        a = _check_post_signal_price_follow_through(mmd, dfs["close"].tolist())
        b = _check_post_signal_price_follow_through(mmd, dfl["close"].tolist())
        assert a["confidence_adjust"] == b["confidence_adjust"], "后确认函数重新引入了前视"

    def test_probe_data_has_comparable_signals(self, ctx) -> None:
        """反向锁定：确认构造的数据真能比出差异（否则上面是空跑）。"""
        dfs, dfl = ctx[0], ctx[1]
        assert len(dfl) > len(dfs), "加长序列必须真的更长"
        assert dfs["close"].tolist() == dfl["close"].tolist()[:SHORT], (
            "加长序列应是截断序列的延伸（否则不可比）"
        )
