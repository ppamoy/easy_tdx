"""V731：`_calc_tf_consistency` 不得使用信号之后的未来数据。

缺陷
----
原实现取 `closes[-5:]` / `closes[-20:]` / `closes[-60:]`，即**整段序列**的尾部。
给历史信号打分时，这三者自然包含了信号**之后**的 K 线 —— 于是同一个历史信号的
多时间框架一致性评分会随着"后来又录入了多少数据"而改变。

量化：本函数单独贡献 `confidence_adjust` 位移 **0.64**，是端到端
`mmd.confidence` 漂移 0.674 的主要来源之一（按各助手逐个归因测得）。

修复：改为以**信号所在 bar**为基准取 MA（`_asof_end`），结果只由该信号之前
（含自身 + 有界的后确认窗口）的数据决定。实测位移 0.64 → **0.0000**。

本文件采用「一个助手、一个测试文件」的粒度 —— 这是第 29/30 轮的教训：试图一次性
批量改造 ~86 个助手（脚本化改名 / 循环内重绑局部变量）两次都失败并使漂移变大，
改为逐个函数加 as-of 语义、逐个配回归测试推进。
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.mmd_conditions import _calc_tf_consistency

SHORT, LONG, CAP = 400, 500, 250


def _bars(n: int) -> pd.DataFrame:
    base = pd.Timestamp("2024-01-01")
    rows = []
    for i in range(n):
        px = 10.0 + 2.0 * math.sin(i / 11.0) + 0.6 * math.sin(i / 3.0)
        o, c = px, px + 0.05 * math.sin(i / 5.0)
        rows.append({
            "datetime": (base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
            "open": round(o, 4), "close": round(c, 4),
            "high": round(max(o, c) + 0.05, 4), "low": round(min(o, c) - 0.05, 4),
            "vol": 1000 + (i % 7) * 50, "amount": 10000.0,
        })
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def ctx():
    ds, dl = _bars(SHORT), _bars(LONG)
    res = ChanlunAnalyser(code="000001", frequency="daily").process_klines(ds)
    early = [m for m in res.mmds if m.bi.end.k.k_index < CAP]
    return ds, dl, early


def _adj(mmd, df) -> float:
    return _calc_tf_consistency(mmd, df["close"].tolist())["confidence_adjust"]


class TestTFConsistencyIsPointInTime:
    def test_adjust_unaffected_by_later_data(self, ctx) -> None:
        ds, dl, early = ctx
        assert early, "需要至少 1 个早期信号"
        worst = max(abs(_adj(m, ds) - _adj(m, dl)) for m in early)
        assert worst == 0, (
            f"confidence_adjust 受后续数据影响（最大 {worst}），存在前视"
        )

    def test_trend_labels_also_stable(self, ctx) -> None:
        """不仅 adjust，趋势标签也必须稳定（否则结论会翻）。

        注意：晚期信号处在后确认窗口内，其标签允许变化 —— 这里只校验早期信号。
        """
        ds, dl, early = ctx
        for m in early:
            a = _calc_tf_consistency(m, ds["close"].tolist())
            b = _calc_tf_consistency(m, dl["close"].tolist())
            assert a["short_term_trend"] == b["short_term_trend"], f"{m.mmd_type.value}: 短期趋势漂移"
            assert a["mid_term_trend"] == b["mid_term_trend"], f"{m.mmd_type.value}: 中期趋势漂移"
            assert a["consistency"] == b["consistency"], f"{m.mmd_type.value}: 一致性结论漂移"

    def test_short_series_still_degrades_gracefully(self, ctx) -> None:
        """不足 60 根时应返回未知，而不是抛异常或给出虚假结论。"""
        ds, _dl, early = ctx
        r = _calc_tf_consistency(early[0], [10.0] * 30)
        assert r["consistency"] == "unknown"
        assert r["confidence_adjust"] == 0.0
