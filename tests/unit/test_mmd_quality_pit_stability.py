"""V731：买卖点**质量评分**不得使用信号之后的未来数据。

缺陷（与置信度同源，但影响更大）
--------------------------------
`_calc_mmd_quality` 的六维评分里，"突破力度""信号新鲜度"等维度读的是传入
closes/volumes 的**序列尾部**。给历史信号打分时传入的是整段序列，于是用到信号
之后的未来数据。

实测：固定 mmd、只把数组从 400 根延到 500 根，8 个信号的质量分**每个都偏移
±8 分**（满分 100），总差异 64 分 —— 影响远大于置信度的 0.042。

修复：入口调用 `_truncate_to_signal_window()`，裁到
「截至信号 bar + `_POST_SIGNAL_WINDOW`(80)」。实测总差异 64.0 → **0.0000**。

注意：最新信号（本就在序列尾部）裁剪是空操作，其实时评分不受影响 —— 测试里
对这一点单独做了断言，确保没有误伤实时语义。
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.mmd_conditions import (
    _POST_SIGNAL_WINDOW,
    _calc_mmd_quality,
)

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
    rs = ChanlunAnalyser(code="000001", frequency="daily").process_klines(ds)
    early = [m for m in rs.mmds if m.bi.end.k.k_index < CAP]
    latest = max(rs.mmds, key=lambda m: m.bi.end.k.k_index)
    return ds, dl, early, latest


def _q(mmd, df) -> float:
    return _calc_mmd_quality(
        mmd, 0.5, "up", df["vol"].tolist(), df["close"].tolist(), None, 0.02
    ).score


class TestQualityIsPointInTime:
    def test_historical_quality_unaffected_by_later_data(self, ctx) -> None:
        ds, dl, early, _latest = ctx
        assert early, "需要至少 1 个早期信号"
        worst = max(abs(_q(m, ds) - _q(m, dl)) for m in early)
        assert worst == 0, (
            f"历史信号质量分受后续数据影响（最大偏移 {worst}），存在前视"
        )

    def test_grade_letter_also_stable(self, ctx) -> None:
        """评级字母（S/A/B/C/D）同样不得漂移。"""
        ds, dl, early, _latest = ctx
        for m in early:
            a = _calc_mmd_quality(
                m, 0.5, "up", ds["vol"].tolist(), ds["close"].tolist(), None, 0.02
            )
            b = _calc_mmd_quality(
                m, 0.5, "up", dl["vol"].tolist(), dl["close"].tolist(), None, 0.02
            )
            assert a.grade == b.grade, f"{m.mmd_type.value}: 评级 {a.grade} -> {b.grade}"

    def test_window_is_bounded(self) -> None:
        """后确认窗口必须有界 —— 无界就等于前视。"""
        assert isinstance(_POST_SIGNAL_WINDOW, int)
        assert 0 < _POST_SIGNAL_WINDOW < 500

    def test_latest_signal_still_uses_full_series(self, ctx) -> None:
        """对照：最新信号不应被裁剪（实时语境不受影响）。"""
        ds, _dl, _early, latest = ctx
        n = len(ds)
        assert latest.bi.end.k.k_index + 1 + _POST_SIGNAL_WINDOW > n - 1, (
            "最新信号应落在窗口内（裁剪对它是空操作）"
        )
        # 且分数应可正常算出
        assert 0 <= _q(latest, ds) <= 100
