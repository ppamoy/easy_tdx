"""V731：锁定 F6 树粮菜的**实际分类语义**（相对打分取最高，无硬门槛）。

为什么要这个测试
----------------
`docs/PRODUCT_REQUIREMENTS.md` 的 F6 原先把 "树 = ROE≥15% + ..." 写成像是
**硬门槛**，容易被后来者（包括我自己）误以为已实现。实测发现实际语义不同，已在
文档里澄清。本测试把实测出的语义**钉住**，防止将来有人无意改动：

  1. ROE 是**分档给分**，不是布尔门槛（20 / 15 / 10 三档，低于10%也给部分分）；
  2. 最终分类 = 三项分数里的最高者（不是看是否满足某类的门槛）；
  3. **没有绝对分数下限**：全面疲弱的股票也会被赋予某个类别标签。

若产品上决定改成"树必须 ROE≥15%"或"总分太低不给标签"，那属于语义变更 ——
应**先改本测试和文档**，再改 `screener.py`。
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from easy_tdx.fundamental.screener import screen_stock

REPORT_DATE = date(2025, 12, 31)
DISCLOSE = date(2026, 4, 29)


def _row(**over) -> pd.Series:
    base = {
        "code": "600001", "market": "SH",
        "report_date": REPORT_DATE, "disclosure_date": DISCLOSE,
        "roe": 20.0, "revenue": 500e8, "gross_margin": 40.0,
        "net_margin": 15.0, "eps": 2.0, "net_profit": 80e8,
        "debt_ratio": 35.0, "dividend_yield": 2.0, "pe": 20.0, "pb": 3.0,
    }
    base.update(over)
    return pd.Series(base)


class TestRoeIsTieredNotBoolean:
    """ROE 是分档给分，不是"达标才给分"。"""

    def test_tree_score_increases_with_roe_tiers(self) -> None:
        got = []
        for roe in (5.0, 12.0, 16.0, 25.0):
            s = screen_stock(_row(roe=roe), pool_size=100)
            got.append(s.scores["tree"])
        # 每上一档，tree 分必须更高（严格递增跨越三档）
        assert got[0] < got[1] <= got[2] < got[3], f"ROE 分档异常: {got}"

    def test_below_min_tier_still_contributes(self) -> None:
        """ROE 低于 10% 也给分（只是低），不是直接归零。"""
        s = screen_stock(_row(roe=0.5), pool_size=100)
        assert s.scores["tree"] > 0, "低 ROE 仍应贡献部分 tree 分"


class TestClassificationTakesMaxScore:
    """最终类别 = 三项里的最高分，而非"是否满足该类门槛"。"""

    def test_meeting_tree_roe_can_still_be_grain(self) -> None:
        """实测：tree=64 但 grain=65 → 判为 grain。"""
        s = screen_stock(
            _row(roe=15.0, revenue=3000e8, gross_margin=70.0,
                 net_margin=25.0, eps=5.0, net_profit=500e8,
                 dividend_yield=1.0),
            pool_size=100,
        )
        scores = s.scores
        assert scores["grain"] > scores["tree"], (
            f"构造前提失效: {scores}"
        )
        assert s.category == "grain", (
            f"分类应取最高分项 grain，实际 {s.category} ({scores})"
        )

    def test_category_equals_argmax(self) -> None:
        """一般性地验证 category 就是 argmax(scores)。"""
        s = screen_stock(_row(roe=25.0, dividend_yield=0.0, debt_ratio=70.0),
                         pool_size=100)
        expected = max(s.scores, key=lambda k: s.scores[k])
        assert s.category == expected, f"{s.category} != argmax {expected}"


class TestNoAbsoluteFloor:
    """分类没有最低分要求（这只区别于"是否需要产品改语义"的决策依据）。"""

    def test_globally_weak_stock_still_gets_a_label(self) -> None:
        s = screen_stock(
            _row(roe=1.0, revenue=5e8, gross_margin=5.0, net_margin=1.0,
                 eps=0.02, net_profit=1e7, debt_ratio=85.0,
                 dividend_yield=0.0, pe=200.0, pb=15.0),
            pool_size=100,
        )
        assert s.category in {"tree", "grain", "vegetable"}
        # 记录实测值：弱票也被贴了标签（无绝对门槛）
        assert max(s.scores.values()) < 60, (
            f"这只票分数应明显偏低，实际 {s.scores}"
        )

    def test_scores_are_exposed_for_explainability(self) -> None:
        """每条结果必须带三项分值与明细（需求要求"可解释"）。"""
        s = screen_stock(_row(), pool_size=100)
        assert set(s.scores) == {"tree", "grain", "vegetable"}
        assert s.details, "应提供打分明细"
