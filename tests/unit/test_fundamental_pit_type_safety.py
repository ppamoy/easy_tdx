"""point-in-time 判定的**类型安全**审计（P1 生命线）。

背景（V731 审计）：
``pick_report`` 的 docstring 声明「杜绝未来函数」，规则是
「只考虑 disclosure_date ≤ target 的记录」。但该比较直接用
``dd <= target``，要求 dd 与 target 类型一致（target 是 ``datetime.date``）。

实测：当调用方传入的 disclosure_date 是 **str** 或 **pandas.Timestamp**
时，``dd <= target`` 直接抛 ``TypeError``。

更危险的是 NaT：``pd.NaT`` **同时是** ``datetime.datetime`` **和**
``datetime.date`` 的实例，所以朴素的 ``isinstance`` 判断会让它蒙混过关，
进而被当成「无披露日」而**退回报告期近似**放行——等于用一条读不懂日期
的记录参与 point-in-time 判定，存在引入未来数据的风险。

生产路径目前都是安全的（gpcw 的 ``_to_date``、新浪适配器的 ``date``、
SQLite 缓存反序列化后经 ``_to_date`` 都产出真 ``date``），所以这是
**健壮性缺口**而非活跃 bug。但 ``pick_report`` 是公开 API 且被 4 处生产
代码直接调用（routers/fundamental.py:91、routers/diagnosis.py:75、
pipeline.py:103/124/714），类型契约不该依赖调用方自觉。

且与 ``pick_reports_bulk``（向量化版）不一致：后者做了 ``pd.to_datetime``
归一化，前者没有——而两者 docstring 自称「规则完全一致」。

修复：新增 ``_coerce_date`` 统一归一化（NaT 检查必须在 isinstance(date)
**之前**），且「有值但无法解析」时**保守排除**，绝不退回报告期近似。
"""

from __future__ import annotations

from datetime import date
from datetime import datetime as dt

import pandas as pd
import pytest

from easy_tdx.fundamental.indicators import pick_report

# _coerce_date 是本次修复新增的内部辅助函数：旧代码上没有它。这里做可选
# 导入，使本测试文件在**旧代码上也能被收集**，从而真正暴露 pick_report
# 的行为缺陷（抛 TypeError），而不是被 ImportError 掩盖成「收集错误」。
_coerce_date = getattr(
    __import__("easy_tdx.fundamental.indicators", fromlist=["x"]), "_coerce_date", None
)
needs_coerce = pytest.mark.skipif(
    _coerce_date is None, reason="旧代码无 _coerce_date（用于 git stash 对照）"
)

TARGET = date(2026, 4, 20)


def _frame(dd, rd, eps: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "code": "T",
                "market": "SH",
                "report_date": rd,
                "disclosure_date": dd,
                "eps": eps,
            }
        ]
    )


@needs_coerce
class TestCoerceDate:
    def test_nat_is_none(self) -> None:
        """NaT 必须收敛为 None（它是 date 的实例，朴素 isinstance 会漏）。"""
        assert _coerce_date(pd.NaT) is None

    def test_various_types_normalize_to_date(self) -> None:
        for v in [
            date(2026, 4, 1),
            "2026-04-01",
            pd.Timestamp("2026-04-01"),
            dt(2026, 4, 1),
        ]:
            assert _coerce_date(v) == date(2026, 4, 1), f"{v!r} 归一化失败"

    def test_invalid_string_is_none(self) -> None:
        assert _coerce_date("not-a-date") is None
        assert _coerce_date(None) is None


class TestPickReportTypeSafety:
    """修复前这些用例会抛 TypeError（前 3 个）或误放行（NaT）。"""

    def test_future_disclosure_str_not_crash(self) -> None:
        """未来披露日为 str：应安全排除，不抛 TypeError。"""
        r = pick_report(_frame("2026-06-01", date(2026, 3, 31), 9.9), "T", TARGET, market="SH")
        assert r is None

    def test_future_disclosure_timestamp_not_crash(self) -> None:
        r = pick_report(
            _frame(pd.Timestamp("2026-06-01"), date(2026, 3, 31), 9.9), "T", TARGET, market="SH"
        )
        assert r is None

    def test_future_disclosure_datetime_not_crash(self) -> None:
        r = pick_report(_frame(dt(2026, 6, 1), date(2026, 3, 31), 9.9), "T", TARGET, market="SH")
        assert r is None

    def test_past_disclosure_str_is_accepted(self) -> None:
        """过去披露日的 str/Timestamp/datetime 应正常选出（不能矫枉过正）。"""
        for dd in ["2026-04-01", pd.Timestamp("2026-04-01"), dt(2026, 4, 1)]:
            r = pick_report(_frame(dd, date(2026, 3, 31), 1.1), "T", TARGET, market="SH")
            assert r is not None, f"{dd!r} 应被选出"
            assert r["eps"] == 1.1

    def test_unparsable_disclusion_is_excluded(self) -> None:
        """有值但无法解析：保守排除，**不得**退回报告期近似放行。"""
        for bad in [pd.NaT, "not-a-date"]:
            r = pick_report(_frame(bad, date(2026, 3, 31), 5.5), "T", TARGET, market="SH")
            assert r is None, f"{bad!r} 不应被选出（否则等于放行未知日期记录）"

    def test_missing_disclosure_falls_back_to_report_date(self) -> None:
        """真正**没有**披露日(None)时，才允许用报告期近似（≤100 天）。"""
        r = pick_report(_frame(None, date(2026, 3, 31), 2.2), "T", TARGET, market="SH")
        assert r is not None and r["eps"] == 2.2
        # 报告期过远则排除
        assert pick_report(_frame(None, date(2025, 1, 1), 3.3), "T", TARGET, market="SH") is None
