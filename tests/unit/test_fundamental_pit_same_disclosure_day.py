"""V731：PIT（point-in-time）选期回归 —— 同披露日多期必须取最新报告期。

缺陷（由 scripts/verify_pit_no_leak.py 实测抓到）：

`pick_report`（逐股）与 `pick_reports_bulk`（向量化）排序时**只用披露日**，
缺 `report_date` 次级键。真实 gpcw 数据里一只股票常有**同一天披露多期**
（实测 000007 的 2025-12-31 与 2026-03-31 两期都在 2026-04-29 披露），此时
两者分别按 `iterrows()` 原顺序和 `groupby.first()` 取第一条 —— 都不确定，
且互相分叉：400 只抽样里 **94 只（23.5%）结果不同**。

后果：可能取到**较旧**的报告期，等于用过期财报选股。这不是"未来数据"
（不违反 PIT 生命线的严格定义），但选股结果同样是错的。

修复：两者都用 (披露日, 报告期) 复合降序键，同披露日取报告期更新的那期。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from easy_tdx.fundamental.indicators import pick_report, pick_reports_bulk


def _frame() -> pd.DataFrame:
    """一只股票、三期；两期**同日披露**（报告期不同）。"""
    return pd.DataFrame(
        [
            {
                "code": "000007",
                "market": "SZ",
                "report_date": date(2025, 9, 30),
                "disclosure_date": date(2025, 10, 30),
                "roe": 5.0,
            },
            # 关键：这两期同一天披露，报告期不同
            {
                "code": "000007",
                "market": "SZ",
                "report_date": date(2025, 12, 31),
                "disclosure_date": date(2026, 4, 29),
                "roe": 11.0,
            },
            {
                "code": "000007",
                "market": "SZ",
                "report_date": date(2026, 3, 31),
                "disclosure_date": date(2026, 4, 29),
                "roe": 22.0,
            },
            # 未来披露：不得被选中
            {
                "code": "000007",
                "market": "SZ",
                "report_date": date(2026, 6, 30),
                "disclosure_date": date(2026, 8, 26),
                "roe": 99.0,
            },
        ]
    )


class TestSameDisclosureDayPicksLatestPeriod:
    """同披露日多期 → 必须取报告期更新的那期。"""

    def test_pick_report_picks_latest_report_period(self) -> None:
        f = _frame()
        row = pick_report(f, "000007", date(2026, 4, 30))
        assert row is not None
        assert row["report_date"] == date(2026, 3, 31), (
            f"同披露日应取最新报告期，实际 {row['report_date']}"
        )
        # 用指标值交叉验证（不是只看日期字段）
        assert float(row["roe"]) == 22.0

    def test_bulk_picks_same_period(self) -> None:
        f = _frame()
        out = pick_reports_bulk(f, date(2026, 4, 30))
        assert not out.empty
        assert out.iloc[0]["report_date"] == date(2026, 3, 31)
        assert float(out.iloc[0]["roe"]) == 22.0

    def test_two_implementations_agree(self) -> None:
        """反向锁定：两实现必须一致（此前 23.5% 分叉）。"""
        f = _frame()
        row = pick_report(f, "000007", date(2026, 4, 30))
        out = pick_reports_bulk(f, date(2026, 4, 30))
        assert row is not None and not out.empty
        assert row["report_date"] == out.iloc[0]["report_date"], (
            f"两实现漂移：逐股={row['report_date']} 批量={out.iloc[0]['report_date']}"
        )

    def test_result_is_order_independent(self) -> None:
        """打乱输入顺序后结果不变 —— 直接针对'靠原顺序碰运气'这个根因。"""
        f = _frame()
        base = pick_report(f, "000007", date(2026, 4, 30))
        assert base is not None
        for seed in (0, 1, 2, 3):
            shuffled = f.sample(frac=1.0, random_state=seed).reset_index(drop=True)
            r = pick_report(shuffled, "000007", date(2026, 4, 30))
            assert r is not None
            assert r["report_date"] == base["report_date"], (
                f"seed={seed} 顺序改变导致结果变化（不确定性未消除）"
            )


class TestPitBoundaryStillHolds:
    """对照组：修复不能破坏原有的 PIT 截断语义。"""

    def test_future_disclosure_excluded(self) -> None:
        f = _frame()
        row = pick_report(f, "000007", date(2026, 4, 30))
        assert row is not None
        assert row["report_date"] != date(2026, 6, 30), "未来披露的期不得被选中"

    def test_earlier_target_picks_earlier_period(self) -> None:
        f = _frame()
        row = pick_report(f, "000007", date(2025, 11, 1))
        assert row is not None
        assert row["report_date"] == date(2025, 9, 30)

    def test_no_report_available_returns_none(self) -> None:
        f = _frame()
        assert pick_report(f, "000007", date(2020, 1, 1)) is None
        assert pick_reports_bulk(f, date(2020, 1, 1)).empty
